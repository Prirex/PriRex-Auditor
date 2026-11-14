"""Экспорт отчёта в PDF (reportlab platypus).

Особенности:
  * шрифт с кириллицей регистрируется из системных TTF (Segoe UI / Arial /
    DejaVu Sans и т.п.); если ни один не найден — аккуратный fallback на
    Helvetica с транслитерацией, чтобы в тексте не было «квадратов»;
  * логотип вставляется как изображение (если файл валиден), иначе —
    текстовая подпись «PriRex»;
  * на каждой странице — футер «Разработано PriRex · github.com/Prirex»
    и номер страницы «стр. N»;
  * палитра и статусы — из общего модуля ``common``.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import Flowable
from xml.sax.saxutils import escape

from app.core.models import CheckResult, CheckStatus, Report
from app.services.report import common
from app.services.report.common import (
    BOOSTY_INLINE,
    BRAND_LINE,
    COLORS,
    REPORT_TITLE,
    STATUS_COLORS,
    category_label,
    counter_rows,
    evidence_items,
    group_progress_text,
    group_summary,
    methodology_note,
    report_meta,
    severity_label,
)
from app.version import APP_DISPLAY_NAME, AUTHOR

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_LR = 16 * mm
MARGIN_TOP = 15 * mm
MARGIN_BOTTOM = 21 * mm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN_LR

_FONT_REGULAR_NAME = "PriRexSans"
_FONT_BOLD_NAME = "PriRexSans-Bold"

_REGULAR_FILES = (
    "segoeui.ttf",
    "arial.ttf",
    "calibri.ttf",
    "tahoma.ttf",
    "DejaVuSans.ttf",
    "LiberationSans-Regular.ttf",
)
_BOLD_FILES = (
    "segoeuib.ttf",
    "arialbd.ttf",
    "calibrib.ttf",
    "tahomabd.ttf",
    "DejaVuSans-Bold.ttf",
    "LiberationSans-Bold.ttf",
)

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E",
    "Ж": "Zh", "З": "Z", "И": "I", "Й": "Y", "К": "K", "Л": "L", "М": "M",
    "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
    "Ф": "F", "Х": "Kh", "Ц": "Ts", "Ч": "Ch", "Ш": "Sh", "Щ": "Shch",
    "Ъ": "", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "Yu", "Я": "Ya",
    "«": '"', "»": '"', "—": "-", "–": "-", "№": "N", "…": "...",
}


@dataclass(frozen=True)
class _FontSet:
    regular: str
    bold: str
    unicode_ok: bool


_FONTS: _FontSet | None = None


# ---------------------------------------------------------------------------
# Шрифты
# ---------------------------------------------------------------------------


def _font_directories() -> list[Path]:
    dirs: list[Path] = []
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
    dirs.append(Path(windir) / "Fonts")
    dirs.append(Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts")
    dirs.extend(
        [
            Path("/usr/share/fonts/truetype/dejavu"),
            Path("/usr/share/fonts/truetype/liberation"),
            Path("/usr/share/fonts"),
            Path("/Library/Fonts"),
            Path("/System/Library/Fonts/Supplemental"),
        ]
    )
    return dirs


def _find_font(filenames: tuple[str, ...]) -> Path | None:
    for directory in _font_directories():
        for name in filenames:
            candidate = directory / name
            try:
                if candidate.is_file() and candidate.stat().st_size > 1000:
                    return candidate
            except OSError:
                continue
    return None


def _ensure_fonts() -> _FontSet:
    """Зарегистрировать TTF с кириллицей; при неудаче — Helvetica + транслит."""
    global _FONTS
    if _FONTS is not None:
        return _FONTS
    regular_path = _find_font(_REGULAR_FILES)
    if regular_path is None:
        _FONTS = _FontSet("Helvetica", "Helvetica-Bold", False)
        return _FONTS
    bold_path = _find_font(_BOLD_FILES) or regular_path
    try:
        pdfmetrics.registerFont(TTFont(_FONT_REGULAR_NAME, str(regular_path)))
        pdfmetrics.registerFont(TTFont(_FONT_BOLD_NAME, str(bold_path)))
        pdfmetrics.registerFontFamily(
            _FONT_REGULAR_NAME,
            normal=_FONT_REGULAR_NAME,
            bold=_FONT_BOLD_NAME,
            italic=_FONT_REGULAR_NAME,
            boldItalic=_FONT_BOLD_NAME,
        )
    except Exception:  # noqa: BLE001 - битый шрифт не должен ронять экспорт
        _FONTS = _FontSet("Helvetica", "Helvetica-Bold", False)
        return _FONTS
    _FONTS = _FontSet(_FONT_REGULAR_NAME, _FONT_BOLD_NAME, True)
    return _FONTS


def _transliterate(value: str) -> str:
    return "".join(_TRANSLIT.get(char, char) for char in value)


def _plain(value: object, unicode_ok: bool) -> str:
    text = str(value or "")
    return text if unicode_ok else _transliterate(text)


def _esc(value: object, unicode_ok: bool) -> str:
    """Экранирование для Paragraph (с транслитерацией при fallback-шрифте)."""
    return escape(_plain(value, unicode_ok))


# ---------------------------------------------------------------------------
# Стили
# ---------------------------------------------------------------------------


def _styles(fonts: _FontSet) -> dict[str, ParagraphStyle]:
    text = HexColor(COLORS["text"])
    strong = HexColor(COLORS["text_strong"])
    muted = HexColor(COLORS["muted"])
    return {
        "appname": ParagraphStyle(
            "appname", fontName=fonts.bold, fontSize=16, leading=19,
            textColor=strong, spaceAfter=1,
        ),
        "appsub": ParagraphStyle(
            "appsub", fontName=fonts.regular, fontSize=9, leading=12,
            textColor=muted,
        ),
        "meta_value": ParagraphStyle(
            "meta_value", fontName=fonts.regular, fontSize=8.6, leading=11,
            textColor=text, alignment=TA_RIGHT, spaceAfter=4,
        ),
        "h2": ParagraphStyle(
            "h2", fontName=fonts.bold, fontSize=12.5, leading=15,
            textColor=strong, spaceBefore=12, spaceAfter=5, keepWithNext=1,
        ),
        "h3": ParagraphStyle(
            "h3", fontName=fonts.bold, fontSize=10.2, leading=13,
            textColor=strong, spaceBefore=8, spaceAfter=3, keepWithNext=1,
        ),
        "body": ParagraphStyle(
            "body", fontName=fonts.regular, fontSize=9, leading=12.5,
            textColor=text, spaceBefore=2,
        ),
        "body_muted": ParagraphStyle(
            "body_muted", fontName=fonts.regular, fontSize=8.6, leading=12,
            textColor=muted,
        ),
        "small": ParagraphStyle(
            "small", fontName=fonts.regular, fontSize=8.2, leading=11.5,
            textColor=muted, leftIndent=10, spaceBefore=1,
        ),
        "cell": ParagraphStyle(
            "cell", fontName=fonts.regular, fontSize=8.8, leading=11.5,
            textColor=text,
        ),
        "cell_muted": ParagraphStyle(
            "cell_muted", fontName=fonts.regular, fontSize=8, leading=11,
            textColor=muted, alignment=TA_RIGHT,
        ),
        "check_title": ParagraphStyle(
            "check_title", fontName=fonts.bold, fontSize=9.6, leading=12.5,
            textColor=strong,
        ),
        "sev": ParagraphStyle(
            "sev", fontName=fonts.regular, fontSize=7.4, leading=10,
            textColor=muted, alignment=TA_RIGHT,
        ),
        "grade": ParagraphStyle(
            "grade", fontName=fonts.regular, fontSize=9.4, leading=13,
            textColor=text,
        ),
        "score": ParagraphStyle(
            "score", fontName=fonts.regular, fontSize=10, leading=31,
            textColor=text,
        ),
        "counter": ParagraphStyle(
            "counter", fontName=fonts.regular, fontSize=8, leading=11,
            textColor=text, alignment=TA_CENTER,
        ),
    }


# ---------------------------------------------------------------------------
# Мелкие помощники цвета/графики
# ---------------------------------------------------------------------------


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _mix(color_hex: str, ratio: float = 0.85, target: str = "#FFFFFF") -> HexColor:
    """Смешать цвет с белым — мягкая подложка под счётчики."""
    r1, g1, b1 = _rgb(color_hex)
    r2, g2, b2 = _rgb(target)
    return HexColor(
        "#%02X%02X%02X"
        % (
            round(r1 + (r2 - r1) * ratio),
            round(g1 + (g2 - g1) * ratio),
            round(b1 + (b2 - b1) * ratio),
        )
    )


class StatusIcon(Flowable):
    """Круглая иконка статуса, нарисованная векторно (без шрифтовых глифов)."""

    def __init__(self, status: CheckStatus, size: float = 9.0) -> None:
        super().__init__()
        self.status = status
        self.size = size
        self.width = size
        self.height = size

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        return self.size, self.size

    def draw(self) -> None:  # pragma: no cover - рисование в canvas
        canvas = self.canv
        s = self.size
        r = s / 2.0
        canvas.saveState()
        canvas.setFillColor(HexColor(STATUS_COLORS[self.status]))
        canvas.setStrokeColor(HexColor(STATUS_COLORS[self.status]))
        canvas.circle(r, r, r, stroke=0, fill=1)
        canvas.setStrokeColor(colors.white)
        canvas.setFillColor(colors.white)
        canvas.setLineWidth(max(0.8, s * 0.13))
        canvas.setLineCap(1)
        canvas.setLineJoin(1)
        if self.status is CheckStatus.PASS:
            path = canvas.beginPath()
            path.moveTo(s * 0.27, s * 0.52)
            path.lineTo(s * 0.43, s * 0.35)
            path.lineTo(s * 0.74, s * 0.66)
            canvas.drawPath(path, stroke=1, fill=0)
        elif self.status is CheckStatus.FAIL:
            canvas.line(s * 0.31, s * 0.31, s * 0.69, s * 0.69)
            canvas.line(s * 0.69, s * 0.31, s * 0.31, s * 0.69)
        elif self.status is CheckStatus.WARN:
            canvas.line(s * 0.5, s * 0.3, s * 0.5, s * 0.6)
            canvas.circle(s * 0.5, s * 0.74, s * 0.06, stroke=0, fill=1)
        elif self.status is CheckStatus.SKIP:
            canvas.line(s * 0.3, s * 0.5, s * 0.7, s * 0.5)
        else:  # NOT_APPLICABLE — одиночный слэш, чтобы не путать с «нарушением»
            canvas.line(s * 0.32, s * 0.68, s * 0.68, s * 0.32)
        canvas.restoreState()


def _logo_flowable(max_height: float = 24.0) -> Image | None:
    path = common.logo_path()
    if path is None:
        return None
    try:
        from PIL import Image as PILImage

        with PILImage.open(path) as probe:
            width, height = probe.size
    except Exception:  # noqa: BLE001 - битый png не должен ронять PDF
        return None
    if not width or not height:
        return None
    scale = min(max_height / float(height), 110.0 / float(width))
    try:
        return Image(str(path), width=width * scale, height=height * scale)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Блоки документа
# ---------------------------------------------------------------------------


def _header(meta: common.ReportMeta, fonts: _FontSet) -> Table:
    styles = _styles(fonts)
    logo = _logo_flowable(24.0)
    name_block = [
        Paragraph(_esc(APP_DISPLAY_NAME, fonts.unicode_ok), styles["appname"]),
        Paragraph(_esc(REPORT_TITLE, fonts.unicode_ok), styles["appsub"]),
    ]
    meta_block = [
        Paragraph(
            f'<font size="7.2" color="{COLORS["muted"]}">Адрес сайта</font><br/>'
            f"{_esc(meta.url or '—', fonts.unicode_ok)}",
            styles["meta_value"],
        ),
        Paragraph(
            f'<font size="7.2" color="{COLORS["muted"]}">Дата проверки</font><br/>'
            f"{_esc(meta.date_text, fonts.unicode_ok)}",
            styles["meta_value"],
        ),
        Paragraph(
            f'<font size="7.2" color="{COLORS["muted"]}">Версия приложения</font><br/>'
            f"{_esc(meta.version, fonts.unicode_ok)}",
            styles["meta_value"],
        ),
    ]
    meta_width = CONTENT_WIDTH * 0.46
    if logo is not None:
        logo_width = min(float(logo.drawWidth) + 10, CONTENT_WIDTH * 0.2)
        name_width = CONTENT_WIDTH - meta_width - logo_width
        data = [[logo, name_block, meta_block]]
        col_widths = [logo_width, name_width, meta_width]
    else:
        name_width = CONTENT_WIDTH - meta_width
        data = [[name_block, meta_block]]
        col_widths = [name_width, meta_width]
    table = Table(data, colWidths=col_widths)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEBELOW", (0, 0), (-1, -1), 0.6, HexColor(COLORS["border"])),
            ]
        )
    )
    return table


def _score_block(report: Report, meta: common.ReportMeta, fonts: _FontSet) -> Table:
    styles = _styles(fonts)
    score_par = Paragraph(
        f'<font size="10" color="{COLORS["muted"]}">Соответствие:</font> '
        f'<font size="25" color="{COLORS["text_strong"]}"><b>{meta.score}%</b></font>',
        styles["score"],
    )
    grade_par = Paragraph(
        f'<font size="12"><b>{_esc(meta.grade_title, fonts.unicode_ok)}</b></font><br/>'
        f'<font size="8.4" color="{COLORS["muted"]}">'
        f"{_esc(meta.grade_hint, fonts.unicode_ok)}</font>",
        styles["grade"],
    )
    table = Table(
        [[score_par, grade_par]],
        colWidths=[CONTENT_WIDTH * 0.36, CONTENT_WIDTH * 0.64],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), HexColor(COLORS["surface"])),
                ("BOX", (0, 0), (-1, -1), 0.6, HexColor(COLORS["border"])),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return table


def _counters(report: Report, fonts: _FontSet) -> Table:
    styles = _styles(fonts)
    cells: list[Paragraph] = []
    tints: list[HexColor] = []
    for label, value, status in counter_rows(report):
        color = STATUS_COLORS[status]
        cells.append(
            Paragraph(
                f'<font size="14" color="{color}"><b>{value}</b></font><br/>'
                f'<font size="7.4" color="{COLORS["muted"]}">'
                f"{_esc(label, fonts.unicode_ok)}</font>",
                styles["counter"],
            )
        )
        tints.append(_mix(color, 0.88))
    table = Table([cells], colWidths=[CONTENT_WIDTH / len(cells)] * len(cells))
    style_commands: list[tuple] = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("BOX", (0, 0), (-1, -1), 0.5, HexColor(COLORS["border"])),
    ]
    for index, tint in enumerate(tints):
        style_commands.append(("BACKGROUND", (index, 0), (index, 0), tint))
        style_commands.append(
            ("LINEAFTER", (index, 0), (index, 0), 0.4, HexColor(COLORS["border"]))
        )
    table.setStyle(TableStyle(style_commands))
    return table


def _summary(report: Report, fonts: _FontSet) -> list:
    styles = _styles(fonts)
    flow: list = [Paragraph("Сводка по блокам", styles["h2"])]
    groups = group_summary(report)
    if not groups:
        flow.append(
            Paragraph("Проверки не выполнялись.", styles["body_muted"])
        )
    for category, items, passed, applicable in groups:
        rows = [
            [
                StatusIcon(result.status, 9),
                Paragraph(_esc(result.title, fonts.unicode_ok), styles["cell"]),
                Paragraph(
                    _esc(result.status.label_ru, fonts.unicode_ok),
                    styles["cell_muted"],
                ),
            ]
            for result in items
        ]
        table = Table(rows, colWidths=[14, CONTENT_WIDTH - 14 - 78, 78])
        style_commands: list[tuple] = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ]
        if len(rows) > 1:
            style_commands.append(
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, HexColor(COLORS["border_soft"]))
            )
        table.setStyle(TableStyle(style_commands))
        heading = Paragraph(
            f'{_esc(category_label(category), fonts.unicode_ok)} '
            f'<font size="7.6" color="{COLORS["muted"]}">— '
            f"{_esc(group_progress_text(passed, applicable), fonts.unicode_ok)}"
            f"</font>",
            styles["h3"],
        )
        flow.append(KeepTogether([heading, table]))
    return flow


def _recommendation_box(text: str, fonts: _FontSet) -> Table:
    styles = _styles(fonts)
    body = Paragraph(
        f"<b>Рекомендация:</b> {_esc(text, fonts.unicode_ok)}",
        styles["body"],
    )
    table = Table([[body]], colWidths=[CONTENT_WIDTH - 8])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), HexColor(COLORS["surface_alt"])),
                ("LINEBEFORE", (0, 0), (0, 0), 2.2, HexColor(COLORS["accent"])),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _check_block(result: CheckResult, fonts: _FontSet) -> list:
    styles = _styles(fonts)
    severity = severity_label(result)
    head = Table(
        [
            [
                StatusIcon(result.status, 9),
                Paragraph(_esc(result.title, fonts.unicode_ok), styles["check_title"]),
                Paragraph(_esc(severity, fonts.unicode_ok), styles["sev"]),
            ]
        ],
        colWidths=[14, CONTENT_WIDTH - 14 - 62, 62],
    )
    head.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                ("LINEBEFORE", (0, 0), (0, 0), 2.2, HexColor(STATUS_COLORS[result.status])),
            ]
        )
    )
    flow: list = [head]
    message = (result.message or "").strip()
    if message:
        flow.append(Paragraph(_esc(message, fonts.unicode_ok), styles["body"]))
    if result.error:
        flow.append(
            Paragraph(
                f'<font size="8" color="{COLORS["muted"]}">'
                f"{_esc(result.error, fonts.unicode_ok)}</font>",
                styles["small"],
            )
        )
    if result.status is not CheckStatus.NOT_APPLICABLE:
        for item in evidence_items(result):
            value = _esc(item["value"] or "—", fonts.unicode_ok)
            selector = item["selector"]
            selector_html = (
                f' <font color="{COLORS["muted"]}" size="7.6">'
                f"(селектор: {_esc(selector, fonts.unicode_ok)})</font>"
                if selector
                else ""
            )
            flow.append(
                Paragraph(
                    f'<font color="{COLORS["muted"]}">•</font> '
                    f"<b>{_esc(item['label'], fonts.unicode_ok)}:</b> "
                    f"{value}{selector_html}",
                    styles["small"],
                )
            )
        recommendation = (result.recommendation or "").strip()
        if recommendation:
            flow.append(Spacer(1, 4))
            flow.append(_recommendation_box(recommendation, fonts))
    note = methodology_note(result.check_id)
    if note:
        flow.append(
            Paragraph(
                f'<font size="7.6" color="{COLORS["muted"]}">'
                f"{_esc(note, fonts.unicode_ok)}</font>",
                styles["small"],
            )
        )
    return [KeepTogether(flow), Spacer(1, 7)]


def _details(report: Report, fonts: _FontSet) -> list:
    styles = _styles(fonts)
    flow: list = [Paragraph("Детальные результаты", styles["h2"])]
    groups = report.grouped()
    if not groups:
        flow.append(Paragraph("Проверки не выполнялись.", styles["body_muted"]))
    for category, items in groups:
        flow.append(Paragraph(_esc(category_label(category), fonts.unicode_ok), styles["h3"]))
        for result in items:
            flow.extend(_check_block(result, fonts))
    return flow


def _na_section(report: Report, fonts: _FontSet) -> list:
    items = report.not_applicable()
    if not items:
        return []
    styles = _styles(fonts)
    flow: list = [
        Paragraph("Не применимо (N/A)", styles["h2"]),
        Paragraph(
            "Эти проверки неприменимы к сайту и не влияют на процент соответствия.",
            styles["body_muted"],
        ),
    ]
    for result in items:
        flow.append(
            Paragraph(
                f'<font color="{COLORS["muted"]}">•</font> '
                f"<b>{_esc(result.title, fonts.unicode_ok)}</b> "
                f'<font size="7.8" color="{COLORS["muted"]}">'
                f"({_esc(category_label(result.category), fonts.unicode_ok)})</font> — "
                f"{_esc(result.message, fonts.unicode_ok)}",
                styles["body"],
            )
        )
    return flow


def _skipped_section(report: Report, fonts: _FontSet) -> list:
    items = report.skipped()
    if not items:
        return []
    styles = _styles(fonts)
    flow: list = [Paragraph("Не удалось проверить", styles["h2"])]
    for result in items:
        message = (result.message or "проверка не выполнена").strip()
        flow.append(
            Paragraph(
                f'<font color="{COLORS["muted"]}">•</font> '
                f"<b>{_esc(result.title, fonts.unicode_ok)}</b> — "
                f"{_esc(message, fonts.unicode_ok)}",
                styles["body"],
            )
        )
    return flow


def _notes_section(report: Report, fonts: _FontSet) -> list:
    if not report.notes:
        return []
    styles = _styles(fonts)
    flow: list = [Paragraph("Примечания сканирования", styles["h2"])]
    for note in report.notes:
        flow.append(
            Paragraph(
                f'<font color="{COLORS["muted"]}">•</font> '
                f"{_esc(note, fonts.unicode_ok)}",
                styles["body_muted"],
            )
        )
    return flow


def _disclaimer(fonts: _FontSet) -> list:
    styles = _styles(fonts)
    return [
        HRFlowable(
            width="100%",
            thickness=0.6,
            color=HexColor(COLORS["border"]),
            spaceBefore=12,
            spaceAfter=8,
        ),
        Paragraph(
            f"<b>Дисклеймер.</b> {_esc(common.DISCLAIMER_TEXT, fonts.unicode_ok)}",
            styles["small"],
        ),
    ]


def _footer(fonts: _FontSet):
    """Футер на каждой странице: брендинг + «стр. N»."""

    def draw(canvas, _doc) -> None:  # pragma: no cover - callback reportlab
        canvas.saveState()
        canvas.setStrokeColor(HexColor(COLORS["border"]))
        canvas.setLineWidth(0.6)
        canvas.line(MARGIN_LR, 14 * mm, PAGE_WIDTH - MARGIN_LR, 14 * mm)
        canvas.setFont(fonts.regular, 8)
        canvas.setFillColor(HexColor(COLORS["muted"]))
        footer_text = f"{BRAND_LINE} · {BOOSTY_INLINE}"
        canvas.drawString(MARGIN_LR, 9.5 * mm, _plain(footer_text, fonts.unicode_ok))
        page_label = _plain(f"стр. {canvas.getPageNumber()}", fonts.unicode_ok)
        canvas.drawRightString(
            PAGE_WIDTH - MARGIN_LR, 9.5 * mm, page_label
        )
        canvas.restoreState()

    return draw


# ---------------------------------------------------------------------------
# Публичная функция
# ---------------------------------------------------------------------------


def build_pdf(report: Report) -> bytes:
    """Собрать PDF-отчёт и вернуть его содержимое как ``bytes``."""
    fonts = _ensure_fonts()
    meta = report_meta(report)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN_LR,
        rightMargin=MARGIN_LR,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title=f"{APP_DISPLAY_NAME} - {meta.domain}",
        author=AUTHOR,
        subject=REPORT_TITLE,
        creator=f"{APP_DISPLAY_NAME} {meta.version}",
    )
    story: list = [
        _header(meta, fonts),
        Spacer(1, 10),
        _score_block(report, meta, fonts),
        Spacer(1, 8),
        _counters(report, fonts),
    ]
    story.extend(_summary(report, fonts))
    story.extend(_details(report, fonts))
    story.extend(_na_section(report, fonts))
    story.extend(_skipped_section(report, fonts))
    story.extend(_notes_section(report, fonts))
    story.extend(_disclaimer(fonts))
    footer = _footer(fonts)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


__all__ = ["build_pdf"]
