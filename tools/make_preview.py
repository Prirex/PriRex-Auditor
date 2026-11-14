"""Генерирует пример отчёта (PDF/HTML) и превью-скриншот для README.

Запуск:  python tools/make_preview.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DOCS = ROOT / "docs"

from app.core.checks import create_checks  # noqa: E402
from app.core.engine.scoring import calculate_score  # noqa: E402
from app.core.models import HttpsInfo, Report, RunOptions  # noqa: E402
from app.services.report import ExportFormat, export_report  # noqa: E402
from app.services.site_context import parse_site_context  # noqa: E402
from app.version import __version__  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "shop.html"


async def build_report() -> Report:
    context = parse_site_context(FIXTURE.read_text(encoding="utf-8"), "https://lutik.ru/")
    context.url = "https://lutik.ru/"
    context.status_code = 200
    context.https = HttpsInfo(
        requested_url="https://lutik.ru/",
        final_url="https://lutik.ru/",
        used_https=True,
        https_available=True,
        cert_valid=True,
        tls_version="TLSv1.3",
        redirects_http_to_https=True,
        http_redirect_checked=True,
        http_status=200,
    )
    context.robots.found = True
    context.robots.status_code = 200
    context.sitemap.found = True
    context.sitemap.status_code = 200
    context.sitemap.url = "https://lutik.ru/sitemap.xml"
    context.sitemap.url_count = 18
    context.security_headers = {
        "x-frame-options": "SAMEORIGIN",
        "x-content-type-options": None,
        "referrer-policy": "strict-origin-when-cross-origin",
        "content-security-policy": None,
        "strict-transport-security": None,
        "permissions-policy": None,
    }

    results = []
    for check in create_checks():
        results.append(await check.run(context))

    return Report(
        url="https://lutik.ru/",
        final_url="https://lutik.ru/",
        score=calculate_score(results),
        results=results,
        deep_analysis=False,
        app_version=__version__,
        duration_ms=8420,
        notes=[
            "Глубокий анализ отключён — динамические элементы и cookie-баннер "
            "проверены только по статическому HTML.",
        ],
    )


def render_pdf_png(pdf_path: Path, png_path: Path) -> bool:
    """Рендерит первую страницу PDF в PNG через QtPdf (если доступен)."""
    try:
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtPdf import QPdfDocument
    except Exception as exc:  # noqa: BLE001
        print(f"QtPdf недоступен: {exc}")
        return False
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    document = QPdfDocument()
    if document.load(str(pdf_path)) != QPdfDocument.Error.None_:
        print("Не удалось открыть PDF")
        return False
    page = document.render(0, document.pagePointSize(0).toSize())
    if page.isNull():
        return False
    page.save(str(png_path), "PNG")
    print(f"Превью отчёта: {png_path}")
    return True


def main() -> int:
    DOCS.mkdir(exist_ok=True)
    report = asyncio.run(build_report())
    pdf = export_report(report, ExportFormat.PDF, DOCS)
    html = export_report(report, ExportFormat.HTML, DOCS)
    report.notes = list(report.notes)
    export_report(report, ExportFormat.MARKDOWN, DOCS)
    export_report(report, ExportFormat.JSON, DOCS)
    print(f"Процент: {report.score}%")
    print(f"PDF: {pdf}")
    print(f"HTML: {html}")
    render_pdf_png(pdf, DOCS / "screenshot-report.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
