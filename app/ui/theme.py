"""Тема оформления: палитра, шрифты, загрузка QSS."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from app.paths import asset_path

#: Приглушённая палитра приложения (единый источник для UI и кода).
PALETTE: dict[str, str] = {
    "bg": "#F2F0EC",
    "surface": "#FBFAF7",
    "surface_alt": "#F6F4EF",
    "card": "#FFFFFF",
    "border": "#E4E0D8",
    "border_strong": "#D6D2CB",
    "divider": "#E0DDD8",
    "text": "#2E2E2E",
    "text_heading": "#4A463F",
    "text_muted": "#6E6A63",
    "text_dim": "#8C877E",
    "accent": "#7A9A7E",
    "accent_hover": "#6B8A6F",
    "accent_soft": "#E6EDE4",
    "link": "#6B7F99",
    "link_hover": "#5A6C83",
    # статусы
    "pass": "#8FAE8B",
    "warn": "#C9A96A",
    "fail": "#B87A6E",
    "skip": "#9AA5B1",
    "na": "#D9A46B",
}

#: Цвет чипа/иконки для каждого статуса.
STATUS_COLORS: dict[str, str] = {
    "pass": PALETTE["pass"],
    "warn": PALETTE["warn"],
    "fail": PALETTE["fail"],
    "skip": PALETTE["skip"],
    "not_applicable": PALETTE["na"],
}

#: Фоновые цвета чипов статусов (светлые, приглушённые).
STATUS_CHIP_BG: dict[str, str] = {
    "pass": "#E6EEE4",
    "warn": "#F5EEDA",
    "fail": "#F3E2DE",
    "skip": "#E8ECF0",
    "not_applicable": "#F8EBDB",
}

STATUS_CHIP_FG: dict[str, str] = {
    "pass": "#52704F",
    "warn": "#8A7137",
    "fail": "#8E5449",
    "skip": "#5C6875",
    "not_applicable": "#966C39",
}

FONT_FAMILIES: tuple[str, ...] = (
    "Inter",
    "Segoe UI Variable Text",
    "Segoe UI",
    "SF Pro Text",
    "Helvetica Neue",
    "Arial",
)


def pick_font_family() -> str:
    """Первый доступный шрифт из предпочтительного списка."""
    try:
        available = set(QFontDatabase.families())
    except Exception:  # pragma: no cover - зависит от платформы
        return "Segoe UI"
    for family in FONT_FAMILIES:
        if family in available:
            return family
    return "Segoe UI"


def load_stylesheet() -> str:
    """Читает assets/theme.qss и подставляет путь к assets."""
    qss_path: Path = asset_path("theme.qss")
    try:
        raw = qss_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    assets_dir = asset_path().as_posix()
    return raw.replace("{assets}", assets_dir)


def apply_theme(app: QApplication) -> None:
    """Применяет шрифт, палитру и QSS ко всему приложению."""
    family = pick_font_family()
    font = QFont(family)
    font.setPointSizeF(9.5)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(font)

    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(PALETTE["bg"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(PALETTE["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(PALETTE["card"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(PALETTE["surface_alt"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(PALETTE["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(PALETTE["surface"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(PALETTE["text_heading"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(PALETTE["accent_soft"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(PALETTE["text"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(PALETTE["text_heading"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#F5F2ED"))
    palette.setColor(QPalette.ColorRole.Link, QColor(PALETTE["link"]))
    app.setPalette(palette)

    app.setStyleSheet(load_stylesheet())


def score_level(score: int) -> str:
    """Уровень для окраски крупного процента (QSS: QLabel#ScoreValue[level])."""
    if score >= 85:
        return "good"
    if score >= 70:
        return "ok"
    if score >= 50:
        return "warn"
    return "bad"


def set_prop(widget: QWidget, name: str, value: object) -> None:
    """Меняет QSS-свойство и перерисовывает виджет."""
    widget.setProperty(name, value)
    repolish(widget)


def repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


__all__ = [
    "FONT_FAMILIES",
    "PALETTE",
    "STATUS_CHIP_BG",
    "STATUS_CHIP_FG",
    "STATUS_COLORS",
    "apply_theme",
    "load_stylesheet",
    "pick_font_family",
    "repolish",
    "score_level",
    "set_prop",
]
