"""Версия приложения — единый источник истины (совместимый ре-экспорт)."""

from app.version import *  # noqa: F401,F403
from app.version import __version__

__all__ = ["__version__"]
