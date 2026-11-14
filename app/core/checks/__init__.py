"""Пакет проверок.

Модули обнаруживаются автоматически: любой файл в этом пакете (кроме
``base.py``) импортируется, и все классы-наследники ``BaseCheck`` с
непустым ``id`` попадают в реестр. Порядок — по ``id``.
"""

from __future__ import annotations

import importlib
import pkgutil

from app.core.checks.base import BaseCheck

DISCOVERY_ERRORS: list[str] = []


def discover_checks() -> list[type[BaseCheck]]:
    """Импортирует все модули пакета и собирает классы проверок."""
    found: dict[str, type[BaseCheck]] = {}
    for module_info in pkgutil.iter_modules(__path__):  # noqa: F821 - определён пакетом
        name = module_info.name
        if name.startswith("_") or name == "base":
            continue
        module_path = f"{__name__}.{name}"
        try:
            module = importlib.import_module(module_path)
        except Exception as exc:  # noqa: BLE001 - один битый модуль не должен ломать всё
            DISCOVERY_ERRORS.append(f"{module_path}: {exc.__class__.__name__}: {exc}")
            continue
        for value in vars(module).values():
            if (
                isinstance(value, type)
                and issubclass(value, BaseCheck)
                and value is not BaseCheck
                and getattr(value, "id", "")
                and value.__module__ == module.__name__
            ):
                found[value.id] = value
    return [found[key] for key in sorted(found)]


ALL_CHECKS: list[type[BaseCheck]] = discover_checks()


def create_checks() -> list[BaseCheck]:
    """Экземпляры всех проверок в порядке id."""
    return [cls() for cls in ALL_CHECKS]


__all__ = ["ALL_CHECKS", "DISCOVERY_ERRORS", "BaseCheck", "create_checks", "discover_checks"]
