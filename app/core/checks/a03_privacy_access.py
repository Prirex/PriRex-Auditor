"""A03. Политика — доступность без регистрации (152-ФЗ, ч. 2 ст. 18.1).

Страница политики должна открываться анонимному посетителю: без авторизации
и без обязательного прохождения cookie-стены.
"""

from __future__ import annotations

from app.core.checks.base import BaseCheck
from app.core.models import Category, CheckResult, Severity, SiteContext


class PrivacyAccessCheck(BaseCheck):
    id = "a03_privacy_access"
    title = "Политика — доступность без регистрации"
    category = Category.FZ152.value
    weight = 5
    severity = Severity.IMPORTANT
    recommendation = (
        "Обеспечьте открытие страницы политики без регистрации, авторизации и "
        "обязательного согласия на cookie (ч. 2 ст. 18.1 152-ФЗ)."
    )

    def evaluate(self, ctx: SiteContext) -> CheckResult:
        if ctx.is_local:
            return self.na(
                "Локальная папка: страницы читаются с диска, авторизации и "
                "cookie-стены нет. Проверка доступности политики актуальна "
                "после публикации сайта."
            )

        page = ctx.pages.get("privacy")

        if page is None:
            return self.na(
                "Страница политики не загружена — проверить доступность без "
                "регистрации нельзя."
            )

        if not page.ok:
            status = f"HTTP {page.status_code}" if page.status_code else "страница не открылась"
            return self.skip(
                f"Страница политики не открылась ({status}) — проверить "
                "доступность без регистрации не удалось.",
                evidence=[
                    self.ev("Страница политики", page.url or "—", kind="url"),
                ],
            )

        evidence = [
            self.ev("Страница политики", page.url or "—", kind="url"),
        ]
        if page.status_code:
            evidence.append(self.ev("HTTP-статус страницы", str(page.status_code)))

        problems: list[str] = []
        if page.redirected_to_login:
            problems.append(
                "Страница политики доступна только после входа/регистрации: "
                "субъект ПДн не может ознакомиться с политикой анонимно."
            )
        if page.has_cookie_wall:
            problems.append(
                "Страница политики закрыта cookie-стеной: текст политики не виден, "
                "пока посетитель не согласится на использование cookie."
            )

        if problems:
            return self.fail(
                " ".join(problems),
                recommendation=self.recommendation,
                evidence=evidence,
            )

        return self.ok(
            "Страница политики открывается без авторизации и cookie-стены.",
            recommendation="",
            evidence=evidence,
        )
