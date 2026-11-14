"""A09. Категории cookie и кнопка отказа (152-ФЗ, ч. 1 ст. 9).

В cookie-баннере должна быть возможность отказаться от необязательных cookie
или настроить их категории, а не только «Принять».
"""

from __future__ import annotations

from app.core.checks.base import BaseCheck
from app.core.detect import normalize_text
from app.core.models import Category, CheckResult, Severity, SiteContext


class CookieCategoriesCheck(BaseCheck):
    id = "a09_cookie_categories"
    title = "Категории cookie и кнопка отказа"
    category = Category.FZ152.value
    weight = 3
    severity = Severity.IMPORTANT
    recommendation = (
        "Добавьте в cookie-баннер кнопки «Только необходимые»/«Отклонить» и "
        "настройки категорий cookie. Отказ от необязательных cookie должен быть "
        "не сложнее согласия (ч. 1 ст. 9 152-ФЗ)."
    )

    def evaluate(self, ctx: SiteContext) -> CheckResult:
        banner = ctx.cookie_banner

        if not banner.found:
            return self.na(
                "Cookie-баннер не обнаружен — проверять категории cookie и кнопку "
                "отказа нечего."
            )

        evidence = [
            self.ev("Текст баннера", normalize_text(banner.text, 300) or "—"),
            self.ev("Кнопка «Принять»", "есть" if banner.has_accept else "нет"),
            self.ev("Кнопка отказа", "есть" if banner.has_reject else "нет"),
            self.ev("Настройки категорий", "есть" if banner.has_settings else "нет"),
        ]
        if banner.selector:
            evidence.append(
                self.ev(
                    "Элемент баннера",
                    banner.selector,
                    selector=banner.selector,
                    kind="selector",
                )
            )

        if banner.has_reject or banner.has_settings:
            if banner.has_reject and banner.has_settings:
                message = (
                    "В cookie-баннере есть и кнопка отказа от необязательных cookie, "
                    "и настройки категорий."
                )
            elif banner.has_reject:
                message = (
                    "В cookie-баннере есть кнопка отказа от необязательных cookie."
                )
            else:
                message = (
                    "В cookie-баннере есть настройки категорий cookie: можно "
                    "отказаться от необязательных."
                )
            return self.ok(message, recommendation="", evidence=evidence)

        if banner.has_accept:
            return self.fail(
                "В cookie-баннере есть только кнопка «Принять»: отказаться от "
                "необязательных cookie или настроить категории нельзя.",
                recommendation=self.recommendation,
                evidence=evidence,
            )

        return self.warn(
            "В cookie-баннере не распознаны кнопки «Принять», «Отклонить» или "
            "настройки категорий. Проверьте баннер вручную.",
            severity=Severity.IMPORTANT,
            recommendation=(
                "Убедитесь, что в баннере есть «Принять все», «Только необходимые» "
                "и настройки категорий cookie."
            ),
            evidence=evidence,
        )
