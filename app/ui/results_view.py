"""Виджеты результатов проверки.

Содержит:
  * ``ResultsView`` — карточку процента, дерево проверок (блок → подраздел
    → проверка), сворачиваемые секции «Не применимо (N/A)» и «Не удалось
    проверить» списком строк в ``QScrollArea``, пустое состояние и мягкий
    баннер ошибки;
  * ``DetailPanel`` — правую панель с сообщением, подтверждениями
    (evidence), рекомендацией и ссылкой на «Критерии проверок».

Виджеты только отображают данные и не ходят в сеть. Все цвета берутся из
``theme.PALETTE``/``STATUS_COLORS``, стилизация — через objectName из
``assets/theme.qss``.
"""

from __future__ import annotations

import html as html_utils

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.models import (
    CATEGORY_LABELS,
    CheckResult,
    CheckStatus,
    Evidence,
    Report,
    section_label,
)
from app.i18n import tr, trf
from app.ui.icons import status_dot
from app.ui.theme import (
    PALETTE,
    STATUS_COLORS,
    score_level,
    set_prop,
)

__all__ = ["DetailPanel", "FlatResultSection", "ResultsView"]

#: Ширина колонки «Статус».
STATUS_COLUMN_WIDTH = 128
#: Диаметр цветной точки статуса (дерево и строки секций), px.
STATUS_DOT_SIZE = 10
#: Цвет крупного прочерка в пустом состоянии (мягкий, не чёрный).
IDLE_SCORE_COLOR = "#C9C4BB"
#: Роль, в которой в дереве лежит ключ проверки.
ITEM_KEY_ROLE = int(Qt.ItemDataRole.UserRole)

#: Максимальная высота секции «Не применимо (N/A)», px.
NA_SECTION_MAX_HEIGHT = 160
#: Максимальная высота секции «Не удалось проверить», px.
SKIP_SECTION_MAX_HEIGHT = 110

#: Соответствие статуса и имени QSS-свойства ``chip``.
CHIP_KINDS: dict[str, str] = {
    CheckStatus.PASS.value: "pass",
    CheckStatus.WARN.value: "warn",
    CheckStatus.FAIL.value: "fail",
    CheckStatus.SKIP.value: "skip",
    CheckStatus.NOT_APPLICABLE.value: "na",
}


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _make_chip(text: str, kind: str, parent: QWidget) -> QLabel:
    """Маленький цветной чип статуса/счётчика."""
    chip = QLabel(text, parent)
    chip.setObjectName("Chip")
    chip.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    set_prop(chip, "chip", kind)
    return chip


