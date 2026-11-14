"""Offscreen-тесты окон-справочников: «Критерии проверок» и «Как работает».

Данные подменяются на тестовые (JSON-файлы пишутся отдельно и в любой
момент могут отсутствовать), но окно обязано работать и без них.
Если реальные ``assets/methodology.json`` / ``assets/how_it_works.json``
уже существуют — дополнительно проверяется открытие на них.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    # Offscreen-плагин Qt не видит системные шрифты без явного каталога:
    # без этого кириллица превращается в «квадратики» на скриншотах.
    os.environ.setdefault(
        "QT_QPA_FONTDIR",
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
    )

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

import pytest

import app.ui.how_it_works_window as hiw_module
import app.ui.methodology_window as mw_module
from app.core.content import loader as content_loader
from app.core.content.models import (
    HowItWorks,
    HowItWorksSection,
    Methodology,
    MethodologyBlock,
    MethodologyCheck,
)
from app.paths import asset_path
from app.ui.theme import apply_theme


# ---------------------------------------------------------------------------
# Фикстуры и данные
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["prirex-content-windows-tests"])
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)
    return app


def sample_methodology() -> Methodology:
    """Две группы и три проверки — достаточно для дерева, поиска и контента."""
    block_a = MethodologyBlock(
        id="A",
        title="152-ФЗ (персональные данные)",
        checks=[
            MethodologyCheck(
                id="4.2",
                check_id="a02_privacy_link",
                title="Политика конфиденциальности — наличие",
                applicability="always",
                applicability_note="Применимо всегда",
                what=(
                    "Проверяется, есть ли на главной странице ссылка на "
                    "политику обработки персональных данных и ведёт ли она "
                    "на существующую страницу."
                ),
                legal_basis=["ч. 2 ст. 18.1 152-ФЗ"],
                violations=[
                    "Ссылки на политику нет в футере",
                    "Ссылка ведёт на 404",
                ],
                normal=[
                    "Ссылка «Политика конфиденциальности» в футере",
                    "Страница открывается без регистрации",
                ],
                recommendation=[
                    "Добавьте ссылку в футер каждой страницы",
                    "Проверьте, что ссылка не ведёт на 404",
                ],
            ),
            MethodologyCheck(
                id="4.3",
                check_id="a04_privacy_content",
                title="Политика — содержание",
                applicability="policy_loaded",
                applicability_note="Применимо, если политика найдена",
                what=(
                    "Проверяется, что в тексте политики есть обязательные "
                    "маркеры: цели обработки, сроки хранения, права субъекта."
                ),
                legal_basis=["ч. 1 ст. 18.1 152-ФЗ", "уточнить"],
                violations=["В политике нет сроков хранения данных"],
                normal=["Политика содержит все обязательные разделы"],
                recommendation=["Дополните политику недостающими разделами"],
            ),
        ],
    )
    block_b = MethodologyBlock(
        id="B",
        title="ЗоЗПП (защита прав потребителей)",
        checks=[
            MethodologyCheck(
                id="4.13",
                check_id="b13_seller_details",
                title="Реквизиты продавца",
                applicability="sales",
                applicability_note="Применимо при наличии продаж",
                what=(
                    "Проверяется, размещены ли на сайте полное наименование "
                    "продавца, ОГРН/ОГРНИП, адрес и контакты."
                ),
                legal_basis=["ст. 9 Закона о защите прав потребителей"],
                violations=[
                    "На сайте нет наименования продавца",
                    "Нет ОГРН/ОГРНИП в футере",
                ],
                normal=[
                    "Реквизиты указаны в футере или разделе «Контакты»",
                ],
                not_applicable_note="Сайт не продаёт товары и услуги.",
                recommendation=[
                    "Разместите реквизиты в футере",
                    "Продублируйте их на странице «Контакты»",
                ],
            ),
        ],
    )
    return Methodology(
        version="1.0",
        updated_at="14.11.2026",
        intro="Справочник по методологии проверок PriRex Auditor.",
        blocks=[block_a, block_b],
    )


def sample_how_it_works() -> HowItWorks:
    """Два раздела — хватает для навигации и переключения контента."""
    return HowItWorks(
        version="1.0",
        updated_at="14.11.2026",
        sections=[
            HowItWorksSection(
                id="what_it_does",
                title="Что делает приложение",
                content_md=(
                    "# Что делает приложение\n\n"
                    "Приложение принимает URL и прогоняет семнадцать проверок."
                ),
            ),
            HowItWorksSection(
                id="technologies",
                title="Какие технологии используются",
                content_md=(
                    "## Какие технологии используются\n\n"
                    "Используются **httpx** и Playwright Chromium."
                ),
            ),
        ],
    )


@pytest.fixture
def methodology_window(qapp, monkeypatch):
    data = sample_methodology()
    monkeypatch.setattr(mw_module, "load_methodology", lambda: data)
    monkeypatch.setattr(mw_module, "methodology_error", lambda: None)
    window = mw_module.MethodologyWindow()
    window.show()
    qapp.processEvents()
    yield window
    window.close()
    window.deleteLater()
    qapp.processEvents()


@pytest.fixture
def how_it_works_window(qapp, monkeypatch):
    data = sample_how_it_works()
    monkeypatch.setattr(hiw_module, "load_how_it_works", lambda: data)
    monkeypatch.setattr(hiw_module, "how_it_works_error", lambda: None)
    window = hiw_module.HowItWorksWindow()
    window.show()
    qapp.processEvents()
    yield window
    window.close()
    window.deleteLater()
    qapp.processEvents()


def _top_titles(window: mw_module.MethodologyWindow) -> list[str]:
    tree = window.tree
    return [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]


def _child_titles(window: mw_module.MethodologyWindow) -> list[str]:
    tree = window.tree
    titles: list[str] = []
    for group_index in range(tree.topLevelItemCount()):
        group = tree.topLevelItem(group_index)
        for index in range(group.childCount()):
            titles.append(group.child(index).text(0))
    return titles


# ---------------------------------------------------------------------------
# «Критерии проверок»: структура и контент
# ---------------------------------------------------------------------------
def test_methodology_window_is_non_modal(qapp, methodology_window):
    window = methodology_window
    assert window.isModal() is False
    assert bool(window.windowFlags() & Qt.WindowType.Window)
    assert window.size().width() > 0
    assert window.size().height() > 0
    assert window.minimumWidth() == 760
    assert window.minimumHeight() == 560
    assert window.close_button.text() == "Закрыть"
    assert "Актуально на 14.11.2026" in window.subtitle_label.text()
    assert window.title_label.text() == "Критерии проверок"


def test_methodology_tree_is_filled(qapp, methodology_window):
    tree = methodology_window.tree
    assert tree.columnCount() == 1
    assert tree.isHeaderHidden() is True
    assert tree.topLevelItemCount() == 2
    assert _top_titles(methodology_window) == [
        "152-ФЗ (персональные данные)",
        "ЗоЗПП (защита прав потребителей)",
    ]
    assert _child_titles(methodology_window) == [
        "4.2. Политика конфиденциальности — наличие",
        "4.3. Политика — содержание",
        "4.13. Реквизиты продавца",
    ]

    # Группа-заголовок не выбирается, лист — выбирается.
    group = tree.topLevelItem(0)
    assert not (group.flags() & Qt.ItemFlag.ItemIsSelectable)
    leaf = group.child(0)
    assert leaf.flags() & Qt.ItemFlag.ItemIsSelectable
    assert group.isExpanded() is True


def test_methodology_select_first_check_shows_content(qapp, methodology_window):
    window = methodology_window
    tree = window.tree
    tree.setCurrentItem(tree.topLevelItem(0).child(0))
    qapp.processEvents()

    assert window.check_title.text() == (
        "4.2. Политика конфиденциальности — наличие"
    )
    assert window.badge_label.text() == "Применимо всегда"
    assert window.badge_label.isVisible() is True
    assert "ссылк" in window.what_label.text().lower()
    assert window.legal_label.text() == "Норма: ч. 2 ст. 18.1 152-ФЗ"
    assert window.violations_label.text().startswith("• ")
    assert window.violations_label.text().count("• ") == 2
    assert window.normal_label.text().count("• ") == 2
    assert window.recommendation_label.text().startswith("1. ")
    assert window.na_label.isVisible() is False
    assert window.copy_button.isEnabled() is True


def test_methodology_search_filters_by_text(qapp, methodology_window):
    window = methodology_window
    window.search_input.setText("реквизит")
    qapp.processEvents()

    assert window.tree.topLevelItemCount() == 1
    assert _child_titles(window) == ["4.13. Реквизиты продавца"]
    assert window.no_results_label.isVisible() is False

    # Верхний регистр кириллицы тоже должен находиться.
    window.search_input.setText("РЕКВИЗИТ")
    qapp.processEvents()
    assert _child_titles(window) == ["4.13. Реквизиты продавца"]

    # Поиск по тексту описания, а не только по названию.
    window.search_input.setText("маркеры")
    qapp.processEvents()
    assert _child_titles(window) == ["4.3. Политика — содержание"]

    # Мусор — пусто и «Ничего не найдено».
    window.search_input.setText("щщщ-нет-такого")
    qapp.processEvents()
    assert window.tree.topLevelItemCount() == 0
    assert window.tree.isVisible() is False
    assert window.no_results_label.isVisible() is True
    assert window.no_results_label.text() == "Ничего не найдено"

    # Пустой запрос возвращает всё.
    window.search_input.clear()
    qapp.processEvents()
    assert window.tree.topLevelItemCount() == 2
    assert window.tree.isVisible() is True
    assert window.no_results_label.isVisible() is False


def test_methodology_focus_check(qapp, methodology_window):
    window = methodology_window
    window.focus_check("b13_seller_details")
    qapp.processEvents()
    current = window.tree.currentItem()
    assert current is not None
    assert current.text(0) == "4.13. Реквизиты продавца"
    assert window.check_title.text().startswith("4.13.")
    assert window.na_label.isVisible() is True
    assert "не продаёт" in window.na_label.text()

    window.focus_check("4.2")
    qapp.processEvents()
    current = window.tree.currentItem()
    assert current is not None
    assert current.text(0).startswith("4.2.")

    # Неизвестный id не должен ронять окно.
    window.focus_check("нет-такой-проверки")
    qapp.processEvents()
    assert window.tree.currentItem() is not None


def test_methodology_focus_check_clears_filter(qapp, methodology_window):
    window = methodology_window
    window.search_input.setText("реквизит")
    qapp.processEvents()
    assert window.tree.topLevelItemCount() == 1

    window.focus_check("4.2")
    qapp.processEvents()
    assert window.search_input.text() == ""
    assert window.tree.topLevelItemCount() == 2
    assert window.tree.currentItem().text(0).startswith("4.2.")


def test_methodology_copy_markdown(qapp, methodology_window):
    window = methodology_window
    window.focus_check("4.13")
    qapp.processEvents()

    window.copy_button.click()
    qapp.processEvents()

    clipboard_text = QGuiApplication.clipboard().text()
    assert "## 4.13" in clipboard_text
    assert "Реквизиты продавца" in clipboard_text
    assert window.copy_button.text() == "Скопировано"


def test_methodology_escape_closes(qapp, monkeypatch):
    data = sample_methodology()
    monkeypatch.setattr(mw_module, "load_methodology", lambda: data)
    monkeypatch.setattr(mw_module, "methodology_error", lambda: None)
    window = mw_module.MethodologyWindow()
    window.show()
    qapp.processEvents()
    assert window.isVisible() is True

    QTest.keyClick(window, Qt.Key.Key_Escape)
    qapp.processEvents()
    assert window.isVisible() is False
    window.deleteLater()
    qapp.processEvents()


# ---------------------------------------------------------------------------
# «Критерии проверок»: файла нет / он битый
# ---------------------------------------------------------------------------
def test_methodology_unavailable_shows_empty_state(qapp, monkeypatch):
    monkeypatch.setattr(mw_module, "load_methodology", lambda: None)
    monkeypatch.setattr(mw_module, "methodology_error", lambda: "Файл повреждён")
    window = mw_module.MethodologyWindow()
    window.show()
    qapp.processEvents()

    assert window.tree.topLevelItemCount() == 0
    assert window.left_panel.isHidden() is True
    assert window.empty_state_label.isVisible() is True
    assert "Описание временно недоступно" in window.empty_state_label.text()
    assert "Файл повреждён" in window.empty_state_label.text()
    assert window.copy_button.isEnabled() is False

    # focus_check на пустых данных не падает.
    window.focus_check("4.13")
    window.close()
    window.deleteLater()
    qapp.processEvents()


def test_methodology_singleton_per_parent(qapp, monkeypatch):
    data = sample_methodology()
    monkeypatch.setattr(mw_module, "load_methodology", lambda: data)
    monkeypatch.setattr(mw_module, "methodology_error", lambda: None)

    parent = QWidget()
    reopened: mw_module.MethodologyWindow | None = None
    try:
        first = mw_module.open_methodology_window(parent)
        second = mw_module.open_methodology_window(parent, check_id="4.13")
        assert first is second
        qapp.processEvents()
        assert second.tree.currentItem().text(0).startswith("4.13.")
        assert second.isModal() is False

        # После закрытия окно не переиспользуется: следующий вызов создаёт новое.
        first.close()
        qapp.processEvents()
        reopened = mw_module.open_methodology_window(parent)
        assert reopened is not first
        assert reopened.isVisible() is True
    finally:
        for window in (reopened,):
            if window is not None:
                window.close()
                window.deleteLater()
        parent.deleteLater()
        qapp.processEvents()


# ---------------------------------------------------------------------------
# «Как работает приложение»
# ---------------------------------------------------------------------------
def test_how_it_works_navigation(qapp, how_it_works_window):
    window = how_it_works_window
    assert window.isModal() is False
    assert window.size().width() > 0
    assert window.minimumWidth() == 700
    assert window.nav.count() == 2
    assert window.nav.item(0).text() == "Что делает приложение"
    assert window.nav.item(1).text() == "Какие технологии используются"
    assert window.nav.currentRow() == 0
    assert "семнадцать проверок" in window.content.toPlainText()


def test_how_it_works_switches_sections(qapp, how_it_works_window):
    window = how_it_works_window
    window.nav.setCurrentRow(1)
    qapp.processEvents()

    text = window.content.toPlainText()
    assert "Playwright" in text
    assert "семнадцать проверок" not in text
    assert window.current_section is not None
    assert window.current_section.id == "technologies"


def test_how_it_works_initial_section(qapp, monkeypatch):
    data = sample_how_it_works()
    monkeypatch.setattr(hiw_module, "load_how_it_works", lambda: data)
    monkeypatch.setattr(hiw_module, "how_it_works_error", lambda: None)

    window = hiw_module.HowItWorksWindow(section_id="technologies")
    window.show()
    qapp.processEvents()

    assert window.nav.currentRow() == 1
    assert "Playwright" in window.content.toPlainText()

    # Неизвестный раздел — остаёмся на первом, без падения.
    window.select_section("нет-такого-раздела")
    assert window.nav.currentRow() == 1
    window.close()
    window.deleteLater()
    qapp.processEvents()


def test_how_it_works_unavailable(qapp, monkeypatch):
    monkeypatch.setattr(hiw_module, "load_how_it_works", lambda: None)
    monkeypatch.setattr(
        hiw_module, "how_it_works_error", lambda: "Файл не найден в сборке."
    )
    window = hiw_module.HowItWorksWindow()
    window.show()
    qapp.processEvents()

    text = window.content.toPlainText()
    assert "Описание временно недоступно" in text
    assert "Файл не найден" in text
    assert window.nav.isHidden() is True

    window.select_section("technologies")
    window.close()
    window.deleteLater()
    qapp.processEvents()


def test_how_it_works_singleton_per_parent(qapp, monkeypatch):
    data = sample_how_it_works()
    monkeypatch.setattr(hiw_module, "load_how_it_works", lambda: data)
    monkeypatch.setattr(hiw_module, "how_it_works_error", lambda: None)

    parent = QWidget()
    try:
        first = hiw_module.open_how_it_works_window(parent)
        second = hiw_module.open_how_it_works_window(
            parent, section_id="technologies"
        )
        assert first is second
        qapp.processEvents()
        assert second.nav.currentRow() == 1
    finally:
        first.close()
        first.deleteLater()
        parent.deleteLater()
        qapp.processEvents()


# ---------------------------------------------------------------------------
# Реальные assets/*.json (если участник с контентом их уже создал)
# ---------------------------------------------------------------------------
def test_real_assets_open(qapp):
    methodology_path = asset_path("methodology.json")
    how_it_works_path = asset_path("how_it_works.json")
    if not methodology_path.exists() or not how_it_works_path.exists():
        pytest.skip("assets/*.json ещё не созданы — проверка на реальных данных пропущена")

    content_loader.reload()
    methodology = content_loader.load_methodology()
    assert methodology is not None, content_loader.methodology_error()
    how_it_works = content_loader.load_how_it_works()
    assert how_it_works is not None, content_loader.how_it_works_error()

    parent = QWidget()
    try:
        method_window = mw_module.open_methodology_window(parent)
        qapp.processEvents()
        assert method_window.tree.topLevelItemCount() >= 1
        assert len(methodology.all_checks()) >= 1
        assert method_window.check_title.text() != ""

        how_window = hiw_module.open_how_it_works_window(parent)
        qapp.processEvents()
        assert how_window.nav.count() == len(how_it_works.sections)
        assert how_window.content.toPlainText().strip() != ""

        method_window.close()
        how_window.close()
    finally:
        parent.deleteLater()
        qapp.processEvents()
