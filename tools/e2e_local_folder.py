"""Сквозной тест локальной проверки: папка с сайтом → окно → отчёт.

Создаёт временную папку с демо-сайтом (index.html, политика, контакты,
robots.txt, sitemap.xml), запускает проверку из настоящего окна (offscreen)
и сохраняет скриншот.

Запуск:  python tools/e2e_local_folder.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUTPUTS = ROOT / ".outputs"
FIXTURES = ROOT / "tests" / "fixtures"

PRIVACY_PAGE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<title>Политика обработки персональных данных</title></head><body>
<h1>Политика обработки персональных данных</h1>
<p>Оператор персональных данных — ООО «Пример».</p>
<h2>Цели обработки</h2><p>Исполнение заказов и поддержка клиентов.</p>
<h2>Срок хранения</h2><p>3 года с последнего обращения.</p>
<h2>Права субъекта</h2><p>Права субъекта по ст. 14 152-ФЗ.</p>
<h2>Отзыв согласия</h2><p>Письмом на info@demo.test.</p>
<h2>Cookie</h2><p>Сайт использует cookie.</p>
</body></html>
"""

CONTACTS_PAGE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><title>Контакты</title></head><body>
<h1>Контакты</h1><p>ООО «Пример», ОГРН 1000000000010, адрес: г. Москва.</p>
<p>+7 (000) 123-45-67, info@demo.test</p></body></html>
"""


def build_site(directory: Path) -> Path:
    index = (FIXTURES / "shop.html").read_text(encoding="utf-8")
    index = index.replace('href="/privacy/"', 'href="privacy/index.html"')
    index = index.replace('href="/contacts/"', 'href="contacts/index.html"')
    (directory / "index.html").write_text(index, encoding="utf-8")
    (directory / "privacy").mkdir()
    (directory / "privacy" / "index.html").write_text(PRIVACY_PAGE, encoding="utf-8")
    (directory / "contacts").mkdir()
    (directory / "contacts" / "index.html").write_text(CONTACTS_PAGE, encoding="utf-8")
    (directory / "robots.txt").write_text(
        "User-agent: *\nDisallow: /admin\n", encoding="utf-8"
    )
    (directory / "sitemap.xml").write_text(
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<urlset><url><loc>index.html</loc></url>"
        "<url><loc>privacy/index.html</loc></url></urlset>",
        encoding="utf-8",
    )
    return directory


def main() -> int:
    folder = Path(tempfile.mkdtemp(prefix="prirex-local-"))
    build_site(folder)

    from PySide6.QtWidgets import QApplication

    from app.ui.icons import app_icon
    from app.ui.main_window import MainWindow
    from app.ui.theme import apply_theme

    application = QApplication(sys.argv)
    application.setWindowIcon(app_icon())
    apply_theme(application)

    window = MainWindow()
    window.resize(1280, 800)
    window.show()
    window.url_input.setText(str(folder))
    window.start_scan()

    deadline = time.time() + 120
    while time.time() < deadline:
        application.processEvents()
        if getattr(window, "_report", None) is not None:
            break
        time.sleep(0.05)

    settle = time.time() + 1.2
    while time.time() < settle:
        application.processEvents()
        time.sleep(0.03)

    report = getattr(window, "_report", None)
    if report is None:
        print("ПРОВАЛ: отчёт не получен")
        print("Ошибка в окне:", window.progress_label.text())
        window.grab().save(str(OUTPUTS / "e2e-folder-error.png"))
        shutil.rmtree(folder, ignore_errors=True)
        return 1

    OUTPUTS.mkdir(exist_ok=True)
    window.grab().save(str(OUTPUTS / "e2e-folder.png"))

    print(f"Локальная папка: {folder}")
    print(f"Соответствие: {report.score}% | is_local={report.is_local}")
    for item in report.results:
        print(f"  {item.status.value:15} {item.check_id:24} {item.message[:66]}")
    print(f"Скриншот: {OUTPUTS / 'e2e-folder.png'}")

    window.close()
    shutil.rmtree(folder, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
