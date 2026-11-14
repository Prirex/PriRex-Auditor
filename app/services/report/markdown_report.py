"""Экспорт отчёта в Markdown.

Структурированный документ: заголовки, таблицы в разрезе блоков,
чек-лист (``- [x]`` / ``- [ ]``), отдельные секции «Не применимо (N/A)»,
«Не удалось проверить», примечания, приложение с полной методологией
проверок и брендинг-строка в конце.
"""

from __future__ import annotations

from app.core.models import CheckResult, CheckStatus, Report
from app.services.report.common import (
    BOOSTY_MARKDOWN,
    BRAND_MARKDOWN,
    DISCLAIMER_TEXT,
    REPORT_TITLE,
    category_label,
    counter_rows,
    evidence_items,
    group_summary,
    md_heading,
    md_text,
    methodology_note,
    report_meta,
    severity_label,
    STATUS_EMOJI,
)
from app.version import APP_DISPLAY_NAME


def _table(headers: list[str], rows: list[list[str]], align: str = "---") -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(align for _ in headers) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def _check_block(result: CheckResult) -> list[str]:
    emoji = STATUS_EMOJI[result.status]
    lines = [
        f"#### {emoji} {md_heading(result.title)}",
        "",
        f"- **Статус:** {emoji} {md_text(result.status.label_ru)}",
    ]
    severity = severity_label(result)
    if severity:
        lines.append(f"- **Приоритет:** {md_text(severity)}")
    message = md_text(result.message)
    if message:
        lines.append(f"- **Сообщение:** {message}")
    if result.error:
        lines.append(f"- **Ошибка:** `{md_text(result.error)}`")

    if result.status is not CheckStatus.NOT_APPLICABLE:
        evidence = evidence_items(result)
        if evidence:
            lines.append("- **Evidence:**")
            for item in evidence:
                value = md_text(item["value"]) or "—"
                suffix = (
                    f" (селектор: `{md_text(item['selector'])}`)"
                    if item["selector"]
                    else ""
                )
                lines.append(f"  - `{md_text(item['label'])}`: {value}{suffix}")
        recommendation = md_text(result.recommendation)
        if recommendation:
            lines.append(f"- **Рекомендация:** {recommendation}")
    note = methodology_note(result.check_id)
    if note:
        lines.append(f"- **Подробнее:** {md_text(note)}")
    lines.append("")
    return lines


def _methodology_appendix() -> list[str]:
    """Приложение с полным содержимым справочника «Критерии проверок»."""
    try:
        from app.core.content.loader import load_methodology

        data = load_methodology()
    except Exception:  # noqa: BLE001 - отчёт не должен падать без справочника
        data = None
    if data is None or not data.blocks:
        return []
    lines: list[str] = ["## Приложение. Критерии проверок", ""]
    if data.updated_at:
        lines.append(f"*Актуально на {md_text(data.updated_at)}.*")
        lines.append("")
    if data.intro:
        lines.append(md_text(data.intro))
        lines.append("")
    for block in data.blocks:
        lines.extend([f"### Блок {block.id}. {md_heading(block.title)}", ""])
        for check in block.checks:
            body = check.as_markdown().strip()
            if body.startswith("## "):
                body = "#### " + body[3:]
            lines.extend([body, ""])
    return lines


def build_markdown(report: Report) -> str:
    """Собрать Markdown-отчёт (UTF-8, без внешних ресурсов)."""
    meta = report_meta(report)
    lines: list[str] = [
        f"# {APP_DISPLAY_NAME} — отчёт о проверке сайта",
        "",
        f"**{REPORT_TITLE}**",
        "",
        f"- **Адрес сайта:** {md_text(meta.url) or '—'}",
        f"- **Дата проверки:** {md_text(meta.date_text)}",
        f"- **Версия приложения:** {md_text(meta.version)}",
        "",
        f"## Соответствие: {meta.score}%",
        "",
        f"**{md_text(meta.grade_title)}** — {md_text(meta.grade_hint)}",
        "",
    ]

    counter_headers = [label for label, _value, _status in counter_rows(report)]
    counter_values = [str(value) for _label, value, _status in counter_rows(report)]
    lines.extend(
        _table(
            counter_headers,
            [counter_values],
            align=":---:",
        )
    )
    lines.append("")

    lines.extend(["## Сводка по блокам", ""])
    groups = group_summary(report)
    if not groups:
        lines.extend(["Проверки не выполнялись.", ""])
    for category, items, passed, applicable in groups:
        lines.append(f"### {md_heading(category_label(category))}")
        lines.append("")
        rows = [
            [
                STATUS_EMOJI[result.status],
                md_text(result.title),
                md_text(result.status.label_ru),
            ]
            for result in items
        ]
        lines.extend(_table(["Статус", "Проверка", "Итог"], rows))
        lines.append("")
        for result in items:
            mark = "x" if result.status is CheckStatus.PASS else " "
            lines.append(
                f"- [{mark}] {STATUS_EMOJI[result.status]} {md_text(result.title)}"
            )
        lines.append("")

    lines.extend(["## Детальные результаты", ""])
    for category, items in report.grouped():
        lines.append(f"### {md_heading(category_label(category))}")
        lines.append("")
        for result in items:
            lines.extend(_check_block(result))

    na_items = report.not_applicable()
    if na_items:
        lines.extend(["## Не применимо (N/A)", ""])
        for result in na_items:
            lines.append(
                f"- {STATUS_EMOJI[result.status]} **{md_text(result.title)}** "
                f"({md_text(category_label(result.category))}) — "
                f"{md_text(result.message) or 'проверка не применима к сайту'}"
            )
        lines.append("")

    skipped_items = report.skipped()
    if skipped_items:
        lines.extend(["## Не удалось проверить", ""])
        for result in skipped_items:
            detail = md_text(result.message) or "проверка не выполнена"
            lines.append(
                f"- {STATUS_EMOJI[result.status]} **{md_text(result.title)}** — {detail}"
            )
        lines.append("")

    if report.notes:
        lines.extend(["## Примечания сканирования", ""])
        for note in report.notes:
            lines.append(f"- {md_text(note)}")
        lines.append("")

    appendix = _methodology_appendix()
    if appendix:
        lines.extend(["---", ""])
        lines.extend(appendix)

    lines.extend(
        [
            "---",
            "",
            md_text(DISCLAIMER_TEXT),
            "",
            "---",
            "",
            f"{BRAND_MARKDOWN} · {BOOSTY_MARKDOWN}",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = ["build_markdown"]
