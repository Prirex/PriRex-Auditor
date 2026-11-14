"""Модуль автообновления (без GitHub API и токенов)."""

from app.updater.updater import (
    UpdateInfo,
    check_for_updates,
    check_for_updates_sync,
    should_check_now,
)

__all__ = [
    "UpdateInfo",
    "check_for_updates",
    "check_for_updates_sync",
    "should_check_now",
]
