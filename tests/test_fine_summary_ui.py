"""Тесты карточки «Итого по сайту: возможные штрафы»."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault(
        "QT_QPA_FONTDIR",
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
    )

from datetime import datetime, timezone

import pytest
from PySide6.QtWidgets import QApplication

import app.ui.fine_summary as fine_summary_module
from app.core.engine.fines import FineRange, FineSummary
from app.core.models import CheckResult, CheckStatus, Report, Severity
from app.ui.fine_summary import FineSummaryCard
from app.ui.main_window import MainWindow
from app.ui.theme import apply_theme


@pytest.fixture(scope="module")
def qt_app():
    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    apply_theme(application)
    return application


def make_report() -> Report:
    results = [
        CheckResult(
            check_id="a02_privacy_link",
            title="Политика конфиденциальности — наличие",
            category="152fz",
            status=CheckStatus.FAIL,
            severity=Severity.CRITICAL,
        ),
        CheckResult(
            check_id="a01_https",
            title="HTTPS и TLS",
            category="152fz",
            status=CheckStatus.PASS,
            severity=Severity.INFO,
        ),
    ]
    return Report(
        url="https://lutik.ru/",
        final_url="https://lutik.ru/",
        scanned_at=datetime.now(timezone.utc),
        score=55,
        results=results,
    )


def test_card_hidden_without_report(qt_app) -> None:
    card = FineSummaryCard()
    assert card.summary is None
    assert card.isHidden()


def test_card_shows_totals(qt_app, monkeypatch) -> None:
    summary = FineSummary(
        individual=FineRange(11500, 18000),
        legal=FineRange(330000, 760000),
        checks=["Политика", "Формы", "Реквизиты"],
        without_fine=2,
    )
    monkeypatch.setattr(
        fine_summary_module, "site_fine_summary", lambda results: summary
    )
    card = FineSummaryCard()
    card.set_report(make_report())
    assert not card.isHidden()
    assert card.summary is summary
    assert "11 500" in card.individual_label.text()
    assert "18 000" in card.individual_label.text()
    assert "330 000" in card.legal_label.text()
    assert "760 000" in card.legal_label.text()
    assert "замечание" in card.note_label.text() or "замечания" in card.note_label.text()


def test_card_no_direct_fines(qt_app, monkeypatch) -> None:
    summary = FineSummary(checks=[], without_fine=3)
    monkeypatch.setattr(
        fine_summary_module, "site_fine_summary", lambda results: summary
    )
    card = FineSummaryCard()
    card.set_report(make_report())
    assert "не предусмотрен" in card.individual_label.text()
    assert "не предусмотрен" in card.legal_label.text()
    assert "не предусмотрено" in card.note_label.text()


def test_card_reset(qt_app) -> None:
    card = FineSummaryCard()
    card.set_report(make_report())
    card.set_report(None)
    assert card.summary is None
    assert card.isHidden()


def test_main_window_shows_summary(qt_app, monkeypatch) -> None:
    summary = FineSummary(
        individual=FineRange(1000, 2000),
        legal=FineRange(10000, 20000),
        checks=["Проверка"],
    )
    monkeypatch.setattr(
        fine_summary_module, "site_fine_summary", lambda results: summary
    )
    window = MainWindow()
    report = make_report()
    window.show_report(report, None)
    assert not window.fine_summary.isHidden()
    assert window.fine_summary.summary is summary
    assert "1 000" in window.fine_summary.individual_label.text()


def test_main_window_hides_summary_on_new_scan(qt_app, monkeypatch) -> None:
    monkeypatch.setattr(
        fine_summary_module,
        "site_fine_summary",
        lambda results: FineSummary(individual=FineRange(100, 200)),
    )
    window = MainWindow()
    window.show_report(make_report(), None)
    assert not window.fine_summary.isHidden()
    window.details_panel.clear()
    window.fine_summary.set_report(None)
    assert window.fine_summary.isHidden()
