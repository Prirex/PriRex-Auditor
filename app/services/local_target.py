"""Локальная проверка: путь к папке или HTML-файлу вместо адреса сайта.

Пользователь может указать:
  * папку с сайтом: ``C:\\sites\\lutik`` (ищется ``index.html`` или ``index``);
  * конкретный файл: ``C:\\sites\\lutik\\index.html``;
  * файл без расширения: ``C:\\sites\\lutik\\index`` (распознаётся по содержимому);
  * file-ссылку: ``file:///C:/sites/lutik/index.html``;
  * UNC-путь: ``\\\\server\\share\\site``.

Модуль намеренно не тянет сеть и Qt — только файловая система.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

#: Расширения, которые считаются HTML-страницами.
HTML_SUFFIXES: tuple[str, ...] = (".html", ".htm", ".xhtml", ".shtml")

#: Имена стартовых страниц по приоритету (с расширением и без).
INDEX_NAMES: tuple[str, ...] = (
    "index.html",
    "index.htm",
    "index.xhtml",
    "index",
    "default.html",
    "default.htm",
    "default",
    "home.html",
    "home",
    "main.html",
)

#: Очевидно не HTML — содержимое не читаем.
_BINARY_SUFFIXES: frozenset[str] = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp",
        ".css", ".js", ".mjs", ".map", ".json", ".md", ".txt", ".xml",
        ".pdf", ".zip", ".rar", ".7z", ".gz", ".exe", ".dll", ".py",
        ".pyc", ".ps1", ".bat", ".cmd", ".woff", ".woff2", ".ttf", ".otf",
        ".mp4", ".mp3", ".webm", ".avi", ".db", ".sqlite", ".log",
    }
)

#: Признаки HTML в первых килобайтах — для файлов без расширения.
_HTML_MARKERS: tuple[bytes, ...] = (
    b"<!doctype html",
    b"<html",
    b"<head",
    b"<body",
    b"<title",
    b"<meta",
    b"<div",
    b"<section",
)

#: Сколько файлов в папке максимум проверяем по содержимому.
MAX_SNIFF_FILES = 300

_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


class LocalTargetError(ValueError):
    """Понятная ошибка разбора локального пути (текст для интерфейса)."""


@dataclass(frozen=True)
class LocalTarget:
    """Разрешённая локальная цель проверки."""

    raw: str
    root: Path
    entry: Path
    from_file: bool

    @property
    def display(self) -> str:
        """Что показать в поле адреса: папка или файл как ввёл пользователь."""
        return str(self.entry if self.from_file else self.root)

    @property
    def base_uri(self) -> str:
        return self.entry.as_uri()


def looks_local(value: str) -> bool:
    """Похоже ли введённое значение на локальный путь (а не на адрес сайта)."""
    text = (value or "").strip().strip('"').strip("'")
    if not text:
        return False
    low = text.lower()
    if low.startswith(("file:", "file://")):
        return True
    if "://" in text:
        # любой другой URL-схемой занимается normalize_url (даст понятную ошибку)
        return False
    if text.startswith("\\\\"):  # UNC \\server\share
        return True
    if _DRIVE_RE.match(text):  # C:\site или D:/site
        return True
    if text.startswith(("./", ".\\", "../", "..\\", "~/")):
        return True
    if "\\" in text:  # обратные слэши — почти наверняка путь Windows
        return True
    if "://" not in text:
        try:
            if Path(text).expanduser().exists():
                return True
        except OSError:
            return False
    return False


def _path_from_input(raw: str) -> Path:
    text = (raw or "").strip().strip('"').strip("'")
    if text.lower().startswith("file:"):
        parsed = urlparse(text)
        path = url2pathname(unquote(parsed.path))
        if parsed.netloc:
            path = f"//{parsed.netloc}{path}"
        return Path(path)
    return Path(text).expanduser()


def _resolve_path(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def file_looks_like_html(path: Path) -> bool:
    """Является ли файл HTML-страницей (по расширению или содержимому)."""
    suffix = path.suffix.lower()
    if suffix in HTML_SUFFIXES:
        return True
    if suffix in _BINARY_SUFFIXES:
        return False
    try:
        with path.open("rb") as handle:
            head = handle.read(4096)
    except OSError:
        return False
    low = head.lower()
    return any(marker in low for marker in _HTML_MARKERS)


def _pick_entry(directory: Path) -> Path | None:
    """Стартовая страница в папке: index.html/index, иначе первый HTML-файл."""
    try:
        files = [item for item in directory.iterdir() if item.is_file()]
    except OSError as exc:
        raise LocalTargetError(f"Не удалось прочитать папку: {exc}") from exc

    by_name = {item.name.lower(): item for item in files}
    for name in INDEX_NAMES:
        candidate = by_name.get(name)
        if candidate is not None:
            return candidate

    html_files = sorted(
        (item for item in files if item.suffix.lower() in HTML_SUFFIXES),
        key=lambda item: item.name.lower(),
    )
    if html_files:
        return html_files[0]

    # Файлы без расширения (например, index, about) — проверяем содержимое.
    suspicious = [
        item
        for item in files
        if item.suffix.lower() not in _BINARY_SUFFIXES
    ][:MAX_SNIFF_FILES]
    sniffed = sorted(
        (item for item in suspicious if file_looks_like_html(item)),
        key=lambda item: item.name.lower(),
    )
    return sniffed[0] if sniffed else None


def resolve_local_target(raw: str) -> LocalTarget:
    """Разрешает путь пользователя в папку и стартовую страницу."""
    path = _resolve_path(_path_from_input(raw))
    if not path.exists():
        raise LocalTargetError(f"Папка или файл не найдены: {path}")
    if path.is_file():
        if not file_looks_like_html(path):
            raise LocalTargetError(
                f"Файл «{path.name}» не похож на HTML-страницу. "
                "Выберите index.html или другой файл сайта."
            )
        return LocalTarget(raw=raw, root=path.parent, entry=path, from_file=True)
    if not path.is_dir():
        raise LocalTargetError("Указанный путь не является папкой или файлом.")
    entry = _pick_entry(path)
    if entry is None:
        raise LocalTargetError(
            f"В папке «{path}» не найдено HTML-страниц. "
            "Нажмите «Файл…» и укажите страницу сайта вручную "
            "(например, index.html или файл index без расширения)."
        )
    return LocalTarget(raw=raw, root=path, entry=entry, from_file=False)


def local_path_from_uri(uri: str) -> Path | None:
    """Преобразует file://-ссылку в Path (для подстраниц локального сайта)."""
    if not (uri or "").lower().startswith("file:"):
        return None
    return _resolve_path(_path_from_input(uri))


def is_inside_root(path: Path, root: Path) -> bool:
    """Не выходит ли файл за пределы папки сайта (защита от ../)."""
    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    return True


__all__ = [
    "HTML_SUFFIXES",
    "INDEX_NAMES",
    "LocalTarget",
    "LocalTargetError",
    "file_looks_like_html",
    "is_inside_root",
    "local_path_from_uri",
    "looks_local",
    "resolve_local_target",
]
