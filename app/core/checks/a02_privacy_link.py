"""A02. Политика конфиденциальности — наличие (152-ФЗ, ч. 2 ст. 18.1).

Оператор обязан опубликовать политику обработки ПДн и обеспечить доступ к ней
с сайта. Проверяем ссылку, её расположение и открытие страницы.
"""

from __future__ import annotations

from app.core.checks.base import BaseCheck
from app.core.models import Category, CheckResult, Severity, SiteContext


class PrivacyLinkCheck(BaseCheck):
    id = "a02_privacy_link"
    title = "Политика конфиденциальности — наличие"
    category = Category.FZ152.value
    weight = 9
    severity = Severity.CRITICAL
    recommendation = (
        "Опубликуйте политику обработки персональных данных и разместите ссылку "
        "на неё в футере каждой страницы сайта (ч. 2 ст. 18.1 152-ФЗ)."
    )

    def evaluate(self, ctx: SiteContext) -> CheckResult:
        link = ctx.privacy_link
        page = ctx.pages.get("privacy")

        if link is None:
            return self.fail(
                "Не найдена ссылка на политику обработки персональных данных. "
                "Посетитель не может ознакомиться с условиями обработки своих данных.",
                recommendation=self.recommendation,
            )

        evidence = [
            self.ev(
                "Ссылка на политику",
                link.href,
                selector=link.selector or None,
                kind="url",
            )
        ]
        if link.text:
            evidence.append(self.ev("Текст ссылки", link.text))
        if link.selector:
            evidence.append(
                self.ev(
                    "Селектор ссылки",
                    link.selector,
                    selector=link.selector,
                    kind="selector",
                )
            )

        if page is None or not page.ok:
            if page is None:
                detail = "страница не загружена"
            elif page.error:
                detail = page.error
            elif page.status_code:
                detail = f"HTTP {page.status_code}"
            else:
                detail = "страница не открылась"
            return self.fail(
                f"Ссылка на политику найдена ({link.href}), но страница политики "
                f"не открывается ({detail}). Требование о доступности политики "
                "не выполнено.",
                severity=Severity.IMPORTANT,
                recommendation=(
                    "Проверьте, что ссылка ведёт на существующую страницу политики, "
                    "она отвечает HTTP 200 и доступна без авторизации."
                ),
                evidence=evidence,
            )

        evidence.append(self.ev("Страница политики", page.url or link.href, kind="url"))
        if page.status_code:
            evidence.append(self.ev("HTTP-статус страницы", str(page.status_code)))

        if not link.in_footer:
            return self.warn(
                "Ссылка на политику найдена, но не в футере: с других страниц сайта "
                "политику может быть сложно найти.",
                severity=Severity.IMPORTANT,
                recommendation=(
                    "Продублируйте ссылку на политику в футере каждой страницы сайта "
                    "(ч. 2 ст. 18.1 152-ФЗ)."
                ),
                evidence=evidence,
            )

        status = f" (HTTP {page.status_code})" if page.status_code else ""
        return self.ok(
            "Ссылка на политику обработки персональных данных найдена в футере, "
            f"страница открывается{status}.",
            recommendation="",
            evidence=evidence,
        )
