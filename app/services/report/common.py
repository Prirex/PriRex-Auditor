"""Общие данные и помощники для всех форматов экспорта отчёта.

Здесь сосредоточено всё, что должно выглядеть одинаково в PDF, HTML,
Markdown и JSON: палитра, иконки/подписи статусов, счётчики, метаданные
отчёта (адрес, дата, версия), путь к логотипу, правила имени файла и
брендинг-футер «Разработка от PriRex · github.com/Prirex».
"""

from __future__ import annotations

import base64
import html
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

from app import paths
from app.core.models import CATEGORY_LABELS, CheckResult, CheckStatus, Report
from app.version import (
    APP_DISPLAY_NAME,
    AUTHOR,
    AUTHOR_URL,
    BOOSTY_LABEL,
    BOOSTY_URL,
    DISCLAIMER,
    __version__,
)

# ---------------------------------------------------------------------------
# Тексты и брендинг
# ---------------------------------------------------------------------------

REPORT_TITLE = "Проверка соответствия сайта требованиям РФ"
REPORT_KIND = "Отчёт о проверке сайта"
BRAND_GITHUB_LABEL = "github.com/Prirex"
BRAND_LINE = f"Разработка от {AUTHOR} · {BRAND_GITHUB_LABEL}"
BRAND_HTML = (
    f"Разработка от {AUTHOR} · "
    f'<a href="{AUTHOR_URL}">{BRAND_GITHUB_LABEL}</a>'
)
BRAND_MARKDOWN = f"Разработка от {AUTHOR} · [github.com/Prirex]({AUTHOR_URL})"
BOOSTY_INLINE = "boosty.to/prirex/donate"
BOOSTY_LINE = f"{BOOSTY_LABEL}: {BOOSTY_URL}"
BOOSTY_HTML = f'<a href="{BOOSTY_URL}">{BOOSTY_LABEL}</a>'
BOOSTY_MARKDOWN = f"[{BOOSTY_LABEL}]({BOOSTY_URL})"
DISCLAIMER_TEXT = DISCLAIMER
DEFAULT_DOMAIN = "site"


def methodology_id(check_id: str) -> str:
    """Номер проверки в справочнике «Критерии проверок» («4.2») или пусто."""
    try:
        from app.core.content.loader import methodology_for

        item = methodology_for(check_id)
        return item.id if item is not None else ""
    except Exception:  # noqa: BLE001 - отчёт не должен зависеть от справочника
        return ""


def methodology_note(check_id: str) -> str:
    """Сноска «Подробнее — см. Критерии проверок, п. 4.X»."""
    number = methodology_id(check_id)
    if not number:
        return ""
    return f"Подробнее — см. Критерии проверок, п. {number}."


def methodology_updated_at() -> str:
    """Дата актуальности методологии («14.11.2026») или пусто."""
    try:
        from app.core.content.loader import methodology_updated_at as updated

        return updated()
    except Exception:  # noqa: BLE001
        return ""


class ExportFormat(str, Enum):
    """Поддерживаемые форматы экспорта отчёта."""

    PDF = "pdf"
    HTML = "html"
    MARKDOWN = "md"
    JSON = "json"

    @property
    def extension(self) -> str:
        return self.value

    def __str__(self) -> str:  # pragma: no cover - удобство логов/UI
        return self.value


# ---------------------------------------------------------------------------
# Палитра (раздел 5.1 ТЗ): приглушённые тёплые тона, без кислотных цветов
# ---------------------------------------------------------------------------

COLORS: dict[str, str] = {
    "bg": "#F2F0EC",
    "surface": "#FBFAF7",
    "surface_alt": "#F7F5F1",
    "text": "#2E2E2E",
    "text_strong": "#4A463F",
    "muted": "#6E6A63",
    "accent": "#7A9A7E",
    "accent_dark": "#6B8A6F",
    "border": "#E0DDD8",
    "border_soft": "#EDEAE4",
    "link": "#6B7F99",
    "pass": "#8FAE8B",
    "warn": "#C9A96A",
    "fail": "#B87A6E",
    "skip": "#9AA5B1",
    "na": "#D9A46B",
}

STATUS_COLORS: dict[CheckStatus, str] = {
    CheckStatus.PASS: COLORS["pass"],
    CheckStatus.WARN: COLORS["warn"],
    CheckStatus.FAIL: COLORS["fail"],
    CheckStatus.SKIP: COLORS["skip"],
    CheckStatus.NOT_APPLICABLE: COLORS["na"],
}

#: Полупрозрачные подложки для HTML-бейджей (rgba, а не 8-значный hex).
STATUS_TINTS: dict[CheckStatus, str] = {
    CheckStatus.PASS: "rgba(143, 174, 139, 0.16)",
    CheckStatus.WARN: "rgba(201, 169, 106, 0.18)",
    CheckStatus.FAIL: "rgba(184, 122, 110, 0.16)",
    CheckStatus.SKIP: "rgba(154, 165, 177, 0.18)",
    CheckStatus.NOT_APPLICABLE: "rgba(217, 164, 107, 0.18)",
}

