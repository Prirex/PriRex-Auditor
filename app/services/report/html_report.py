"""Экспорт отчёта в самодостаточный HTML-файл.

Один файл: инлайн-CSS в ``<style>``, логотип — base64 PNG из
``assets/logo.png`` (при отсутствии — текстовая подпись «PriRex»),
никаких внешних запросов. Внизу страницы — фиксированный (sticky) футер
с брендингом «Разработано PriRex · github.com/Prirex».
"""

from __future__ import annotations

from string import Template

from app.core.models import CheckResult, CheckStatus, Report
from app.services.report import common
from app.services.report.common import (
    BOOSTY_HTML,
    BRAND_HTML,
    COLORS,
    REPORT_KIND,
    REPORT_TITLE,
    ReportMeta,
    category_label,
    counter_rows,
    evidence_items,
    group_progress_text,
    group_summary,
    html_text,
    logo_data_uri,
    methodology_note,
    report_meta,
    severity_label,
    STATUS_COLORS,
    STATUS_TINTS,
)
from app.version import APP_DISPLAY_NAME

# ---------------------------------------------------------------------------
# Иконки статусов — inline SVG (без внешних файлов и без зависимости от эмодзи)
# ---------------------------------------------------------------------------

_ICON_PATHS: dict[CheckStatus, str] = {
    CheckStatus.PASS: (
        '<path d="M4.9 8.4l2.2 2.2 4.4-4.7" fill="none" stroke="#FFFFFF" '
        'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    CheckStatus.WARN: (
        '<path d="M8 4.5v4.2" fill="none" stroke="#FFFFFF" stroke-width="1.7" '
        'stroke-linecap="round"/><circle cx="8" cy="11.5" r="0.95" fill="#FFFFFF"/>'
    ),
    CheckStatus.FAIL: (
        '<path d="M5.8 5.8l4.4 4.4M10.2 5.8l-4.4 4.4" fill="none" stroke="#FFFFFF" '
        'stroke-width="1.7" stroke-linecap="round"/>'
    ),
    CheckStatus.SKIP: (
        '<path d="M5.2 8h5.6" fill="none" stroke="#FFFFFF" stroke-width="1.7" '
        'stroke-linecap="round"/>'
    ),
    CheckStatus.NOT_APPLICABLE: (
        '<path d="M5.8 10.2l4.4-4.4" fill="none" stroke="#FFFFFF" stroke-width="1.7" '
        'stroke-linecap="round"/>'
    ),
}

_BADGE_LABEL: dict[CheckStatus, str] = {
    CheckStatus.PASS: CheckStatus.PASS.label_ru,
    CheckStatus.WARN: CheckStatus.WARN.label_ru,
    CheckStatus.FAIL: CheckStatus.FAIL.label_ru,
    CheckStatus.SKIP: CheckStatus.SKIP.label_ru,
    CheckStatus.NOT_APPLICABLE: CheckStatus.NOT_APPLICABLE.label_ru,
}

