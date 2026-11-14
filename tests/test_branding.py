"""Тесты брендинга и кнопки Boosty (офлайн, offscreen)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault(
        "QT_QPA_FONTDIR",
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
    )

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton

import app.config as config_module
from app.config import AppConfig
from app.services.report import common as report_common
from app.ui import branding
from app.ui.about_dialog import AboutDialog
from app.ui.branding import BOOSTY_URL, BrandFooter, boosty_button, open_boosty
from app.ui.theme import apply_theme


@pytest.fixture(scope="module")
def qt_app():
    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    apply_theme(application)
    return application


@pytest.fixture
def opened(monkeypatch) -> list[str]:
    """Перехватывает open_external и собирает открытые адреса."""
    calls: list[str] = []
    monkeypatch.setattr(branding, "open_external", lambda url: calls.append(url))
    return calls


def test_open_boosty_without_confirmation(qt_app, opened, monkeypatch) -> None:
    monkeypatch.setattr(config_module, "get_config", lambda: AppConfig())
    open_boosty(None)
    assert opened == [BOOSTY_URL]
    assert BOOSTY_URL == "https://boosty.to/prirex/donate"


def test_boosty_button_click_opens_url(qt_app, opened, monkeypatch) -> None:
    monkeypatch.setattr(config_module, "get_config", lambda: AppConfig())
    button = boosty_button()
    assert button.objectName() == "boostyButton"
    assert "Поддержать автора" in button.text()
    button.click()
    assert opened == [BOOSTY_URL]


def test_open_boosty_asks_when_configured(qt_app, opened, monkeypatch) -> None:
    monkeypatch.setattr(
        config_module, "get_config", lambda: AppConfig(boosty_ask_confirm=True)
    )

    answers: list[QMessageBox.StandardButton] = []

    def fake_question(*_args, **_kwargs):
        return answers.pop(0)

    monkeypatch.setattr(QMessageBox, "question", fake_question)

    answers.append(QMessageBox.StandardButton.Cancel)
    open_boosty(None)
    assert opened == []

    answers.append(QMessageBox.StandardButton.Yes)
    open_boosty(None)
    assert opened == [BOOSTY_URL]


def test_footer_has_branding_and_boosty(qt_app) -> None:
    footer = BrandFooter()
    joined = " ".join(label.text() for label in footer.findChildren(QLabel))
    assert "Разработка от" in joined
    assert "PriRex" in joined
    assert footer.boosty_button.objectName() == "boostyButton"
    assert footer.link is not None
    # ссылка на автора реальная
    assert "github.com/Prirex" in footer.link.toolTip()


def test_about_dialog_has_boosty(qt_app) -> None:
    dialog = AboutDialog()
    buttons = [button.text() for button in dialog.findChildren(QPushButton)]
    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert any("Boosty" in text for text in buttons)
    assert any("Разработка от" in text for text in labels)


def test_report_branding_constants() -> None:
    """Отчёты используют новую подпись и ссылку на Boosty."""
    assert report_common.BRAND_LINE.startswith("Разработка от PriRex")
    assert BOOSTY_URL in report_common.BOOSTY_LINE
    assert report_common.BOOSTY_MARKDOWN.startswith("[Поддержать автора]")
