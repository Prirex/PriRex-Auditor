"""Доступ к проверкам (реестр)."""

from __future__ import annotations

from app.core.checks import ALL_CHECKS, DISCOVERY_ERRORS, create_checks
from app.core.checks.base import BaseCheck


def all_check_classes() -> list[type[BaseCheck]]:
    return list(ALL_CHECKS)


def build_checks(categories: list[str] | None = None) -> list[BaseCheck]:
    """Экземпляры проверок, при необходимости — только из указанных блоков."""
    checks = create_checks()
    if categories:
        checks = [c for c in checks if c.category in categories]
    return checks


def check_titles() -> dict[str, str]:
    return {cls.id: cls.title for cls in ALL_CHECKS}


__all__ = [
    "ALL_CHECKS",
    "DISCOVERY_ERRORS",
    "BaseCheck",
    "all_check_classes",
    "build_checks",
    "check_titles",
]