_CSS_TEMPLATE = Template(
    """
:root {
  --bg: $bg;
  --surface: $surface;
  --surface-alt: $surface_alt;
  --text: $text;
  --text-strong: $text_strong;
  --muted: $muted;
  --accent: $accent;
  --border: $border;
  --border-soft: $border_soft;
  --link: $link;
  --pass: $pass;
  --warn: $warn;
  --fail: $fail;
  --skip: $skip;
  --na: $na;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 0 0 82px;
  background: var(--bg);
  color: var(--text);
  font-family: "Segoe UI", "Inter", -apple-system, "DejaVu Sans", Arial, sans-serif;
  font-size: 14px;
  line-height: 1.55;
  -webkit-text-size-adjust: 100%;
}
.wrap { max-width: 940px; margin: 0 auto; padding: 26px 22px 8px; }
header.report, section {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: 0 1px 3px rgba(46, 46, 46, 0.05);
}
header.report { padding: 22px 24px; }
section { padding: 20px 24px; margin-top: 16px; }
.brand { display: flex; align-items: center; gap: 12px; }
.brand-logo { height: 22px; width: auto; max-width: 200px; display: block; }
.brand-placeholder {
  height: 22px; line-height: 22px; font-size: 15px; font-weight: 600;
  letter-spacing: 0.3px; color: var(--text-strong);
}
.brand-name { font-size: 18px; font-weight: 600; color: var(--text-strong); }
.brand-sub { font-size: 12.5px; color: var(--muted); }
dl.meta {
  display: flex; flex-wrap: wrap; gap: 6px 26px;
  margin: 16px 0 0; padding: 0; font-size: 12.5px;
}
dl.meta div { display: flex; gap: 6px; }
dl.meta dt { color: var(--muted); }
dl.meta dd { margin: 0; color: var(--text); font-weight: 600; }
.score { display: flex; flex-wrap: wrap; align-items: center; gap: 26px; }
.score-value {
  font-size: 42px; line-height: 1.05; font-weight: 600;
  color: var(--text-strong); letter-spacing: -0.5px;
}
.score-value .caption {
  display: block; font-size: 11.5px; font-weight: 500;
  letter-spacing: 0.4px; color: var(--muted); text-transform: uppercase;
}
.score-grade { flex: 1 1 260px; }
.grade-title { font-size: 17px; font-weight: 600; color: var(--text-strong); }
.grade-hint { font-size: 12.5px; color: var(--muted); margin-top: 2px; }
.counters {
  display: grid; grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px; margin-top: 18px;
}
.counter {
  border: 1px solid var(--border-soft); border-radius: 6px;
  padding: 10px 12px; background: var(--surface-alt);
}
.counter b { display: block; font-size: 20px; line-height: 1.2; font-weight: 600; }
.counter span { font-size: 11.5px; color: var(--muted); }
.counter.pass b { color: var(--pass); }
.counter.warn b { color: var(--warn); }
.counter.fail b { color: var(--fail); }
.counter.not_applicable b { color: var(--na); }
.counter.skip b { color: var(--skip); }
h2 { font-size: 16px; margin: 0 0 6px; color: var(--text-strong); }
.lead { font-size: 12.5px; color: var(--muted); margin: 0 0 14px; }
h3 {
  font-size: 14px; margin: 20px 0 8px; color: var(--text-strong);
  display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline;
}
h3 .group-meta { font-size: 11.5px; font-weight: 400; color: var(--muted); }
table.mini { width: 100%; border-collapse: collapse; font-size: 12.5px; }
table.mini td { padding: 6px 8px; border-bottom: 1px solid var(--border-soft); vertical-align: middle; }
table.mini tr:last-child td { border-bottom: none; }
table.mini td.ico { width: 24px; }
table.mini td.st {
  width: 96px; text-align: right; white-space: nowrap;
  color: var(--muted); font-size: 11.5px;
}
.badge {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 2px 9px 2px 7px; border-radius: 999px;
  font-size: 11.5px; font-weight: 600; white-space: nowrap;
  border: 1px solid transparent;
}
.badge svg { display: block; }
.badge.st-pass { color: #5F7F5B; background: $pass_tint; border-color: rgba(143, 174, 139, 0.38); }
.badge.st-warn { color: #8A7038; background: $warn_tint; border-color: rgba(201, 169, 106, 0.40); }
.badge.st-fail { color: #94594E; background: $fail_tint; border-color: rgba(184, 122, 110, 0.38); }
.badge.st-skip { color: #5F6B78; background: $skip_tint; border-color: rgba(154, 165, 177, 0.40); }
.badge.st-not_applicable { color: #97692F; background: $na_tint; border-color: rgba(217, 164, 107, 0.40); }
article.check {
  border: 1px solid var(--border-soft);
  border-left: 3px solid var(--border);
  border-radius: 6px; padding: 12px 14px; margin: 10px 0;
  background: #FFFFFF;
}
article.check.st-pass { border-left-color: var(--pass); }
article.check.st-warn { border-left-color: var(--warn); }
article.check.st-fail { border-left-color: var(--fail); }
article.check.st-skip { border-left-color: var(--skip); }
article.check.st-not_applicable { border-left-color: var(--na); }
.check-head { display: flex; flex-wrap: wrap; gap: 8px 10px; align-items: center; }
.check-head h4 {
  margin: 0; font-size: 13.5px; font-weight: 600;
  color: var(--text-strong); flex: 1 1 auto;
}
.sev {
  font-size: 11px; color: var(--muted);
  border: 1px dashed var(--border); border-radius: 999px;
  padding: 1px 8px; white-space: nowrap;
}
.msg { margin: 9px 0 0; font-size: 13px; }
.evidence { list-style: none; margin: 9px 0 0; padding: 0; font-size: 12.5px; }
.evidence li { margin: 3px 0; color: var(--muted); }
.evidence .ev-label { color: var(--text); font-weight: 600; }
code {
  font-family: "Cascadia Mono", Consolas, "DejaVu Sans Mono", monospace;
  font-size: 11.5px; background: var(--surface-alt);
  border: 1px solid var(--border); border-radius: 4px;
  padding: 1px 5px; color: var(--text-strong);
}
.rec {
  margin-top: 10px; padding: 9px 12px;
  border-left: 3px solid var(--accent); border-radius: 0 6px 6px 0;
  background: rgba(122, 154, 126, 0.09); font-size: 12.5px;
}
.rec .rec-label { font-weight: 600; color: var(--text-strong); }
ul.plain { list-style: none; margin: 0; padding: 0; }
ul.plain > li { padding: 10px 0; border-bottom: 1px solid var(--border-soft); }
ul.plain > li:last-child { border-bottom: none; }
ul.plain p { margin: 5px 0 0; font-size: 12.5px; color: var(--muted); }
.item-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.item-head strong { font-size: 13px; color: var(--text-strong); }
.cat-tag { font-size: 11px; color: var(--muted); }
ul.notes { margin: 0; padding-left: 20px; font-size: 12.5px; color: var(--muted); }
ul.notes li { margin: 5px 0; }
.disclaimer p { margin: 0; font-size: 12px; color: var(--muted); }
.disclaimer strong { color: var(--text-strong); }
footer.brand {
  position: fixed; left: 0; right: 0; bottom: 0;
  background: var(--surface); border-top: 1px solid var(--border);
  box-shadow: 0 -1px 3px rgba(46, 46, 46, 0.04);
}
footer.brand .inner {
  max-width: 940px; margin: 0 auto; padding: 11px 22px;
  display: flex; flex-wrap: wrap; gap: 6px 18px;
  justify-content: space-between; align-items: center;
  font-size: 12px; color: var(--muted);
}
footer.brand a { color: var(--link); text-decoration: none; }
footer.brand a:hover { text-decoration: underline; }
@media (max-width: 720px) {
  .counters { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .score-value { font-size: 34px; }
  section, header.report { padding: 16px; }
}
    """
)


