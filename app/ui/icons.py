"""Иконки статусов и приложения (нарисованные SVG из assets/icons)."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from app.core.models import CheckStatus
from app.paths import asset_path
from app.ui.theme import STATUS_COLORS

STATUS_ICON_FILES: dict[str, str] = {
    "pass": "pass.svg",
    "warn": "warn.svg",
    "fail": "fail.svg",
    "skip": "skip.svg",
    "not_applicable": "na.svg",
}


def _status_key(status: CheckStatus | str) -> str:
    return status.value if isinstance(status, CheckStatus) else str(status)


@lru_cache(maxsize=None)
def asset_icon(name: str) -> QIcon:
    """Иконка из assets/icons по имени файла."""
    path = asset_path("icons", name)
    if path.exists():
        icon = QIcon(str(path))
        if not icon.isNull():
            return icon
    return QIcon()


@lru_cache(maxsize=None)
def status_icon(status: CheckStatus | str) -> QIcon:
    """Иконка статуса проверки (со своим цветом для каждого статуса)."""
    key = _status_key(status)
    filename = STATUS_ICON_FILES.get(key)
    if filename:
        icon = asset_icon(filename)
        if not icon.isNull():
            return icon
    return QIcon(_fallback_pixmap(key, 18))


def _fallback_pixmap(key: str, size: int) -> QPixmap:
    """Нарисованный вручную кружок, если SVG не нашёлся."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(STATUS_COLORS.get(key, "#9AA5B1"))
    painter.setBrush(color)
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(QRectF(1, 1, size - 2, size - 2))
    painter.setPen(QPen(QColor("#FFFFFF"), 1.7))
    if key == "fail":
        painter.drawLine(6, 6, size - 6, size - 6)
        painter.drawLine(size - 6, 6, 6, size - 6)
    elif key == "warn":
        painter.drawLine(size // 2, 5, size // 2, size - 7)
        painter.drawPoint(size // 2, size - 4)
    else:
        painter.drawLine(6, size // 2, size - 6, size // 2)
    painter.end()
    return pixmap


def status_pixmap(status: CheckStatus | str, size: int = 18) -> QPixmap:
    icon = status_icon(status)
    if not icon.isNull():
        pixmap = icon.pixmap(size, size)
        if not pixmap.isNull():
            return pixmap
    return _fallback_pixmap(_status_key(status), size)


@lru_cache(maxsize=None)
def status_dot(status: CheckStatus | str, size: int = 10) -> QPixmap:
    """Маленький цветной кружок статуса — для дерева проверок (меньше шума)."""
    key = _status_key(status)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(STATUS_COLORS.get(key, "#9AA5B1")))
    inset = 1.0 if size >= 8 else 0.5
    painter.drawEllipse(QRectF(inset, inset, size - 2 * inset, size - 2 * inset))
    painter.end()
    return pixmap


@lru_cache(maxsize=None)
def app_icon() -> QIcon:
    """Иконка приложения: .ico для Windows, иначе PNG."""
    for name in ("logo.ico", "icon.png", "logo.png"):
        path = asset_path(name)
        if path.exists():
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon
    return status_icon(CheckStatus.PASS)


__all__ = [
    "app_icon",
    "asset_icon",
    "status_dot",
    "status_icon",
    "status_pixmap",
]
