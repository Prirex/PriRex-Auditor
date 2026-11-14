"""Утилита для скриншотов главного окна (offscreen).

Запуск из корня проекта::

    python tools/ui_screenshots.py

Результат — ``.outputs/ui-main.png`` (отчёт) и ``.outputs/ui-empty.png``
(пустое состояние). Удобно для визуальной приёмки без запуска сети.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault(
        "QT_QPA_FONTDIR",
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
    )

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.theme import apply_theme  # noqa: E402
from tests.test_ui_smoke import make_synthetic_report  # noqa: E402


def main() -> int:
    output_dir = PROJECT_ROOT / ".outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication(["prirex-ui-screenshots"])
    apply_theme(app)

    report_window = MainWindow()
    report_window._update_timer.stop()
    report_window.show_na_check.setChecked(True)
    report_window.resize(1200, 780)
    report_window.show()
    app.processEvents()
    report_window.show_report(make_synthetic_report())
    app.processEvents()
    app.processEvents()
    report_path = output_dir / "ui-main.png"
    ok_main = report_window.grab().save(str(report_path))
    report_window.close()
    app.processEvents()

    empty_window = MainWindow()
    empty_window._update_timer.stop()
    empty_window.resize(1200, 780)
    empty_window.show()
    app.processEvents()
    empty_path = output_dir / "ui-empty.png"
    ok_empty = empty_window.grab().save(str(empty_path))
    empty_window.close()
    app.processEvents()

    print(f"ui-main.png:  {report_path}  ({'ok' if ok_main else 'fail'})")
    print(f"ui-empty.png: {empty_path} ({'ok' if ok_empty else 'fail'})")
    return 0 if ok_main and ok_empty else 1


if __name__ == "__main__":
    raise SystemExit(main())
