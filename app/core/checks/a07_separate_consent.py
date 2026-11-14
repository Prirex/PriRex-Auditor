"""A07. Отдельное согласие, не вшитое в договор (152-ФЗ, ч. 1 ст. 9).

Согласие на обработку ПДн должно быть отделено от принятия оферты или
пользовательского соглашения: это разные юридические действия и два разных
чекбокса.
"""

from __future__ import annotations

from app.core import detect
from app.core.checks.base import BaseCheck
from app.core.models import Category, CheckResult, FormInfo, Severity, SiteContext

#: Явные маркеры оферты/пользовательского соглашения. Общий маркер «услови»
#: из ``detect.OFFER_MARKERS`` здесь не используется, чтобы «условия обработки
#: персональных данных» не считались офертой.
_OFFER_MARKERS: tuple[str, ...] = (
    "оферт",
    "пользовательск",
    "terms",
    "договор",
)


class SeparateConsentCheck(BaseCheck):
    id = "a07_separate_consent"
    title = "Отдельное согласие (не вшито в договор)"
    category = Category.FZ152.value
    weight = 4
    severity = Severity.IMPORTANT
    recommendation = (
        "Разделите согласие на обработку ПДн и принятие оферты на два отдельных "
        "чекбокса. Согласие должно быть конкретным и предметным, а не частью "
        "договора (ч. 1 ст. 9 152-ФЗ)."
    )

    @staticmethod
    def _checkbox_count(form: FormInfo) -> int:
        return sum(1 for item in form.fields if item.type in {"checkbox", "radio"})

    @classmethod
    def _is_combined(cls, form: FormInfo) -> bool:
        """Согласие объединено с офертой / один чекбокс на два действия."""
        text = form.consent_text or ""
        if detect.is_offer_text(text):
            return True
        if detect.has_any(text, _OFFER_MARKERS):
            return True
        # Отдельного чекбокса оферты нет: единственный чекбокс обслуживает оба действия.
        if form.has_offer_checkbox and cls._checkbox_count(form) <= 1:
            return True
        return False

    def evaluate(self, ctx: SiteContext) -> CheckResult:
        consent_forms = [item for item in ctx.forms if item.has_consent_checkbox]

        if not consent_forms:
            return self.na(
                "На сайте не обнаружены чекбоксы согласия на обработку ПДн — "
                "проверять отдельность согласия нечего."
            )

        combined = [item for item in consent_forms if self._is_combined(item)]
        if combined:
            evidence = []
            parts: list[str] = []
            for item in combined[:5]:
                selector = item.selector or "форма без селектора"
                parts.append(selector)
                evidence.append(
                    self.ev(
                        "Форма с объединённым согласием",
                        selector,
                        selector=item.selector or None,
                        kind="selector",
                    )
                )
                if item.consent_text:
                    evidence.append(
                        self.ev(
                            "Текст чекбокса",
                            detect.normalize_text(item.consent_text, 200),
                            selector=item.selector or None,
                        )
                    )
            hidden = len(combined) - len(parts)
            if hidden > 0:
                parts.append(f"и ещё {hidden}")

            return self.warn(
                "Согласие на обработку ПДн объединено с принятием оферты или "
                "пользовательского соглашения: "
                + "; ".join(parts)
                + ". Нужны два отдельных чекбокса: согласие на обработку ПДн "
                "и принятие оферты.",
                severity=Severity.IMPORTANT,
                recommendation=self.recommendation,
                evidence=evidence,
            )

        evidence = [
            self.ev(
                "Форма с отдельным согласием",
                item.selector or "форма без селектора",
                selector=item.selector or None,
                kind="selector",
            )
            for item in consent_forms[:5]
        ]
        return self.ok(
            "Согласие на обработку ПДн оформлено отдельно от принятия оферты или "
            "пользовательского соглашения. Форм с чекбоксом согласия: "
            f"{len(consent_forms)}.",
            recommendation="",
            evidence=evidence,
        )
