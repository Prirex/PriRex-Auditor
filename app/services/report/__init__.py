"""Публичный API экспорта отчётов.

UI должен работать только через этот модуль::

    from app.services.report import (
        ExportFormat, build_html, export_report, suggest_path,
    )

    path = export_report(report, ExportFormat.PDF, report_dir)

Ни один модуль пакета не импортирует Qt и не показывает диалогов —
выбор папки/имени файла остаётся за UI.
"""

from __future__ import annotations

from pathlib import Path

from app import paths
from app.core.models import Report
from app.services.report.common import ExportFormat, report_filename
from app.services.report.html_report import build_html
from app.services.report.json_report import build_json
from app.services.report.markdown_report import build_markdown
from app.services.report.pdf_report import build_pdf

_TEXT_BUILDERS = {
    ExportFormat.HTML: build_html,
    ExportFormat.MARKDOWN: build_markdown,
    ExportFormat.JSON: build_json,
}


def _coerce_format(fmt: ExportFormat | str) -> ExportFormat:
    return fmt if isinstance(fmt, ExportFormat) else ExportFormat(fmt)


def suggest_path(
    report: Report,
    fmt: ExportFormat | str,
    directory: Path | str | None = None,
) -> Path:
    """Предложить полный путь файла отчёта (папка создаётся, файл — нет).

    Имя: ``otchet-<домен>-<YYYY-MM-DD-HHMM>.<ext>``, домен берётся из
    ``report.final_url`` (или ``report.url``) и чистится от опасных символов.
    По умолчанию папка — ``app.paths.default_report_dir()``.
    """
    export_format = _coerce_format(fmt)
    target_dir = paths.ensure_report_dir(directory)
    return target_dir / report_filename(report, export_format)


def export_report(
    report: Report,
    fmt: ExportFormat | str,
    directory: Path | str | None = None,
) -> Path:
    """Экспортировать отчёт и вернуть путь к созданному файлу.

    Папка создаётся автоматически. Кодировка текстовых форматов — UTF-8.
    """
    export_format = _coerce_format(fmt)
    target = suggest_path(report, export_format, directory)
    if export_format is ExportFormat.PDF:
        target.write_bytes(build_pdf(report))
    else:
        content = _TEXT_BUILDERS[export_format](report)
        target.write_text(content, encoding="utf-8", newline="\n")
    return target


__all__ = [
    "ExportFormat",
    "build_html",
    "build_json",
    "build_markdown",
    "build_pdf",
    "export_report",
    "report_filename",
    "suggest_path",
]