def _css() -> str:
    variables = dict(COLORS)
    variables.update(
        {
            "pass_tint": STATUS_TINTS[CheckStatus.PASS],
            "warn_tint": STATUS_TINTS[CheckStatus.WARN],
            "fail_tint": STATUS_TINTS[CheckStatus.FAIL],
            "skip_tint": STATUS_TINTS[CheckStatus.SKIP],
            "na_tint": STATUS_TINTS[CheckStatus.NOT_APPLICABLE],
        }
    )
    return _CSS_TEMPLATE.substitute(variables)


def _icon_svg(status: CheckStatus, size: int = 16) -> str:
    color = STATUS_COLORS[status]
    return (
        f'<svg viewBox="0 0 16 16" width="{size}" height="{size}" '
        f'role="img" aria-hidden="true" focusable="false">'
        f'<circle cx="8" cy="8" r="8" fill="{color}"/>'
        f"{_ICON_PATHS[status]}</svg>"
    )


def _badge(status: CheckStatus, size: int = 14) -> str:
    return (
        f'<span class="badge st-{status.value}">'
        f"{_icon_svg(status, size)}{_BADGE_LABEL[status]}</span>"
    )


# ---------------------------------------------------------------------------
# Блоки документа
# ---------------------------------------------------------------------------


def _header(meta: ReportMeta) -> list[str]:
    logo = logo_data_uri()
    if logo:
        brand_mark = (
            f'<img class="brand-logo" src="{logo}" alt="{html_text(APP_DISPLAY_NAME)}">'
        )
    else:
        brand_mark = f'<span class="brand-placeholder">{html_text("PriRex")}</span>'
    address = html_text(meta.url) or "—"
    return [
        '<header class="report">',
        '<div class="brand">',
        brand_mark,
        '<div>',
        f'<div class="brand-name">{html_text(APP_DISPLAY_NAME)}</div>',
        f'<div class="brand-sub">{html_text(REPORT_TITLE)}</div>',
        "</div>",
        "</div>",
        '<dl class="meta">',
        f"<div><dt>Адрес сайта:</dt><dd>{address}</dd></div>",
        f"<div><dt>Дата проверки:</dt><dd>{html_text(meta.date_text)}</dd></div>",
        f"<div><dt>Версия приложения:</dt><dd>{html_text(meta.version)}</dd></div>",
        "</dl>",
        "</header>",
    ]


