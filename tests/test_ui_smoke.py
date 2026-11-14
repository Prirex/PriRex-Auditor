"""Smoke-тесты UI: окно, отчёт, валидация URL и скриншоты (offscreen)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    # Offscreen-плагин Qt не видит системные шрифты, если не указать каталог:
    # без этого кириллица превращается в «квадратики» на скриншотах.
    os.environ.setdefault(
        "QT_QPA_FONTDIR",
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
    )

from datetime import datetime, timezone
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from app.core.models import (
    Category,
    CheckResult,
    CheckStatus,
    Evidence,
    Report,
    Severity,
)
from app.ui.branding import BrandFooter
from app.ui.main_window import MainWindow
from app.ui.theme import apply_theme, score_level

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / ".outputs"


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["prirex-ui-tests"])
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)
    return app


@pytest.fixture
def window(qapp):
    win = MainWindow()
    # В тестах не дёргаем сеть проверки обновлений.
    win._update_timer.stop()
    win.show_na_check.setChecked(True)
    win.show()
    qapp.processEvents()
    yield win
    win.close()
    qapp.processEvents()


# ---------------------------------------------------------------------------
# Синтетический отчёт: все статусы, группы, evidence
# ---------------------------------------------------------------------------
def make_synthetic_report() -> Report:
    results = [
        CheckResult(
            check_id="a01_https",
            title="HTTPS и TLS",
            category=Category.FZ152.value,
            status=CheckStatus.PASS,
            severity=Severity.CRITICAL,
            weight=3,
            message="Сайт открывается по https, сертификат валиден.",
            duration_ms=120,
        ),
        CheckResult(
            check_id="a02_privacy_link",
            title="Политика конфиденциальности — наличие",
            category=Category.FZ152.value,
            status=CheckStatus.PASS,
            severity=Severity.IMPORTANT,
            weight=3,
            message="Ссылка на политику найдена в футере.",
            evidence=[
                Evidence(
                    kind="url",
                    label="Ссылка",
                    value="https://example.com/privacy",
                )
            ],
        ),
        CheckResult(
            check_id="a04_privacy_content",
            title="Политика — содержание",
            category=Category.FZ152.value,
            status=CheckStatus.WARN,
            severity=Severity.IMPORTANT,
            weight=2,
            message="Найдено 4 из 7 маркеров содержательной политики.",
            recommendation="Добавьте разделы о целях обработки и сроках хранения.",
            evidence=[
                Evidence(
                    kind="text",
                    label="Не найдено",
                    value="срок хранения, отзыв согласия",
                )
            ],
        ),
        CheckResult(
            check_id="a11_privacy_contact",
            title="Контакт для обращений субъектов ПДн",
            category=Category.FZ152.value,
            status=CheckStatus.SKIP,
            severity=Severity.INFO,
            weight=1,
            message="Страница контактов не загрузилась — проверить не удалось.",
            error="timeout",
        ),
        CheckResult(
            check_id="b13_seller_details",
            title="Реквизиты продавца",
            category=Category.ZOZPP.value,
            status=CheckStatus.FAIL,
            severity=Severity.CRITICAL,
            weight=3,
            message="На сайте есть признаки продаж, но реквизиты продавца не найдены.",
            recommendation="Разместите полное наименование, ОГРН/ОГРНИП, адрес и контакты в футере.",
            evidence=[
                Evidence(
                    kind="selector",
                    label="Кнопка «Купить»",
                    value="Купить",
                    selector="main .product .buy",
                ),
                Evidence(
                    kind="text",
                    label="Футер",
                    value="© 2026 Ромашка",
                ),
            ],
        ),
        CheckResult(
            check_id="c14_erid",
            title="Маркировка интернет-рекламы (ERID)",
            category=Category.AD.value,
            status=CheckStatus.NOT_APPLICABLE,
            severity=Severity.INFO,
            weight=1,
            message=(
                "На странице не обнаружены рекламные блоки. "
                "Маркировка ERID не требуется."
            ),
        ),
        CheckResult(
            check_id="c15_ad_consent",
            title="Согласие на рекламную рассылку",
            category=Category.AD.value,
            status=CheckStatus.NOT_APPLICABLE,
            severity=Severity.INFO,
            weight=1,
            message=(
                "На сайте не обнаружены формы подписки на рассылку. "
                "Отдельное согласие на рекламу не требуется."
            ),
        ),
        CheckResult(
            check_id="d16_robots",
            title="robots.txt",
            category=Category.TECH.value,
            status=CheckStatus.PASS,
            severity=Severity.RECOMMENDATION,
            weight=1,
            message="robots.txt доступен.",
            evidence=[
                Evidence(
                    kind="url",
                    label="Адрес",
                    value="https://example.com/robots.txt",
                )
            ],
        ),
    ]
    return Report(
        url="https://example.com/",
        final_url="https://example.com/",
        scanned_at=datetime.now(timezone.utc),
        score=72,
        results=results,
        deep_analysis=False,
        app_version="1.0.0",
        duration_ms=8200,
        notes=["Playwright недоступен: динамические проверки выполнены через HTTP."],
    )


def _iter_tree_items(item):
    """Все потомки пункта дерева (блок → подраздел → проверка)."""
    for index in range(item.childCount()):
        child = item.child(index)
        yield child
        yield from _iter_tree_items(child)


def _find_item(tree, title: str):
    for index in range(tree.topLevelItemCount()):
        group = tree.topLevelItem(index)
        for child in _iter_tree_items(group):
            if child.text(0) == title:
                return child
    return None


def _count_check_items(tree) -> int:
    """Число проверок: только листья глубины «подраздел → проверка»."""
    total = 0
    for index in range(tree.topLevelItemCount()):
        group = tree.topLevelItem(index)
        for section_index in range(group.childCount()):
            total += group.child(section_index).childCount()
    return total


# ---------------------------------------------------------------------------
# Тесты
# ---------------------------------------------------------------------------
def test_main_window_creates(window):
    assert "PriRex Auditor" in window.windowTitle()
    assert isinstance(window.footer, BrandFooter)
    assert window.footer.isHidden() is False
    assert "—" in window.results_view.score_value.text()
    assert window.export_pdf_button.isEnabled() is False
    assert window.conclusion_button.isEnabled() is False
    assert window.export_md_action.isEnabled() is False
    assert window.copy_link_action.isEnabled() is False


def test_show_report_fills_tree_and_sections(window, qapp):
    report = make_synthetic_report()
    window.show_report(report)
    qapp.processEvents()

    view = window.results_view
    assert view.report is report
    assert view.score_value.text() == f"{report.score}%"
    assert view.score_value.property("level") == score_level(report.score)

    groups = report.grouped()
    assert view.check_tree.topLevelItemCount() == len(groups)
    assert _count_check_items(view.check_tree) == len(report.results)

    assert len(view.na_rows) == len(report.not_applicable())
    assert len(view.skip_rows) == len(report.skipped())
    assert view.na_section.isVisible()
    assert view.skip_section.isVisible()

    view.set_na_visible(False)
    assert view.na_section.isVisible() is False
    window.show_na_check.setChecked(False)
    assert view.na_section.isVisible() is False
    window.show_na_check.setChecked(True)
    assert view.na_section.isVisible()

    assert window.export_pdf_button.isEnabled()
    assert window.conclusion_button.isEnabled()
    assert window.export_md_action.isEnabled()
    assert window.copy_link_action.isEnabled()
    assert "проверок" in window.result_hint.text()

    fail_result = next(
        result for result in report.results if result.status is CheckStatus.FAIL
    )
    fail_item = _find_item(view.check_tree, fail_result.title)
    assert fail_item is not None
    view.check_tree.setCurrentItem(fail_item)
    qapp.processEvents()
    assert window.details_panel.current_result is fail_result
    detail_titles = [
        label.text()
        for label in window.details_panel.findChildren(type(window.result_hint))
        if label.objectName() == "DetailTitle"
    ]
    assert fail_result.title in detail_titles


def test_invalid_url_does_not_start_worker(window, qapp):
    window.url_input.setText("не сайт")
    window.check_button.click()
    qapp.processEvents()
    assert window._worker is None
    first_error = window.progress_label.text()
    assert first_error.strip()
    assert "пробел" in first_error.lower() or "адрес" in first_error.lower()

    window.url_input.setText("ftp://x\\y")
    window.check_button.click()
    qapp.processEvents()
    assert window._worker is None
    second_error = window.progress_label.text()
    assert second_error.strip()
    assert "http" in second_error.lower() or "адрес" in second_error.lower()
    assert window.results_view.check_tree.topLevelItemCount() == 0


def test_screenshots(qapp):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    report_window = MainWindow()
    report_window._update_timer.stop()
    report_window.show_na_check.setChecked(True)
    report_window.resize(1200, 780)
    report_window.show()
    qapp.processEvents()
    report_window.show_report(make_synthetic_report())
    qapp.processEvents()
    qapp.processEvents()
    assert report_window.size().width() == 1200
    assert report_window.size().height() == 780
    main_pixmap = report_window.grab()
    assert main_pixmap.isNull() is False
    assert main_pixmap.save(str(OUTPUT_DIR / "ui-main.png")) is True
    report_window.close()
    qapp.processEvents()

    empty_window = MainWindow()
    empty_window._update_timer.stop()
    empty_window.resize(1200, 780)
    empty_window.show()
    qapp.processEvents()
    empty_pixmap = empty_window.grab()
    assert empty_pixmap.isNull() is False
    assert empty_pixmap.save(str(OUTPUT_DIR / "ui-empty.png")) is True
    empty_window.close()
    qapp.processEvents()

    assert (OUTPUT_DIR / "ui-main.png").stat().st_size > 0
    assert (OUTPUT_DIR / "ui-empty.png").stat().st_size > 0
