"""Единая точка нормализации ввода: адрес сайта или локальная папка."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.core.detect import normalize_url
from app.services.local_target import (
    LocalTargetError,
    looks_local,
    resolve_local_target,
)


class TargetKind(str, Enum):
    URL = "url"
    LOCAL = "local"


@dataclass
class NormalizedTarget:
    """Результат разбора поля ввода."""

    kind: str = TargetKind.URL.value
    #: Для URL — http(s)-адрес, для локальной проверки — путь к файлу/папке.
    value: str = ""
    #: Отображаемое значение в поле ввода.
    display: str = ""
    path: Path | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.value) and self.error is None

    @property
    def is_local(self) -> bool:
        return self.kind == TargetKind.LOCAL.value


def normalize_target(raw: str) -> NormalizedTarget:
    """Приводит ввод к адресу сайта или локальному пути с понятной ошибкой."""
    text = (raw or "").strip().strip('"').strip("'")
    if not text:
        return NormalizedTarget(error="Введите адрес сайта или путь к локальной папке")

    if looks_local(text):
        try:
            target = resolve_local_target(text)
        except LocalTargetError as exc:
            return NormalizedTarget(kind=TargetKind.LOCAL.value, error=str(exc))
        except OSError as exc:
            return NormalizedTarget(
                kind=TargetKind.LOCAL.value,
                error=f"Не удалось прочитать локальный путь: {exc}",
            )
        return NormalizedTarget(
            kind=TargetKind.LOCAL.value,
            value=str(target.entry),
            display=target.display,
            path=target.root,
        )

    normalized = normalize_url(text)
    if not normalized.ok:
        return NormalizedTarget(error=normalized.error)
    return NormalizedTarget(
        kind=TargetKind.URL.value,
        value=normalized.url,
        display=normalized.url,
    )


__all__ = ["NormalizedTarget", "TargetKind", "normalize_target"]
