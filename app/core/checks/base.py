"""Базовый интерфейс проверки.

Каждая проверка — отдельный модуль в ``app/core/checks`` с классом-наследником
``BaseCheck``. Минимальный контракт:

    class MyCheck(BaseCheck):
        id = "a01_https"
        title = "HTTPS и TLS"
        category = Category.FZ152.value
        weight = 5
        severity = Severity.CRITICAL
        recommendation = "..."

        def evaluate(self, ctx: SiteContext) -> CheckResult:
            ...
            return self.ok("...") / self.fail("...") / self.na("...")

Синхронный ``evaluate`` удобен для чистых правил; если проверке нужен
асинхронный ввод-вывод, переопределите ``async def check``. Вызывается всегда
``await check.run(ctx)`` — она добавляет тайминг, ловит исключения и
проставляет id/title/category/weight.
"""

from __future__ import annotations

import time
from abc import ABC
from collections.abc import Sequence

from app.core.models import (
    CheckResult,
    CheckStatus,
    Evidence,
    Severity,
    SiteContext,
)


class BaseCheck(ABC):
    #: Уникальный идентификатор, например ``a01_https``.
    id: str = ""
    #: Название для UI и отчёта.
    title: str = ""
    #: Блок: ``Category.*.value``.
    category: str = "152fz"
    #: Вес в общем проценте соответствия (0 — не влияет).
    weight: int = 1
    #: Контексты применимости (``["*"]`` — всегда).
    applies_to: list[str] = ["*"]
    #: Приоритет нарушения по умолчанию.
    severity: Severity = Severity.IMPORTANT
    #: Рекомендация по исправлению по умолчанию.
    recommendation: str = ""

    # ------------------------------------------------------------------
    # Точка входа
    # ------------------------------------------------------------------
    async def run(self, ctx: SiteContext) -> CheckResult:
        """Запускает проверку, замеряет время и гарантирует CheckResult."""
        started = time.perf_counter()
        try:
            result = await self.check(ctx)
        except Exception as exc:  # проверка не должна ронять весь отчёт
            result = self.skip(
                f"Проверка не выполнена из-за ошибки: {exc}",
                error=f"{exc.__class__.__name__}: {exc}",
            )
        result.check_id = self.id
        result.title = self.title
        result.category = self.category
        result.weight = self.weight
        result.duration_ms = int((time.perf_counter() - started) * 1000)
        return result

    async def check(self, ctx: SiteContext) -> CheckResult:
        """Асинхронная обёртка над синхронным ``evaluate``."""
        return self.evaluate(ctx)

    def evaluate(self, ctx: SiteContext) -> CheckResult:
        raise NotImplementedError(
            f"{self.__class__.__name__}: опишите evaluate() или check()"
        )

    # ------------------------------------------------------------------
    # Конструкторы результата
    # ------------------------------------------------------------------
    def result(
        self,
        status: CheckStatus,
        message: str,
        *,
        severity: Severity | None = None,
        recommendation: str | None = None,
        evidence: Sequence[Evidence] | None = None,
        error: str | None = None,
    ) -> CheckResult:
        return CheckResult(
            check_id=self.id,
            title=self.title,
            category=self.category,
            status=status,
            severity=severity or self.severity,
            weight=self.weight,
            message=message,
            recommendation=self.recommendation if recommendation is None else recommendation,
            evidence=list(evidence or []),
            error=error,
        )

    def ok(
        self,
        message: str,
        *,
        recommendation: str | None = None,
        evidence: Sequence[Evidence] | None = None,
    ) -> CheckResult:
        return self.result(
            CheckStatus.PASS,
            message,
            severity=Severity.INFO,
            recommendation=recommendation,
            evidence=evidence,
        )

    def warn(
        self,
        message: str,
        *,
        severity: Severity | None = None,
        recommendation: str | None = None,
        evidence: Sequence[Evidence] | None = None,
    ) -> CheckResult:
        return self.result(
            CheckStatus.WARN,
            message,
            severity=severity,
            recommendation=recommendation,
            evidence=evidence,
        )

    def fail(
        self,
        message: str,
        *,
        severity: Severity | None = None,
        recommendation: str | None = None,
        evidence: Sequence[Evidence] | None = None,
    ) -> CheckResult:
        return self.result(
            CheckStatus.FAIL,
            message,
            severity=severity,
            recommendation=recommendation,
            evidence=evidence,
        )

    def na(
        self,
        message: str,
        *,
        evidence: Sequence[Evidence] | None = None,
        recommendation: str | None = None,
    ) -> CheckResult:
        """Не применимо к сайту. Не влияет на процент соответствия."""
        return self.result(
            CheckStatus.NOT_APPLICABLE,
            message,
            severity=Severity.INFO,
            recommendation="" if recommendation is None else recommendation,
            evidence=evidence,
        )

    def skip(
        self,
        message: str,
        *,
        error: str | None = None,
        evidence: Sequence[Evidence] | None = None,
    ) -> CheckResult:
        """Технически не удалось проверить. Не влияет на процент соответствия."""
        return self.result(
            CheckStatus.SKIP,
            message,
            severity=Severity.INFO,
            recommendation="",
            evidence=evidence,
            error=error,
        )

    # ------------------------------------------------------------------
    # Помощники для evidence
    # ------------------------------------------------------------------
    @staticmethod
    def ev(
        label: str,
        value: str = "",
        *,
        selector: str | None = None,
        kind: str = "text",
    ) -> Evidence:
        return Evidence(kind=kind, label=label, value=value, selector=selector)

    def __repr__(self) -> str:  # pragma: no cover - удобно в логах
        return f"<{self.__class__.__name__} {self.id} w={self.weight}>"
