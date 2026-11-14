"""Окно «О программе» с брендингом."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.branding import LinkLabel, boosty_button, logo_pixmap
from app.version import (
    APP_DISPLAY_NAME,
    APP_SUBTITLE,
    DISCLAIMER_SHORT,
    __build__,
    __version__,
)


class AboutDialog(QDialog):
    """Модальное окно ~400×340: логотип, версия, автор, дисклеймер."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AboutDialog")
        self.setWindowTitle("О программе")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(8)

        # логотип
        logo = QLabel(self)
        logo.setObjectName("AboutLogo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = logo_pixmap(64)
        if pixmap is not None:
            logo.setPixmap(pixmap)
        else:
            logo.setText("PriRex")
            logo.setStyleSheet(
                "font-size:24px;font-weight:600;color:#4A463F;background:transparent;"
            )
        layout.addWidget(logo)

        # название
        title = QLabel(APP_DISPLAY_NAME, self)
        title.setObjectName("AboutName")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(APP_SUBTITLE, self)
        subtitle.setObjectName("AboutVersion")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        version = QLabel(f"Версия {__version__} · сборка {__build__}", self)
        version.setObjectName("AboutVersion")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        layout.addSpacing(6)

        made_by = QLabel("Разработка от PriRex", self)
        made_by.setObjectName("AboutVersion")
        made_by.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(made_by)

        link_row = QHBoxLayout()
        link_row.setContentsMargins(0, 0, 0, 0)
        link_row.addStretch(1)
        link_row.addWidget(LinkLabel("github.com/Prirex", "https://github.com/Prirex", self))
        link_row.addStretch(1)
        layout.addLayout(link_row)

        boosty_row = QHBoxLayout()
        boosty_row.setContentsMargins(0, 0, 0, 0)
        boosty_row.addStretch(1)
        boosty_row.addWidget(boosty_button(self, "Поддержать автора на Boosty"))
        boosty_row.addStretch(1)
        layout.addLayout(boosty_row)

        layout.addSpacing(6)

        disclaimer = QLabel(DISCLAIMER_SHORT, self)
        disclaimer.setObjectName("AboutDisclaimer")
        disclaimer.setWordWrap(True)
        disclaimer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(disclaimer)

        layout.addStretch(1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        close_button = QPushButton("Закрыть", self)
        close_button.setObjectName("PrimaryButton")
        close_button.setMinimumWidth(112)
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)


__all__ = ["AboutDialog"]
