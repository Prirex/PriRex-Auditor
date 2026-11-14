"""Сбор контекста для локальной папки с сайтом (без хостинга).

Проверка работает офлайн: читает ``index.html`` и связанные с ним страницы
(политика, контакты, оферта) прямо с диска. Всё, что требует опубликованного
сайта (HTTPS, HTTP-заголовки, загрузка в браузере), помечается ограниченно —
это честно сообщается в примечаниях и в самих проверках.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.core import detect
from app.core.errors import ScanCancelled
from app.core.models import (
    HttpsInfo,
    PageInfo,
    RobotsInfo,
    SiteContext,
    SitemapInfo,
)
from app.services.http.client import decode_html
from app.services.local_target import (
    INDEX_NAMES,
    LocalTarget,
    LocalTargetError,
    is_inside_root,
    local_path_from_uri,
    resolve_local_target,
)
from app.services.site_context import (
    _count_sitemap_urls,
    _parse_robots,
    extract_cookie_banner,
    parse_site_context,
)

ProgressCallback = Callable[[float, str], None]
CancelCallback = Callable[[], bool]

#: Максимум html-файла для разбора.
MAX_LOCAL_BYTES = 5 * 1024 * 1024

#: Маркеры ссылок на служебные страницы локального сайта.
_PAGE_MARKERS: dict[str, tuple[str, ...]] = {
    "privacy": ("политик", "privacy", "конфиденц", "персональн", "policy"),
    "contacts": ("контакт", "contact", "связаться", "обратная связь", "support"),
    "offer": ("оферт", "условия", "terms", "правила", "договор", "agreement"),
}


def _check_cancel(cancelled: CancelCallback | None) -> None:
    if cancelled is not None and cancelled():
        raise ScanCancelled()


def _report(progress: ProgressCallback | None, fraction: float, message: str) -> None:
    if progress is not None:
        progress(fraction, message)


def _read_html(path: Path) -> str:
    """Читает HTML-файл с ограничением размера и подбором кодировки."""
    raw = path.read_bytes()
    if len(raw) > MAX_LOCAL_BYTES:
        raw = raw[:MAX_LOCAL_BYTES]
    return decode_html(raw, "")


def _local_robots(root: Path) -> RobotsInfo:
    path = root / "robots.txt"
    info = RobotsInfo()
    if not path.is_file():
        return info
    try:
        text = decode_html(path.read_bytes()[:512 * 1024], "text/plain")
    except OSError as exc:
        info.error = str(exc)
        return info
    info.found = True
    info.content = text
    info.disallow_all, info.sitemaps = _parse_robots(text)
    return info


def _local_sitemap(root: Path, robots: RobotsInfo) -> SitemapInfo:
    candidates: list[Path] = []
    for raw in robots.sitemaps:
        local = local_path_from_uri(raw) if raw.lower().startswith("file:") else None
        if local is not None:
            candidates.append(local)
        elif raw and "/" not in raw:
            candidates.append(root / raw)
    candidates.append(root / "sitemap.xml")

    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            text = decode_html(candidate.read_bytes()[:2 * 1024 * 1024], "application/xml")
        except OSError:
            continue
        count, is_index = _count_sitemap_urls(text)
        return SitemapInfo(
            found=True,
            url=candidate.as_uri(),
            url_count=count,
            is_index=is_index,
        )
    return SitemapInfo()


def _page_from_file(path: Path, key: str, root: Path) -> PageInfo | None:
    if path.is_dir():
        try:
            files = {
                item.name.lower(): item
                for item in path.iterdir()
                if item.is_file() and item.suffix.lower() in (".html", ".htm", ".xhtml")
            }
        except OSError:
            return None
        for name in INDEX_NAMES:
            if name in files:
                path = files[name]
                break
        else:
            return PageInfo(
                key=key,
                url=path.as_uri(),
                ok=False,
                error="Папка без index.html: страницу не из чего собрать.",
            )
    if not path.is_file():
        return None
    if not is_inside_root(path, root):
        return PageInfo(
            key=key,
            url=path.as_uri(),
            ok=False,
            error="Файл находится вне папки сайта и не проверялся.",
        )
    try:
        html = _read_html(path)
    except OSError as exc:
        return PageInfo(key=key, url=path.as_uri(), ok=False, error=str(exc))
    if not html.strip():
        return PageInfo(key=key, url=path.as_uri(), ok=False, error="Файл пуст.")
    soup = detect.make_soup(html)
    page = PageInfo(
        key=key,
        url=path.as_uri(),
        ok=True,
        title=detect.collapse_text(soup.title.get_text() if soup.title else "", 200),
        text=detect.visible_text(soup, 60_000),
    )
    banner = extract_cookie_banner(soup)
    page.has_cookie_wall = bool(banner.found and len(page.text) < 1500)
    return page


def _local_pages(
    context: SiteContext,
    target: LocalTarget,
    max_pages: int,
) -> dict[str, PageInfo]:
    """Локальные подстраницы: политика, контакты, оферта."""
    pages: dict[str, PageInfo] = {}
    chosen: dict[str, Path] = {}
    main_path = target.entry

    privacy_link = detect.find_privacy_link(context.links)
    if privacy_link is not None:
        path = local_path_from_uri(privacy_link.href)
        if path is not None:
            chosen["privacy"] = path

    for key, markers in _PAGE_MARKERS.items():
        if key in chosen:
            continue
        for link in context.links:
            if not link.href.lower().startswith("file:"):
                continue
            haystack = f"{link.text} {link.href}".lower()
            if not any(marker in haystack for marker in markers):
                continue
            path = local_path_from_uri(link.href)
            if path is None or path == main_path:
                continue
            chosen[key] = path
            break

    for key, path in list(chosen.items())[: max(0, int(max_pages))]:
        page = _page_from_file(path, key, target.root)
        if page is not None:
            pages[key] = page
    return pages


def build_local_context(
    raw: str,
    options,
    progress: ProgressCallback | None = None,
    cancelled: CancelCallback | None = None,
) -> SiteContext:
    """Собирает SiteContext из локальной папки (синхронно, диск — быстрый)."""
    _check_cancel(cancelled)
    _report(progress, 0.1, "Чтение локальной папки…")
    target = resolve_local_target(raw)

    try:
        html = _read_html(target.entry)
    except OSError as exc:
        raise LocalTargetError(f"Не удалось прочитать {target.entry}: {exc}") from exc
    if not html.strip():
        raise LocalTargetError("Главная страница пуста — проверять нечего.")

    base_uri = target.base_uri
    context = parse_site_context(html, base_uri, local_root=target.root)
    context.target_url = raw
    context.url = base_uri
    context.domain = target.root.name or "local"
    context.is_local = True
    context.local_root = str(target.root)
    context.deep_analysis = False
    context.status_code = None
    context.headers = {}
    context.security_headers = {}
    context.https = HttpsInfo(
        requested_url=raw,
        final_url=base_uri,
        used_https=False,
        https_available=False,
        cert_valid=False,
        error="Локальная папка: HTTPS не используется",
    )

    _check_cancel(cancelled)
    _report(progress, 0.45, "Проверка robots.txt и sitemap.xml…")
    context.robots = _local_robots(target.root)
    context.sitemap = _local_sitemap(target.root, context.robots)

    _check_cancel(cancelled)
    _report(progress, 0.7, "Чтение страниц политики и контактов…")
    context.pages = _local_pages(context, target, int(options.max_pages))

    context.note(
        "Проверка локальной папки: страницы читаются с диска, без публикации. "
        "HTTPS, HTTP-заголовки и динамические элементы (cookie-баннер) "
        "проверяются только после публикации сайта."
    )
    if target.from_file and target.entry.name.lower() not in {
        "index.html",
        "index.htm",
        "index.xhtml",
    }:
        context.note(
            f"Проверяется файл «{target.entry.name}». Чтобы проверить весь сайт, "
            "укажите папку или её index.html."
        )
    _report(progress, 1.0, "Локальная папка прочитана")
    return context


async def build_local_site_context(
    raw: str,
    options,
    progress: ProgressCallback | None = None,
    cancelled: CancelCallback | None = None,
) -> SiteContext:
    """Асинхронная обёртка (чтение диска — в отдельном потоке, чтобы не блокировать)."""
    import asyncio

    return await asyncio.to_thread(
        build_local_context, raw, options, progress, cancelled
    )


__all__ = [
    "MAX_LOCAL_BYTES",
    "build_local_context",
    "build_local_site_context",
]
