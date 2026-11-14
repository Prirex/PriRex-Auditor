"""Исключения ядра."""

from __future__ import annotations


class ScanCancelled(Exception):
    """Пользователь отменил проверку."""


__all__ = ["ScanCancelled"]
