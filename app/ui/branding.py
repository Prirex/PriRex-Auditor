"""Брендинг: логотип, ссылки, футер «Разработано PriRex · github.com/Prirex»."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from app.i18n import tr
from app.paths import asset_path
from app.ui.icons import asset_icon
from app.ui.theme import PALETTE
from app.version import BOOSTY_LABEL as _BOOSTY_LABEL
from app.version import BOOSTY_URL as _BOOSTY_URL

AUTHOR_LINK_TEXT = "github.com/Prirex"
AUTHOR_LINK_URL = "https://github.com/Prirex"
#: Псевдонимы для удобства вызовов из UI.
AUTHOR_TEXT = AUTHOR_LINK_TEXT
AUTHOR_URL = AUTHOR_LINK_URL
FOOTER_HEIGHT = 52

#: Страница поддержки автора.
BOOSTY_URL = _BOOSTY_URL
BOOSTY_TEXT = _BOOSTY_LABEL


def open_boosty(parent: QWidget | None = None, ask: bool | None = None) -> None:
    """Открывает страницу поддержки в системном браузере.

    ``ask=None`` — поведение из настроек (по умолчанию без подтверждения).
    """
    if ask is None:
        try:
            from app.config import get_config

            ask = bool(get_config().boosty_ask_confirm)
        except Exception:  # noqa: BLE001 - настройки не должны мешать
            ask = False
    if ask:
        from PySide6.QtWidgets import QMessageBox

        answer = QMessageBox.question(
            parent,
            "Поддержать автора",
            "Открыть страницу поддержки в браузере?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
    open_external(BOOSTY_URL)


def boosty_button(parent: QWidget | None = None, text: str = BOOSTY_TEXT) -> QPushButton:
    """Кнопка-пилюля «Поддержать автора» с сердечком."""
    button = QPushButton(f" {text}", parent)
    button.setObjectName("boostyButton")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setToolTip(f"Поддержать автора на Boosty: {BOOSTY_URL}")
    icon = asset_icon("heart.svg")
    if not icon.isNull():
        button.setIcon(icon)
        button.setIconSize(QSize(14, 14))
    button.clicked.connect(lambda: open_boosty(button))
    return button


def open_external(url: str) -> None:
    """Открывает ссылку в системном браузере."""
    if not url:
        return
    QDesktopServices.openUrl(QUrl(url))


@lru_cache(maxsize=None)
def _logo_source() -> QPixmap | None:
    for name in ("logo_header.png", "logo.png", "logo.svg"):
        path = asset_path(name)
        if not path.exists():
            continue
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            return pixmap
    return None


def logo_pixmap(height: int = 28) -> QPixmap | None:
    """Логотип нужной высоты с сохранением пропорций (None, если файла нет)."""
    source = _logo_source()
    if source is None:
        return None
    height = max(8, int(height))
    if source.height() == height:
        return source
    return source.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)


class ClickableLabel(QLabel):
    """QLabel, который умеет кликаться."""

    clicked = Signal()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class LinkLabel(QLabel):
    """Ссылка без подчёркивания, с подчёркиванием при наведении."""

    def __init__(
        self,
        text: str = AUTHOR_LINK_TEXT,
        url: str = AUTHOR_LINK_URL,
        parent: QWidget | None = None,
        color: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._url = url
        self._color = color or PALETTE["link"]
        self._hovered = False
        self.setObjectName("FooterLink")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        self.setOpenExternalLinks(False)
        self.linkActivated.connect(self._on_activated)
        self.setToolTip(url)
        self._refresh()

    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        decoration = "underline" if self._hovered else "none"
        self.setText(
            f'<a href="{self._url}" style="color:{self._color};'
            f'text-decoration:{decoration};font-size:12px;">{self._text}</a>'
        )

    def _on_activated(self, url: str) -> None:
        open_external(url or self._url)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._hovered = True
        self._refresh()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._hovered = False
        self._refresh()
        super().leaveEvent(event)


def _made_by_html(font_size: int = 12) -> str:
    return (
        f'<span style="color:{PALETTE["text_muted"]};font-size:{font_size}px;">'
        f'Разработка от </span>'
        f'<span style="color:{PALETTE["text_heading"]};font-size:{font_size}px;">PriRex</span>'
    )


class BrandFooter(QFrame):
    """Нижняя панель с логотипом и ссылкой на автора. Всегда видима."""

    about_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Footer")
        self.setFixedHeight(FOOTER_HEIGHT)
        self.setFrameShape(QFrame.Shape.NoFrame)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(10)

        self.logo_label = ClickableLabel(self)
        self.logo_label.setObjectName("FooterLogo")
        self.logo_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logo_label.setToolTip("О программе")
        self.logo_label.clicked.connect(self.about_requested)
        self._apply_logo()
        layout.addWidget(self.logo_label, 0, Qt.AlignmentFlag.AlignVCenter)

        made_by = QLabel(self)
        made_by.setObjectName("FooterText")
        made_by.setTextFormat(Qt.TextFormat.RichText)
        made_by.setText(_made_by_html())
        layout.addWidget(made_by, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addStretch(1)

        self.boosty_button = boosty_button(self)
        layout.addWidget(self.boosty_button, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addStretch(1)

        self.link = LinkLabel(AUTHOR_LINK_TEXT, AUTHOR_LINK_URL, self)
        layout.addWidget(self.link, 0, Qt.AlignmentFlag.AlignVCenter)

    # ------------------------------------------------------------------
    def _apply_logo(self) -> None:
        pixmap = logo_pixmap(26)
        if pixmap is not None:
            self.logo_label.setPixmap(pixmap)
            self.logo_label.setFixedSize(pixmap.size())
        else:
            self.logo_label.setText("PriRex")
            font = QFont(self.font())
            font.setPointSizeF(10.0)
            font.setWeight(QFont.Weight.DemiBold)
            self.logo_label.setFont(font)
            self.logo_label.setStyleSheet(
                f"color:{PALETTE['text_heading']};background:transparent;"
            )


__all__ = [
    "AUTHOR_LINK_TEXT",
    "AUTHOR_LINK_URL",
    "BOOSTY_TEXT",
    "BOOSTY_URL",
    "BrandFooter",
    "ClickableLabel",
    "FOOTER_HEIGHT",
    "LinkLabel",
    "boosty_button",
    "logo_pixmap",
    "open_boosty",
    "open_external",
]
