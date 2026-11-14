"""Версия и метаданные приложения — единый источник истины."""

from __future__ import annotations

__version__ = "1.1.0"
__build__ = "2026.11.14"

APP_NAME = "PriRex Auditor"
APP_DISPLAY_NAME = "PriRex Auditor"
APP_SUBTITLE = "проверка сайта по 152-ФЗ"
APP_TITLE = f"{APP_DISPLAY_NAME} — {APP_SUBTITLE}"

AUTHOR = "PriRex"
AUTHOR_URL = "https://github.com/Prirex"
BOOSTY_URL = "https://boosty.to/prirex/donate"
BOOSTY_LABEL = "Поддержать автора"
REPO_OWNER = "PriRex"
REPO_NAME = "PriRex-Auditor"
REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"
RELEASES_URL = f"{REPO_URL}/releases/latest"
VERSION_JSON_URL = (
    f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/version.json"
)
DOWNLOAD_URL = f"{REPO_URL}/releases/latest"

DISCLAIMER = (
    "Это автоматическая эвристическая проверка. Она не заменяет аудит юриста "
    "и не гарантирует отсутствие претензий Роскомнадзора, Роспотребнадзора или ФАС."
)

DISCLAIMER_SHORT = (
    "Автоматическая эвристическая проверка. Не заменяет аудит юриста и не "
    "гарантирует отсутствие претензий регуляторов."
)

__all__ = [
    "APP_DISPLAY_NAME",
    "APP_NAME",
    "APP_SUBTITLE",
    "APP_TITLE",
    "AUTHOR",
    "AUTHOR_URL",
    "BOOSTY_LABEL",
    "BOOSTY_URL",
    "DISCLAIMER",
    "DISCLAIMER_SHORT",
    "DOWNLOAD_URL",
    "RELEASES_URL",
    "REPO_NAME",
    "REPO_OWNER",
    "REPO_URL",
    "VERSION_JSON_URL",
    "__build__",
    "__version__",
]
