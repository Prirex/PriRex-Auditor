"""Окно-справочник «Критерии проверок»: что проверяется и по какой норме.

Окно немодальное — его можно держать открытым параллельно с главным.
Тексты приходят из ``assets/methodology.json`` через
:func:`app.core.content.loader.load_methodology`. Если файла нет или он
битый, окно всё равно открывается и показывает «Описание временно
недоступно» с причиной — приложение из-за справочника не падает.

Стилизация — только через ``objectName`` из ``assets/theme.qss``
(``MethodologyWindow``, ``methodologyTree``, ``MethodologyTitle`` и т. д.).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.content.loader import load_methodology, methodology_error
from app.core.content.models import Methodology, MethodologyCheck
from app.i18n import tr, trf
from app.ui.theme import PALETTE

__all__ = ["MethodologyWindow", "open_methodology_window"]

#: Ширина левой панели с деревом (по ТЗ 260–280 px).
LEFT_PANEL_WIDTH = 268
#: Сколько миллисекунд кнопка копирования показывает «Скопировано».
COPY_FEEDBACK_MS = 2000
#: Текст пустого состояния, когда файла методологии нет/он битый.
EMPTY_TEXT = "Описание временно недоступно"
#: Текст пустого состояния для поиска без результатов.
NO_RESULTS_TEXT = "Ничего не найдено"
#: Роль, в которой в дереве лежит ключ проверки.
KEY_ROLE = int(Qt.ItemDataRole.UserRole)

#: Секции правой панели: ключ, заголовок, objectName тела.
_SECTION_TITLES: tuple[tuple[str, str, str], ...] = (
    ("what", "ЧТО ПРОВЕРЯЕТСЯ", "InfoBody"),
    ("legal", "ПРАВОВОЕ ОСНОВАНИЕ", "LegalBasis"),
    ("violations", "ЧТО СЧИТАЕТСЯ НАРУШЕНИЕМ", "InfoBody"),
    ("normal", "ЧТО СЧИТАЕТСЯ НОРМОЙ", "InfoBody"),
    ("na", "КОГДА НЕ ПРИМЕНИМО (N/A)", "InfoBody"),
    ("recommendation", "РЕКОМЕНДАЦИЯ ПО ИСПРАВЛЕНИЮ", "InfoBody"),
)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------
def _label(
    text: str,
    object_name: str,
    parent: QWidget,
    *,
    selectable: bool = False,
) -> QLabel:
    """QLabel с мягким текстом, переносом слов и (опционально) выделением."""
    label = QLabel(text, parent)
    label.setObjectName(object_name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if selectable:
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _bullet_list(items: list[str]) -> str:
    """Маркированный список: каждый пункт с новой строки."""
    return "\n".join(f"• {item.strip()}" for item in items if item.strip())


def _numbered_list(items: list[str]) -> str:
    """Нумерованный список: каждый пункт с новой строки."""
    lines = [
        f"{index}. {item.strip()}"
        for index, item in enumerate(items, start=1)
        if item.strip()
    ]
    return "\n".join(lines)


def _legal_norm_text(check: MethodologyCheck) -> str:
    """«Норма: …» без дублирования префикса у заглушки «требует уточнения»."""
    text = (check.legal_basis_text or "").strip()
    if not text:
        return "Норма: требует уточнения юристом"
    if text.lower().startswith("норма:"):
        return text
    return f"Норма: {text}"


def _check_haystack(check: MethodologyCheck) -> str:
    """Весь текст проверки в нижнем регистре — для поиска без учёта регистра."""
    parts: list[str] = [
        check.id,
        check.check_id,
        check.title,
        check.what,
        check.legal_basis_text,
        check.applicability_note,
        check.not_applicable_note or "",
    ]
    parts.extend(check.legal_basis)
    parts.extend(check.violations)
    parts.extend(check.normal)
    parts.extend(check.recommendation)
    return "\n".join(part for part in parts if part).casefold()


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


# ---------------------------------------------------------------------------
# Окно
# ---------------------------------------------------------------------------
class MethodologyWindow(QDialog):
    """Справочник по методологии: дерево проверок слева, описание справа."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._methodology: Methodology | None = load_methodology()
        self._error: str | None = methodology_error()
        self._current: MethodologyCheck | None = None
        self._rebuilding = False
        self._check_by_key: dict[str, MethodologyCheck] = {}
        self._item_by_key: dict[str, QTreeWidgetItem] = {}
        self._sections: dict[str, QLabel] = {}
        self._bodies: dict[str, QLabel] = {}

        self.setObjectName("MethodologyWindow")
        self.setWindowTitle(tr("Критерии проверок"))
        _apply_window_flags(self)
        self.resize(900, 700)
        self.setMinimumSize(760, 560)

        self._copy_timer = QTimer(self)
        self._copy_timer.setSingleShot(True)
        self._copy_timer.timeout.connect(self._reset_copy_text)

        self._build_ui()
        self._populate()

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
        self.title_label = _label(tr("Критерии проверок"), "MethodologyTitle", self)
        self.subtitle_label = _label("", "MethodologySubtitle", self)
        header.addWidget(self.title_label)
        header.addWidget(self.subtitle_label)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(14)
        self.left_panel = self._build_left_panel()
        body.addWidget(self.left_panel, 0)
        self.scroll = self._build_right_panel()
        body.addWidget(self.scroll, 1)
        root.addLayout(body, 1)

        root.addLayout(self._build_buttons())

    def _build_left_panel(self) -> QWidget:
        panel = QWidget(self)
        panel.setFixedWidth(LEFT_PANEL_WIDTH)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.search_input = QLineEdit(panel)
        self.search_input.setObjectName("SearchInput")
        self.search_input.setPlaceholderText(tr("Поиск по проверкам…"))
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumHeight(30)
        self.search_input.setCursorPosition(0)
        self.search_input.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search_input)

        self.tree = QTreeWidget(panel)
        self.tree.setObjectName("methodologyTree")
        self.tree.setColumnCount(1)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setIndentation(14)
        self.tree.setUniformRowHeights(True)
        self.tree.setAnimated(False)
        self.tree.setAlternatingRowColors(False)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.tree.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.tree.currentItemChanged.connect(self._on_current_changed)
        layout.addWidget(self.tree, 1)

        self.no_results_label = _label(tr(NO_RESULTS_TEXT), "EmptyState", panel)
        self.no_results_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_results_label.hide()
        layout.addWidget(self.no_results_label, 1)
        return panel

    def _build_right_panel(self) -> QScrollArea:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        container = QWidget(scroll)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(18, 16, 18, 16)
        container_layout.setSpacing(8)

        self.check_panel = self._build_check_panel(container)
        container_layout.addWidget(self.check_panel)

        self.empty_state_label = _label("", "EmptyState", container)
        self.empty_state_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.empty_state_label.hide()
        container_layout.addWidget(self.empty_state_label)
        container_layout.addStretch(1)

        scroll.setWidget(container)
        self.content = container
        return scroll

    def _build_check_panel(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.check_title = _label("", "MethodologyTitle", panel)
        layout.addWidget(self.check_title)

        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(0)
        self.badge_label = _label("", "PillBadge", panel)
        # Пилюля должна оставаться в одну строку, как бейдж, а не переноситься.
        self.badge_label.setWordWrap(False)
        self.badge_label.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
        )
        self.badge_label.hide()
        badge_row.addWidget(self.badge_label, 0, Qt.AlignmentFlag.AlignLeft)
        badge_row.addStretch(1)
        layout.addLayout(badge_row)

        for index, (key, title, object_name) in enumerate(_SECTION_TITLES):
            if index:
                layout.addSpacing(8)
            section = QLabel(tr(title), panel)
            section.setObjectName("InfoSectionLabel")
            section.setTextFormat(Qt.TextFormat.PlainText)
            body = _label("", object_name, panel, selectable=True)
            if key == "legal":
                body.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
            layout.addWidget(section)
            layout.addWidget(body)
            self._sections[key] = section
            self._bodies[key] = body

        self.what_label = self._bodies["what"]
        self.legal_label = self._bodies["legal"]
        self.violations_label = self._bodies["violations"]
        self.normal_label = self._bodies["normal"]
        self.na_label = self._bodies["na"]
        self.recommendation_label = self._bodies["recommendation"]
        return panel

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 2, 0, 0)
        row.setSpacing(8)

        self.copy_button = QPushButton(tr("Копировать описание"), self)
        self.copy_button.setObjectName("GhostButton")
        self.copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self._copy_markdown)
        row.addWidget(self.copy_button, 0)

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
        if self._methodology is None or not self._methodology.blocks:
            self.left_panel.hide()
            self.check_panel.hide()
            self.empty_state_label.setText(self._empty_state_text())
            self.empty_state_label.show()
            self.copy_button.setEnabled(False)
            return

        self.left_panel.show()
        self.empty_state_label.hide()
        self._rebuild_tree()

    def _subtitle_text(self) -> str:
        data = self._methodology
        if data is None:
            return ""
        lines: list[str] = []
        if data.updated_at:
            lines.append(trf("Актуально на {date}", date=data.updated_at))
        intro = (data.intro or "").strip()
        if intro:
            lines.append(intro)
        return "\n".join(lines)

    def _empty_state_text(self) -> str:
        error = (self._error or "").strip()
        return f"{tr(EMPTY_TEXT)}\n{error}" if error else tr(EMPTY_TEXT)

    # ------------------------------------------------------------------
    # Дерево и поиск
    # ------------------------------------------------------------------
    def _apply_filter(self, _text: str = "") -> None:
        if self._methodology is None:
            return
        self._rebuild_tree()

    def _query_tokens(self) -> list[str]:
        return [token for token in self.search_input.text().casefold().split() if token]

    def _matches(self, check: MethodologyCheck, tokens: list[str]) -> bool:
        if not tokens:
            return True
        haystack = _check_haystack(check)
        return all(token in haystack for token in tokens)

    def _rebuild_tree(self) -> None:
        data = self._methodology
        if data is None:
            return
        tokens = self._query_tokens()
        previous = self._current

        self._rebuilding = True
        self.tree.clear()
        self._check_by_key.clear()
        self._item_by_key.clear()

        total = 0
        for block in data.blocks:
            visible = [check for check in block.checks if self._matches(check, tokens)]
            if tokens and not visible:
                continue
            group = QTreeWidgetItem(self.tree)
            group.setText(0, block.title or block.id)
            group.setToolTip(0, block.title or block.id)
            group_font = QFont(self.tree.font())
            group_font.setBold(True)
            group.setFont(0, group_font)
            group.setForeground(0, QBrush(QColor(PALETTE["text_heading"])))
            # Группа-заголовок не выбирается — только раскрывается.
            group.setFlags(Qt.ItemFlag.ItemIsEnabled)
            for check in visible:
                key = str(len(self._check_by_key))
                item = QTreeWidgetItem(group)
                item.setText(0, f"{check.id}. {check.title}")
                item.setToolTip(0, check.what or check.title)
                item.setData(0, KEY_ROLE, key)
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                )
                self._check_by_key[key] = check
                self._item_by_key[key] = item
                total += 1
            # При поиске блоки раскрыты, чтобы совпадения было видно сразу.
            group.setExpanded(True)
        self._rebuilding = False

        has_items = total > 0
        self.tree.setVisible(has_items)
        self.no_results_label.setVisible(not has_items)

        target = self._item_for(previous) if previous is not None else None
        if target is None and has_items:
            target = next(iter(self._item_by_key.values()), None)
        if target is not None:
            self.tree.setCurrentItem(target)

    def _item_for(self, check: MethodologyCheck) -> QTreeWidgetItem | None:
        for key, stored in self._check_by_key.items():
            if stored is check or stored == check:
                return self._item_by_key.get(key)
        return None

    def _on_current_changed(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        if self._rebuilding or current is None:
            return
        key = current.data(0, KEY_ROLE)
        if not key:
            # Клик по заголовку блока: контент не меняем.
            return
        check = self._check_by_key.get(str(key))
        if check is not None:
            self._show_check(check)

    # ------------------------------------------------------------------
    # Правая панель
    # ------------------------------------------------------------------
    def _show_check(self, check: MethodologyCheck) -> None:
        self._current = check
        self.check_panel.show()
        self.empty_state_label.hide()
        self.copy_button.setEnabled(True)
        self._copy_timer.stop()
        self.copy_button.setText(tr("Копировать описание"))

        self.check_title.setText(f"{check.id}. {check.title}")

        note = (check.applicability_note or "").strip()
        self.badge_label.setText(note)
        self.badge_label.setVisible(bool(note))

        self._set_section("what", (check.what or "").strip())
        self._set_section("legal", _legal_norm_text(check))
        self._set_section("violations", _bullet_list(check.violations))
        self._set_section("normal", _bullet_list(check.normal))
        self._set_section("na", (check.not_applicable_note or "").strip())
        self._set_section("recommendation", _numbered_list(check.recommendation))

        self.scroll.verticalScrollBar().setValue(0)

    def _set_section(self, key: str, text: str) -> None:
        body = self._bodies[key]
        section = self._sections[key]
        body.setText(text)
        visible = bool(text.strip())
        body.setVisible(visible)
        section.setVisible(visible)

    # ------------------------------------------------------------------
    # Копирование и фокус
    # ------------------------------------------------------------------
    def _copy_markdown(self) -> None:
        if self._current is None:
            return
        QGuiApplication.clipboard().setText(self._current.as_markdown())
        self.copy_button.setText(tr("Скопировано"))
        self._copy_timer.start(COPY_FEEDBACK_MS)

    def _reset_copy_text(self) -> None:
        self.copy_button.setText(tr("Копировать описание"))

    def focus_check(self, check_id: str) -> None:
        """Выделяет проверку по id (``b13_seller_details``) или номеру («4.13»)."""
        data = self._methodology
        if data is None or not check_id:
            return
        check = data.find(check_id)
        if check is None:
            return
        if self.search_input.text().strip():
            # Снимаем фильтр: иначе нужной проверки может не быть в дереве.
            self.search_input.clear()
        item = self._item_for(check)
        if item is None:
            return
        self.tree.setCurrentItem(item)
        self.tree.scrollToItem(
            item, QAbstractItemView.ScrollHint.PositionAtCenter
        )


# ---------------------------------------------------------------------------
# Фабрика с единственным экземпляром на родителя
# ---------------------------------------------------------------------------
_OPEN_WINDOWS: dict[int, MethodologyWindow] = {}


def _parent_key(parent: QWidget | None) -> int:
    return id(parent) if parent is not None else 0


def _forget_window(key: int, window: MethodologyWindow) -> None:
    if _OPEN_WINDOWS.get(key) is window:
        _OPEN_WINDOWS.pop(key, None)
    window.deleteLater()


def _alive_window(parent: QWidget | None) -> MethodologyWindow | None:
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


def open_methodology_window(
    parent: QWidget | None = None,
    check_id: str | None = None,
) -> MethodologyWindow:
    """Открывает (или поднимает уже открытое) окно «Критерии проверок»."""
    key = _parent_key(parent)
    window = _alive_window(parent)
    if window is None:
        window = MethodologyWindow(parent)
        _OPEN_WINDOWS[key] = window
        window.finished.connect(
            lambda _result, w=window, k=key: _forget_window(k, w)
        )
    if check_id:
        window.focus_check(check_id)
    window.show()
    window.raise_()
    window.activateWindow()
    return window
