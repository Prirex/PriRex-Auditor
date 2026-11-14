"""UI-тесты второго этапа: тулбар, подразделы, N/A-секция, заключение.

Все тесты работают в offscreen-режиме (как ``tests/test_ui_smoke.py``),
поэтому не требуют реального дисплея и не ходят в сеть.
"""

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
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from app.core.models import (
    Category,
    CheckResult,
    CheckStatus,
    Report,
    Severity,
)
from app.ui.conclusion_dialog import ConclusionDialog
from app.ui.main_window import MainWindow
from app.ui.theme import apply_theme
from app.version import __version__

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / ".outputs"

#: Длинное пояснение N/A: проверяем, что оно не обрезается и переносится.
NA_MESSAGE = (
    "На странице не обнаружены рекламные блоки, поэтому обязательная "
    "маркировка интернет-рекламы (ERID) не требуется — проверка не влияет "
    "на процент соответствия."
)


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["prirex-ui-v2-tests"])
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
# Синтетический отчёт: ровно 10 проверок, все статусы, оба подраздела
# ---------------------------------------------------------------------------
def make_report() -> Report:
    results = [
        CheckResult(
            check_id="a01_https",
            title="HTTPS и TLS",
            category=Category.FZ152.value,
            status=CheckStatus.PASS,
            severity=Severity.CRITICAL,
            weight=3,
            message="Сайт открывается по https, сертификат валиден.",
        ),
        CheckResult(
            check_id="a02_privacy_link",
            title="Политика конфиденциальности — наличие",
            category=Category.FZ152.value,
            status=CheckStatus.PASS,
            severity=Severity.IMPORTANT,
            weight=3,
            message="Ссылка на политику найдена в футере.",
        ),
        CheckResult(
            check_id="a03_privacy_access",
            title="Политика — доступность",
            category=Category.FZ152.value,
            status=CheckStatus.PASS,
            severity=Severity.IMPORTANT,
            weight=2,
            message="Страница политики открывается без авторизации.",
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
        ),
        CheckResult(
            check_id="a05_forms_consent",
            title="Согласие в формах",
            category=Category.FZ152.value,
            status=CheckStatus.FAIL,
            severity=Severity.CRITICAL,
            weight=3,
            message="В форме заявки нет чекбокса согласия на обработку ПДн.",
            recommendation="Добавьте обязательный чекбокс согласия.",
        ),
        CheckResult(
            check_id="a06_consent_prechecked",
            title="Согласие не предустановлено",
            category=Category.FZ152.value,
            status=CheckStatus.PASS,
            severity=Severity.IMPORTANT,
            weight=2,
            message="Чекбоксы не отмечены заранее.",
        ),
        CheckResult(
            check_id="a11_pdn_contact",
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
            message=(
                "На сайте есть признаки продаж, но реквизиты продавца "
                "не найдены."
            ),
            recommendation=(
                "Разместите полное наименование, ОГРН/ОГРНИП, адрес и "
                "контакты в футере."
            ),
        ),
        CheckResult(
            check_id="c14_erid",
            title="Маркировка интернет-рекламы (ERID)",
            category=Category.AD.value,
            status=CheckStatus.NOT_APPLICABLE,
            severity=Severity.INFO,
            weight=1,
            message=NA_MESSAGE,
        ),
        CheckResult(
            check_id="d17_security_headers",
            title="Заголовки безопасности",
            category=Category.TECH.value,
            status=CheckStatus.WARN,
            severity=Severity.RECOMMENDATION,
            weight=2,
            message="Не найдены заголовки X-Frame-Options и CSP.",
            recommendation="Добавьте X-Frame-Options и Content-Security-Policy.",
        ),
    ]
    return Report(
        url="https://example.com/",
        final_url="https://example.com/",
        scanned_at=datetime.now(timezone.utc),
        score=68,
        results=results,
        app_version="1.0.0",
        duration_ms=8200,
        notes=["Playwright недоступен: динамические проверки выполнены через HTTP."],
    )


def _iter_tree_items(item):
    for index in range(item.childCount()):
        child = item.child(index)
        yield child
        yield from _iter_tree_items(child)


def _section_titles(tree) -> list[str]:
    titles: list[str] = []
    for index in range(tree.topLevelItemCount()):
        group = tree.topLevelItem(index)
        for child_index in range(group.childCount()):
            titles.append(group.child(child_index).text(0))
    return titles


