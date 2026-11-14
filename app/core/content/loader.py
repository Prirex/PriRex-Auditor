"""Загрузка справочных JSON из assets (с учётом PyInstaller ``sys._MEIPASS``)."""

from __future__ import annotations

import json
from functools import lru_cache

from loguru import logger

from app.core.content.models import HowItWorks, Methodology, MethodologyCheck
from app.paths import asset_path

METHODOLOGY_FILE = "methodology.json"
HOW_IT_WORKS_FILE = "how_it_works.json"


def _read_json(name: str) -> tuple[dict | None, str | None]:
    path = asset_path(name)
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return None, f"Файл «{name}» не найден в сборке."
    except OSError as exc:
        return None, f"Не удалось прочитать «{name}»: {exc}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Битый JSON {}: {}", name, exc)
        return None, f"Файл «{name}» повреждён (строка {exc.lineno})."
    if not isinstance(data, dict):
        return None, f"Файл «{name}» имеет неверный формат."
    return data, None


@lru_cache(maxsize=1)
def _methodology() -> tuple[Methodology | None, str | None]:
    data, error = _read_json(METHODOLOGY_FILE)
    if data is None:
        return None, error
    try:
        return Methodology(**data), None
    except Exception as exc:  # noqa: BLE001 - валидация не должна ронять приложение
        logger.warning("Методология не прошла валидацию: {}", exc)
        return None, "Методология не прошла проверку формата."


@lru_cache(maxsize=1)
def _how_it_works() -> tuple[HowItWorks | None, str | None]:
    data, error = _read_json(HOW_IT_WORKS_FILE)
    if data is None:
        return None, error
    try:
        return HowItWorks(**data), None
    except Exception as exc:  # noqa: BLE001
        logger.warning("how_it_works.json не прошёл валидацию: {}", exc)
        return None, "Описание работы приложения не прошло проверку формата."


def load_methodology() -> Methodology | None:
    """Справочник проверок (``None``, если файл недоступен/битый)."""
    return _methodology()[0]


def methodology_error() -> str | None:
    return _methodology()[1]


def load_how_it_works() -> HowItWorks | None:
    return _how_it_works()[0]


def how_it_works_error() -> str | None:
    return _how_it_works()[1]


def methodology_updated_at() -> str:
    """Дата актуальности методологии («14.11.2026») или пустая строка."""
    data = load_methodology()
    return (data.updated_at if data else "") or ""


def methodology_for(check_id: str) -> MethodologyCheck | None:
    """Описание проверки по её id (``a02_privacy_link``)."""
    data = load_methodology()
    return data.find(check_id) if data else None


def reload() -> None:
    """Сбрасывает кэш (используется в тестах и при обновлении файлов)."""
    _methodology.cache_clear()
    _how_it_works.cache_clear()


__all__ = [
    "HOW_IT_WORKS_FILE",
    "METHODOLOGY_FILE",
    "how_it_works_error",
    "load_how_it_works",
    "load_methodology",
    "methodology_error",
    "methodology_for",
    "methodology_updated_at",
    "reload",
]
