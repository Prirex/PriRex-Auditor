"""UI-тесты третьего этапа: блоки «Как исправить», штрафы, точки статусов.

Проверяем три правки по замечаниям заказчика:

* окно «Заключение» — исправление отдельным салатовым блоком
  ``QLabel#DetailRecommendation``, а не серой строкой;
* панель деталей — блок «ПОТЕНЦИАЛЬНАЯ СУММА ШТРАФА» по методологии;
* дерево проверок — маленькие цветные точки статусов и цветной полужирный
  текст колонки «Статус».

Все тесты работают в offscreen-режиме (как ``tests/test_ui_v2.py``),
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
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QFont, QGuiApplication
from PySide6.QtWidgets import QApplication, QFrame, QLabel

import app.core.content.loader as loader_module
from app.core.content.models import MethodologyCheck
from app.core.models import (
    Category,
    CheckResult,
    CheckStatus,
    Report,
    Severity,
)
from app.ui.conclusion_dialog import ConclusionDialog
from app.ui.main_window import MainWindow
from app.ui.results_view import STATUS_DOT_SIZE, DetailPanel
from app.ui.theme import STATUS_COLORS, apply_theme, load_stylesheet

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / ".outputs"


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["prirex-ui-v3-tests"])
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
# Синтетический отчёт: пройдено/замечание/нарушение/N/A/skip
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
            message="Реквизиты продавца не найдены.",
            recommendation=(
                "Разместите полное наименование, ОГРН/ОГРНИП, адрес и "
                "контакты в футере."
            ),
        ),
        CheckResult(
            # Проблемная проверка без рекомендации: салатового блока быть не
            # должно, а в «Копировать план» попадает сообщение.
            check_id="d17_security_headers",
            title="Заголовки безопасности",
            category=Category.TECH.value,
            status=CheckStatus.WARN,
            severity=Severity.RECOMMENDATION,
            weight=1,
            message="Не найдены заголовки X-Frame-Options и CSP.",
        ),
        CheckResult(
            check_id="c14_erid",
            title="Маркировка интернет-рекламы (ERID)",
            category=Category.AD.value,
            status=CheckStatus.NOT_APPLICABLE,
            severity=Severity.INFO,
            weight=1,
            message=(
                "На странице не обнаружены рекламные блоки — маркировка "
                "ERID не требуется, проверка не влияет на оценку."
            ),
        ),
    ]
    return Report(
        url="https://example.com/",
        final_url="https://example.com/",
        scanned_at=datetime.now(timezone.utc),
        score=62,
        results=results,
        app_version="1.0.0",
        duration_ms=8200,
    )


def _fines_methodology(**overrides: str) -> MethodologyCheck:
    """Методология проверки с заполненными штрафами (JSON ещё может пустеть)."""
    data: dict[str, str] = {
        "id": "4.5",
        "check_id": "a05_forms_consent",
        "title": "Формы сбора данных и чекбокс согласия",
        "fine_individual": "от 6 000 до 10 000 ₽",
        "fine_legal": "от 60 000 до 100 000 ₽",
        "fine_basis": "ч. 1 ст. 13.11 КоАП РФ",
        "fine_note": "Оценка ориентировочная: итоговый размер определяет суд.",
    }
    data.update(overrides)
    return MethodologyCheck(**data)


def _patch_methodology(monkeypatch, value) -> None:
    """Подменяет поиск методологии (results_view импортирует его лениво)."""
    monkeypatch.setattr(
        loader_module, "methodology_for", lambda _check_id: value
    )


def _result_by_id(check_id: str) -> CheckResult:
    return next(result for result in make_report().results if result.check_id == check_id)


def _iter_check_items(tree):
    """Все листья дерева (блок → подраздел → проверка)."""
    for group_index in range(tree.topLevelItemCount()):
        group = tree.topLevelItem(group_index)
        for section_index in range(group.childCount()):
            section = group.child(section_index)
            for check_index in range(section.childCount()):
                yield section.child(check_index)


def _find_check_item(tree, title: str):
    for item in _iter_check_items(tree):
        if item.text(0) == title:
            return item
    return None


def _fines_headers(panel: DetailPanel) -> list[QLabel]:
    return [
        label
        for label in panel.findChildren(QLabel)
        if label.objectName() == "InfoSectionLabel"
        and "ПОТЕНЦИАЛЬНАЯ СУММА ШТРАФА" in label.text()
    ]


def _dot_center_color(pixmap) -> QColor:
    image = pixmap.toImage()
    return image.pixelColor(image.width() // 2, image.height() // 2)


# ---------------------------------------------------------------------------
# 1. Окно «Заключение»: исправление — салатовым блоком
# ---------------------------------------------------------------------------
def test_conclusion_recommendation_blocks(qapp):
    report = make_report()
    dialog = ConclusionDialog(report)
    dialog.show()
    qapp.processEvents()
    try:
        fixes = [
            label
            for label in dialog.findChildren(QLabel)
            if label.objectName() == "DetailRecommendation"
        ]
        expected = [
            result
            for result, _lost in dialog.items
            if (result.recommendation or "").strip()
        ]
        assert len(fixes) == len(expected)
        assert fixes, "в заключении нет салатовых блоков исправления"
        for label in fixes:
            assert label.text().startswith("Как исправить:")
            assert label.wordWrap() is True

        # У проблемной проверки без рекомендации блока нет.
        checked_without = 0
        for (result, _lost), frame in zip(dialog.items, dialog.item_frames):
            blocks = [
                label
                for label in frame.findChildren(QLabel)
                if label.objectName() == "DetailRecommendation"
            ]
            if (result.recommendation or "").strip():
                assert len(blocks) == 1
                assert blocks[0].parent() is frame
            else:
                checked_without += 1
                assert blocks == []
        assert checked_without >= 1, "в отчёте нет проблемы без рекомендации"

        # Сообщение больше не повторяет «Как исправить» серым текстом.
        item_texts = [
            label.text()
            for label in dialog.findChildren(QLabel)
            if label.objectName() == "ConclusionItemText"
        ]
        assert item_texts
        assert all("Как исправить" not in text for text in item_texts)

        # «Копировать план» тоже содержит «Как исправить: …».
        QGuiApplication.clipboard().clear()
        dialog.copy_button.click()
        qapp.processEvents()
        copied = QGuiApplication.clipboard().text()
        assert copied.startswith("- [ ] ")
        assert "Как исправить:" in copied
        assert "Добавьте обязательный чекбокс согласия." in copied
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()


# ---------------------------------------------------------------------------
# 2. Панель деталей: блок «ПОТЕНЦИАЛЬНАЯ СУММА ШТРАФА»
# ---------------------------------------------------------------------------
def test_detail_panel_fines_block(qapp, monkeypatch):
    _patch_methodology(monkeypatch, _fines_methodology())
    panel = DetailPanel()
    panel.resize(420, 720)
    panel.show()
    panel.show_result(_result_by_id("a05_forms_consent"))
    qapp.processEvents()
    try:
        headers = _fines_headers(panel)
        assert len(headers) == 1
        assert headers[0].text() == "ПОТЕНЦИАЛЬНАЯ СУММА ШТРАФА"

        frames = [
            frame
            for frame in panel.findChildren(QFrame)
            if frame.objectName() == "ConclusionItem"
        ]
        assert frames, "контейнер блока штрафа не создан"
        frame = frames[0]
        texts = [
            label.text() for label in frame.findChildren(QLabel)
        ]
        joined = "\n".join(texts)
        assert "Для физлица" in joined
        assert "от 6 000 до 10 000 ₽" in joined
        assert "Для юрлица" in joined
        assert "от 60 000 до 100 000 ₽" in joined
        # Основание и примечание — отдельными строками.
        assert any(
            "Основание: ч. 1 ст. 13.11 КоАП РФ" in text for text in texts
        )
        assert "Оценка ориентировочная" in joined
        # Сумма выделена цветом #B87A6E и полужирным.
        lowered = joined.lower()
        assert STATUS_COLORS["fail"].lower() in lowered
        assert "font-weight:600" in lowered
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_detail_panel_hides_fines_without_amounts(qapp, monkeypatch):
    _patch_methodology(
        monkeypatch,
        _fines_methodology(
            fine_individual="",
            fine_legal="",
            fine_basis="",
            fine_note="",
        ),
    )
    panel = DetailPanel()
    panel.show_result(_result_by_id("a05_forms_consent"))
    qapp.processEvents()
    try:
        assert not _fines_headers(panel)
        assert not [
            frame
            for frame in panel.findChildren(QFrame)
            if frame.objectName() == "ConclusionItem"
        ]
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_detail_panel_survives_missing_methodology(qapp, monkeypatch):
    _patch_methodology(monkeypatch, None)
    result = _result_by_id("a05_forms_consent")
    panel = DetailPanel()
    panel.show_result(result)
    qapp.processEvents()
    try:
        assert panel.current_result is result
        assert not _fines_headers(panel)
        # Панель всё равно показывает детали проверки, а не падает.
        titles = [
            label.text()
            for label in panel.findChildren(QLabel)
            if label.objectName() == "DetailTitle"
        ]
        assert titles == [result.title]
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


# ---------------------------------------------------------------------------
# 3. Дерево проверок: точки статусов + цветная полужирная колонка
# ---------------------------------------------------------------------------
def test_tree_uses_status_dots_and_colored_status(window, qapp):
    report = make_report()
    window.show_report(report)
    qapp.processEvents()

    tree = window.results_view.check_tree
    # Точки не растягиваются: у дерева фиксированный iconSize 10×10.
    assert tree.iconSize() == QSize(STATUS_DOT_SIZE, STATUS_DOT_SIZE)

    items = list(_iter_check_items(tree))
    assert len(items) == len(report.results)
    results_by_title = {result.title: result for result in report.results}

    for item in items:
        result = results_by_title[item.text(0)]
        expected = QColor(STATUS_COLORS[result.status.value])

        icon = item.icon(0)
        assert not icon.isNull(), "у проверки нет иконки статуса"
        pixmap = icon.pixmap(STATUS_DOT_SIZE, STATUS_DOT_SIZE)
        assert not pixmap.isNull()
        assert pixmap.size() == QSize(STATUS_DOT_SIZE, STATUS_DOT_SIZE)
        assert _dot_center_color(pixmap).name() == expected.name()

        # Правая колонка: статус цветом и полужирным.
        assert item.text(1) == result.status.label_ru
        assert item.foreground(1).color().name() == expected.name()
        assert int(item.font(1).weight()) == int(QFont.Weight.DemiBold)

    # N/A — тёплый оранжевый в STATUS_COLORS.
    na_result = report.not_applicable()[0]
    na_item = _find_check_item(tree, na_result.title)
    assert na_item is not None
    assert (
        na_item.foreground(1).color().name()
        == QColor(STATUS_COLORS["not_applicable"]).name()
    )

    # Строки секций N/A — тоже маленькая точка.
    assert window.results_view.na_rows
    na_row = window.results_view.na_rows[0]
    row_pixmap = na_row.icon_label.pixmap()
    assert not row_pixmap.isNull()
    assert row_pixmap.size() == QSize(STATUS_DOT_SIZE, STATUS_DOT_SIZE)
    assert (
        _dot_center_color(row_pixmap).name()
        == QColor(STATUS_COLORS["not_applicable"]).name()
    )

    # Точка у заголовка секции «Не удалось проверить» (skip — серо-голубой).
    skip_toggle = window.results_view.skip_toggle
    assert skip_toggle.iconSize() == QSize(STATUS_DOT_SIZE, STATUS_DOT_SIZE)
    skip_icon = skip_toggle.icon()
    assert not skip_icon.isNull()
    skip_pixmap = skip_icon.pixmap(STATUS_DOT_SIZE, STATUS_DOT_SIZE)
    assert skip_pixmap.size() == QSize(STATUS_DOT_SIZE, STATUS_DOT_SIZE)
    assert (
        _dot_center_color(skip_pixmap).name()
        == QColor(STATUS_COLORS["skip"]).name()
    )

    # Баг «трёх полосок» лечится QSS: правил QTreeView::branch нет.
    assert "QTreeView::branch" not in load_stylesheet()


# ---------------------------------------------------------------------------
# 4. Скриншоты
# ---------------------------------------------------------------------------
def test_screenshots_v3(qapp, monkeypatch):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # JSON методологии может быть ещё не заполнен — подставляем тестовые
    # суммы для проверки со штрафом.
    fines = _fines_methodology()
    monkeypatch.setattr(
        loader_module,
        "methodology_for",
        lambda check_id: fines if check_id == "a05_forms_consent" else None,
    )

    win = MainWindow()
    win._update_timer.stop()
    win.show_na_check.setChecked(True)
    win.resize(1280, 830)
    win.show()
    qapp.processEvents()
    win.show_report(make_report())
    for _ in range(3):
        qapp.processEvents()

    # Выделяем строку проверки: полос при выделении быть не должно.
    item = _find_check_item(win.results_view.check_tree, "Согласие в формах")
    assert item is not None
    win.results_view.check_tree.setCurrentItem(item)
    win.results_view.check_tree.setFocus()
    for _ in range(3):
        qapp.processEvents()
    assert win.details_panel.current_result is not None
    assert win.details_panel.current_result.check_id == "a05_forms_consent"

    main_pixmap = win.grab()
    assert main_pixmap.isNull() is False
    assert main_pixmap.save(str(OUTPUT_DIR / "ui-v3-main.png")) is True

    detail_pixmap = win.details_panel.grab()
    assert detail_pixmap.isNull() is False
    assert detail_pixmap.save(str(OUTPUT_DIR / "ui-v3-detail.png")) is True

    dialog = ConclusionDialog(win._report, win)
    dialog.show()
    for _ in range(3):
        qapp.processEvents()
    conclusion_pixmap = dialog.grab()
    assert conclusion_pixmap.isNull() is False
    assert conclusion_pixmap.save(
        str(OUTPUT_DIR / "ui-v3-conclusion.png")
    ) is True

    dialog.close()
    win.close()
    qapp.processEvents()

    for name in (
        "ui-v3-main.png",
        "ui-v3-detail.png",
        "ui-v3-conclusion.png",
    ):
        assert (OUTPUT_DIR / name).stat().st_size > 0