def _find_check_item_by_title(tree, title: str):
    for index in range(tree.topLevelItemCount()):
        group = tree.topLevelItem(index)
        for child in _iter_tree_items(group):
            if child.childCount() == 0 and child.text(0) == title:
                return child
    return None


# ---------------------------------------------------------------------------
# 1. Тулбар и кнопки
# ---------------------------------------------------------------------------
def test_toolbar_has_version_and_update_button(window):
    assert window.version_label.objectName() == "VersionLabel"
    assert window.version_label.text().startswith(f"Версия {__version__}")
    assert window.toolbar.height() == 36
    assert window.toolbar.isVisible()

    assert window.update_button.objectName() == "GhostButton"
    assert window.update_button.text() == "Проверить обновление"
    assert window.update_button.isEnabled()

    assert window.how_it_works_button.objectName() == "howItWorksButton"
    assert "Как работает приложение" in window.how_it_works_button.text()
    assert window.how_it_works_button.icon().isNull() is False


def test_methodology_button_next_to_url(window, qapp):
    qapp.processEvents()
    assert window.methodology_button.objectName() == "methodologyButton"
    assert window.methodology_button.text() == "Критерии проверок"
    # Кнопка живёт в той же строке, что поле URL и «Проверить», справа от неё.
    assert window.input_card.isAncestorOf(window.methodology_button)
    check_geometry = window.check_button.geometry()
    methodology_geometry = window.methodology_button.geometry()
    assert abs(
        check_geometry.center().y() - methodology_geometry.center().y()
    ) <= 2
    assert methodology_geometry.left() > check_geometry.left()

    assert window.methodology_action.shortcut().toString() == "F1"
    assert window.methodology_action.text() == "Критерии проверок"
    assert window.boosty_action.text() == "Поддержать автора"


def test_window_defaults_and_splitter(window, qapp):
    qapp.processEvents()
    assert window.minimumWidth() == 1100
    assert window.minimumHeight() == 720
    assert window.size().width() >= 1100
    assert window.size().height() >= 720
    assert window.details_panel.minimumWidth() == 360
    sizes = window.splitter.sizes()
    assert abs(sizes[0] - 820) <= 12
    assert abs(sizes[1] - 420) <= 12


# ---------------------------------------------------------------------------
# 2. Подразделы дерева, N/A-секция, нижняя панель
# ---------------------------------------------------------------------------
def test_sections_and_na_rows(window, qapp):
    report = make_report()
    assert len(report.results) == 10
    window.show_report(report)
    qapp.processEvents()

    view = window.results_view
    tree = view.check_tree
    assert tree.topLevelItemCount() == len(report.grouped_by_section())

    section_titles = _section_titles(tree)
    assert "Наличие и формальности" in section_titles
    assert "Содержание и полнота" in section_titles
    # В каждом блоке — подразделы, а не сразу проверки.
    assert tree.topLevelItem(0).child(0).childCount() >= 1

    # Заголовки подразделов не выбираются мышью и набраны мельче проверок.
    first_section = tree.topLevelItem(0).child(0)
    assert not bool(
        first_section.flags() & Qt.ItemFlag.ItemIsSelectable
    )
    section_font = first_section.font(0)
    tree_font = tree.font()
    if section_font.pointSizeF() > 0 and tree_font.pointSizeF() > 0:
        assert section_font.pointSizeF() < tree_font.pointSizeF()
    else:
        assert section_font.pixelSize() < tree_font.pixelSize()

    # N/A-секция: строки-карточки, полный текст с переносом.
    na_results = report.not_applicable()
    assert len(view.na_rows) == len(na_results) == 1
    assert len(view.skip_rows) == len(report.skipped()) == 1
    for row, result in zip(view.na_rows, na_results):
        assert row.result is result
        assert row.message_label.wordWrap() is True
        assert row.message_label.text() == result.message
        assert row.message_label.text().strip()
        assert row.title_label.text() == result.title
        assert row.size().height() > 0
        # Пояснение не обрезано: высоты хватает на все строки при текущей ширине.
        needed = row.message_label.heightForWidth(row.message_label.width())
        assert row.message_label.height() >= needed
    # N/A раскрыта автоматически, skip — свёрнут.
    assert view.na_toggle.isChecked() is True
    assert view.na_toggle.text().endswith("1")
    assert view.na_section.scroll.isVisible() is True
    assert view.skip_toggle.isChecked() is False
    assert view.skip_section.scroll.isVisible() is False

    # Нижняя панель: только PDF + «Заключение».
    bar_texts = [
        button.text()
        for button in window.bottom_bar.findChildren(QPushButton)
    ]
    assert "Экспорт в PDF" in bar_texts
    assert "Заключение" in bar_texts
    assert "Экспорт в Markdown" not in bar_texts
    assert "Копировать ссылку на отчёт" not in bar_texts
    # Функциональность сохранена в меню «Файл».
    assert "Markdown" in window.export_md_action.text()
    assert window.export_md_action.isEnabled()
    assert window.copy_link_action.isEnabled()


