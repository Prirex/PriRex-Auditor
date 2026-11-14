"""D17. Заголовки безопасности (техническая гигиена).

Проверяются X-Frame-Options (или frame-ancestors в CSP),
X-Content-Type-Options: nosniff и Referrer-Policy. Отсутствие заголовков —
всегда ``warn`` (рекомендация), но не ``fail``.
"""

from __future__ import annotations

from app.core.checks.base import BaseCheck
from app.core.detect import (
    SECURITY_HEADERS,
    csp_has_frame_ancestors,
    header_value,
)
from app.core.models import Category, CheckResult, Evidence, Severity, SiteContext

_RECOMMENDATION = (
    "Настройте на сервере: X-Frame-Options: SAMEORIGIN (или "
    "Content-Security-Policy: frame-ancestors 'self'); "
    "X-Content-Type-Options: nosniff; Referrer-Policy: "
    "strict-origin-when-cross-origin. Убедитесь, что заголовки отдаются "
    "не только для HTML, но и для статических файлов."
)


def _present_headers(headers: dict[str, str | None]) -> list[Evidence]:
    """Evidence по фактически выставленным заголовкам."""
    items: list[Evidence] = []
    for name in ("x-frame-options", "content-security-policy",
                 "x-content-type-options", "referrer-policy"):
        value = header_value(headers, name)  # type: ignore[arg-type]
        if value and value.strip():
            items.append(
                BaseCheck.ev(
                    SECURITY_HEADERS.get(name, name),
                    value.strip()[:200],
                    kind="header",
                )
            )
    return items


class SecurityHeadersCheck(BaseCheck):
    """Проверка базовых заголовков безопасности."""

    id = "d17_security_headers"
    title = "Заголовки безопасности"
    category = Category.TECH.value
    weight = 3
    severity = Severity.RECOMMENDATION
    recommendation = _RECOMMENDATION

    def evaluate(self, ctx: SiteContext) -> CheckResult:
        if ctx.is_local:
            return self.na(
                "Локальная папка: HTTP-заголовки безопасности отдаёт сервер, "
                "у файлов на диске их нет. Проверьте после публикации сайта.",
                evidence=[self.ev("Источник", ctx.local_root or ctx.target_url, kind="url")],
            )

        headers: dict[str, str | None] = dict(ctx.security_headers or {})
        if not headers and ctx.headers:
            # Мягкий fallback: сборщик мог не выделить security_headers,
            # но сохранить полный набор заголовков ответа.
            headers = dict(ctx.headers)

        xfo = header_value(headers, "x-frame-options")  # type: ignore[arg-type]
        csp = header_value(headers, "content-security-policy")  # type: ignore[arg-type]
        frame_ok = bool((xfo or "").strip()) or csp_has_frame_ancestors(csp)

        nosniff_value = header_value(headers, "x-content-type-options")  # type: ignore[arg-type]
        nosniff_ok = (nosniff_value or "").strip().lower() == "nosniff"

        referrer_value = header_value(headers, "referrer-policy")  # type: ignore[arg-type]
        referrer_ok = bool((referrer_value or "").strip())

        requirements = [
            ("X-Frame-Options (или CSP frame-ancestors)", frame_ok),
            ("X-Content-Type-Options: nosniff", nosniff_ok),
            ("Referrer-Policy", referrer_ok),
        ]
        missing = [name for name, found in requirements if not found]
        evidence = _present_headers(headers)

        if not missing:
            return self.ok(
                "Все ключевые заголовки безопасности настроены: "
                "X-Frame-Options (или CSP frame-ancestors), "
                "X-Content-Type-Options: nosniff, Referrer-Policy.",
                evidence=evidence,
            )

        if len(missing) == len(requirements):
            return self.warn(
                "Заголовки безопасности не настроены: отсутствуют "
                "X-Frame-Options (или CSP frame-ancestors), "
                "X-Content-Type-Options: nosniff и Referrer-Policy. "
                "Это создаёт риск кликджекинга и MIME-sniffing.",
                severity=Severity.IMPORTANT,
                recommendation=_RECOMMENDATION,
                evidence=evidence,
            )

        return self.warn(
            "Настроены не все заголовки безопасности. Отсутствуют: "
            f"{', '.join(missing)}.",
            recommendation=_RECOMMENDATION,
            evidence=evidence,
        )
