"""B13. Реквизиты продавца (ЗоЗПП, ст. 8–10).

Проверка применима только к сайтам с признаками дистанционной продажи.
Информационные сайты, блоги и лендинги без продаж получают
``not_applicable`` (а не ``fail``) — это прямое требование ТЗ.
"""

from __future__ import annotations

import re

from app.core.checks.base import BaseCheck
from app.core.detect import extract_requisites
from app.core.models import Category, CheckResult, Evidence, Severity, SiteContext

NA_MESSAGE = (
    "На сайте не обнаружены признаки дистанционной продажи товаров/услуг. "
    "Проверка реквизитов не требуется."
)

#: «ип» как отдельное слово (не «тип», «принцип» и т.п.).
_IP_RE = re.compile(r"(?<![а-яёa-z])ип(?![а-яёa-z])", re.IGNORECASE)

_UL_MARKERS: tuple[str, ...] = (
    "ооо",
    "оао",
    "зао",
    "пао",
    "ао ",
    "огрн",
    "юридическое лицо",
    "полное наименование",
    "наименование организации",
)

_IP_MARKERS: tuple[str, ...] = (
    "огрнип",
    "индивидуальный предприниматель",
)


def _corpus(ctx: SiteContext) -> str:
    """Видимый текст: футер, главная и загруженные страницы (детерминированно)."""
    parts: list[str] = [ctx.footer_text, ctx.text]
    for key in sorted(ctx.pages):
        page = ctx.pages[key]
        if page.text:
            parts.append(page.text)
    return "\n".join(part for part in parts if part)


def _entity_kind(req, corpus: str) -> str:
    """Тип продавца: ``ip``, ``ul`` или ``unknown``."""
    if req.ogrnip:
        return "ip"
    if req.ogrn:
        return "ul"
    low = corpus.lower()
    if any(marker in low for marker in _IP_MARKERS) or _IP_RE.search(low):
        return "ip"
    if any(marker in low for marker in _UL_MARKERS):
        return "ul"
    return "unknown"


def _requirements(req, kind: str) -> list[tuple[str, bool]]:
    """Пары «требование — найдено ли» для конкретного типа продавца."""
    name_ok = bool(req.has_legal_name)
    contact_ok = bool(req.has_email or req.has_phone)
    if kind == "ip":
        return [
            ("наименование (ФИО или ИП)", name_ok),
            ("ОГРНИП", bool(req.ogrnip)),
            ("email или телефон", contact_ok),
        ]
    if kind == "ul":
        return [
            ("наименование организации", name_ok),
            ("ОГРН", bool(req.ogrn)),
            ("адрес (место нахождения)", bool(req.has_address)),
            ("email или телефон", contact_ok),
        ]
    return [
        ("наименование организации или ФИО", name_ok),
        ("ОГРН или ОГРНИП", bool(req.ogrn or req.ogrnip)),
        ("email или телефон", contact_ok),
    ]


def _requisite_evidence(req) -> list[Evidence]:
    """Evidence по найденным реквизитам."""
    items: list[Evidence] = []
    if req.ogrn:
        items.append(BaseCheck.ev("ОГРН", req.ogrn[0]))
    if req.ogrnip:
        items.append(BaseCheck.ev("ОГРНИП", req.ogrnip[0]))
    if req.inn:
        items.append(BaseCheck.ev("ИНН", req.inn[0]))
    if req.has_address:
        items.append(BaseCheck.ev("Адрес", "указан на сайте"))
    return items


def _sales_evidence(ctx: SiteContext) -> list[Evidence]:
    """Evidence признаков продаж — полезно, когда реквизитов нет."""
    items: list[Evidence] = []
    if ctx.price_samples:
        items.append(
            BaseCheck.ev("Цены на сайте", "; ".join(ctx.price_samples[:3]))
        )
    if ctx.buy_button_samples:
        items.append(
            BaseCheck.ev("Кнопки покупки", "; ".join(ctx.buy_button_samples[:3]))
        )
    if ctx.has_cart:
        items.append(BaseCheck.ev("Корзина", "обнаружена на сайте"))
    if ctx.has_order_form:
        items.append(BaseCheck.ev("Форма заказа", "обнаружена на сайте"))
    return items


class SellerDetailsCheck(BaseCheck):
    """Проверка раскрытия реквизитов продавца."""

    id = "b13_seller_details"
    title = "Реквизиты продавца"
    category = Category.ZOZPP.value
    weight = 8
    severity = Severity.CRITICAL
    recommendation = (
        "Разместите реквизиты в футере и на странице «О продавце»/в оферте: "
        "для юрлица — полное наименование, ОГРН, адрес (место нахождения), "
        "email и/или телефон; для ИП — ФИО, ОГРНИП, email и/или телефон."
    )

    def evaluate(self, ctx: SiteContext) -> CheckResult:
        # Применимо только при явных признаках продаж. Подписка на рассылку
        # продажей не считается.
        if not (ctx.has_sales_signs or ctx.buy_button_samples):
            return self.na(NA_MESSAGE)

        text = _corpus(ctx)
        # Email может встречаться в HTML (mailto:) или в тексте загруженных
        # страниц — поэтому передаём детектору объединённый источник.
        html_for_emails = f"{ctx.html}\n{text}" if ctx.html else text
        req = extract_requisites(text, html_for_emails)

        kind = _entity_kind(req, text)
        requirements = _requirements(req, kind)
        missing = [name for name, found in requirements if not found]
        found = [name for name, found in requirements if found]

        # Контакты сами по себе (email/телефон) — ещё не раскрытие продавца.
        anything_meaningful = bool(
            req.has_legal_name
            or req.ogrn
            or req.ogrnip
            or req.inn
            or req.has_address
        )

        if not anything_meaningful:
            return self.fail(
                "На сайте есть признаки дистанционной продажи, но реквизиты "
                "продавца не найдены. По ст. 8–10 ЗоЗПП продавец обязан "
                "раскрыть фирменное наименование, адрес и ОГРН "
                "(для ИП — ФИО и ОГРНИП).",
                severity=Severity.CRITICAL,
                evidence=_sales_evidence(ctx),
            )

        if missing:
            return self.warn(
                "Реквизиты продавца раскрыты не полностью. Не хватает: "
                f"{', '.join(missing)}. Найдено: {req.summary or ', '.join(found)}.",
                severity=Severity.IMPORTANT,
                evidence=_requisite_evidence(req),
            )

        return self.ok(
            f"Реквизиты продавца раскрыты: {req.summary}.",
            evidence=_requisite_evidence(req),
        )
