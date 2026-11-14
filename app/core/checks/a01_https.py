"""A01. HTTPS и TLS (152-ФЗ).

Соединение должно быть защищено: HTTPS с валидным сертификатом и TLS 1.2+.
Проверка применима всегда, данные берутся из уже собранного ``SiteContext``.
"""

from __future__ import annotations

import re

from app.core.checks.base import BaseCheck
from app.core.models import Category, CheckResult, Severity, SiteContext

#: «TLSv1.2», «TLS 1.3», «SSLv3» и т.п.
_TLS_RE = re.compile(r"(?:TLS|SSL)\s*v?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)


def _tls_number(value: str | None) -> float | None:
    """Версия TLS числом (``1.2``), либо ``None``, если её не удалось разобрать."""
    if not value:
        return None
    match = _TLS_RE.search(value)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:  # pragma: no cover - защита от экзотических строк
        return None


class HttpsCheck(BaseCheck):
    id = "a01_https"
    title = "HTTPS и TLS"
    category = Category.FZ152.value
    weight = 10
    severity = Severity.CRITICAL
    recommendation = (
        "Установите действующий SSL/TLS-сертификат, настройте HTTPS и постоянное "
        "перенаправление (301) с http:// на https://, включите TLS 1.2 или 1.3. "
        "Это меры по защите персональных данных (ч. 2 ст. 19 152-ФЗ)."
    )

    def evaluate(self, ctx: SiteContext) -> CheckResult:
        info = ctx.https

        if ctx.is_local:
            return self.na(
                "Локальная папка: сайт не опубликован, HTTPS/TLS проверить нельзя. "
                "Загрузите сайт на хостинг и проверьте его адрес.",
                evidence=[self.ev("Источник", ctx.local_root or ctx.target_url, kind="url")],
            )

        # Сайт вообще не удалось открыть — проверять HTTPS технически нельзя.
        if ctx.fetch_failed and not info.used_https and not info.https_available:
            reason = f" Причина: {ctx.fetch_error}" if ctx.fetch_error else ""
            return self.skip("Сайт недоступен — проверить HTTPS/TLS не удалось." + reason)

        evidence = [
            self.ev(
                "Финальный адрес",
                info.final_url or ctx.url or ctx.target_url,
                kind="url",
            )
        ]
        if info.http_status is not None:
            evidence.append(self.ev("HTTP-статус", str(info.http_status)))
        evidence.append(
            self.ev(
                "Сертификат",
                "действителен" if info.cert_valid else "недействителен",
            )
        )
        if info.cert_error:
            evidence.append(self.ev("Ошибка сертификата", info.cert_error))
        if info.tls_version:
            evidence.append(self.ev("Версия TLS", info.tls_version))
        if info.https_available:
            evidence.append(
                self.ev(
                    "Редирект HTTP → HTTPS",
                    (
                        "не проверено"
                        if not info.http_redirect_checked
                        else ("настроен" if info.redirects_http_to_https else "не обнаружен")
                    ),
                )
            )

        problems: list[str] = []
        if not info.used_https:
            if info.https_available:
                problems.append(
                    "Сайт открывается по HTTP, хотя HTTPS доступен: пользователь "
                    "остаётся на незащищённом соединении."
                )
            else:
                problems.append(
                    "Сайт не поддерживает HTTPS: соединение не защищено, данные "
                    "форм могут быть перехвачены."
                )
        elif not info.cert_valid:
            detail = f": {info.cert_error}" if info.cert_error else ""
            problems.append(
                "HTTPS-сертификат недействителен (истёк, самоподписанный или не "
                f"соответствует домену){detail}."
            )

        if (
            info.https_available
            and info.http_redirect_checked
            and not info.redirects_http_to_https
        ):
            problems.append(
                "HTTP-версия сайта не перенаправляет на HTTPS: посетитель может "
                "остаться на незащищённом соединении."
            )

        tls = _tls_number(info.tls_version)
        tls_outdated = tls is not None and tls < 1.2

        if problems:
            message = " ".join(problems)
            if tls_outdated:
                message += (
                    f" Дополнительно: устаревшая версия TLS ({info.tls_version}), "
                    "нужна TLS 1.2 или новее."
                )
            return self.fail(
                message,
                recommendation=self.recommendation,
                evidence=evidence,
            )

        if tls_outdated:
            return self.warn(
                f"Используется устаревшая версия TLS ({info.tls_version}). "
                "TLS 1.0 и 1.1 не обеспечивают достаточную защиту данных.",
                severity=Severity.IMPORTANT,
                recommendation=(
                    "Отключите TLS 1.0/1.1 в настройках веб-сервера, оставьте "
                    "TLS 1.2 и 1.3 (ч. 2 ст. 19 152-ФЗ)."
                ),
                evidence=evidence,
            )

        tls_label = info.tls_version or "версия TLS не определена"
        redirect_note = (
            " HTTP перенаправляется на HTTPS."
            if info.redirects_http_to_https
            else ""
        )
        return self.ok(
            f"Сайт открывается по HTTPS, сертификат действителен, используется "
            f"{tls_label}.{redirect_note}".strip(),
            recommendation="",
            evidence=evidence,
        )
