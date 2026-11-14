"""Пути к ресурсам и пользовательским данным.

Работает и из исходников, и из PyInstaller-бандла (``sys._MEIPASS``).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from app.version import APP_NAME

APP_ROOT = Path(__file__).resolve().parent.parent
APPDATA_SUBDIR = APP_NAME


def is_frozen() -> bool:
    """Запущено ли приложение из собранного exe."""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Каталог с ресурсами (в бандле — распакованный ``_MEIPASS``)."""
    if is_frozen():
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle:
            return Path(bundle)
        return Path(sys.executable).resolve().parent
    return APP_ROOT


def asset_path(*parts: str) -> Path:
    """Путь к файлу в ``assets``."""
    return resource_dir().joinpath("assets", *parts)


def asset_url(*parts: str) -> str:
    """Путь к ресурсу для Qt (прямые слеши)."""
    return asset_path(*parts).as_posix()


def appdata_dir() -> Path:
    """``%APPDATA%\\PriRex Auditor`` (или XDG-аналог)."""
    base = os.environ.get("APPDATA")
    if base:
        path = Path(base) / APPDATA_SUBDIR
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        path = (Path(xdg) if xdg else Path.home() / ".config") / APPDATA_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return appdata_dir() / "config.json"


def log_dir() -> Path:
    path = appdata_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    path = appdata_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def screenshots_dir() -> Path:
    """Каталог для скриншотов текущего запуска."""
    path = cache_dir() / "screenshots"
    path.mkdir(parents=True, exist_ok=True)
    return path


def temp_report_dir() -> Path:
    path = Path(tempfile.gettempdir()) / APPDATA_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_report_dir() -> Path:
    """Папка для экспортированных отчётов по умолчанию."""
    documents = Path.home() / "Documents"
    base = documents if documents.exists() else Path.home()
    path = base / APPDATA_SUBDIR / "Отчёты"
    return path


def ensure_report_dir(path: str | Path | None) -> Path:
    target = Path(path) if path else default_report_dir()
    target.mkdir(parents=True, exist_ok=True)
    return target


def safe_filename(value: str, fallback: str = "report") -> str:
    """Имя файла без запрещённых символов."""
    cleaned = "".join(
        ch if ch not in '\\/:*?"<>|\n\r\t' else "_" for ch in (value or "")
    ).strip(" .")
    return cleaned or fallback
