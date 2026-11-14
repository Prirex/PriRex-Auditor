"""Проверка обновлений без GitHub API и без токенов.

Логика (раздел 9 ТЗ):
  1. HEAD-запрос на ``RELEASES_URL`` **без** follow_redirects; при 301/302
     берём ``Location`` и вытаскиваем тег ``/tag/vX.Y.Z``.
  2. Fallback — GET ``VERSION_JSON_URL`` (собственный ``version.json`` на
     raw.githubusercontent.com), поле ``version``.
  3. Сравнение через ``packaging.version.parse``; нестандартные теги просто
     не считаются обновлением (исключения глушим).

Ничего не скачиваем. Любые сетевые/парсинговые ошибки — молча ``None``
(на уровне ``logger.debug``). ``config`` не изменяется: отметку о проверке
ставит вызывающий код (``config.mark_update_checked()``).
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading

import httpx
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel

from app.config import AppConfig
from app.version import RELEASES_URL, REPO_URL, VERSION_JSON_URL, __version__

logger = logging.getLogger(__name__)

#: Тег релиза вида ``/tag/v1.2.3`` (допускаем суффиксы пре-релизов).
_TAG_RE = re.compile(r"/tag/v?([0-9][0-9A-Za-z.+_-]*)")

#: Коды редиректов, из которых достаём Location.
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})

_USER_AGENT = f"PriRexAuditor/{__version__} (+https://github.com/Prirex)"


class UpdateInfo(BaseModel):
    """Результат проверки обновлений (не блокирующее уведомление в UI)."""

    available: bool = False
    current: str = ""
    latest: str = ""
    url: str = ""  # ссылка на релиз/скачивание
    notes: str = ""
    error: str | None = None


def should_check_now(config: AppConfig) -> bool:
    """Пора ли проверять обновления (интервал и выключатель — в конфиге)."""
    return bool(config.update_is_due())


def _normalize_version(value: str) -> str:
    text = (value or "").strip()
    if text[:1] in ("v", "V"):
        text = text[1:]
    return text.strip()


def _tag_from_location(location: str) -> str | None:
    """Извлечь версию из ``Location`` вида ``.../releases/tag/v1.2.0``."""
    match = _TAG_RE.search(location or "")
    if not match:
        return None
    return _normalize_version(match.group(1)) or None


async def _latest_from_release_redirect(client: httpx.AsyncClient) -> str | None:
    """HEAD без follow_redirects → тег из Location."""
    response = await client.head(RELEASES_URL)
    if response.status_code not in _REDIRECT_CODES:
        return None
    return _tag_from_location(response.headers.get("location", ""))


async def _latest_from_version_json(
    client: httpx.AsyncClient,
) -> tuple[str, str, str] | None:
    """GET собственного version.json → (version, url, notes)."""
    response = await client.get(VERSION_JSON_URL)
    if response.status_code != 200:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    latest = _normalize_version(str(payload.get("version") or ""))
    if not latest:
        return None
    url = str(payload.get("url") or "").strip()
    notes = str(payload.get("notes") or "").strip()
    return latest, url, notes


async def check_for_updates(
    config: AppConfig,
    current_version: str | None = None,
    timeout: float = 8.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> UpdateInfo | None:
    """Проверить наличие новой версии.

    Возвращает ``UpdateInfo`` либо ``None``, если проверить не удалось
    (сеть/парсинг/проверки отключены). ``transport`` предназначен для тестов
    (``httpx.MockTransport``); в UI его передавать не нужно.
    """
    if not getattr(config, "check_updates", True):
        return None

    current = _normalize_version(current_version or __version__)
    if not current:
        return None

    headers = {"User-Agent": _USER_AGENT, "Accept": "*/*"}
    latest: str | None = None
    release_url = ""
    notes = ""

    # 1) HEAD-редирект релиза — основной, самый дешёвый способ.
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout,
            headers=headers,
            transport=transport,
        ) as client:
            latest = await _latest_from_release_redirect(client)
    except Exception as exc:  # noqa: BLE001 - любые сетевые ошибки молча
        logger.debug("Не удалось получить тег релиза: %s", exc)

    # 2) Fallback — version.json.
    if not latest:
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=timeout,
                headers=headers,
                transport=transport,
            ) as client:
                payload = await _latest_from_version_json(client)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Не удалось прочитать version.json: %s", exc)
            payload = None
        if payload is not None:
            latest, release_url, notes = payload

    if not latest:
        logger.debug("Проверка обновлений не дала результата")
        return None

    try:
        latest_parsed = Version(_normalize_version(latest))
        current_parsed = Version(current)
    except (InvalidVersion, TypeError, ValueError) as exc:
        logger.debug("Нестандартная версия (%r / %r): %s", latest, current, exc)
        return None

    available = latest_parsed > current_parsed
    download_url = (
        f"{REPO_URL}/releases/latest" if available else (release_url or "")
    )
    return UpdateInfo(
        available=available,
        current=current,
        latest=str(latest_parsed),
        url=download_url,
        notes=notes,
    )


def check_for_updates_sync(
    config: AppConfig,
    current_version: str | None = None,
) -> UpdateInfo | None:
    """Синхронная обёртка для Qt-потока (``asyncio.run``).

    Вызывать из рабочего потока (QThread/QRunnable/ThreadPoolExecutor), чтобы
    не блокировать event loop Qt. Если вызов случился внутри уже работающего
    event loop (например, из asyncio-контекста), проверка выполняется в
    отдельном потоке с собственным loop — исключения наружу не пробрасываются.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            return asyncio.run(check_for_updates(config, current_version))
        except Exception as exc:  # noqa: BLE001 - UI не должен падать
            logger.debug("Ошибка check_for_updates_sync: %s", exc)
            return None

    result: list[UpdateInfo | None] = []

    def worker() -> None:
        try:
            result.append(asyncio.run(check_for_updates(config, current_version)))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Ошибка check_for_updates_sync (thread): %s", exc)
            result.append(None)

    thread = threading.Thread(target=worker, name="prirex-update-check", daemon=True)
    thread.start()
    thread.join()
    return result[0] if result else None


__all__ = [
    "UpdateInfo",
    "check_for_updates",
    "check_for_updates_sync",
    "should_check_now",
]
