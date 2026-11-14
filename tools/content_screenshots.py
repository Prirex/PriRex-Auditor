"""Скриншоты окон-справочников (offscreen) для визуальной приёмки.

Запуск из корня проекта::

    python tools/content_screenshots.py

Результат — ``.outputs/methodology.png`` и ``.outputs/how-it-works.png``.
Если ``assets/methodology.json`` или ``assets/how_it_works.json`` ещё не
созданы, в окна инжектируются тестовые данные из
``tests/test_content_windows.py`` — скриншоты можно снимать в любой момент.
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

import app.ui.how_it_works_window as hiw_module  # noqa: E402
import app.ui.methodology_window as mw_module  # noqa: E402
from app.core.content.loader import (  # noqa: E402
    load_how_it_works,
    load_methodology,
)
from app.ui.theme import apply_theme  # noqa: E402


def _methodology_window(app: QApplication) -> mw_module.MethodologyWindow:
    if load_methodology() is None:
        from tests.test_content_windows import sample_methodology

        mw_module.load_methodology = sample_methodology
        mw_module.methodology_error = lambda: None
    window = mw_module.MethodologyWindow()
    # Богатая по контенту проверка: заголовок, бейдж, все секции.
    window.focus_check("4.13")
    window.resize(900, 700)
    window.show()
    app.processEvents()
    window.focus_check("4.13")
    app.processEvents()
    return window


def _how_it_works_window(app: QApplication) -> hiw_module.HowItWorksWindow:
    if load_how_it_works() is None:
        from tests.test_content_windows import sample_how_it_works

        hiw_module.load_how_it_works = sample_how_it_works
        hiw_module.how_it_works_error = lambda: None
    window = hiw_module.HowItWorksWindow()
    window.resize(820, 650)
    window.show()
    app.processEvents()
    # Раздел «Как проходит проверка (пошагово)» — самый наглядный.
    window.select_section("how_scan_works")
    app.processEvents()
    return window


def main() -> int:
    output_dir = PROJECT_ROOT / ".outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication(["prirex-content-screenshots"])
    apply_theme(app)

    method_window = _methodology_window(app)
    app.processEvents()
    app.processEvents()
    method_path = output_dir / "methodology.png"
    ok_method = method_window.grab().save(str(method_path))
    method_window.close()
    app.processEvents()

    how_window = _how_it_works_window(app)
    app.processEvents()
    app.processEvents()
    how_path = output_dir / "how-it-works.png"
    ok_how = how_window.grab().save(str(how_path))
    how_window.close()
    app.processEvents()

    print(f"methodology.png: {method_path} ({'ok' if ok_method else 'fail'})")
    print(f"how-it-works.png: {how_path} ({'ok' if ok_how else 'fail'})")
    return 0 if ok_method and ok_how else 1


if __name__ == "__main__":
    raise SystemExit(main())