#: Эмодзи для Markdown (раздел 5.1 ТЗ).
STATUS_EMOJI: dict[CheckStatus, str] = {
    CheckStatus.PASS: "✅",
    CheckStatus.WARN: "⚠️",
    CheckStatus.FAIL: "❌",
    CheckStatus.SKIP: "⏭",
    CheckStatus.NOT_APPLICABLE: "🟠",
}

#: Подписи счётчиков: (ключ counts(), подпись).
COUNTERS: list[tuple[str, str]] = [
    ("pass", "Пройдено"),
    ("warn", "Замечаний"),
    ("fail", "Нарушений"),
    ("not_applicable", "Не применимо"),
    ("skip", "Не проверено"),
]

COUNTER_STATUS: dict[str, CheckStatus] = {
    "pass": CheckStatus.PASS,
    "warn": CheckStatus.WARN,
    "fail": CheckStatus.FAIL,
    "not_applicable": CheckStatus.NOT_APPLICABLE,
    "skip": CheckStatus.SKIP,
}


# ---------------------------------------------------------------------------
# Словесная оценка процента
# ---------------------------------------------------------------------------

#: Резервная копия оценок из ``app.core.engine.scoring`` — используется, если
#: пакет движка ещё не собрался (идёт параллельная разработка) или импорт
#: по какой-то причине недоступен. Значения совпадают с оригиналом.
_FALLBACK_GRADES: list[tuple[int, str, str]] = [
    (90, "Отличное соответствие", "Формальные требования в основном соблюдены."),
    (75, "Хорошее соответствие", "Есть замечания, которые стоит устранить."),
    (60, "Умеренное соответствие", "Несколько важных требований не выполнено."),
    (40, "Много замечаний", "Значительная часть требований не выполнена."),
    (0, "Высокий риск", "Есть критические нарушения — нужна доработка сайта."),
]


def _fallback_grade(score: int) -> tuple[str, str]:
    for threshold, title, hint in _FALLBACK_GRADES:
        if score >= threshold:
            return title, hint
    return _FALLBACK_GRADES[-1][1], _FALLBACK_GRADES[-1][2]


def grade_for(score: int) -> tuple[str, str]:
    """Заголовок и пояснение для процента соответствия.

    Основной источник — ``app.core.engine.scoring.score_grade``; ленивый
    импорт не даёт отчётам зависеть от полной загрузки движка проверок.
    """
    try:
        from app.core.engine.scoring import score_grade
    except Exception:  # noqa: BLE001 - движок может быть ещё не собран
        return _fallback_grade(int(score))
    try:
        return score_grade(int(score))
    except Exception:  # noqa: BLE001 - не роняем экспорт из-за скоринга
        return _fallback_grade(int(score))


# ---------------------------------------------------------------------------
# Метаданные отчёта
# ---------------------------------------------------------------------------


def report_url(report: Report) -> str:
    """Адрес сайта: ``final_url``, иначе исходный ``url``."""
    return (report.final_url or report.url or "").strip()


def report_domain(report: Report) -> str:
    """Домен для имени файла и заголовков (без схемы, порта и userinfo)."""
    raw = report_url(report)
    if not raw:
        return DEFAULT_DOMAIN
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    host = (parsed.netloc or parsed.path or "").strip()
    host = host.rsplit("@", 1)[-1]
    if host.startswith("["):  # IPv6
        host = host.split("]")[0].lstrip("[")
    elif ":" in host:
        host = host.split(":", 1)[0]
    host = host.strip().lower().strip(".")
    return host or DEFAULT_DOMAIN


def local_scanned_at(report: Report) -> datetime:
    """Время проверки в локальной зоне (naive-время считаем локальным)."""
    when = report.scanned_at
    if when is None:
        return datetime.now()
    if when.tzinfo is not None:
        return when.astimezone()
    return when


def format_scanned_at(report: Report) -> str:
    """``14.11.2026 10:45`` — как в ТЗ."""
    return local_scanned_at(report).strftime("%d.%m.%Y %H:%M")


def report_version(report: Report) -> str:
    return (report.app_version or __version__).strip()


@dataclass(frozen=True)
class ReportMeta:
    """Всё, что нужно шапке отчёта в любом формате."""

    url: str
    domain: str
    scanned_at: datetime
    date_text: str
    version: str
    score: int
    grade_title: str
    grade_hint: str
    counts: dict[str, int]
    generated_by: str


def report_meta(report: Report) -> ReportMeta:
    score = int(report.score or 0)
    grade_title, grade_hint = grade_for(score)
    return ReportMeta(
        url=report_url(report),
        domain=report_domain(report),
        scanned_at=local_scanned_at(report),
        date_text=format_scanned_at(report),
        version=report_version(report),
        score=score,
        grade_title=grade_title,
        grade_hint=grade_hint,
        counts=report.counts(),
        generated_by=f"{APP_DISPLAY_NAME} {report_version(report)}",
    )