def _score_block(report: Report, meta: ReportMeta) -> list[str]:
    counters = []
    for label, value, status in counter_rows(report):
        counters.append(
            f'<div class="counter {status.value}">'
            f"<b>{value}</b><span>{html_text(label)}</span></div>"
        )
    return [
        '<section class="score-card">',
        '<div class="score">',
        '<div class="score-value">'
        f'<span class="caption">Соответствие:</span>{meta.score}<span class="pct">%</span>'
        "</div>",
        '<div class="score-grade">',
        f'<div class="grade-title">{html_text(meta.grade_title)}</div>',
        f'<div class="grade-hint">{html_text(meta.grade_hint)}</div>',
        "</div>",
        "</div>",
        f'<div class="counters">{"".join(counters)}</div>',
        "</section>",
    ]


def _summary(report: Report) -> list[str]:
    parts: list[str] = ["<section>", "<h2>Сводка по блокам</h2>"]
    groups = group_summary(report)
    if not groups:
        parts.append('<p class="lead">Проверки не выполнялись.</p>')
    for category, items, passed, applicable in groups:
        parts.append("<div>")
        parts.append(
            f'<h3>{html_text(category_label(category))}'
            f'<span class="group-meta">'
            f"{html_text(group_progress_text(passed, applicable))}</span></h3>"
        )
        parts.append('<table class="mini"><tbody>')
        for result in items:
            parts.append(
                "<tr>"
                f'<td class="ico">{_icon_svg(result.status)}</td>'
                f"<td>{html_text(result.title)}</td>"
                f'<td class="st">{html_text(result.status.label_ru)}</td>'
                "</tr>"
            )
        parts.append("</tbody></table>")
        parts.append("</div>")
    parts.append("</section>")
    return parts


def _check_card(result: CheckResult) -> list[str]:
    severity = severity_label(result)
    parts = [
        f'<article class="check st-{result.status.value}">',
        '<div class="check-head">',
        _badge(result.status),
        f"<h4>{html_text(result.title)}</h4>",
    ]
    if severity:
        parts.append(f'<span class="sev">{html_text(severity)}</span>')
    parts.append("</div>")

    message = html_text(result.message)
    if message:
        parts.append(f'<p class="msg">{message}</p>')
    if result.error:
        parts.append(f'<p class="msg"><code>{html_text(result.error)}</code></p>')

    if result.status is not CheckStatus.NOT_APPLICABLE:
        evidence = evidence_items(result)
        if evidence:
            parts.append('<ul class="evidence">')
            for item in evidence:
                value = html_text(item["value"]) or "—"
                selector = (
                    f' <code>{html_text(item["selector"])}</code>'
                    if item["selector"]
                    else ""
                )
                parts.append(
                    f'<li><span class="ev-label">{html_text(item["label"])}:</span> '
                    f"{value}{selector}</li>"
                )
            parts.append("</ul>")
        recommendation = html_text(result.recommendation)
        if recommendation:
            parts.append(
                f'<div class="rec"><span class="rec-label">Рекомендация:</span> '
                f"{recommendation}</div>"
            )
    note = methodology_note(result.check_id)
    if note:
        parts.append(
            '<p class="mref">'
            f'<span style="font-size:11px;color:{COLORS["muted"]};">'
            f"{html_text(note)}</span></p>"
        )
    parts.append("</article>")
    return parts


