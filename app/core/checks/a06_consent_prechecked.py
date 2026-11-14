"""A06. Чекбокс не предзаполнен (152-ФЗ, ч. 1 ст. 9).

Согласие на обработку ПДн — активное действие пользователя. Атрибут
``checked`` у чекбокса согласия недопустим.
"""

from __future__ import annotations

from app.core.checks.base import BaseCheck
from app.core.models import Category, CheckResult, Severity, SiteContext


class ConsentPrecheckedCheck(BaseCheck):
    id = "a06_consent_prechecked"
    title = "Чекбокс не предзаполнен"
    category = Category.FZ152.value
    weight = 4
    severity = Severity.IMPORTANT
    recommendation = (
        "Уберите атрибут checked у чекбокса согласия: пользователь должен поставить "
        "его самостоятельно. Согласие — конкретное, информированное и осознанное "
        "действие (ч. 1 ст. 9 152-ФЗ)."
    )

    def evaluate(self, ctx: SiteContext) -> CheckResult:
        consent_forms = [item for item in ctx.forms if item.has_consent_checkbox]

        if not consent_forms:
            return self.na(
                "На сайте не обнаружены чекбоксы согласия на обработку ПДн — "
                "проверять предзаполнение нечего."
            )

        checked = [item for item in consent_forms if item.consent_checked]
        if checked:
            selectors = [item.selector or "форма без селектора" for item in checked[:5]]
            evidence = [
                self.ev(
                    "Предзаполненный чекбокс",
                    item.selector or "форма без селектора",
                    selector=item.selector or None,
                    kind="selector",
                )
                for item in checked[:5]
            ]
            hidden = len(checked) - len(evidence)
            suffix = f" и ещё {hidden}" if hidden > 0 else ""
            return self.fail(
                "Чекбокс согласия предзаполнен (атрибут checked): "
                f"{len(checked)} из {len(consent_forms)} — "
                + "; ".join(selectors)
                + suffix
                + ". Согласие выдаётся по умолчанию, а не по воле пользователя.",
                recommendation=self.recommendation,
                evidence=evidence,
            )

        evidence = [
            self.ev(
                "Чекбокс согласия",
                item.selector or "форма без селектора",
                selector=item.selector or None,
                kind="selector",
            )
            for item in consent_forms[:5]
        ]
        return self.ok(
            f"Чекбоксы согласия не предзаполнены ({len(consent_forms)} шт.): "
            "пользователь ставит их самостоятельно.",
            recommendation="",
            evidence=evidence,
        )
