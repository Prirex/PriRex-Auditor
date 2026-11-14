"""Главное окно PriRex Auditor: ввод адреса, сканирование, отчёт, экспорт."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.config import AppConfig, get_config, get_config_manager
from app.core.models import Report, RunOptions, SiteContext
from app.services.targets import normalize_target
from app.i18n import tr, trf
from app.paths import (
    default_report_dir,
    ensure_report_dir,
    screenshots_dir,
    temp_report_dir,
)
from app.ui.about_dialog import AboutDialog
from app.ui.branding import (
    AUTHOR_LINK_URL,
    BrandFooter,
    LinkLabel,
    logo_pixmap,
    open_boosty,
    open_external,
)
from app.ui.icons import app_icon, asset_icon
from app.ui.results_view import DetailPanel, ResultsView
from app.ui.fine_summary import FineSummaryCard
from app.ui.settings_dialog import SettingsDialog
from app.ui.theme import PALETTE
from app.ui.worker import ScanWorker
from app.version import (
    APP_DISPLAY_NAME,
    APP_SUBTITLE,
    APP_TITLE,
    DOWNLOAD_URL,
    __version__,
)

__all__ = ["MainWindow"]

#: Соответствие UI-действия и значения ``ExportFormat``.
_EXPORT_KINDS: dict[str, str] = {
    "pdf": "PDF",
    "markdown": "MARKDOWN",
    "html": "HTML",
    "json": "JSON",
}

#: Фильтры диалога сохранения для каждого формата.
_EXPORT_FILTERS: dict[str, str] = {
    "pdf": "PDF (*.pdf)",
    "markdown": "Markdown (*.md)",
    "html": "HTML (*.html)",
    "json": "JSON (*.json)",
}


class _UpdateCheckWorker(QThread):
    """Фоновая проверка обновлений (не блокирует UI)."""

    #: Автопроверка: новая версия действительно доступна.
    available = Signal(object)
    #: Ручная проверка: всегда сообщает результат (``UpdateInfo`` или ``None``).
    checked = Signal(object)

    def __init__(
        self,
        config: AppConfig,
        parent: QWidget | None = None,
        *,
        manual: bool = False,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self.manual = bool(manual)

    def run(self) -> None:  # noqa: D401 - Qt API
        info: object | None = None
        try:
            # Локальный импорт: апдейтер может появиться позже и не тянет Qt.
            from app.updater import check_for_updates_sync

            info = check_for_updates_sync(self._config, __version__)
        except Exception:  # noqa: BLE001 - сетевые ошибки игнорируем молча
            info = None
        if self.manual:
            self.checked.emit(info)
        elif info is not None and getattr(info, "available", False):
            self.available.emit(info)


class MainWindow(QMainWindow):
    """Главное окно приложения."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config: AppConfig = get_config()
        self._report: Report | None = None
        self._context: SiteContext | None = None
        self._worker: ScanWorker | None = None
        self._update_worker: _UpdateCheckWorker | None = None
        self._conclusion_dialog: object | None = None
        self._last_scan_url = ""

        self.setObjectName("MainWindow")
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(app_icon())
        self.resize(1280, 800)
        self.setMinimumSize(1100, 720)

        self._build_menu()
        self._build_ui(self._config)
        self._connect_signals()
        self._init_timers()

    # ------------------------------------------------------------------
    # Построение интерфейса
    # ------------------------------------------------------------------
    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu(tr("Файл"))

        self.settings_action = QAction(tr("Настройки"), self)
        self.settings_action.setShortcut(QKeySequence("Ctrl+,"))
        self.settings_action.triggered.connect(self.open_settings)
        file_menu.addAction(self.settings_action)

        self.rescan_action = QAction(tr("Проверить заново"), self)
        self.rescan_action.setShortcut(QKeySequence("F5"))
        self.rescan_action.triggered.connect(self._rescan)
        file_menu.addAction(self.rescan_action)

        self.open_reports_action = QAction(tr("Открыть папку отчётов"), self)
        self.open_reports_action.triggered.connect(self._open_reports_folder)
        file_menu.addAction(self.open_reports_action)

        file_menu.addSeparator()

        # Экспорт живёт в меню «Файл»; в нижней панели — только PDF и «Заключение».
        self.export_pdf_action = QAction(tr("Экспорт в PDF…"), self)
        self.export_pdf_action.triggered.connect(
            lambda: self._export_report("pdf")
        )
        file_menu.addAction(self.export_pdf_action)

        self.export_md_action = QAction(tr("Экспорт в Markdown…"), self)
        self.export_md_action.triggered.connect(
            lambda: self._export_report("markdown")
        )
        file_menu.addAction(self.export_md_action)

        self.export_html_action = QAction(tr("Экспорт в HTML…"), self)
        self.export_html_action.triggered.connect(
            lambda: self._export_report("html")
        )
        file_menu.addAction(self.export_html_action)

        self.export_json_action = QAction(tr("Экспорт в JSON…"), self)
        self.export_json_action.triggered.connect(
            lambda: self._export_report("json")
        )
        file_menu.addAction(self.export_json_action)

        self.copy_link_action = QAction(tr("Копировать ссылку на отчёт"), self)
        self.copy_link_action.triggered.connect(self._copy_report_link)
        file_menu.addAction(self.copy_link_action)

        file_menu.addSeparator()

        self.quit_action = QAction(tr("Выход"), self)
        self.quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self.quit_action.triggered.connect(self.close)
        file_menu.addAction(self.quit_action)

        help_menu = menu_bar.addMenu(tr("Справка"))

        self.methodology_action = QAction(tr("Критерии проверок"), self)
        self.methodology_action.setShortcut(QKeySequence("F1"))
        self.methodology_action.triggered.connect(
            lambda: self.open_methodology(None)
        )
        help_menu.addAction(self.methodology_action)

        self.how_it_works_action = QAction(tr("Как работает приложение"), self)
        self.how_it_works_action.triggered.connect(
            lambda: self.open_how_it_works(None)
        )
        help_menu.addAction(self.how_it_works_action)

        help_menu.addSeparator()

        self.boosty_action = QAction(tr("Поддержать автора"), self)
        self.boosty_action.triggered.connect(lambda: open_boosty(self))
        help_menu.addAction(self.boosty_action)

        self.author_action = QAction(tr("Открыть сайт автора"), self)
        self.author_action.triggered.connect(
            lambda: open_external(AUTHOR_LINK_URL)
        )
        help_menu.addAction(self.author_action)

        help_menu.addSeparator()

        self.about_action = QAction(tr("О программе"), self)
        self.about_action.triggered.connect(self.show_about)
        help_menu.addAction(self.about_action)

    def _build_ui(self, config: AppConfig) -> None:
        central = QWidget(self)
        central.setObjectName("Root")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header(central))

        header_line = QFrame(central)
        header_line.setObjectName("HLine")
        header_line.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(header_line)

        root.addWidget(self._build_toolbar(central))
        root.addWidget(self._build_update_banner(central))
        root.addWidget(self._build_input_card(central, config))
        root.addWidget(self._build_main_area(central), 1)
        root.addWidget(self._build_bottom_bar(central))

        self.footer = BrandFooter(central)
        root.addWidget(self.footer)

    def _build_toolbar(self, parent: QWidget) -> QWidget:
        """Тонкая панель над карточкой ввода: версия, обновление, справка."""
        toolbar = QWidget(parent)
        toolbar.setObjectName("Toolbar")
        toolbar.setFixedHeight(36)
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        self.version_label = QLabel(self._version_text(), toolbar)
        self.version_label.setObjectName("VersionLabel")
        self.version_label.setTextFormat(Qt.TextFormat.PlainText)
        self.version_label.setToolTip(
            tr("Версия приложения и дата актуальности критериев проверок")
        )
        layout.addWidget(
            self.version_label, 0, Qt.AlignmentFlag.AlignVCenter
        )

        self.update_button = QPushButton(tr("Проверить обновление"), toolbar)
        self.update_button.setObjectName("GhostButton")
        self.update_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_button.setToolTip(
            tr("Проверить наличие новой версии приложения")
        )
        layout.addWidget(self.update_button, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addStretch(1)

        self.how_it_works_button = QPushButton(
            tr("Как работает приложение"), toolbar
        )
        self.how_it_works_button.setObjectName("howItWorksButton")
        self.how_it_works_button.setCursor(Qt.CursorShape.PointingHandCursor)
        help_icon = asset_icon("help.svg")
        if not help_icon.isNull():
            self.how_it_works_button.setIcon(help_icon)
            self.how_it_works_button.setIconSize(QSize(14, 14))
        layout.addWidget(
            self.how_it_works_button, 0, Qt.AlignmentFlag.AlignVCenter
        )

        self.toolbar = toolbar
        return toolbar

    def _version_text(self) -> str:
        text = f"{tr('Версия')} {__version__}"
        try:
            # Локальный импорт: справочник методологии может отсутствовать.
            from app.core.content.loader import methodology_updated_at

            updated = (methodology_updated_at() or "").strip()
        except Exception:  # noqa: BLE001 - дата не должна ломать UI
            updated = ""
        if updated:
            text += f" · {tr('проверки актуальны на')} {updated}"
        return text

    def _build_header(self, parent: QWidget) -> QWidget:
        header = QWidget(parent)
        header.setFixedHeight(44)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 3, 16, 3)
        layout.setSpacing(10)

        self.logo_label = QLabel(header)
        pixmap = logo_pixmap(24)
        if pixmap is not None:
            self.logo_label.setPixmap(pixmap)
            self.logo_label.setFixedSize(pixmap.size())
        else:
            self.logo_label.setText("PriRex")
            self.logo_label.setObjectName("AppTitle")
        layout.addWidget(self.logo_label, 0, Qt.AlignmentFlag.AlignVCenter)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(0)
        self.app_title = QLabel(APP_DISPLAY_NAME, header)
        self.app_title.setObjectName("AppTitle")
        self.app_title.setTextFormat(Qt.TextFormat.PlainText)
        self.app_subtitle = QLabel(tr(APP_SUBTITLE), header)
        self.app_subtitle.setObjectName("AppSubtitle")
        self.app_subtitle.setTextFormat(Qt.TextFormat.PlainText)
        title_box.addWidget(self.app_title)
        title_box.addWidget(self.app_subtitle)
        title_box.addStretch(1)
        layout.addLayout(title_box, 0)

        layout.addStretch(1)

        self.settings_button = QPushButton(tr("Настройки"), header)
        self.settings_button.setObjectName("GhostButton")
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.settings_button, 0, Qt.AlignmentFlag.AlignVCenter)
        return header

    def _build_update_banner(self, parent: QWidget) -> QWidget:
        container = QWidget(parent)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(16, 8, 16, 0)
        container_layout.setSpacing(0)

        self.update_banner = QFrame(container)
        self.update_banner.setObjectName("Card")
        self.update_banner.setFixedHeight(40)
        banner_layout = QHBoxLayout(self.update_banner)
        banner_layout.setContentsMargins(12, 5, 8, 5)
        banner_layout.setSpacing(8)
        self.update_banner_layout = banner_layout

        self.update_label = QLabel(self.update_banner)
        self.update_label.setObjectName("DetailBody")
        self.update_label.setTextFormat(Qt.TextFormat.PlainText)
        banner_layout.addWidget(self.update_label, 0, Qt.AlignmentFlag.AlignVCenter)
        banner_layout.addStretch(1)

        self.update_link = LinkLabel(tr("Скачать"), DOWNLOAD_URL, self.update_banner)
        banner_layout.addWidget(self.update_link, 0, Qt.AlignmentFlag.AlignVCenter)

        self.update_close_button = QPushButton("×", self.update_banner)
        self.update_close_button.setObjectName("GhostButton")
        self.update_close_button.setFixedSize(24, 24)
        self.update_close_button.setToolTip(tr("Скрыть"))
        self.update_close_button.clicked.connect(container.hide)
        banner_layout.addWidget(self.update_close_button, 0, Qt.AlignmentFlag.AlignVCenter)

        container_layout.addWidget(self.update_banner)
        container.hide()
        self.update_banner_container = container
        return container

    def _build_input_card(self, parent: QWidget, config: AppConfig) -> QWidget:
        wrapper = QWidget(parent)
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(16, 4, 16, 0)
        wrapper_layout.setSpacing(0)

        card = QFrame(wrapper)
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(4)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(8)

        self.folder_button = QPushButton(tr("Папка…"), card)
        self.folder_button.setObjectName("SecondaryButton")
        self.folder_button.setFixedHeight(40)
        self.folder_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folder_button.setToolTip(
            tr("Выбрать локальную папку с сайтом (например, до публикации)")
        )
        input_row.addWidget(self.folder_button, 0)

        self.file_button = QPushButton(tr("Файл…"), card)
        self.file_button.setObjectName("SecondaryButton")
        self.file_button.setFixedHeight(40)
        self.file_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.file_button.setToolTip(
            tr(
                "Выбрать конкретную страницу сайта (index.html или файл без "
                "расширения) для локальной проверки"
            )
        )
        input_row.addWidget(self.file_button, 0)

        self.url_input = QLineEdit(card)
        self.url_input.setObjectName("UrlInput")
        self.url_input.setPlaceholderText(
            tr("example.com, https://example.com, путь к папке или файлу сайта")
        )
        self.url_input.setToolTip(
            tr(
                "Можно проверить адрес сайта, локальную папку с index.html или "
                "конкретную страницу (в том числе файл без расширения). "
                "HTTPS и заголовки проверяются только у опубликованного сайта."
            )
        )
        self.url_input.setText(config.last_url or "")
        self.url_input.setMinimumHeight(40)
        input_row.addWidget(self.url_input, 1)

        self.check_button = QPushButton(tr("Проверить"), card)
        self.check_button.setObjectName("PrimaryButton")
        self.check_button.setMinimumWidth(132)
        self.check_button.setFixedHeight(40)
        self.check_button.setCursor(Qt.CursorShape.PointingHandCursor)
        input_row.addWidget(self.check_button, 0)

        self.cancel_button = QPushButton(tr("Отмена"), card)
        self.cancel_button.setObjectName("SecondaryButton")
        self.cancel_button.setFixedHeight(40)
        self.cancel_button.hide()
        input_row.addWidget(self.cancel_button, 0)

        # Иерархия кнопок: «Проверить» — акцентная, «Критерии проверок» — outline.
        self.methodology_button = QPushButton(tr("Критерии проверок"), card)
        self.methodology_button.setObjectName("methodologyButton")
        self.methodology_button.setFixedHeight(40)
        self.methodology_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.methodology_button.setToolTip(
            tr("Открыть справочник: что и на основании чего проверяется")
        )
        input_row.addWidget(self.methodology_button, 0)
        layout.addLayout(input_row)

        checks_row = QHBoxLayout()
        checks_row.setContentsMargins(0, 0, 0, 0)
        checks_row.setSpacing(16)
        self.deep_check = QCheckBox(tr("Глубокий анализ (Playwright)"), card)
        self.deep_check.setChecked(bool(config.deep_analysis))
        self.trackers_check = QCheckBox(tr("Проверять сторонние трекеры"), card)
        self.trackers_check.setChecked(bool(config.check_trackers))
        self.show_na_check = QCheckBox(
            tr("Показывать проверки со статусом N/A"), card
        )
        self.show_na_check.setChecked(bool(config.show_na))
        checks_row.addWidget(self.deep_check, 0)
        checks_row.addWidget(self.trackers_check, 0)
        checks_row.addWidget(self.show_na_check, 0)
        checks_row.addStretch(1)
        layout.addLayout(checks_row)

        self.progress_bar = QProgressBar(card)
        self.progress_bar.setObjectName("ScanProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        self.progress_label = QLabel(card)
        self.progress_label.setObjectName("ProgressLabel")
        self.progress_label.setWordWrap(True)
        self.progress_label.setTextFormat(Qt.TextFormat.PlainText)
        self.progress_label.hide()
        layout.addWidget(self.progress_label)

        self.notes_label = QLabel(card)
        self.notes_label.setObjectName("Hint")
        self.notes_label.setTextFormat(Qt.TextFormat.PlainText)
        self.notes_label.setWordWrap(True)
        self.notes_label.setMaximumHeight(34)
        self.notes_label.hide()
        layout.addWidget(self.notes_label)

        wrapper_layout.addWidget(card)
        self.input_card = card
        return wrapper

    def _build_main_area(self, parent: QWidget) -> QWidget:
        container = QWidget(parent)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 2, 16, 0)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, container)
        self.splitter.setHandleWidth(10)
        self.splitter.setChildrenCollapsible(False)

        self.results_view = ResultsView(self.splitter)
        self.results_view.setMinimumWidth(480)

        self.details_container = QWidget(self.splitter)
        details_layout = QVBoxLayout(self.details_container)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(6)
        self.details_panel = DetailPanel(self.details_container)
        self.fine_summary = FineSummaryCard(self.details_container)
        details_layout.addWidget(self.details_panel, 1)
        details_layout.addWidget(self.fine_summary, 0)

        self.splitter.addWidget(self.results_view)
        self.splitter.addWidget(self.details_container)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([820, 420])

        layout.addWidget(self.splitter)
        self.main_area = container
        return container

    def _build_bottom_bar(self, parent: QWidget) -> QWidget:
        bar = QWidget(parent)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        self.export_pdf_button = QPushButton(tr("Экспорт в PDF"), bar)
        self.export_pdf_button.setObjectName("SecondaryButton")
        layout.addWidget(self.export_pdf_button, 0)

        self.conclusion_button = QPushButton(tr("Заключение"), bar)
        self.conclusion_button.setObjectName("SecondaryButton")
        layout.addWidget(self.conclusion_button, 0)

        layout.addStretch(1)

        self.result_hint = QLabel("", bar)
        self.result_hint.setObjectName("Hint")
        self.result_hint.setTextFormat(Qt.TextFormat.PlainText)
        self.result_hint.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self.result_hint, 0)
        self.bottom_bar = bar
        self._set_export_enabled(False)
        return bar

    def _init_timers(self) -> None:
        self._progress_hide_timer = QTimer(self)
        self._progress_hide_timer.setSingleShot(True)
        self._progress_hide_timer.timeout.connect(self._hide_progress)

        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._maybe_check_updates)
        self._update_timer.start(1200)

    def _connect_signals(self) -> None:
        self.check_button.clicked.connect(self.start_scan)
        self.url_input.returnPressed.connect(self.start_scan)
        self.folder_button.clicked.connect(self.choose_local_folder)
        self.file_button.clicked.connect(self.choose_local_file)
        self.cancel_button.clicked.connect(self.cancel_scan)
        self.settings_button.clicked.connect(self.open_settings)
        self.methodology_button.clicked.connect(
            lambda: self.open_methodology(None)
        )
        self.how_it_works_button.clicked.connect(
            lambda: self.open_how_it_works(None)
        )
        self.update_button.clicked.connect(self.check_updates_manual)
        self.conclusion_button.clicked.connect(self.open_conclusion)
        self.show_na_check.toggled.connect(self._on_show_na_toggled)
        self.results_view.selected_result_changed.connect(
            self.details_panel.show_result
        )
        self.results_view.settings_requested.connect(self.open_settings)
        self.results_view.methodology_check_requested.connect(
            self.open_methodology
        )
        self.details_panel.methodology_requested.connect(
            self.open_methodology
        )
        self.export_pdf_button.clicked.connect(
            lambda: self._export_report("pdf")
        )
        self.footer.about_requested.connect(self.show_about)

    # ------------------------------------------------------------------
    # Сканирование
    # ------------------------------------------------------------------
    def start_scan(self) -> None:
        """Валидирует адрес или локальный путь и запускает проверку."""
        if self._worker is not None:
            return

        target = normalize_target(self.url_input.text())
        if not target.ok:
            self._set_progress_error(
                target.error or tr("Некорректный адрес сайта")
            )
            self.url_input.setFocus()
            return

        self.url_input.setText(target.display)
        self._last_scan_url = target.value
        self._report = None
        self._context = None
        self._set_export_enabled(False)
        self.result_hint.setText("")
        self.details_panel.clear()
        self.fine_summary.set_report(None)
        self._set_busy(True)

        worker = ScanWorker(target.value, self._build_run_options(), self)
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_scan_finished)
        worker.failed.connect(self._on_scan_failed)
        worker.cancelled.connect(self._on_scan_cancelled)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        worker.start()

    def choose_local_folder(self) -> None:
        """Выбор локальной папки с сайтом (проверка без публикации)."""
        start_dir = self._local_start_dir()
        folder = QFileDialog.getExistingDirectory(
            self, tr("Выберите папку с сайтом"), start_dir
        )
        if folder:
            self.url_input.setText(str(Path(folder)))
            self.url_input.setFocus()

    def choose_local_file(self) -> None:
        """Выбор конкретной HTML-страницы (включая файлы без расширения)."""
        start_dir = self._local_start_dir()
        chosen, _selected_filter = QFileDialog.getOpenFileName(
            self,
            tr("Выберите страницу сайта"),
            start_dir,
            tr("HTML-страницы (*.html *.htm *.xhtml);;Все файлы (*.*)"),
        )
        if chosen:
            self.url_input.setText(str(Path(chosen)))
            self.url_input.setFocus()

    def _local_start_dir(self) -> str:
        """Стартовая папка для диалогов выбора локального сайта."""
        current = self.url_input.text().strip().strip('"').strip("'")
        if current:
            try:
                candidate = Path(current)
                if candidate.is_file():
                    candidate = candidate.parent
                if candidate.is_dir():
                    return str(candidate)
            except OSError:
                pass
        try:
            fallback = Path(get_config().report_dir)
            if fallback.is_dir():
                return str(fallback)
        except Exception:  # noqa: BLE001 - путь по умолчанию не критичен
            pass
        return ""

    def cancel_scan(self) -> None:
        """Останавливает проверку и возвращает UI в спокойное состояние."""
        worker = self._worker
        if worker is None:
            return
        worker.cancel()
        if not worker.wait(3000):
            # Поток ещё жив (например, ждёт сеть) — дождёмся его сигнала.
            return
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()
        self._on_scan_cancelled()

    def _build_run_options(self) -> RunOptions:
        config = get_config()
        try:
            shot_dir: str | None = str(screenshots_dir())
        except OSError:  # pragma: no cover - зависит от прав на %APPDATA%
            shot_dir = None
        options = config.to_run_options(screenshot_dir=shot_dir)
        return options.model_copy(
            update={
                "deep_analysis": self.deep_check.isChecked(),
                "check_trackers": self.trackers_check.isChecked(),
                "show_na": self.show_na_check.isChecked(),
            }
        )

    def _rescan(self) -> None:
        if self._worker is not None:
            return
        url = self.url_input.text().strip()
        if not url and self._report is not None:
            url = self._report.url
        if url:
            self.url_input.setText(url)
        self.start_scan()

    def _on_progress(self, fraction: float, message: str) -> None:
        if not self._is_current_worker():
            return
        value = int(round(max(0.0, min(1.0, float(fraction))) * 100))
        self.progress_bar.setValue(value)
        self._set_progress_plain(message or tr("Проверка…"))
        self.results_view.set_progress(fraction, message)

    def _on_scan_finished(self, scan_result: object) -> None:
        if not self._is_current_worker():
            return
        report = getattr(scan_result, "report", None)
        context = getattr(scan_result, "context", None)
        if not isinstance(report, Report):
            self._on_scan_failed(tr("Не удалось получить отчёт."))
            return

        self._set_busy(False)
        self.progress_bar.setValue(100)
        self.progress_bar.show()
        self.progress_label.show()
        seconds = report.duration_ms / 1000.0
        self._set_progress_plain(
            f"{tr('Готово')} · {seconds:.1f} {tr('с')}"
            if seconds
            else tr("Готово")
        )
        self._progress_hide_timer.start(600)
        self.show_report(report, context if isinstance(context, SiteContext) else None)
        try:
            get_config_manager().update(last_url=self._last_scan_url or report.url)
        except Exception:  # noqa: BLE001 - сбой записи конфига не должен ломать UI
            pass

    def _on_scan_failed(self, message: str) -> None:
        if not self._is_current_worker():
            return
        self._set_busy(False)
        self._progress_hide_timer.stop()
        self.progress_bar.hide()
        self._set_progress_plain(tr("Проверка не выполнена"))
        self.results_view.show_error(message)
        self.details_panel.clear()
        self.fine_summary.set_report(None)
        self._report = None
        self._context = None
        self._set_export_enabled(False)
        self.result_hint.setText("")
        self.url_input.setFocus()

    def _on_scan_cancelled(self) -> None:
        if not self._is_current_worker():
            return
        self._set_busy(False)
        self._progress_hide_timer.stop()
        self.progress_bar.hide()
        self._set_progress_plain(tr("Проверка отменена"))
        self.results_view.show_empty_state()
        self.details_panel.clear()
        self.fine_summary.set_report(None)
        self._report = None
        self._context = None
        self._set_export_enabled(False)
        self.result_hint.setText("")

    def _on_worker_finished(self) -> None:
        worker = self.sender()
        if worker is self._worker:
            self._worker = None
        if isinstance(worker, QThread):
            worker.deleteLater()

    def _is_current_worker(self) -> bool:
        """Отсекает устаревшие сигналы отменённого/заменённого воркера."""
        worker = self.sender()
        if worker is None:
            return True
        return worker is self._worker

    def _set_busy(self, busy: bool) -> None:
        self.url_input.setEnabled(not busy)
        self.check_button.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        if busy:
            self._progress_hide_timer.stop()
            self.progress_bar.setValue(0)
            self.progress_bar.show()
            self.progress_label.show()
            self._set_progress_plain(tr("Подготовка…"))
            self.notes_label.hide()
            self._set_export_enabled(False)
            self.results_view.set_loading(True)

    def _hide_progress(self) -> None:
        self.progress_bar.hide()
        self.progress_label.hide()

    # ------------------------------------------------------------------
    # Готовый отчёт
    # ------------------------------------------------------------------
    def show_report(
        self,
        report: Report,
        context: SiteContext | None = None,
    ) -> None:
        """Заполняет окно готовым отчётом (публичный метод для тестов/истории)."""
        self._report = report
        self._context = context
        self.results_view.set_na_visible(self.show_na_check.isChecked())
        self.results_view.show_report(report)
        self.details_panel.clear()
        self.fine_summary.set_report(report)
        self._set_export_enabled(True)
        self.result_hint.setText(self._format_result_hint(report))
        self._show_notes(report, context)

    def _format_result_hint(self, report: Report) -> str:
        parts: list[str] = []
        if report.is_local:
            parts.append(tr("Локальная папка"))
        try:
            when = report.scanned_at.astimezone().strftime("%d.%m.%Y %H:%M")
        except Exception:  # noqa: BLE001 - экзотическая дата не должна ломать UI
            when = ""
        if when:
            parts.append(f"{tr('Проверено')} {when}")
        parts.append(f"{len(report.results)} {tr('проверок')}")
        seconds = report.duration_ms / 1000.0
        parts.append(f"{seconds:.1f} {tr('с')}")
        return " · ".join(parts)

    def _show_notes(self, report: Report, context: SiteContext | None) -> None:
        notes: list[str] = []
        sources: list[list[str]] = [list(report.notes)]
        if context is not None:
            sources.append(list(context.notes))
            sources.append(list(context.errors))
        for source in sources:
            for note in source:
                text = (note or "").strip()
                if text and text not in notes:
                    notes.append(text)
        if not notes:
            self.notes_label.hide()
            return
        shown = " · ".join(notes[:2])
        if len(notes) > 2:
            shown += " …"
        self.notes_label.setText(shown)
        self.notes_label.setToolTip("\n".join(notes))
        self.notes_label.show()

    # ------------------------------------------------------------------
    # Служебные состояния
    # ------------------------------------------------------------------
    def _set_progress_plain(self, text: str) -> None:
        self.progress_label.setTextFormat(Qt.TextFormat.PlainText)
        self.progress_label.setText(text)

    def _set_progress_error(self, text: str) -> None:
        # Единственный цветной текст в коде: QSS не умеет «красный по свойству»
        # у QLabel#ProgressLabel, а требование ТЗ — терракотовый акцент ошибки.
        import html as html_utils

        self._progress_hide_timer.stop()
        self.progress_label.show()
        self.progress_label.setTextFormat(Qt.TextFormat.RichText)
        self.progress_label.setText(
            f'<span style="color:{PALETTE["fail"]};">'
            f"{html_utils.escape(text)}</span>"
        )

    def _set_export_enabled(self, enabled: bool) -> None:
        for widget in (self.export_pdf_button, self.conclusion_button):
            widget.setEnabled(enabled)
        for action in (
            self.export_pdf_action,
            self.export_md_action,
            self.export_html_action,
            self.export_json_action,
            self.copy_link_action,
        ):
            action.setEnabled(enabled)

    def _on_show_na_toggled(self, checked: bool) -> None:
        self.results_view.set_na_visible(checked)

    # ------------------------------------------------------------------
    # Экспорт
    # ------------------------------------------------------------------
    def _export_report(self, kind: str) -> None:
        if self._report is None:
            return
        try:
            from app.services.report import (
                ExportFormat,
                export_report,
                suggest_path,
            )
        except Exception as exc:  # noqa: BLE001 - модуль может быть не собран
            QMessageBox.warning(
                self,
                tr("Экспорт"),
                trf("Модуль экспорта отчётов недоступен:\n{error}", error=exc),
            )
            return

        member = _EXPORT_KINDS.get(kind)
        fmt = getattr(ExportFormat, member, None) if member else None
        if fmt is None:
            QMessageBox.warning(
                self,
                tr("Экспорт"),
                tr("Этот формат экспорта недоступен."),
            )
            return

        config = get_config()
        try:
            default_path = Path(suggest_path(self._report, fmt, config.report_dir))
        except Exception:  # noqa: BLE001 - предложение пути не критично
            suffix = Path(getattr(fmt, "value", "txt")).suffix or "txt"
            default_path = Path(config.report_dir) / f"otchet.{suffix}"

        chosen, _selected_filter = QFileDialog.getSaveFileName(
            self,
            tr("Экспорт отчёта"),
            str(default_path),
            _EXPORT_FILTERS.get(kind, "Все файлы (*.*)"),
        )
        if not chosen:
            return

        target = Path(chosen)
        if target.suffix == "" and default_path.suffix:
            target = target.with_suffix(default_path.suffix)

        try:
            saved = Path(export_report(self._report, fmt, target.parent))
            final = saved
            if target.resolve() != saved.resolve():
                try:
                    saved.replace(target)
                    final = target
                except OSError:
                    final = saved
        except Exception as exc:  # noqa: BLE001 - показываем ошибку, не падаем
            QMessageBox.critical(
                self,
                tr("Ошибка"),
                trf("Не удалось сохранить отчёт:\n{error}", error=exc),
            )
            return

        self._show_saved_dialog(final)

    def _copy_report_link(self) -> None:
        if self._report is None:
            return
        try:
            from app.services.report import ExportFormat, export_report

            path = Path(
                export_report(self._report, ExportFormat.HTML, temp_report_dir())
            )
            QGuiApplication.clipboard().setText(
                QUrl.fromLocalFile(str(path)).toString()
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                tr("Ошибка"),
                trf("Не удалось скопировать ссылку на отчёт:\n{error}", error=exc),
            )
            return

        self._progress_hide_timer.stop()
        self.progress_bar.hide()
        self.progress_label.show()
        self._set_progress_plain(
            tr("Ссылка на отчёт скопирована в буфер обмена")
        )

    def _show_saved_dialog(self, path: Path) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(tr("Экспорт"))
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(tr("Отчёт сохранён:"))
        box.setInformativeText(str(path))
        open_button = box.addButton(
            tr("Открыть папку"), QMessageBox.ButtonRole.ActionRole
        )
        box.addButton(tr("ОК"), QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        if box.clickedButton() is open_button:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def _open_reports_folder(self) -> None:
        try:
            path = Path(get_config().report_dir) or default_report_dir()
        except Exception:  # noqa: BLE001
            path = default_report_dir()
        try:
            path = ensure_report_dir(path)
        except OSError as exc:
            QMessageBox.warning(
                self,
                tr("Отчёты"),
                trf("Не удалось открыть папку отчётов:\n{error}", error=exc),
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # ------------------------------------------------------------------
    # Настройки и «О программе»
    # ------------------------------------------------------------------
    def open_settings(self) -> None:
        dialog = SettingsDialog(self)
        dialog.settings_saved.connect(self._on_settings_saved)
        dialog.exec()

    def _on_settings_saved(self) -> None:
        config = get_config()
        self._config = config
        self.deep_check.setChecked(bool(config.deep_analysis))
        self.trackers_check.setChecked(bool(config.check_trackers))
        self.show_na_check.setChecked(bool(config.show_na))

    def show_about(self) -> None:
        AboutDialog(self).exec()

    # ------------------------------------------------------------------
    # Справочные окна (создаются параллельно — импорт локальный)
    # ------------------------------------------------------------------
    def open_methodology(self, check_id: str | None = None) -> None:
        """Открывает «Критерии проверок» (при ``check_id`` — сразу на проверке)."""
        try:
            from app.ui.methodology_window import open_methodology_window
        except (ImportError, AttributeError):
            self._show_unavailable_hint(tr("Критерии проверок"))
            return
        open_methodology_window(parent=self, check_id=check_id)

    def open_how_it_works(self, section_id: str | None = None) -> None:
        """Открывает «Как работает приложение» (при ``section_id`` — на разделе)."""
        try:
            from app.ui.how_it_works_window import open_how_it_works_window
        except (ImportError, AttributeError):
            self._show_unavailable_hint(tr("Как работает приложение"))
            return
        open_how_it_works_window(parent=self, section_id=section_id)

    def _show_unavailable_hint(self, title: str) -> None:
        """Мягко сообщает, что справочное окно ещё не собрано."""
        self.progress_label.show()
        self._set_progress_plain(
            trf("Окно «{title}» пока недоступно.", title=title)
        )

    # ------------------------------------------------------------------
    # Заключение
    # ------------------------------------------------------------------
    def open_conclusion(self) -> None:
        """Открывает немодальное окно «Заключение» по текущему отчёту."""
        if self._report is None:
            return
        try:
            from app.ui.conclusion_dialog import ConclusionDialog
        except (ImportError, AttributeError):
            self._show_unavailable_hint(tr("Заключение"))
            return

        previous = self._conclusion_dialog
        if previous is not None and hasattr(previous, "close"):
            previous.close()

        dialog = ConclusionDialog(self._report, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.destroyed.connect(
            lambda *_, target=dialog: self._on_conclusion_destroyed(target)
        )
        self._conclusion_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _on_conclusion_destroyed(self, dialog: object) -> None:
        if self._conclusion_dialog is dialog:
            self._conclusion_dialog = None

    # ------------------------------------------------------------------
    # Проверка обновлений
    # ------------------------------------------------------------------
    def _maybe_check_updates(self) -> None:
        if self._update_worker is not None:
            return
        try:
            config = get_config()
        except Exception:  # noqa: BLE001
            return
        if not config.update_is_due():
            return

        worker = _UpdateCheckWorker(config.model_copy(), self)
        worker.available.connect(self._on_update_available)
        worker.finished.connect(self._on_update_worker_finished)
        self._update_worker = worker
        worker.start()

    def check_updates_manual(self) -> None:
        """Ручная проверка обновлений в фоне (кнопка тулбара)."""
        if self._update_worker is not None or self._worker is not None:
            return
        try:
            config = get_config().model_copy(update={"check_updates": True})
        except Exception:  # noqa: BLE001 - конфиг не должен мешать проверке
            config = AppConfig(check_updates=True)

        self.update_button.setEnabled(False)
        self._progress_hide_timer.stop()
        self.progress_label.show()
        self._set_progress_plain(tr("Проверка обновлений…"))

        worker = _UpdateCheckWorker(config, self, manual=True)
        worker.checked.connect(self._on_manual_update_checked)
        worker.finished.connect(self._on_update_worker_finished)
        self._update_worker = worker
        worker.start()

    def _on_update_available(self, info: object) -> None:
        latest = str(getattr(info, "latest", "") or "").strip().lstrip("vV")
        url = str(getattr(info, "url", "") or DOWNLOAD_URL)
        if not latest or latest == __version__:
            return
        self.update_label.setText(
            trf("Доступна версия {version}", version=latest)
        )
        self._set_update_link(url)
        self.update_banner_container.show()

    def _set_update_link(self, url: str) -> None:
        if not url:
            return
        parent = self.update_banner
        index = self.update_banner_layout.indexOf(self.update_link)
        self.update_link.setParent(None)
        self.update_link.deleteLater()
        self.update_link = LinkLabel(tr("Скачать"), url, parent)
        if index < 0:
            index = self.update_banner_layout.count() - 1
        self.update_banner_layout.insertWidget(
            index, self.update_link, 0, Qt.AlignmentFlag.AlignVCenter
        )

    def _on_update_worker_finished(self) -> None:
        worker = self.sender()
        manual = bool(getattr(worker, "manual", False))
        if worker is self._update_worker:
            self._update_worker = None
        if isinstance(worker, QThread):
            worker.deleteLater()
        self.update_button.setEnabled(True)
        if manual:
            self._progress_hide_timer.stop()
            # Не прячем статус сканирования, если пользователь уже запустил его.
            if self._worker is None:
                self.progress_label.hide()
        else:
            self._mark_update_checked()

    def _mark_update_checked(self) -> None:
        try:
            manager = get_config_manager()
            manager.config.mark_update_checked()
            manager.save()
        except Exception:  # noqa: BLE001 - конфиг не критичен для работы
            pass

    def _on_manual_update_checked(self, info: object | None) -> None:
        """Реакция на ручную проверку: диалог по результату (без сети)."""
        self._mark_update_checked()
        latest = str(getattr(info, "latest", "") or "").strip().lstrip("vV")
        available = bool(getattr(info, "available", False))
        if info is not None and available and latest and latest != __version__:
            self._show_update_available_dialog(info, latest)
        elif info is not None:
            self._show_up_to_date_dialog()
        else:
            self._show_update_error_dialog()

    def _show_update_available_dialog(
        self, info: object, latest: str
    ) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(tr("Обновление"))
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(
            trf(
                "Доступна версия {latest}. У вас {current}.",
                latest=latest,
                current=__version__,
            )
        )
        notes = str(getattr(info, "notes", "") or "").strip()
        if notes:
            box.setInformativeText(notes)
        download_button = box.addButton(
            tr("Скачать"), QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton(tr("Позже"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is download_button:
            QDesktopServices.openUrl(QUrl(DOWNLOAD_URL))
            self._on_update_available(info)

    def _show_up_to_date_dialog(self) -> None:
        QMessageBox.information(
            self,
            tr("Обновление"),
            trf(
                "Установлена актуальная версия {version}. "
                "Обновление не требуется.",
                version=__version__,
            ),
        )

    def _show_update_error_dialog(self) -> None:
        QMessageBox.warning(
            self,
            tr("Обновление"),
            tr(
                "Не удалось проверить обновления. "
                "Проверьте подключение к интернету."
            ),
        )

    # ------------------------------------------------------------------
    # Закрытие
    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._update_timer.stop()
        self._progress_hide_timer.stop()
        worker = self._worker
        if worker is not None:
            worker.cancel()
            if not worker.wait(3000):
                worker.terminate()
                worker.wait(1000)
            self._worker = None
        update_worker = self._update_worker
        if update_worker is not None:
            if not update_worker.wait(1000):
                update_worker.terminate()
                update_worker.wait(1000)
            self._update_worker = None
        dialog = self._conclusion_dialog
        if dialog is not None and hasattr(dialog, "close"):
            dialog.close()
            self._conclusion_dialog = None
        super().closeEvent(event)