def _details(report: Report) -> list[str]:
    parts = ["<section>", "<h2>Детальные результаты</h2>"]
    groups = report.grouped()
    if not groups:
        parts.append('<p class="lead">Проверки не выполнялись.</p>')
    for category, items in groups:
        parts.append(f"<h3>{html_text(category_label(category))}</h3>")
        for result in items:
            parts.extend(_check_card(result))
    parts.append("</section>")
    return parts


def _na_section(report: Report) -> list[str]:
    items = report.not_applicable()
    if not items:
        return []
    parts = [
        '<section class="na">',
        "<h2>Не применимо (N/A)</h2>",
        '<p class="lead">Эти проверки не применимы к сайту и не влияют на процент '
        "соответствия. Пояснение указано для каждой проверки.</p>",
        '<ul class="plain">',
    ]
    for result in items:
        parts.append("<li>")
        parts.append('<div class="item-head">')
        parts.append(_badge(result.status))
        parts.append(f"<strong>{html_text(result.title)}</strong>")
        parts.append(
            f'<span class="cat-tag">{html_text(category_label(result.category))}</span>'
        )
        parts.append("</div>")
        if result.message:
            parts.append(f"<p>{html_text(result.message)}</p>")
        parts.append("</li>")
    parts.extend(["</ul>", "</section>"])
    return parts


def _skipped_section(report: Report) -> list[str]:
    items = report.skipped()
    if not items:
        return []
    parts = [
        '<section class="skipped">',
        "<h2>Не удалось проверить</h2>",
        '<ul class="plain">',
    ]
    for result in items:
        parts.append("<li>")
        parts.append('<div class="item-head">')
        parts.append(_badge(result.status))
        parts.append(f"<strong>{html_text(result.title)}</strong>")
        parts.append(
            f'<span class="cat-tag">{html_text(category_label(result.category))}</span>'
        )
        parts.append("</div>")
        if result.message:
            parts.append(f"<p>{html_text(result.message)}</p>")
        if result.error:
            parts.append(f'<p><code>{html_text(result.error)}</code></p>')
        parts.append("</li>")
    parts.extend(["</ul>", "</section>"])
    return parts


def _notes(report: Report) -> list[str]:
    if not report.notes:
        return []
    items = "".join(f"<li>{html_text(note)}</li>" for note in report.notes)
    return [
        '<section class="notes">',
        "<h2>Примечания сканирования</h2>",
        '<p class="lead">Ограничения проверки, о которых стоит знать при чтении отчёта.</p>',
        f'<ul class="notes">{items}</ul>',
        "</section>",
    ]


def _disclaimer() -> list[str]:
    return [
        '<section class="disclaimer">',
        "<h2>Дисклеймер</h2>",
        f"<p><strong>{html_text(APP_DISPLAY_NAME)}</strong> — автоматическая "
        f"эвристическая проверка. {html_text(common.DISCLAIMER_TEXT)}</p>",
        "</section>",
    ]


def _footer(meta: ReportMeta) -> list[str]:
    return [
        '<footer class="brand">',
        '<div class="inner">',
        f"<span>{BRAND_HTML} · {BOOSTY_HTML}</span>",
        f"<span>{html_text(APP_DISPLAY_NAME)} · v{html_text(meta.version)}</span>",
        "</div>",
        "</footer>",
        "</div>",
        "</body>",
        "</html>",
    ]


# ---------------------------------------------------------------------------
# Публичная функция
# ---------------------------------------------------------------------------


def build_html(report: Report) -> str:
    """Собрать самодостаточный HTML-отчёт одной строкой-документом."""
    meta = report_meta(report)
    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="ru">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<meta name="generator" content="{html_text(APP_DISPLAY_NAME)} v{html_text(meta.version)}">',
        f"<title>{html_text(APP_DISPLAY_NAME)} — {html_text(REPORT_KIND)} "
        f"({html_text(meta.domain)})</title>",
        f"<style>{_css()}</style>",
        "</head>",
        "<body>",
        '<div class="wrap">',
    ]
    parts.extend(_header(meta))
    parts.extend(_score_block(report, meta))
    parts.extend(_summary(report))
    parts.extend(_details(report))
    parts.extend(_na_section(report))
    parts.extend(_skipped_section(report))
    parts.extend(_notes(report))
    parts.extend(_disclaimer())
    parts.extend(_footer(meta))
    return "\n".join(parts) + "\n"


__all__ = ["build_html"]
