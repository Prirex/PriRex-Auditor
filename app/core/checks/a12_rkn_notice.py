"""A12. Признаки уведомления в РКН (152-ФЗ, ст. 22).

Эвристика: ищем в тексте сайта упоминания реестра операторов, Роскомнадзора
и уведомления о начале обработки ПДн. Это подсказка, а не вывод о нарушении,
поэтому проверка никогда не возвращает fail.
"""

from __future__ import annotations

from app.core.checks.base import BaseCheck
from app.core.detect import RKN_MARKERS, has_any
from app.core.models import Category, CheckResult, Severity, SiteContext


class RknNoticeCheck(BaseCheck):
    id = "a12_rkn_notice"
    title = "Признаки уведомления в РКН"
    category = Category.FZ152.value
    weight = 2
    severity = Severity.RECOMMENDATION
    recommendation = (
        "Проверьте, подано ли уведомление об обработке персональных данных в "
        "Роскомнадзор (ст. 22 152-ФЗ). Если нет — подайте уведомление через "
        "портал РКН; в случаях из ч. 2 ст. 22 уведомление не требуется."
    )

    def evaluate(self, ctx: SiteContext) -> CheckResult:
        text = ctx.all_text()
        found = has_any(text, RKN_MARKERS)

        if found:
            return self.ok(
                "Найдены признаки уведомления в РКН: " + ", ".join(found) + ".",
                recommendation="",
                evidence=[
                    self.ev("Маркеры", ", ".join(found)),
                ],
            )

        return self.warn(
            "Признаков уведомления в РКН не найдено: на сайте нет упоминаний "
            "«реестр операторов», «Роскомнадзор», «уведомление о начале обработки». "
            "Это лишь подсказка — проверьте, подано ли уведомление об обработке ПДн.",
            severity=Severity.RECOMMENDATION,
            recommendation=self.recommendation,
        )
