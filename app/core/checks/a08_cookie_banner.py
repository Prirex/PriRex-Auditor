"""A08. Cookie-баннер (152-ФЗ, ч. 1 ст. 9).

Если на сайте есть сторонние скрипты/трекеры, до их запуска должно
запрашиваться согласие на использование cookie (cookie-баннер).
"""

from __future__ import annotations

from app.core.checks.base import BaseCheck
from app.core.detect import normalize_text
from app.core.models import Category, CheckResult, Severity, SiteContext


class CookieBannerCheck(BaseCheck):
    id = "a08_cookie_banner"
    title = "Cookie-баннер"
    category = Category.FZ152.value
    weight = 5
    severity = Severity.IMPORTANT
    recommendation = (
        "Добавьте cookie-баннер, который до загрузки необязательных скриптов "
        "информирует о cookie и запрашивает согласие. Cookie-идентификаторы "
        "относятся к персональным данным (ч. 1 ст. 9 152-ФЗ)."
    )

    def evaluate(self, ctx: SiteContext) -> CheckResult:
        if not ctx.trackers:
            return self.na(
                "На сайте не обнаружены сторонние скрипты/трекеры — cookie-баннер "
                "не обязателен."
            )

        banner = ctx.cookie_banner
        domains: list[str] = []
        for item in ctx.trackers:
            if item.domain not in domains:
                domains.append(item.domain)
        summary = ", ".join(domains[:5]) + (" и др." if len(domains) > 5 else "")

        if banner.found:
            banner_text = normalize_text(banner.text, 300)
            message = f"Cookie-баннер обнаружен (источник: {banner.source or 'не указан'})."
            if banner_text:
                message += f" Текст: «{banner_text}»."
            evidence = [
                self.ev("Источник обнаружения", banner.source or "не указан"),
                self.ev("Текст баннера", banner_text or banner.text or "—"),
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
            return self.ok(message, recommendation="", evidence=evidence)

        if not ctx.deep_analysis:
            if ctx.is_local:
                return self.skip(
                    "Локальная папка: cookie-баннер появляется в браузере, "
                    "по файлам он не проверяется. Проверьте после публикации сайта.",
                    evidence=[self.ev("Сторонние трекеры", summary)],
                )
            return self.skip(
                "Глубокий анализ (Playwright) отключён или недоступен — "
                "cookie-баннер не проверялся. Включите «Глубокий анализ», чтобы "
                "проверить наличие баннера.",
                evidence=[self.ev("Сторонние трекеры", summary)],
            )

        return self.fail(
            f"На сайте есть сторонние скрипты/трекеры ({summary}), но cookie-баннер "
            "не обнаружен: согласие на использование cookie не запрашивается.",
            recommendation=self.recommendation,
            evidence=[
                self.ev("Сторонние трекеры", summary),
                self.ev("Количество трекеров", str(len(ctx.trackers))),
            ],
        )
