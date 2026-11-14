"""C15. Согласие на рекламную рассылку (38-ФЗ, ч. 1 ст. 18).

Применимо только при наличии форм подписки на рассылку. Отдельное согласие
на рекламу не должно быть «вшито» в согласие на обработку персональных
данных или в оферту.
"""

from __future__ import annotations

import re

from app.core.checks.base import BaseCheck
from app.core.detect import MARKETING_MARKERS, has_any
from app.core.models import (
    Category,
    CheckResult,
    Evidence,
    FormFieldInfo,
    FormInfo,
    Severity,
    SiteContext,
)

NA_MESSAGE = (
    "На сайте не обнаружены формы подписки на рассылку. "
    "Отдельное согласие на рекламу не требуется."
)

_WS_RE = re.compile(r"\s+")
_EMAIL_HINTS = ("email", "e-mail", "mail", "почт")


def _snippet(text: str, limit: int = 120) -> str:
    cleaned = _WS_RE.sub(" ", text or "").strip()
    return cleaned[:limit]


def _has_email_field(form: FormInfo) -> bool:
    for form_field in form.fields:
        if _is_email_field(form_field):
            return True
    return False


def _is_email_field(form_field: FormFieldInfo) -> bool:
    if form_field.type == "email":
        return True
    hint = " ".join(
        part
        for part in (
            form_field.name or "",
            form_field.placeholder or "",
            form_field.label_text or "",
        )
        if part
    ).lower()
    return any(marker in hint for marker in _EMAIL_HINTS)


def _market_context(form: FormInfo) -> bool:
    return bool(has_any(form.context_text, MARKETING_MARKERS))


def _looks_like_subscribe(form: FormInfo) -> bool:
    """Эвристика формы подписки.

    Учитываем флаг сборщика, отдельный маркетинговый чекбокс, а также
    email-поле в маркетинговом контексте (новости, акции, рассылка).
    """
    if form.is_subscribe_form or form.has_marketing_checkbox:
        return True
    return _has_email_field(form) and _market_context(form)


def _form_evidence(form: FormInfo, label: str) -> Evidence:
    return BaseCheck.ev(
        label,
        _snippet(form.context_text) or (form.consent_text or ""),
        selector=form.selector or None,
        kind="selector",
    )


class AdConsentCheck(BaseCheck):
    """Проверка отдельного чекбокса согласия на рекламную рассылку."""

    id = "c15_ad_consent"
    title = "Согласие на рекламную рассылку"
    category = Category.AD.value
    weight = 5
    severity = Severity.IMPORTANT
    recommendation = (
        "Добавьте в форму подписки отдельный (не предзаполненный) чекбокс "
        "«Согласен получать рекламные сообщения». Не объединяйте его с "
        "согласием на обработку персональных данных или с принятием оферты."
    )

    def evaluate(self, ctx: SiteContext) -> CheckResult:
        subscribe_forms = [form for form in ctx.forms if _looks_like_subscribe(form)]

        if not ctx.has_subscribe_form and not subscribe_forms:
            return self.na(NA_MESSAGE)

        # Сборщик мог отметить подписку без детализации формы: проверяем все
        # формы, у которых вообще есть отдельный маркетинговый чекбокс.
        relevant = list(subscribe_forms)
        for form in ctx.forms:
            if form.has_marketing_checkbox and form not in relevant:
                relevant.append(form)

        if not relevant:
            return self.fail(
                "На сайте есть форма подписки на рассылку, но отдельного "
                "чекбокса согласия на рекламную рассылку не найдено. "
                "Это нарушает ч. 1 ст. 18 38-ФЗ: реклама по сетям связи "
                "допускается только с предварительного согласия абонента. "
                "Согласие на ПДн ≠ согласие на рекламу.",
                severity=Severity.IMPORTANT,
            )

        without_marketing = [
            form for form in relevant if not form.has_marketing_checkbox
        ]
        with_marketing = [
            form for form in relevant if form.has_marketing_checkbox
        ]

        if not without_marketing:
            evidence: list[Evidence] = []
            for form in with_marketing:
                evidence.append(
                    _form_evidence(
                        form,
                        "Форма подписки с отдельным согласием на рекламу",
                    )
                )
                evidence.append(
                    self.ev(
                        "Отдельный чекбокс рекламной рассылки",
                        form.consent_text or "обнаружен",
                        selector=form.selector or None,
                    )
                )
            return self.ok(
                "У формы подписки есть отдельный чекбокс согласия на "
                f"рекламную рассылку ({len(with_marketing)} из {len(relevant)}).",
                evidence=evidence,
            )

        selectors = ", ".join(
            form.selector or "форма подписки" for form in without_marketing[:5]
        )
        message = (
            "Форма подписки на рассылку есть, но отдельного согласия на "
            f"рекламную рассылку нет (селекторы: {selectors}). "
            "Это нарушает ч. 1 ст. 18 38-ФЗ: реклама по сетям связи "
            "допускается только с предварительного согласия абонента. "
            "Согласие на ПДн ≠ согласие на рекламу."
        )
        if with_marketing:
            message += (
                f" Отдельное согласие есть только в части форм: "
                f"{len(with_marketing)} из {len(relevant)}."
            )

        evidence = []
        for form in without_marketing[:10]:
            evidence.append(
                _form_evidence(
                    form,
                    "Форма подписки без отдельного согласия на рекламу",
                )
            )
            if form.has_consent_checkbox:
                evidence.append(
                    self.ev(
                        "Найден только чекбокс согласия на ПДн",
                        form.consent_text or "чекбокс согласия на обработку ПДн",
                        selector=form.selector or None,
                    )
                )
        return self.fail(
            message,
            severity=Severity.IMPORTANT,
            evidence=evidence,
        )
