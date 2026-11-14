"""UI-тесты локальной проверки: поле URL, кнопка «Папка…», валидация."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault(
        "QT_QPA_FONTDIR",
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
    )

from datetime import datetime, timezone
from pathlib import Path

import pytest
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication, QFileDialog

import app.ui.main_window as main_window_module
from app.core.models import CheckResult, CheckStatus, Report
from app.ui.main_window import MainWindow
from app.ui.theme import apply_theme


class FakeWorker(QThread):
    """Подменяет реальный ScanWorker: запоминает адрес и ничего не делает."""

    progress = Signal(float, str)
    finished_ok = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    instances: list["FakeWorker"] = []

    def __init__(self, url, options, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.url = url
        self.options = options
        FakeWorker.instances.append(self)

    def run(self) -> None:  # noqa: D401 - Qt API
        return

    def cancel(self) -> None:
        return


@pytest.fixture(scope="module")
def qt_app():
    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    apply_theme(application)
    return application


@pytest.fixture(autouse=True)
def reset_workers():
    FakeWorker.instances.clear()
    yield
    FakeWorker.instances.clear()


@pytest.fixture
def window(qt_app, monkeypatch):
    monkeypatch.setattr(main_window_module, "ScanWorker", FakeWorker)
    widget = MainWindow()
    yield widget
    widget.close()


def make_local_site(directory: Path) -> Path:
    (directory / "index.html").write_text(
        "<html><body><h1>Сайт</h1></body></html>", encoding="utf-8"
    )
    return directory


def test_placeholder_mentions_local_folder(window) -> None:
    text = window.url_input.placeholderText().lower()
    assert "example.com" in text
    assert "папк" in text


def test_folder_button_exists(window) -> None:
    assert window.folder_button.text() == "Папка…"
    assert window.folder_button.objectName() == "SecondaryButton"


def test_start_scan_accepts_local_folder(window, tmp_path) -> None:
    make_local_site(tmp_path)
    window.url_input.setText(str(tmp_path))
    window.start_scan()
    assert FakeWorker.instances, "воркер не создан"
    assert FakeWorker.instances[0].url.endswith("index.html")
    assert window.url_input.text() == str(tmp_path)


def test_start_scan_accepts_file_path(window, tmp_path) -> None:
    make_local_site(tmp_path)
    file_path = tmp_path / "index.html"
    window.url_input.setText(str(file_path))
    window.start_scan()
    assert FakeWorker.instances
    assert FakeWorker.instances[0].url == str(file_path.resolve())


def test_start_scan_rejects_missing_folder(window, tmp_path) -> None:
    window.url_input.setText(str(tmp_path / "нет-такой-папки"))
    window.start_scan()
    assert not FakeWorker.instances
    assert "не найдены" in window.progress_label.text().lower()


def test_choose_local_folder_fills_input(window, tmp_path, monkeypatch) -> None:
    make_local_site(tmp_path)
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *args, **kwargs: str(tmp_path)),
    )
    window.choose_local_folder()
    assert window.url_input.text() == str(tmp_path)


def test_result_hint_marks_local_report(window) -> None:
    report = Report(
        url=str(Path("C:/site")),
        final_url="file:///C:/site/index.html",
        scanned_at=datetime.now(timezone.utc),
        score=80,
        is_local=True,
        results=[
            CheckResult(
                check_id="a01_https",
                title="HTTPS и TLS",
                status=CheckStatus.NOT_APPLICABLE,
            )
        ],
    )
    window.show_report(report, None)
    assert "Локальная папка" in window.result_hint.text()


def test_file_button_exists(window) -> None:
    assert window.file_button.text() == "Файл…"
    assert window.file_button.objectName() == "SecondaryButton"


def test_choose_local_file_fills_input(window, tmp_path, monkeypatch) -> None:
    page = tmp_path / "index"
    page.write_text("<!DOCTYPE html><html><body>Сайт</body></html>", encoding="utf-8")
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *args, **kwargs: (str(page), "")),
    )
    window.choose_local_file()
    assert window.url_input.text() == str(page)


def test_start_scan_accepts_extensionless_file(window, tmp_path) -> None:
    page = tmp_path / "index"
    page.write_text("<!DOCTYPE html><html><body>Сайт</body></html>", encoding="utf-8")
    window.url_input.setText(str(page))
    window.start_scan()
    assert FakeWorker.instances
    assert FakeWorker.instances[0].url == str(page.resolve())
