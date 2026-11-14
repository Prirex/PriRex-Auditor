"""Окно настроек приложения (ТЗ 5.9)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.config import (
    DEFAULT_USER_AGENT,
    LANGUAGES,
    AppConfig,
    get_config,
    get_config_manager,
)
from app.i18n import tr, trf
from app.paths import default_report_dir

__all__ = ["SettingsDialog"]


class SettingsDialog(QDialog):
    """Модальное окно настроек: проверка, отчёты, обновления, интерфейс."""

    #: Настройки успешно сохранены в config.json.
    settings_saved = Signal()

    def __init__(self, parent: QWidget | None = None, config: AppConfig | None = None) -> None:
        super().__init__(parent)
        self._config = config or get_config()
        self._initial_language = self._config.language

        self.setObjectName("SettingsDialog")
        self.setWindowTitle(tr("Настройки"))
        self.setModal(True)
        self.setMinimumWidth(520)
        self.resize(540, 600)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        root.addWidget(self._build_scan_group())
        root.addWidget(self._build_reports_group())
        root.addWidget(self._build_updates_group())
        root.addWidget(self._build_interface_group())
        root.addStretch(1)
        root.addLayout(self._build_buttons())

    # ------------------------------------------------------------------
    # Группы
    # ------------------------------------------------------------------
    def _build_scan_group(self) -> QGroupBox:
        group = QGroupBox(tr("Проверка"), self)
        form = self._form_layout(group)

        self.timeout_spin = QDoubleSpinBox(group)
        self.timeout_spin.setRange(3.0, 120.0)
        self.timeout_spin.setDecimals(1)
        self.timeout_spin.setSingleStep(1.0)
        self.timeout_spin.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.timeout_spin.setMinimumWidth(160)
        self.timeout_spin.setValue(float(self._config.timeout))
        form.addRow(tr("Таймаут запросов, сек"), self.timeout_spin)

        ua_widget = QWidget(group)
        ua_layout = QHBoxLayout(ua_widget)
        ua_layout.setContentsMargins(0, 0, 0, 0)
        ua_layout.setSpacing(6)
        self.ua_edit = QLineEdit(ua_widget)
        self.ua_edit.setText(self._config.user_agent or DEFAULT_USER_AGENT)
        self.ua_edit.setCursorPosition(0)
        self.ua_edit.setClearButtonEnabled(True)
        ua_layout.addWidget(self.ua_edit, 1)
        self.ua_reset_button = QPushButton(tr("Сбросить"), ua_widget)
        self.ua_reset_button.setObjectName("SecondaryButton")
        self.ua_reset_button.clicked.connect(
            lambda: self.ua_edit.setText(DEFAULT_USER_AGENT)
        )
        ua_layout.addWidget(self.ua_reset_button, 0)
        form.addRow(tr("User-Agent"), ua_widget)

        self.depth_spin = QSpinBox(group)
        self.depth_spin.setRange(0, 12)
        self.depth_spin.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.depth_spin.setMinimumWidth(160)
        self.depth_spin.setValue(int(self._config.max_pages))
        self.depth_spin.setToolTip(
            tr("Сколько дополнительных страниц сайта загружать при глубоком анализе.")
        )
        form.addRow(tr("Глубина проверки (страниц)"), self.depth_spin)
        return group

    def _build_reports_group(self) -> QGroupBox:
        group = QGroupBox(tr("Отчёты"), self)
        form = self._form_layout(group)

        dir_widget = QWidget(group)
        dir_layout = QHBoxLayout(dir_widget)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.setSpacing(6)
        self.report_dir_edit = QLineEdit(dir_widget)
        self.report_dir_edit.setText(self._config.report_dir)
        self.report_dir_edit.setCursorPosition(0)
        self.report_dir_edit.setToolTip(self._config.report_dir)
        dir_layout.addWidget(self.report_dir_edit, 1)
        self.report_dir_button = QPushButton(tr("Обзор"), dir_widget)
        self.report_dir_button.setObjectName("SecondaryButton")
        self.report_dir_button.clicked.connect(self._choose_report_dir)
        dir_layout.addWidget(self.report_dir_button, 0)
        form.addRow(tr("Папка для отчётов"), dir_widget)
        return group

    def _build_updates_group(self) -> QGroupBox:
        group = QGroupBox(tr("Обновления"), self)
        form = self._form_layout(group)

        self.updates_check = QCheckBox(tr("Проверять обновления"), group)
        self.updates_check.setChecked(bool(self._config.check_updates))
        form.addRow(self.updates_check)

        self.update_interval_spin = QSpinBox(group)
        self.update_interval_spin.setRange(1, 720)
        self.update_interval_spin.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.update_interval_spin.setMinimumWidth(160)
        self.update_interval_spin.setValue(int(self._config.update_interval_hours))
        self.update_interval_spin.setEnabled(self.updates_check.isChecked())
        self.updates_check.toggled.connect(self.update_interval_spin.setEnabled)
        form.addRow(tr("Частота проверки обновлений, ч"), self.update_interval_spin)
        return group

    def _build_interface_group(self) -> QGroupBox:
        group = QGroupBox(tr("Интерфейс"), self)
        form = self._form_layout(group)

        self.show_na_check = QCheckBox(tr("Показывать проверки со статусом N/A"), group)
        self.show_na_check.setChecked(bool(self._config.show_na))
        form.addRow(self.show_na_check)

        self.verify_tls_check = QCheckBox(tr("Проверять TLS-сертификат"), group)
        self.verify_tls_check.setChecked(bool(self._config.verify_tls))
        form.addRow(self.verify_tls_check)

        self.boosty_ask_check = QCheckBox(
            tr("Спрашивать перед открытием Boosty"), group
        )
        self.boosty_ask_check.setChecked(bool(self._config.boosty_ask_confirm))
        form.addRow(self.boosty_ask_check)

        language_widget = QWidget(group)
        language_layout = QVBoxLayout(language_widget)
        language_layout.setContentsMargins(0, 0, 0, 0)
        language_layout.setSpacing(2)
        self.language_combo = QComboBox(language_widget)
        for code, title in LANGUAGES.items():
            self.language_combo.addItem(tr(title), code)
        index = self.language_combo.findData(self._config.language)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        language_layout.addWidget(self.language_combo)
        self.language_hint = QLabel(
            tr("Язык применится после перезапуска"), language_widget
        )
        self.language_hint.setObjectName("Hint")
        self.language_hint.hide()
        language_layout.addWidget(self.language_hint)
        form.addRow(tr("Язык интерфейса"), language_widget)
        return group

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 4, 0, 0)
        row.setSpacing(8)
        row.addStretch(1)

        self.cancel_button = QPushButton(tr("Отмена"), self)
        self.cancel_button.setObjectName("SecondaryButton")
        self.cancel_button.setMinimumWidth(110)
        self.cancel_button.clicked.connect(self.reject)
        row.addWidget(self.cancel_button)

        self.save_button = QPushButton(tr("Сохранить"), self)
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.setMinimumWidth(120)
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._save)
        row.addWidget(self.save_button)
        return row

    # ------------------------------------------------------------------
    # Вспомогательные действия
    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        # Не оставляем каретку в первом числовом поле: значение должно быть
        # видно целиком, без «|5,0» при открытии окна.
        self.save_button.setFocus()

    def _form_layout(self, parent: QWidget) -> QFormLayout:
        form = QFormLayout(parent)
        form.setContentsMargins(12, 16, 12, 8)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        return form

    def _choose_report_dir(self) -> None:
        start = self.report_dir_edit.text().strip() or str(default_report_dir())
        chosen = QFileDialog.getExistingDirectory(
            self, tr("Папка для отчётов"), start
        )
        if chosen:
            self.report_dir_edit.setText(chosen)

    def _on_language_changed(self, _index: int) -> None:
        code = self.language_combo.currentData()
        self.language_hint.setVisible(code != self._initial_language)

    # ------------------------------------------------------------------
    def selected_values(self) -> dict[str, object]:
        """Готовые значения формы (используется и тестами)."""
        return {
            "timeout": round(float(self.timeout_spin.value()), 1),
            "user_agent": self.ua_edit.text().strip() or DEFAULT_USER_AGENT,
            "max_pages": int(self.depth_spin.value()),
            "report_dir": self.report_dir_edit.text().strip()
            or str(default_report_dir()),
            "check_updates": self.updates_check.isChecked(),
            "update_interval_hours": int(self.update_interval_spin.value()),
            "show_na": self.show_na_check.isChecked(),
            "verify_tls": self.verify_tls_check.isChecked(),
            "boosty_ask_confirm": self.boosty_ask_check.isChecked(),
            "language": self.language_combo.currentData() or "ru",
        }

    def _save(self) -> None:
        values = self.selected_values()
        report_dir = str(values["report_dir"])
        try:
            Path(report_dir).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(
                self,
                tr("Настройки"),
                trf(
                    "Не удалось создать папку для отчётов:\n{error}",
                    error=exc,
                ),
            )
            return
        if not Path(report_dir).is_dir():
            QMessageBox.warning(
                self,
                tr("Настройки"),
                tr("Указанный путь не является папкой."),
            )
            return

        try:
            get_config_manager().update(**values)
        except Exception as exc:  # noqa: BLE001 - битый конфиг не должен ронять окно
            QMessageBox.critical(
                self,
                tr("Ошибка"),
                trf("Не удалось сохранить настройки:\n{error}", error=exc),
            )
            return

        self.settings_saved.emit()
        self.accept()


__all__ = ["SettingsDialog"]
