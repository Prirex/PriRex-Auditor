"""A10. Зарубежные трекеры — риск локализации (152-ФЗ, ч. 5 ст. 18).

Использование зарубежных счётчиков и пикселей означает передачу данных
за границу и потенциальное нарушение требования о локализации баз данных.
"""

from __future__ import annotations

from app.core.checks.base import BaseCheck
from app.core.models import Category, CheckResult, Severity, SiteContext


class ForeignTrackersCheck(BaseCheck):
    id = "a10_foreign_trackers"
    title = "Зарубежные трекеры (риск локализации)"
    category = Category.FZ152.value
    weight = 3
    severity = Severity.IMPORTANT
    recommendation = (
        "Откажитесь от зарубежных трекеров в пользу российских аналогов "
        "(Яндекс.Метрика, VK Pixel, Top.Mail.Ru) либо исключите передачу "
        "персональных данных за границу. Требование о локализации баз данных — "
        "ч. 5 ст. 18 152-ФЗ."
    )

    def evaluate(self, ctx: SiteContext) -> CheckResult:
        if not ctx.trackers:
            return self.na(
                "На сайте не обнаружены сторонние трекеры — риск нарушения "
                "локализации отсутствует."
            )

        foreign = ctx.foreign_trackers
        if not foreign:
            domains = sorted({item.domain for item in ctx.trackers})
            return self.ok(
                "Сторонние трекеры есть, но все они российские: "
                + ", ".join(domains[:6])
                + ". Риск по ч. 5 ст. 18 152-ФЗ не выявлен.",
                recommendation="",
                evidence=[
                    self.ev("Российские трекеры", ", ".join(domains[:10])),
                    self.ev("Количество трекеров", str(len(ctx.trackers))),
                ],
            )

        details = "; ".join(
            f"{item.domain} ({item.title_ru})" for item in foreign[:8]
        )
        hidden = len(foreign) - min(len(foreign), 8)
        if hidden > 0:
            details += f"; ещё {hidden}"

        evidence = [
            self.ev(
                "Зарубежный трекер",
                f"{item.domain} — {item.title_ru}" + (f" ({item.url})" if item.url else ""),
                kind="url",
            )
            for item in foreign[:8]
        ]
        return self.warn(
            f"Обнаружены зарубежные трекеры ({len(foreign)}): {details}. "
            "Данные посетителей могут передаваться за границу и храниться вне РФ — "
            "риск нарушения ч. 5 ст. 18 152-ФЗ (локализация баз данных).",
            severity=Severity.IMPORTANT,
            recommendation=self.recommendation,
            evidence=evidence,
        )