def counter_rows(report: Report) -> list[tuple[str, str, int, CheckStatus]]:
    """Счётчики для блока «Крупно»: (подпись, значение, статус)."""
    counts = report.counts()
    return [
        (label, counts.get(key, 0), COUNTER_STATUS[key])
        for key, label in COUNTERS
    ]


# ---------------------------------------------------------------------------
# Статусы, категории, evidence
# ---------------------------------------------------------------------------


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category or "Прочее")


def severity_label(result: CheckResult) -> str:
    """Приоритет показываем только для fail/warn."""
    if result.status in (CheckStatus.FAIL, CheckStatus.WARN):
        return result.severity.label_ru
    return ""


def evidence_items(result: CheckResult) -> list[dict[str, str]]:
    """Нормализованный список evidence: label / value / selector."""
    items: list[dict[str, str]] = []
    for entry in result.evidence or []:
        value = (entry.value or "").strip()
        selector = (entry.selector or "").strip()
        if not value and not selector:
            continue
        items.append(
            {
                "label": (entry.label or "").strip() or "Данные",
                "value": value,
                "selector": selector,
                "kind": entry.kind or "text",
            }
        )
    return items


def group_summary(report: Report) -> list[tuple[str, list[CheckResult], int, int]]:
    """Блоки отчёта: (категория, проверки, пройдено применимых, всего применимых)."""

    out: list[tuple[str, list[CheckResult], int, int]] = []
    for category, items in report.grouped():
        applicable = [r for r in items if r.affects_score]
        passed = sum(1 for r in applicable if r.status is CheckStatus.PASS)
        out.append((category, items, passed, len(applicable)))
    return out


def group_progress_text(passed: int, applicable: int) -> str:
    """Подпись к блоку: «пройдено 2 из 5 применимых» / «проверки не применимы»."""
    if applicable <= 0:
        return "проверки не применимы"
    return f"пройдено {passed} из {applicable} применимых"


# ---------------------------------------------------------------------------
# Текстовые помощники
# ---------------------------------------------------------------------------


def one_line(value: object) -> str:
    """Схлопывает переводы строк и повторные пробелы."""
    return " ".join(str(value or "").split())


def html_text(value: object) -> str:
    """Безопасный текст для HTML (все спецсимволы экранируются)."""
    return html.escape(one_line(value), quote=True)


def md_text(value: object) -> str:
    """Однострочный текст, безопасный внутри markdown-таблицы/строки."""
    return one_line(value).replace("\\", "\\\\").replace("|", "\\|")


def md_heading(value: object) -> str:
    """Текст для заголовка: без решёток и переносов."""
    return one_line(value).replace("#", "＃")


# ---------------------------------------------------------------------------
# Логотип
# ---------------------------------------------------------------------------


def logo_path() -> Path | None:
    """Путь к ``assets/logo.png``, если файл существует и не пуст."""
    try:
        candidate = Path(paths.asset_path("logo.png"))
    except Exception:  # noqa: BLE001 - путь не должен ронять экспорт
        return None
    try:
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    except OSError:
        return None
    return None


def logo_data_uri() -> str | None:
    """``data:image/png;base64,...`` для самодостаточного HTML."""
    path = logo_path()
    if path is None:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if not data:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif data[:6] in (b"GIF87a", b"GIF89a"):
        mime = "image/gif"
    else:
        mime = "image/png"
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


# ---------------------------------------------------------------------------
# Имя файла отчёта
# ---------------------------------------------------------------------------


def report_filename(
    report: Report,
    fmt: ExportFormat,
    moment: datetime | None = None,
) -> str:
    """``otchet-<домен>-<YYYY-MM-DD-HHMM>.<ext>`` только из безопасных символов."""
    fmt = fmt if isinstance(fmt, ExportFormat) else ExportFormat(fmt)
    when = moment or local_scanned_at(report)
    stamp = when.strftime("%Y-%m-%d-%H%M")
    domain = paths.safe_filename(report_domain(report), DEFAULT_DOMAIN)
    return f"otchet-{domain}-{stamp}.{fmt.extension}"


__all__ = [
    "BOOSTY_HTML",
    "BOOSTY_INLINE",
    "BOOSTY_LINE",
    "BOOSTY_MARKDOWN",
    "BRAND_GITHUB_LABEL",
    "BRAND_HTML",
    "BRAND_LINE",
    "BRAND_MARKDOWN",
    "COLORS",
    "COUNTERS",
    "DEFAULT_DOMAIN",
    "DISCLAIMER_TEXT",
    "ExportFormat",
    "REPORT_KIND",
    "REPORT_TITLE",
    "STATUS_COLORS",
    "STATUS_EMOJI",
    "STATUS_TINTS",
    "ReportMeta",
    "category_label",
    "counter_rows",
    "evidence_items",
    "format_scanned_at",
    "grade_for",
    "group_progress_text",
    "group_summary",
    "html_text",
    "local_scanned_at",
    "logo_data_uri",
    "logo_path",
    "md_heading",
    "md_text",
    "methodology_id",
    "methodology_note",
    "methodology_updated_at",
    "one_line",
    "report_domain",
    "report_filename",
    "report_meta",
    "report_url",
    "report_version",
    "severity_label",
]
