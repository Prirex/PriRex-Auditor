"""Окно «Как работает приложение»: техническая механика сканера.

Немодальное окно-справочник: слева навигация по разделам, справа Markdown
из ``assets/how_it_works.json``, отрендеренный ``QTextBrowser.setMarkdown()``.
Если файла нет или он битый — окно открывается с сообщением «Описание
временно недоступно» и причиной, приложение не падает.

Стилизация — только через ``objectName`` из ``assets/theme.qss``
(``HowItWorksWindow``, ``howItWorksNav``, ``howItWorksContent``).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.core.content.loader import how_it_works_error, load_how_it_works
from app.core.content.models import HowItWorks, HowItWorksSection
from app.i18n import tr, trf

__all__ = ["HowItWorksWindow", "open_how_it_works_window"]

#: Ширина левой панели навигации (по ТЗ 220–240 px).
NAV_WIDTH = 240
#: Текст пустого состояния, когда файла нет/он битый.
EMPTY_TEXT = "Описание временно недоступно"
#: Текст для раздела без содержимого.
MISSING_SECTION_TEXT = "Описание отсутствует"


def _label(text: str, object_name: str, parent: QWidget) -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName(object_name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


def _apply_window_flags(dialog: QDialog) -> None:
    """Самостоятельное немодальное окно (не блокирует главное, Esc закрывает)."""
    dialog.setWindowFlags(
        Qt.WindowType.Window
        | Qt.WindowType.WindowTitleHint
        | Qt.WindowType.WindowSystemMenuHint
        | Qt.WindowType.WindowMinMaxButtonsHint
        | Qt.WindowType.WindowCloseButtonHint
    )
    dialog.setModal(False)
    dialog.setWindowModality(Qt.WindowModality.NonModal)


class HowItWorksWindow(QDialog):
    """Навигация по разделам слева + Markdown-контент раздела справа."""

    def __init__(
        self,
        parent: QWidget | None = None,
        section_id: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._data: HowItWorks | None = load_how_it_works()
        self._error: str | None = how_it_works_error()
        self._sections: list[HowItWorksSection] = []
        self._current: HowItWorksSection | None = None

        self.setObjectName("HowItWorksWindow")
        self.setWindowTitle(tr("Как работает приложение"))
        _apply_window_flags(self)
        self.resize(820, 650)
        self.setMinimumSize(700, 520)

        self._build_ui()
        self._populate()
        if section_id:
            self.select_section(section_id)

    # ------------------------------------------------------------------
    # Построение интерфейса
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(12)

        header = QVBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(2)
        self.title_label = _label(
            tr("Как работает приложение"), "MethodologyTitle", self
        )
        self.subtitle_label = _label("", "MethodologySubtitle", self)
        header.addWidget(self.title_label)
        header.addWidget(self.subtitle_label)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(14)
        self.nav = self._build_nav()
        body.addWidget(self.nav, 0)
        self.content = self._build_content()
        body.addWidget(self.content, 1)
        root.addLayout(body, 1)

        root.addLayout(self._build_buttons())

    def _build_nav(self) -> QListWidget:
        nav = QListWidget(self)
        nav.setObjectName("howItWorksNav")
        nav.setFixedWidth(NAV_WIDTH)
        nav.setFrameShape(QFrame.Shape.NoFrame)
        nav.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        nav.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav.setTextElideMode(Qt.TextElideMode.ElideRight)
        nav.setWordWrap(True)
        nav.setUniformItemSizes(False)
        nav.setCursor(Qt.CursorShape.PointingHandCursor)
        nav.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        nav.currentRowChanged.connect(self._on_row_changed)
        return nav

    def _build_content(self) -> QTextBrowser:
        content = QTextBrowser(self)
        content.setObjectName("howItWorksContent")
        content.setOpenExternalLinks(False)
        content.setOpenLinks(False)
        content.setReadOnly(True)
        content.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        return content

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 2, 0, 0)
        row.setSpacing(8)
        row.addStretch(1)

        self.close_button = QPushButton(tr("Закрыть"), self)
        self.close_button.setObjectName("SecondaryButton")
        self.close_button.setMinimumWidth(112)
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.clicked.connect(self.reject)
        row.addWidget(self.close_button, 0)
        return row

    # ------------------------------------------------------------------
    # Заполнение данными
    # ------------------------------------------------------------------
    def _populate(self) -> None:
        self.subtitle_label.setText(self._subtitle_text())
        data = self._data
        if data is None or not data.sections:
            self.nav.hide()
            self.content.setPlainText(self._empty_state_text())
            return

        self._sections = list(data.sections)
        self.nav.show()
        for section in self._sections:
            item = QListWidgetItem(section.title, self.nav)
            item.setData(int(Qt.ItemDataRole.UserRole), section.id)
            item.setToolTip(section.title)
        if self._sections:
            self.nav.setCurrentRow(0)

    def _subtitle_text(self) -> str:
        data = self._data
        if data is None:
            return ""
        if data.updated_at:
            return trf("Актуально на {date}", date=data.updated_at)
        return ""

    def _empty_state_text(self) -> str:
        error = (self._error or "").strip()
        return f"{tr(EMPTY_TEXT)}\n\n{error}" if error else tr(EMPTY_TEXT)

    # ------------------------------------------------------------------
    # Навигация и контент
    # ------------------------------------------------------------------
    def _on_row_changed(self, row: int) -> None:
        if 0 <= row < len(self._sections):
            self._show_section(self._sections[row])

    def _show_section(self, section: HowItWorksSection) -> None:
        self._current = section
        text = (section.content_md or "").strip()
        if text:
            self.content.setMarkdown(text)
        else:
            self.content.setPlainText(tr(MISSING_SECTION_TEXT))
        self.content.verticalScrollBar().setValue(0)

    def select_section(self, section_id: str) -> None:
        """Открывает раздел по id (``technologies``) или по заголовку."""
        if not section_id or not self._sections:
            return
        for index, section in enumerate(self._sections):
            if section_id in {section.id, section.title}:
                self.nav.setCurrentRow(index)
                return

    @property
    def current_section(self) -> HowItWorksSection | None:
        return self._current


# ---------------------------------------------------------------------------
# Фабрика с единственным экземпляром на родителя
# ---------------------------------------------------------------------------
_OPEN_WINDOWS: dict[int, HowItWorksWindow] = {}


def _parent_key(parent: QWidget | None) -> int:
    return id(parent) if parent is not None else 0


def _forget_window(key: int, window: HowItWorksWindow) -> None:
    if _OPEN_WINDOWS.get(key) is window:
        _OPEN_WINDOWS.pop(key, None)
    window.deleteLater()


def _alive_window(parent: QWidget | None) -> HowItWorksWindow | None:
    key = _parent_key(parent)
    window = _OPEN_WINDOWS.get(key)
    if window is None:
        return None
    try:
        # Обращение к C++ объекту: после удаления родителя он уже мёртв.
        window.isVisible()
    except RuntimeError:
        _OPEN_WINDOWS.pop(key, None)
        return None
    return window


def open_how_it_works_window(
    parent: QWidget | None = None,
    section_id: str | None = None,
) -> HowItWorksWindow:
    """Открывает (или поднимает уже открытое) окно «Как работает приложение»."""
    key = _parent_key(parent)
    window = _alive_window(parent)
    if window is None:
        window = HowItWorksWindow(parent, section_id=section_id)
        _OPEN_WINDOWS[key] = window
        window.finished.connect(
            lambda _result, w=window, k=key: _forget_window(k, w)
        )
    elif section_id:
        window.select_section(section_id)
    window.show()
    window.raise_()
    window.activateWindow()
    return window
