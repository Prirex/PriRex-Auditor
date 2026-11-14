"""Тесты экспорта отчётов: PDF / HTML / Markdown / JSON.

Проверяем контракт публичного API (``app.services.report``): путь и имя
файла, содержимое каждого формата, брендинг и устойчивость к отсутствию
``assets/logo.png``.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core.models import CheckResult, CheckStatus, Evidence, Report, Severity
from app.services.report import (
    ExportFormat,
    build_html,
    build_json,
    build_markdown,
    export_report,
    suggest_path,
)
from app.services.report.common import BRAND_LINE, format_scanned_at
from app.version import DISCLAIMER, __version__

SCANNED_AT = datetime(2026, 11, 14, 5, 45, tzinfo=timezone.utc)
DOMAIN = "example-shop.ru"


def _result(
    check_id: str,
    title: str,
    category: str,
    status: CheckStatus,
    *,
    severity: Severity = Severity.INFO,
    message: str = "",
    recommendation: str = "",
    evidence: list[Evidence] | None = None,
    weight: int = 1,
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        title=title,
        category=category,
        status=status,
        severity=severity,
        weight=weight,
        message=message,
        recommendation=recommendation,
        evidence=evidence or [],
    )


@pytest.fixture
def sample_report() -> Report:
    """Отчёт с 8 проверками: все статусы, evidence, рекомендации."""
    return Report(
        url=f"http://{DOMAIN}/",
        final_url=f"https://{DOMAIN}/",
        scanned_at=SCANNED_AT,
        score=62,
        app_version=__version__,
        notes=[
            "Playwright недоступен: глубокий анализ не выполнен.",
            "robots.txt запрещает часть обхода — проверена только главная.",
        ],
        results=[
            _result(
                "a01_https",
                "HTTPS и TLS",
                "152fz",
                CheckStatus.PASS,
                message="Сайт открывается по HTTPS, сертификат валиден, TLS 1.3.",
                evidence=[Evidence(kind="header", label="TLS", value="TLSv1.3")],
            ),
            _result(
                "a02_privacy",
                "Политика конфиденциальности",
                "152fz",
                CheckStatus.FAIL,
                severity=Severity.CRITICAL,
                message="Ссылка на политику конфиденциальности не найдена в футере.",
                recommendation="Добавьте в футер ссылку на политику конфиденциальности.",
                evidence=[
                    Evidence(
                        kind="selector",
                        label="Футер",
                        value="ссылка не обнаружена",
                        selector="footer",
                    )
                ],
            ),
            _result(
                "a05_forms",
                "Формы и чекбокс согласия",
                "152fz",
                CheckStatus.WARN,
                severity=Severity.IMPORTANT,
                message="Найдена форма с e-mail без отдельного чекбокса согласия.",
                recommendation="Добавьте обязательный непредзаполненный чекбокс.",
                evidence=[
                    Evidence(
                        kind="selector",
                        label="Форма",
                        value="form#callback",
                        selector="form#callback",
                    )
                ],
            ),
            _result(
                "b01_seller",
                "Реквизиты продавца",
                "zozpp",
                CheckStatus.NOT_APPLICABLE,
                message=(
                    "На сайте не обнаружены признаки дистанционной продажи "
                    "товаров/услуг. Проверка реквизитов не требуется."
                ),
            ),
            _result(
                "c01_erid",
                "Маркировка интернет-рекламы (ERID)",
                "ad",
                CheckStatus.NOT_APPLICABLE,
                message="На странице не обнаружены рекламные блоки. Маркировка ERID не требуется.",
            ),
            _result(
                "d01_robots",
                "robots.txt",
                "tech",
                CheckStatus.PASS,
                message="robots.txt доступен.",
            ),
            _result(
                "d02_security",
                "Заголовки безопасности",
                "tech",
                CheckStatus.SKIP,
                message="Проверка не выполнена: сервер не ответил вовремя.",
            ),
            _result(
                "d03_sitemap",
                "sitemap.xml",
                "tech",
                CheckStatus.PASS,
                message="sitemap.xml найден.",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Фикстура и имена файлов
# ---------------------------------------------------------------------------


def test_fixture_covers_all_statuses(sample_report: Report) -> None:
    statuses = {result.status for result in sample_report.results}
    assert statuses == set(CheckStatus)
    assert len(sample_report.results) == 8
    assert sample_report.not_applicable()
    assert sample_report.skipped()


def test_export_format_values() -> None:
    assert ExportFormat.PDF.value == "pdf"
    assert ExportFormat.HTML.value == "html"
    assert ExportFormat.MARKDOWN.value == "md"
    assert ExportFormat.JSON.value == "json"
    assert ExportFormat("pdf") is ExportFormat.PDF


def test_suggest_path_creates_dir_without_file(
    sample_report: Report, tmp_path: Path
) -> None:
    target_dir = tmp_path / "nested" / "reports"
    path = suggest_path(sample_report, ExportFormat.PDF, target_dir)
    assert path.parent == target_dir
    assert target_dir.is_dir()
    assert not path.exists()
    pattern = "otchet-" + re.escape(DOMAIN) + r"-\d{4}-\d{2}-\d{2}-\d{4}\.pdf"
    assert re.fullmatch(pattern, path.name)
    assert path.suffix == ".pdf"


# ---------------------------------------------------------------------------
# Экспорт во все форматы
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", list(ExportFormat))
def test_export_each_format(
    sample_report: Report, tmp_path: Path, fmt: ExportFormat
) -> None:
    path = export_report(sample_report, fmt, tmp_path)
    assert isinstance(path, Path)
    assert path.exists()
    assert path.parent == tmp_path
    assert path.suffix == f".{fmt.value}"
    assert path.stat().st_size > 500


def test_export_accepts_string_format(sample_report: Report, tmp_path: Path) -> None:
    path = export_report(sample_report, "md", tmp_path)
    assert path.suffix == ".md"
    assert path.exists()


def test_export_creates_missing_directory(
    sample_report: Report, tmp_path: Path
) -> None:
    nested = tmp_path / "a" / "b" / "c"
    path = export_report(sample_report, ExportFormat.HTML, nested)
    assert nested.is_dir()
    assert path.exists()


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------


def test_html_content(sample_report: Report) -> None:
    html = build_html(sample_report)

    assert 'charset="utf-8"' in html
    assert "Разработка от PriRex" in html
    assert "boosty.to/prirex/donate" in html
    assert "Соответствие" in html
    assert "Не применимо" in html
    assert "Примечания сканирования" in html
    assert "Не удалось проверить" in html
    assert "Дисклеймер" in html
    assert "Рекомендация:" in html
    assert DOMAIN in html
    assert format_scanned_at(sample_report) in html
    assert __version__ in html
    assert "Политика конфиденциальности" in html
    # NA-проверка: пояснение есть, рекомендации нет
    na_part = html.split("Реквизиты продавца", 1)[1]
    assert "признаки дистанционной продажи" in na_part


def test_html_is_self_contained(sample_report: Report) -> None:
    html = build_html(sample_report)
    assert "<link" not in html.lower()
    assert "<script" not in html.lower()
    assert 'src="http' not in html.lower()
    assert "@import" not in html
    # инлайн-CSS присутствует
    assert "<style>" in html


def test_html_escapes_markup(tmp_path: Path) -> None:
    report = Report(
        url="https://evil.example/",
        final_url="https://evil.example/",
        scanned_at=SCANNED_AT,
        score=0,
        app_version=__version__,
        results=[
            _result(
                "x1",
                "<script>alert(1)</script>",
                "152fz",
                CheckStatus.FAIL,
                severity=Severity.CRITICAL,
                message="<b>не экранировано</b>",
            )
        ],
    )
    html = build_html(report)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<b>не экранировано</b>" not in html


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def test_markdown_content(sample_report: Report) -> None:
    markdown = build_markdown(sample_report)

    assert "Разработка от PriRex" in markdown
    assert "boosty.to/prirex/donate" in markdown
    assert "github.com/Prirex" in markdown
    assert "## Не применимо (N/A)" in markdown
    assert "## Не удалось проверить" in markdown
    assert "## Примечания сканирования" in markdown
    # чек-лист
    assert "- [x]" in markdown
    assert "- [ ]" in markdown
    # таблицы
    assert "| Статус |" in markdown
    # детали
    assert "**Рекомендация:**" in markdown
    assert "селектор: `footer`" in markdown
    assert DISCLAIMER.split(".")[0] in markdown


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def test_json_content(sample_report: Report) -> None:
    raw = build_json(sample_report)
    payload = json.loads(raw)

    assert payload["score"] == 62
    assert len(payload["results"]) == 8
    assert payload["generated_by"].startswith("PriRex Auditor")
    assert payload["disclaimer"] == DISCLAIMER
    # ensure_ascii=False: кириллица читается в сыром тексте
    assert "Политика конфиденциальности" in raw
    assert "not_applicable" in raw
    statuses = {item["status"] for item in payload["results"]}
    assert {"pass", "warn", "fail", "skip", "not_applicable"} <= statuses


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def test_pdf_content(sample_report: Report, tmp_path: Path) -> None:
    path = export_report(sample_report, ExportFormat.PDF, tmp_path)
    data = path.read_bytes()

    assert data.startswith(b"%PDF")
    assert len(data) > 3000
    assert b"%%EOF" in data[-1024:]
    # TrueType-шрифт встроен (кириллица не должна быть «квадратами»)
    assert b"/FontFile2" in data
    # имя файла соответствует шаблону
    pattern = "otchet-" + re.escape(DOMAIN) + r"-\d{4}-\d{2}-\d{2}-\d{4}\.pdf"
    assert re.fullmatch(pattern, path.name)


# ---------------------------------------------------------------------------
# Отсутствие логотипа не должно ронять экспорт
# ---------------------------------------------------------------------------


def test_missing_logo_falls_back_to_text(
    sample_report: Report, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "nowhere" / "logo.png"
    monkeypatch.setattr("app.paths.asset_path", lambda *parts, **kwargs: missing)

    html = build_html(sample_report)
    assert "PriRex" in html
    assert "data:image" not in html
    assert "brand-placeholder" in html

    html_path = export_report(sample_report, ExportFormat.HTML, tmp_path)
    assert html_path.exists() and html_path.stat().st_size > 500

    pdf_path = export_report(sample_report, ExportFormat.PDF, tmp_path)
    assert pdf_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF")
    assert pdf_path.stat().st_size > 3000


def test_brand_line_constant() -> None:
    assert BRAND_LINE == "Разработка от PriRex · github.com/Prirex"