def test_na_row_click_shows_details(window, qapp):
    report = make_report()
    window.show_report(report)
    qapp.processEvents()

    na_result = report.not_applicable()[0]
    view = window.results_view
    row = view.na_rows[0]
    QTest.mouseClick(row, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert window.details_panel.current_result is na_result


def test_detail_methodology_link_and_double_click(window, qapp):
    report = make_report()
    window.show_report(report)
    qapp.processEvents()

    warn_result = next(
        result for result in report.results if result.status is CheckStatus.WARN
    )
    window.details_panel.show_result(warn_result)
    qapp.processEvents()

    links = [
        button
        for button in window.details_panel.findChildren(QPushButton)
        if "Критерии проверок" in button.text()
    ]
    assert links, "в панели деталей нет ссылки на «Критерии проверок»"

    emitted: list[str] = []
    view = window.results_view
    view.methodology_check_requested.connect(emitted.append)
    item = _find_check_item_by_title(tree=view.check_tree, title=warn_result.title)
    assert item is not None
    view._on_tree_item_double_clicked(item, 0)
    assert emitted == [warn_result.check_id]


# ---------------------------------------------------------------------------
# 3. Заключение
# ---------------------------------------------------------------------------
def test_conclusion_dialog_lists_only_problems(qapp):
    report = make_report()
    dialog = ConclusionDialog(report)
    dialog.show()
    qapp.processEvents()
    try:
        problem_ids = {
            result.check_id
            for result in report.results
            if result.status in (CheckStatus.FAIL, CheckStatus.WARN)
        }
        item_ids = {result.check_id for result, _lost in dialog.items}
        assert item_ids == problem_ids
        assert len(dialog.item_frames) == len(problem_ids)

        titles = [
            label.text()
            for label in dialog.findChildren(QLabel)
            if label.objectName() == "ConclusionItemTitle"
        ]
        assert any("Реквизиты продавца" in title for title in titles)

        hints = [
            label.text()
            for label in dialog.findChildren(QLabel)
            if label.objectName() == "ConclusionHint"
        ]
        assert hints and f"{report.score}%" in hints[0]

        # Копирование плана в буфер обмена.
        QGuiApplication.clipboard().clear()
        dialog.copy_button.click()
        qapp.processEvents()
        copied = QGuiApplication.clipboard().text()
        assert copied.strip()
        assert copied.startswith("- [ ] ")
        assert "Реквизиты продавца" in copied
        assert "(Критично)" in copied
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


def test_conclusion_dialog_perfect_score(qapp):
    report = make_report()
    report.score = 100
    dialog = ConclusionDialog(report)
    try:
        dialog.show()
        qapp.processEvents()
        assert dialog.items == []
        info = [
            label
            for label in dialog.findChildren(QLabel)
            if label.objectName() == "InfoBody"
        ]
        assert info
        assert "Все применимые проверки пройдены" in info[0].text()
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


def test_conclusion_dialog_esc_and_non_modal(window, qapp):
    window.show_report(make_report())
    qapp.processEvents()

    standalone = ConclusionDialog(make_report())
    standalone.show()
    qapp.processEvents()
    assert standalone.isModal() is False
    QTest.keyClick(standalone, Qt.Key.Key_Escape)
    qapp.processEvents()
    assert standalone.isVisible() is False
    standalone.deleteLater()
    qapp.processEvents()

    window.open_conclusion()
    qapp.processEvents()
    opened = window._conclusion_dialog
    assert opened is not None
    assert opened.isModal() is False
    assert opened.isVisible() is True
    opened.close()
    qapp.processEvents()


# ---------------------------------------------------------------------------
# 4. Ручная проверка обновлений (без сети)
# ---------------------------------------------------------------------------
def test_manual_update_check_branches(window, monkeypatch):
    calls: list[object] = []
    monkeypatch.setattr(
        window, "_mark_update_checked", lambda: calls.append("marked")
    )
    monkeypatch.setattr(
        window,
        "_show_update_available_dialog",
        lambda info, latest: calls.append(("available", latest)),
    )
    monkeypatch.setattr(
        window, "_show_up_to_date_dialog", lambda: calls.append(("current",))
    )
    monkeypatch.setattr(
        window, "_show_update_error_dialog", lambda: calls.append(("error",))
    )

    class Info:
        available = True
        latest = "9.9.9"
        current = "1.0.0"
        url = "https://example.com/download"
        notes = ""

    window._on_manual_update_checked(Info())
    assert calls == ["marked", ("available", "9.9.9")]

    calls.clear()
    Info.available = False
    Info.latest = "1.0.0"
    window._on_manual_update_checked(Info())
    assert calls == ["marked", ("current",)]

    calls.clear()
    window._on_manual_update_checked(None)
    assert calls == ["marked", ("error",)]


def test_manual_update_check_runs_in_background(window, monkeypatch, qapp):
    """``check_updates_manual`` берёт результат из подменённого апдейтера."""
    import app.updater as updater_module
    from app.updater import UpdateInfo

    def fake_sync(config, current_version):
        return UpdateInfo(
            available=False,
            current=str(current_version),
            latest=str(current_version),
            url="",
        )

    monkeypatch.setattr(
        updater_module, "check_for_updates_sync", fake_sync
    )
    monkeypatch.setattr(window, "_mark_update_checked", lambda: None)

    seen: list[object] = []
    monkeypatch.setattr(
        window, "_on_manual_update_checked", lambda info: seen.append(info)
    )

    window.check_updates_manual()
    assert window._update_worker is not None
    assert window.update_button.isEnabled() is False

    worker = window._update_worker
    assert worker.wait(5000) is True
    for _ in range(20):
        qapp.processEvents()
    assert seen, "сигнал ручной проверки не дошёл"
    assert seen[0] is not None
    assert window.update_button.isEnabled() is True


def test_mark_update_checked_saves_config(window, monkeypatch):
    import app.ui.main_window as main_window_module

    class FakeConfig:
        marked = False

        def mark_update_checked(self) -> None:
            self.marked = True

    class FakeManager:
        def __init__(self) -> None:
            self.config = FakeConfig()
            self.saved = False

        def save(self) -> None:
            self.saved = True

    manager = FakeManager()
    monkeypatch.setattr(
        main_window_module, "get_config_manager", lambda: manager
    )
    window._mark_update_checked()
    assert manager.config.marked is True
    assert manager.saved is True


# ---------------------------------------------------------------------------
# 5. Пустое состояние и скриншоты
# ---------------------------------------------------------------------------
def test_empty_state_disables_export(window):
    assert window._report is None
    assert window.export_pdf_button.isEnabled() is False
    assert window.conclusion_button.isEnabled() is False
    assert window.export_pdf_action.isEnabled() is False
    assert window.export_md_action.isEnabled() is False
    assert window.copy_link_action.isEnabled() is False


def test_screenshots_v2(qapp):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    win = MainWindow()
    win._update_timer.stop()
    win.show_na_check.setChecked(True)
    win.resize(1280, 800)
    win.show()
    qapp.processEvents()
    win.show_report(make_report())
    for _ in range(3):
        qapp.processEvents()

    main_pixmap = win.grab()
    assert main_pixmap.isNull() is False
    assert main_pixmap.save(str(OUTPUT_DIR / "ui-v2-main.png")) is True

    # Секция N/A целиком: видно полное пояснение причины.
    na_widget = win.results_view.na_section
    na_pixmap = na_widget.grab()
    assert na_pixmap.isNull() is False
    assert na_pixmap.save(str(OUTPUT_DIR / "ui-v2-na.png")) is True

    dialog = ConclusionDialog(win._report, win)
    dialog.show()
    for _ in range(3):
        qapp.processEvents()
    conclusion_pixmap = dialog.grab()
    assert conclusion_pixmap.isNull() is False
    assert conclusion_pixmap.save(
        str(OUTPUT_DIR / "ui-v2-conclusion.png")
    ) is True

    dialog.close()
    win.close()
    qapp.processEvents()

    assert (OUTPUT_DIR / "ui-v2-main.png").stat().st_size > 0
    assert (OUTPUT_DIR / "ui-v2-na.png").stat().st_size > 0
    assert (OUTPUT_DIR / "ui-v2-conclusion.png").stat().st_size > 0
