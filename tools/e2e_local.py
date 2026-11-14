"""Сквозной тест: главное окно + воркер + движок + экспорт на локальном сайте.

Поднимает временный HTTP-сервер с демо-сайтом (магазин с политикой, cookie-
баннером, трекерами и рекламой), запускает проверку из настоящего окна
(offscreen), ждёт результат и сохраняет скриншот.

Запуск:  python tools/e2e_local.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Без каталога шрифтов offscreen-плагин рисует кириллицу квадратами.
os.environ.setdefault(
    "QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUTPUTS = ROOT / ".outputs"

PRIVACY_PAGE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<title>Политика обработки персональных данных</title></head><body>
<h1>Политика обработки персональных данных</h1>
<p>Оператор персональных данных — ООО «Лютик», ИНН 7707083893.</p>
<h2>Цели обработки</h2><p>Цели обработки — исполнение заказов и поддержка клиентов.</p>
<h2>Срок хранения</h2><p>Срок хранения данных — 3 года с момента последнего обращения.</p>
<h2>Права субъекта</h2><p>Права субъекта персональных данных описаны в ст. 14 152-ФЗ.</p>
<h2>Отзыв согласия</h2><p>Отозвать согласие можно письмом на info@lutik.ru.</p>
<h2>Cookie</h2><p>Сайт использует файлы cookie для аналитики.</p>
</body></html>
"""

CONTACTS_PAGE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><title>Контакты</title></head><body>
<h1>Контакты</h1><p>ООО «Лютик», ОГРН 1027700132195, адрес: г. Москва, ул. Ленина, 1.</p>
<p>Телефон: +7 (495) 123-45-67, e-mail: info@lutik.ru</p>
</body></html>
"""

ROBOTS = "User-agent: *\nDisallow: /admin\nSitemap: http://{host}/sitemap.xml\n"
SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>http://{host}/index.html</loc></url>
<url><loc>http://{host}/privacy.html</loc></url>
<url><loc>http://{host}/contacts.html</loc></url>
</urlset>
"""


def build_site(directory: Path) -> None:
    """Копирует магазин из тестовых фикстур и добавляет окружение сайта."""
    index = (ROOT / "tests" / "fixtures" / "shop.html").read_text(encoding="utf-8")
    # плоские адреса страниц для простого статического сервера
    index = index.replace('href="/privacy/"', 'href="/privacy.html"')
    index = index.replace('href="/contacts/"', 'href="/contacts.html"')
    (directory / "index.html").write_text(index, encoding="utf-8")
    (directory / "privacy.html").write_text(PRIVACY_PAGE, encoding="utf-8")
    (directory / "contacts.html").write_text(CONTACTS_PAGE, encoding="utf-8")


def start_server(directory: Path) -> tuple[ThreadingHTTPServer, int]:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, *args, **kwargs):  # noqa: ANN002, ANN003
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def main() -> int:
    temp_dir = Path(tempfile.mkdtemp(prefix="prirex-e2e-"))
    build_site(temp_dir)
    server, port = start_server(temp_dir)
    host = f"127.0.0.1:{port}"
    (temp_dir / "robots.txt").write_text(ROBOTS.format(host=host), encoding="utf-8")
    (temp_dir / "sitemap.xml").write_text(SITEMAP.format(host=host), encoding="utf-8")

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

    url = f"http://{host}/index.html"
    window.url_input.setText(url)
    window.start_scan()

    deadline = time.time() + 150
    while time.time() < deadline:
        application.processEvents()
        if getattr(window, "_report", None) is not None:
            break
        time.sleep(0.05)

    # Даём Qt пересчитать раскладку и скрыть прогресс-бар, иначе скриншот
    # показывает ещё не перестроенную нижнюю панель.
    settle_until = time.time() + 1.2
    while time.time() < settle_until:
        application.processEvents()
        time.sleep(0.03)

    report = getattr(window, "_report", None)
    if report is None:
        print("ПРОВАЛ: отчёт не получен (см. сообщение в окне)")
        window.grab().save(str(OUTPUTS / "e2e-local-error.png"))
        server.shutdown()
        return 1

    OUTPUTS.mkdir(exist_ok=True)
    window.grab().save(str(OUTPUTS / "e2e-local.png"))

    print(f"Соответствие: {report.score}%")
    for item in report.results:
        print(f"  {item.status.value:15} {item.check_id:24} {item.message[:60]}")
    print(f"Заметки: {report.notes}")

    from app.services.report import ExportFormat, export_report

    for fmt in (ExportFormat.PDF, ExportFormat.HTML, ExportFormat.MARKDOWN, ExportFormat.JSON):
        path = export_report(report, fmt, OUTPUTS / "e2e")
        print(f"Экспорт {fmt.value}: {path.name} ({path.stat().st_size} байт)")

    print(f"Скриншот: {OUTPUTS / 'e2e-local.png'}")
    window.close()
    server.shutdown()
    shutil.rmtree(temp_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