def _plain_label(text: str, object_name: str, parent: QWidget) -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName(object_name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _status_color(status: CheckStatus) -> str:
    return STATUS_COLORS.get(status.value, PALETTE["text_muted"])


def _methodology_for(check_id: str):
    """Методология проверки; справочник не должен ломать панель деталей.

    Импорт ленивый: ``assets/methodology.json`` может отсутствовать/быть
    битым в сборке, а панель деталей обязана работать и без него.
    """
    if not check_id:
        return None
    try:
        from app.core.content.loader import methodology_for as lookup

        return lookup(check_id)
    except Exception:  # noqa: BLE001 - справочник не должен ронять UI
        return None


def _clear_layout(layout: QVBoxLayout) -> None:
    """Удаляет из layout все элементы (виджеты и распорки)."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        child_layout = item.layout()
        if child_layout is not None:
            _clear_layout(child_layout)  # type: ignore[arg-type]


def _section_font(base: QFont) -> QFont:
    """Приглушённый мелкий шрифт заголовка подраздела."""
    font = QFont(base)
    if base.pointSizeF() > 0:
        font.setPointSizeF(max(7.5, base.pointSizeF() - 1.5))
    else:
        font.setPixelSize(11)
    font.setBold(False)
    return font


class _StatusTextDelegate(QStyledItemDelegate):
    """Красит текст колонки «Статус» цветом статуса.

    QSS-правило ``QTreeWidget#CheckTree::item { color: ... }`` перекрывает
    ``ForegroundRole``, поэтому текст рисуем сами — тем же шрифтом (полужирным)
    и цветом из ``STATUS_COLORS``, но поверх штатного фона/выделения.
    """

    def paint(self, painter, option, index) -> None:  # noqa: N802 - Qt API
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        if index.column() != 1 or not text:
            super().paint(painter, option, index)
            return

        brush = index.data(Qt.ItemDataRole.ForegroundRole)
        color = (
            brush.color()
            if isinstance(brush, QBrush)
            else opt.palette.color(QPalette.ColorRole.Text)
        )
        widget = opt.widget
        style = (
            widget.style() if widget is not None else QApplication.style()
        )
        opt.text = ""
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget
        )
        text_rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText, opt, widget
        )
        if text_rect.isEmpty():
            text_rect = opt.rect.adjusted(4, 0, -4, 0)

        painter.save()
        painter.setFont(opt.font)
        painter.setPen(color)
        painter.drawText(
            text_rect,
            opt.displayAlignment | Qt.AlignmentFlag.AlignVCenter,
            text,
        )
        painter.restore()


# ---------------------------------------------------------------------------
# Строка списка N/A / «не удалось проверить»
# ---------------------------------------------------------------------------


class _ResultRow(QFrame):
    """Строка секции: иконка + название + полное пояснение с переносом слов."""

    clicked = Signal(object)

    def __init__(
        self,
        result: CheckResult,
        explanation: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.result = result
        self.setObjectName("Card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.setToolTip(explanation)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(8)

        self.icon_label = QLabel(self)
        self.icon_label.setObjectName("ResultRowIcon")
        self.icon_label.setFixedSize(STATUS_DOT_SIZE, STATUS_DOT_SIZE)
        pixmap = status_dot(result.status, STATUS_DOT_SIZE)
        if not pixmap.isNull():
            self.icon_label.setPixmap(pixmap)
        layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignTop)

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(1)

        self.title_label = QLabel(result.title or result.check_id, self)
        self.title_label.setObjectName("SectionTitle")
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        self.title_label.setWordWrap(True)
        text_box.addWidget(self.title_label)

        self.message_label = QLabel(explanation, self)
        self.message_label.setObjectName("Hint")
        self.message_label.setTextFormat(Qt.TextFormat.PlainText)
        self.message_label.setWordWrap(True)
        text_box.addWidget(self.message_label)

        layout.addLayout(text_box, 1)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit(self.result)
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
# Сворачиваемая секция со списком строк
# ---------------------------------------------------------------------------


class FlatResultSection(QWidget):
    """Сворачиваемая секция ``QToolButton#NaToggle`` + список строк в скролле.

    Не использует ``QTreeWidget`` с двумя колонками, поэтому длинное
    объяснение не обрезается границей панели.
    """

    result_clicked = Signal(object)

    def __init__(
        self,
        title: str,
        icon_status: CheckStatus | None,
        max_height: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._max_height = max(80, int(max_height))
        self.rows: list[_ResultRow] = []
        self.results: list[CheckResult] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        line = QFrame(self)
        line.setObjectName("HLine")
        line.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(line)

        self.toggle = QToolButton(self)
        self.toggle.setObjectName("NaToggle")
        self.toggle.setCheckable(True)
        self.toggle.setChecked(False)
        self.toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        if icon_status is not None:
            # У секции «не удалось проверить» — маленькая точка статуса.
            self.toggle.setArrowType(Qt.ArrowType.NoArrow)
            self.toggle.setIconSize(QSize(STATUS_DOT_SIZE, STATUS_DOT_SIZE))
            self.toggle.setIcon(
                QIcon(status_dot(icon_status, STATUS_DOT_SIZE))
            )
        else:
            self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        layout.addWidget(self.toggle)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        self.scroll.setFixedHeight(0)
        self.scroll.hide()

        self.content = QWidget(self.scroll)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 2, 0)
        self.content_layout.setSpacing(4)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll)

        self.toggle.toggled.connect(self.set_expanded)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        self.update_toggle_text()
        self.hide()

    # ------------------------------------------------------------------
    def set_rows(self, rows: list[tuple[CheckResult, str]]) -> None:
        """Заполняет секцию строками ``(результат, объяснение)``."""
        self.clear()
        for result, explanation in rows:
            row = _ResultRow(result, explanation, self.content)
            row.clicked.connect(self.result_clicked.emit)
            self.content_layout.addWidget(row)
            self.rows.append(row)
            self.results.append(result)
        self.update_toggle_text()
        self._fit_height()

    def clear(self) -> None:
        """Удаляет все строки и обнуляет высоту секции."""
        _clear_layout(self.content_layout)
        self.rows.clear()
        self.results.clear()
        self.update_toggle_text()
        self.scroll.setFixedHeight(0)

    def update_toggle_text(self) -> None:
        self.toggle.setText(f"{self._title} — {len(self.rows)}")

    def set_expanded(self, expanded: bool) -> None:
        """Показывает/скрывает содержимое (заголовок остаётся видимым)."""
        if self.toggle.arrowType() != Qt.ArrowType.NoArrow:
            self.toggle.setArrowType(
                Qt.ArrowType.DownArrow
                if expanded
                else Qt.ArrowType.RightArrow
            )
        self.scroll.setVisible(bool(expanded))

    # ------------------------------------------------------------------
    def _fit_height(self) -> None:
        count = len(self.rows)
        if count <= 0:
            self.scroll.setFixedHeight(0)
            return
        # Заголовок + пояснение ≈ 2 строки; при большем числе строк
        # появляется внутренний скролл (высота ограничена ТЗ).
        needed = 8 + count * 66
        self.scroll.setFixedHeight(min(self._max_height, max(62, needed)))


# ---------------------------------------------------------------------------
# Левая часть: карточка результата + дерево проверок + секции
# ---------------------------------------------------------------------------


class ResultsView(QWidget):
    """Результаты проверки: процент, дерево, N/A и «не удалось проверить»."""

    #: Пользователь выбрал проверку (или ``None``, если выбор сброшен).
    selected_result_changed = Signal(object)
    #: Из баннера ошибки нажата кнопка «Настройки».
    settings_requested = Signal()
    #: Двойной клик по проверке — открыть «Критерии проверок» на ней.
    methodology_check_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._report: Report | None = None
        self._loading = False
        self._na_visible = True
        self._result_by_key: dict[str, CheckResult] = {}
        self._key_by_object: dict[int, str] = {}

        self._build_ui()

    # ------------------------------------------------------------------
    # Построение
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.banner = self._build_error_banner()
        layout.addWidget(self.banner)

        self.score_card = self._build_score_card()
        layout.addWidget(self.score_card)

        self.checks_card = QFrame(self)
        self.checks_card.setObjectName("Panel")
        checks_layout = QVBoxLayout(self.checks_card)
        checks_layout.setContentsMargins(6, 6, 6, 6)
        checks_layout.setSpacing(4)

        self.stack = QStackedWidget(self.checks_card)
        self.stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.empty_page = self._build_message_page(
            tr("Введите адрес сайта и нажмите «Проверить». Отчёт появится здесь.")
        )
        self.loading_page = self._build_message_page(tr("Идёт проверка…"))
        self.check_tree = self._build_check_tree(self.checks_card)

        self.stack.addWidget(self.empty_page)
        self.stack.addWidget(self.loading_page)
        self.stack.addWidget(self.check_tree)
        checks_layout.addWidget(self.stack, 1)

        self.na_section = FlatResultSection(
            tr("Не применимо (N/A)"),
            None,
            NA_SECTION_MAX_HEIGHT,
            self.checks_card,
        )
        self.na_toggle = self.na_section.toggle
        self.na_section.result_clicked.connect(
            self.selected_result_changed.emit
        )
        checks_layout.addWidget(self.na_section, 0)

        self.skip_section = FlatResultSection(
            tr("Не удалось проверить"),
            CheckStatus.SKIP,
            SKIP_SECTION_MAX_HEIGHT,
            self.checks_card,
        )
        self.skip_toggle = self.skip_section.toggle
        self.skip_section.result_clicked.connect(
            self.selected_result_changed.emit
        )
        checks_layout.addWidget(self.skip_section, 0)

        layout.addWidget(self.checks_card, 1)

        self._set_idle_score()
        self.na_section.hide()
        self.skip_section.hide()
        self.stack.setCurrentWidget(self.empty_page)

    def _build_error_banner(self) -> QWidget:
        banner = QWidget(self)
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(0, 0, 0, 0)
        banner_layout.setSpacing(8)

        self.error_label = _plain_label("", "DetailNa", banner)
        self.error_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        banner_layout.addWidget(self.error_label, 1)

        self.error_settings_button = QPushButton(tr("Настройки"), banner)
        self.error_settings_button.setObjectName("GhostButton")
        self.error_settings_button.clicked.connect(self.settings_requested)
        banner_layout.addWidget(
            self.error_settings_button, 0, Qt.AlignmentFlag.AlignVCenter
        )

        banner.hide()
        self.banner_widget = banner
        return banner

    def _build_score_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 3, 10, 3)
        card_layout.setSpacing(2)

        score_row = QHBoxLayout()
        score_row.setContentsMargins(0, 0, 0, 0)
        score_row.setSpacing(18)

        self.score_value = QLabel("—", card)
        self.score_value.setObjectName("ScoreValue")
        self.score_value.setTextFormat(Qt.TextFormat.PlainText)
        self.score_value.setMinimumWidth(112)
        self.score_value.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        score_row.addWidget(self.score_value, 0, Qt.AlignmentFlag.AlignVCenter)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)
        self.score_title = _plain_label("", "ScoreTitle", card)
        self.score_hint = _plain_label("", "ScoreHint", card)
        title_box.addWidget(self.score_title)
        title_box.addWidget(self.score_hint)
        title_box.addStretch(1)
        score_row.addLayout(title_box, 1)
        card_layout.addLayout(score_row)

        self.chips_widget = QWidget(card)
        self.chips_layout = QHBoxLayout(self.chips_widget)
        self.chips_layout.setContentsMargins(0, 0, 0, 0)
        self.chips_layout.setSpacing(8)
        self.chips: dict[str, QLabel] = {}
        chip_titles = {
            "pass": "Пройдено",
            "warn": "Замечаний",
            "fail": "Нарушений",
            "na": "N/A",
            "skip": "Не проверено",
        }
        for kind, title in chip_titles.items():
            chip = _make_chip(f"{tr(title)} 0", kind, self.chips_widget)
            self.chips[kind] = chip
            self.chips_layout.addWidget(chip, 0)
        self.chips_layout.addStretch(1)
        card_layout.addWidget(self.chips_widget)
        return card

    def _build_message_page(self, text: str) -> QWidget:
        page = QWidget(self)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(24, 24, 24, 24)
        label = QLabel(text, page)
        label.setObjectName("Muted")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_layout.addStretch(1)
        page_layout.addWidget(label)
        page_layout.addStretch(1)
        return page

    def _build_check_tree(self, parent: QWidget) -> QTreeWidget:
        tree = QTreeWidget(parent)
        tree.setObjectName("CheckTree")
        tree.setColumnCount(2)
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(True)
        tree.setAnimated(False)
        tree.setIndentation(16)
        # Маленькие цветные точки статусов не должны растягиваться.
        tree.setIconSize(QSize(STATUS_DOT_SIZE, STATUS_DOT_SIZE))
        # Подразделы — мелким шрифтом, поэтому высота строк не унифицируется.
        tree.setUniformRowHeights(False)
        tree.setMinimumHeight(160)
        tree.setAlternatingRowColors(False)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tree.setExpandsOnDoubleClick(True)
        tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # QSS перекрывает ForegroundRole у элементов, поэтому цветной текст
        # статуса рисует делегат.
        self._status_delegate = _StatusTextDelegate(tree)
        tree.setItemDelegate(self._status_delegate)

        header = tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, STATUS_COLUMN_WIDTH)

        tree.currentItemChanged.connect(
            lambda current, _previous: self._on_tree_current_changed(
                current, tree
            )
        )
        tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        return tree

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------
    @property
    def report(self) -> Report | None:
        return self._report

    @property
    def na_rows(self) -> list[_ResultRow]:
        """Строки секции «Не применимо (N/A)» (для тестов/отладки)."""
        return self.na_section.rows

    @property
    def skip_rows(self) -> list[_ResultRow]:
        """Строки секции «Не удалось проверить» (для тестов/отладки)."""
        return self.skip_section.rows

    def set_na_visible(self, visible: bool) -> None:
        """Показывать ли секцию «Не применимо (N/A)» (чекбокс в карточке ввода)."""
        self._na_visible = bool(visible)
        self._apply_na_visibility()

    def set_loading(self, loading: bool) -> None:
        """Переводит карточку в состояние «идёт проверка»."""
        self._loading = bool(loading)
        if loading:
            self.banner_widget.hide()
            self._report = None
            self._result_by_key.clear()
            self._key_by_object.clear()
            self.check_tree.clear()
            self.na_section.clear()
            self.skip_section.clear()
            self.na_section.hide()
            self.skip_section.hide()
            self._set_idle_score()
            self.score_title.setText(tr("Проверка…"))
            self.score_hint.setText(
                tr("Собираем данные сайта и прогоняем проверки.")
            )
            self.chips_widget.hide()
            self.stack.setCurrentWidget(self.loading_page)

    def set_progress(self, fraction: float, message: str) -> None:
        """Обновляет подсказку на карточке процента во время проверки."""
        if not self._loading:
            return
        _ = fraction
        if message:
            self.score_hint.setText(message)

    def show_empty_state(self) -> None:
        """Сбрасывает результаты к исходному состоянию."""
        self._loading = False
        self._report = None
        self._result_by_key.clear()
        self._key_by_object.clear()
        self.check_tree.clear()
        self.na_section.clear()
        self.skip_section.clear()
        self.na_section.hide()
        self.skip_section.hide()
        self.banner_widget.hide()
        self._set_idle_score()
        self.chips_widget.hide()
        self.stack.setCurrentWidget(self.empty_page)
        self.selected_result_changed.emit(None)

    def show_error(self, message: str) -> None:
        """Показывает мягкий баннер ошибки вместо отчёта."""
        self.show_empty_state()
        text = (message or "").strip() or tr("Не удалось выполнить проверку.")
        low = text.lower()
        # Не повторяем один и тот же совет дважды (сообщение уже про таймаут).
        if "таймаут" in low or "настройк" in low:
            hint = tr("Проверьте адрес сайта.")
        else:
            hint = tr("Проверьте адрес или увеличьте таймаут в настройках.")
        self.error_label.setText(f"{text}\n{hint}")
        self.banner_widget.show()
        self.stack.setCurrentWidget(self.empty_page)

    def show_report(self, report: Report) -> None:
        """Заполняет дерево, карточку процента и секции готовым отчётом."""
        self._loading = False
        self._report = report
        self.banner_widget.hide()
        self._result_by_key.clear()
        self._key_by_object.clear()
        self.check_tree.clear()
        self.na_section.clear()
        self.skip_section.clear()

        self._populate_check_tree(report)
        self._update_score(report)
        self._update_chips(report)
        self._populate_na_section(report)
        self._populate_skip_section(report)

        self.chips_widget.show()
        self.stack.setCurrentWidget(self.check_tree)

    # ------------------------------------------------------------------
    # Заполнение
    # ------------------------------------------------------------------
    def _populate_check_tree(self, report: Report) -> None:
        index = 0
        # Статус в правой колонке — цветной и полужирный (читается с первого
        # взгляда даже без иконки).
        status_font = QFont(self.check_tree.font())
        status_font.setWeight(QFont.Weight.DemiBold)
        for category, sections in report.grouped_by_section():
            all_results = [
                result for _section, items in sections for result in items
            ]
            applicable = [
                result for result in all_results if result.affects_score
            ]
            passed = [
                result
                for result in all_results
                if result.status is CheckStatus.PASS
            ]
            group_title = tr(CATEGORY_LABELS.get(category, category))
            denominator = len(applicable) or len(all_results)
            if denominator:
                group_title += f" · {len(passed)} {tr('из')} {denominator}"
            group = QTreeWidgetItem(self.check_tree)
            group.setText(0, group_title)
            group.setToolTip(
                0,
                trf(
                    "Проверок в блоке: {total}, применимых: {applicable}, "
                    "пройдено: {passed}",
                    total=len(all_results),
                    applicable=len(applicable),
                    passed=len(passed),
                ),
            )
            group.setFlags(Qt.ItemFlag.ItemIsEnabled)
            group_font = QFont(self.check_tree.font())
            group_font.setBold(True)
            group.setFont(0, group_font)
            group.setFont(1, group_font)
            group.setForeground(0, QBrush(QColor(PALETTE["text_heading"])))
            group.setFirstColumnSpanned(True)

            for section, section_results in sections:
                section_item = QTreeWidgetItem(group)
                section_item.setText(0, tr(section_label(section)))
                section_item.setFont(0, _section_font(self.check_tree.font()))
                section_item.setForeground(
                    0, QBrush(QColor(PALETTE["text_dim"]))
                )
                section_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                section_item.setFirstColumnSpanned(True)
                section_item.setToolTip(0, tr(section_label(section)))

                for result in section_results:
                    key = str(index)
                    index += 1
                    self._result_by_key[key] = result
                    self._key_by_object[id(result)] = key

                    child = QTreeWidgetItem(section_item)
                    child.setData(0, ITEM_KEY_ROLE, key)
                    child.setText(0, result.title or result.check_id)
                    child.setIcon(
                        0, QIcon(status_dot(result.status, STATUS_DOT_SIZE))
                    )
                    child.setText(1, result.status.label_ru)
                    child.setFont(1, status_font)
                    child.setForeground(
                        1, QBrush(QColor(_status_color(result.status)))
                    )
                    child.setToolTip(0, result.message)
                    child.setToolTip(1, result.status.label_ru)
                    child.setFlags(
                        Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsSelectable
                    )
                    child.setTextAlignment(
                        1,
                        Qt.AlignmentFlag.AlignLeft
                        | Qt.AlignmentFlag.AlignVCenter,
                    )
                section_item.setExpanded(True)
            group.setExpanded(True)

    def _update_score(self, report: Report) -> None:
        self.score_value.setTextFormat(Qt.TextFormat.PlainText)
        self.score_value.setText(f"{report.score}%")
        set_prop(self.score_value, "level", score_level(report.score))
        from app.core.engine.scoring import score_grade

        title, hint = score_grade(report.score)
        self.score_title.setText(tr(title))
        self.score_hint.setText(tr(hint))

    def _update_chips(self, report: Report) -> None:
        counts = report.counts()
        mapping = {
            "pass": ("Пройдено", CheckStatus.PASS.value),
            "warn": ("Замечаний", CheckStatus.WARN.value),
            "fail": ("Нарушений", CheckStatus.FAIL.value),
            "na": ("N/A", CheckStatus.NOT_APPLICABLE.value),
            "skip": ("Не проверено", CheckStatus.SKIP.value),
        }
        for kind, (title, status_key) in mapping.items():
            chip = self.chips.get(kind)
            if chip is not None:
                chip.setText(f"{tr(title)} {counts.get(status_key, 0)}")

    def _populate_na_section(self, report: Report) -> None:
        rows: list[tuple[CheckResult, str]] = []
        for result in report.not_applicable():
            explanation = (
                result.message
                or tr("Проверка не применима к этому сайту.")
            ).strip()
            rows.append((result, explanation))
        self.na_section.set_rows(rows)
        has_items = bool(rows)
        self.na_toggle.setChecked(has_items)
        self.na_section.set_expanded(has_items)
        self._apply_na_visibility()

    def _populate_skip_section(self, report: Report) -> None:
        rows: list[tuple[CheckResult, str]] = []
        for result in report.skipped():
            reason = (
                result.message
                or result.error
                or tr("Причина неизвестна")
            ).strip()
            rows.append((result, reason))
        self.skip_section.set_rows(rows)
        has_items = bool(rows)
        # «Не удалось проверить» по умолчанию свёрнуто.
        self.skip_toggle.setChecked(False)
        self.skip_section.set_expanded(False)
        self.skip_section.setVisible(has_items)

    # ------------------------------------------------------------------
    # Вспомогательное состояние
    # ------------------------------------------------------------------
    def _set_idle_score(self) -> None:
        self.score_value.setTextFormat(Qt.TextFormat.RichText)
        self.score_value.setText(
            f'<span style="color:{IDLE_SCORE_COLOR};">—</span>'
        )
        set_prop(self.score_value, "level", "")
        self.score_title.setText(tr("Нет данных"))
        self.score_hint.setText(
            tr("Запустите проверку, чтобы увидеть результат.")
        )
        self.chips_widget.hide()

    def _apply_na_visibility(self) -> None:
        has_items = bool(self.na_section.results)
        self.na_section.setVisible(bool(self._na_visible and has_items))

    def _on_tree_current_changed(
        self,
        current: QTreeWidgetItem | None,
        tree: QTreeWidget,
    ) -> None:
        _ = tree
        if current is None:
            return
        key = current.data(0, ITEM_KEY_ROLE)
        if not key:
            return
        result = self._result_by_key.get(str(key))
        if result is not None:
            self.selected_result_changed.emit(result)

    def _on_tree_item_double_clicked(
        self,
        item: QTreeWidgetItem,
        _column: int,
    ) -> None:
        key = item.data(0, ITEM_KEY_ROLE)
        if not key:
            return
        result = self._result_by_key.get(str(key))
        if result is not None and result.check_id:
            self.methodology_check_requested.emit(result.check_id)


# ---------------------------------------------------------------------------
# Правая часть: панель деталей
# ---------------------------------------------------------------------------


class DetailPanel(QFrame):
    """Панель с деталями выбранной проверки."""

    #: Нажата ссылка «Подробнее — см. Критерии проверок, п. 4.X».
    methodology_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame(self)
        header.setObjectName("DetailHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 12, 18, 10)
        header_layout.setSpacing(0)
        header_title = QLabel(tr("Детали проверки"), header)
        header_title.setObjectName("SectionTitle")
        header_title.setTextFormat(Qt.TextFormat.PlainText)
        header_layout.addWidget(header_title)
        layout.addWidget(header)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        layout.addWidget(self.scroll, 1)

        self.content = QWidget(self.scroll)
        self._content_layout = QVBoxLayout(self.content)
        self._content_layout.setContentsMargins(18, 16, 18, 16)
        self._content_layout.setSpacing(10)
        self.scroll.setWidget(self.content)

        self._current: CheckResult | None = None
        self.clear()

    # ------------------------------------------------------------------
    @property
    def current_result(self) -> CheckResult | None:
        return self._current

    def clear(self) -> None:
        """Сбрасывает панель к подсказке «Выберите проверку слева»."""
        self._current = None
        self._clear_content()
        placeholder = _plain_label(
            tr("Выберите проверку слева"), "DetailMuted", self.content
        )
        placeholder.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self._content_layout.addWidget(placeholder)
        self._content_layout.addStretch(1)

    def show_result(self, result: CheckResult | None) -> None:
        """Показывает детали проверки (``None`` — сброс)."""
        if result is None:
            self.clear()
            return
        self._current = result
        self._clear_content()

        title = _plain_label(
            result.title or result.check_id, "DetailTitle", self.content
        )
        self._content_layout.addWidget(title)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(8)
        status_row.addWidget(
            _make_chip(
                result.status.label_ru,
                CHIP_KINDS.get(result.status.value, "na"),
                self.content,
            ),
            0,
        )
        if result.status in (CheckStatus.FAIL, CheckStatus.WARN):
            severity = QLabel(self.content)
            severity.setObjectName("Hint")
            severity.setTextFormat(Qt.TextFormat.RichText)
            severity.setText(
                f'<span style="color:{_status_color(result.status)};font-size:11px;">'
                f"{html_utils.escape(tr('Приоритет'))}: "
                f"{html_utils.escape(result.severity.label_ru)}</span>"
            )
            status_row.addWidget(severity, 0, Qt.AlignmentFlag.AlignVCenter)
        status_row.addStretch(1)
        self._content_layout.addLayout(status_row)

        if result.status is CheckStatus.NOT_APPLICABLE:
            na_text = (
                result.message
                or tr("Проверка не применима к этому сайту.")
            ) + "\n\n" + tr("Проверка не влияет на процент соответствия.")
            self._content_layout.addWidget(
                _plain_label(na_text, "DetailNa", self.content)
            )
        else:
            self._add_section(tr("Сообщение").upper())
            self._content_layout.addWidget(
                _plain_label(result.message or "—", "DetailBody", self.content)
            )

        evidence = [
            item
            for item in result.evidence
            if (item.value or "").strip() or item.selector
        ]
        if evidence:
            self._add_section(tr("Подтверждение").upper())
            for item in evidence:
                self._content_layout.addWidget(self._build_evidence_label(item))

        if (
            result.recommendation
            and result.status is not CheckStatus.NOT_APPLICABLE
        ):
            recommendation = _plain_label(
                f"{tr('Как исправить')}: {result.recommendation}",
                "DetailRecommendation",
                self.content,
            )
            self._content_layout.addWidget(recommendation)

        self._add_fines_block(result)
        self._add_methodology_link(result)
        self._content_layout.addStretch(1)

    # ------------------------------------------------------------------
    def _clear_content(self) -> None:
        _clear_layout(self._content_layout)

    def _add_section(self, title: str) -> None:
        label = QLabel(title, self.content)
        label.setObjectName("DetailSection")
        label.setTextFormat(Qt.TextFormat.PlainText)
        self._content_layout.addWidget(label)

    def _add_fines_block(self, result: CheckResult) -> None:
        """Блок «Потенциальная сумма штрафа» по данным методологии.

        Скрывается целиком, если справочник недоступен, ``has_fines`` ложно
        или ни одной суммы нет, — пустых заголовков в панели быть не должно.
        """
        info = _methodology_for(result.check_id)
        if info is None or not bool(getattr(info, "has_fines", True)):
            return

        rows: list[tuple[str, str]] = []
        try:
            fine_rows = getattr(info, "fine_rows", None)
            raw_rows = fine_rows() if callable(fine_rows) else []
        except Exception:  # noqa: BLE001 - методология не должна ронять UI
            raw_rows = []
        for caption, amount in raw_rows or []:
            text = str(amount or "").strip()
            if text:
                rows.append((str(caption), text))
        if not rows:
            # Запасной путь, если модель методологии пришла без fine_rows().
            individual = str(
                getattr(info, "fine_individual", "") or ""
            ).strip()
            legal = str(getattr(info, "fine_legal", "") or "").strip()
            if individual:
                rows.append((tr("Для физлица"), individual))
            if legal:
                rows.append((tr("Для юрлица"), legal))
        if not rows:
            return

        basis = str(getattr(info, "fine_basis", "") or "").strip()
        note = str(getattr(info, "fine_note", "") or "").strip()

        header = QLabel(tr("ПОТЕНЦИАЛЬНАЯ СУММА ШТРАФА"), self.content)
        header.setObjectName("InfoSectionLabel")
        header.setTextFormat(Qt.TextFormat.PlainText)
        self._content_layout.addWidget(header)

        frame = QFrame(self.content)
        frame.setObjectName("ConclusionItem")
        frame.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(12, 9, 12, 9)
        frame_layout.setSpacing(4)

        caption_color = PALETTE["text_muted"]
        amount_color = PALETTE.get("fail", "#B87A6E")
        for caption, amount in rows:
            row = QLabel(frame)
            row.setObjectName("DetailMuted")
            row.setTextFormat(Qt.TextFormat.RichText)
            row.setWordWrap(True)
            row.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            row.setText(
                f'<span style="color:{caption_color};">'
                f"{html_utils.escape(caption)} — </span>"
                f'<span style="color:{amount_color};font-weight:600;">'
                f"{html_utils.escape(amount)}</span>"
            )
            frame_layout.addWidget(row)

        if basis:
            basis_label = QLabel(f"{tr('Основание')}: {basis}", frame)
            basis_label.setObjectName("Hint")
            basis_label.setTextFormat(Qt.TextFormat.PlainText)
            basis_label.setWordWrap(True)
            basis_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            frame_layout.addWidget(basis_label)

        if note:
            note_label = QLabel(frame)
            note_label.setObjectName("Hint")
            note_label.setTextFormat(Qt.TextFormat.RichText)
            note_label.setWordWrap(True)
            note_label.setText(
                f'<span style="font-size:10px;color:{PALETTE["text_dim"]};">'
                f"{html_utils.escape(note)}</span>"
            )
            frame_layout.addWidget(note_label)

        self._content_layout.addWidget(frame)

    def _add_methodology_link(self, result: CheckResult) -> None:
        """Маленькая ссылка «Подробнее — см. Критерии проверок, п. 4.X»."""
        number = ""
        try:
            # Локальный импорт: справочник может отсутствовать в сборке.
            from app.core.content.loader import methodology_for

            info = methodology_for(result.check_id)
            number = info.id if info is not None else ""
        except Exception:  # noqa: BLE001 - справочник не должен ломать детали
            number = ""
        text = (
            trf(
                "Подробнее — см. Критерии проверок, п. {number}.",
                number=number,
            )
            if number
            else tr("Подробнее — см. Критерии проверок")
        )
        button = QPushButton(text, self.content)
        button.setObjectName("GhostButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
        )
        button.setToolTip(
            tr("Открыть справочник «Критерии проверок» на этой проверке")
        )
        button.clicked.connect(
            lambda _checked=False: self.methodology_requested.emit(
                result.check_id
            )
        )
        self._content_layout.addWidget(
            button, 0, Qt.AlignmentFlag.AlignLeft
        )

    def _build_evidence_label(self, item: Evidence) -> QLabel:
        parts: list[str] = []
        if item.label:
            parts.append(
                f'<span style="color:{PALETTE["text_muted"]};font-size:11px;">'
                f"{html_utils.escape(item.label)}</span>"
            )
        if (item.value or "").strip():
            parts.append(
                f'<span style="color:{PALETTE["text"]};font-size:12px;">'
                f"{html_utils.escape(item.value)}</span>"
            )
        html = " — ".join(parts)
        if item.selector:
            if html:
                html += "<br>"
            html += (
                f'<span style="font-family:Consolas;color:{PALETTE["text_muted"]};'
                f'font-size:11px;">{html_utils.escape(item.selector)}</span>'
            )
        label = QLabel(html, self.content)
        label.setObjectName("DetailBody")
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        return label
