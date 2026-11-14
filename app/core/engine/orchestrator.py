"""Оркестратор: собирает контекст сайта и прогоняет все проверки."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from app.core.engine.registry import ALL_CHECKS
from app.core.engine.scoring import calculate_score
from app.core.errors import ScanCancelled
from app.core.models import (
    CheckResult,
    CheckStatus,
    Report,
    RunOptions,
    Severity,
    SiteContext,
)
from app.services.site_context import build_site_context
from app.services.targets import normalize_target
from app.version import __version__

# progress(доля 0..1, текст шага)
ProgressCallback = Callable[[float, str], None]
# cancelled() -> True, если пользователь нажал «Отмена»
CancelCallback = Callable[[], bool]

#: Доля прогресса, отведённая на сбор контекста (остальное — проверки).
CONTEXT_SHARE = 0.7


@dataclass
class ScanResult:
    report: Report
    context: SiteContext = field(default=None)  # type: ignore[assignment]


def _scale(
    progress: ProgressCallback | None,
    start: float,
    end: float,
) -> ProgressCallback:
    def callback(fraction: float, message: str) -> None:
        if progress is None:
            return
        fraction = min(1.0, max(0.0, fraction))
        progress(start + (end - start) * fraction, message)

    return callback


def _ensure_not_cancelled(cancelled: CancelCallback | None) -> None:
    if cancelled is not None and cancelled():
        raise ScanCancelled()


def apply_option_filters(
    results: list[CheckResult],
    options: RunOptions,
) -> list[CheckResult]:
    """Учитывает чекбоксы пользователя (например, отключённые трекеры)."""
    if options.check_trackers:
        return results
    tracker_ids = {"a10_foreign_trackers", "a08_cookie_banner"}
    filtered: list[CheckResult] = []
    for result in results:
        if result.check_id in tracker_ids and result.status is not CheckStatus.SKIP:
            filtered.append(
                result.model_copy(
                    update={
                        "status": CheckStatus.SKIP,
                        "severity": result.severity,
                        "message": (
                            "Проверка сторонних трекеров отключена в параметрах запуска. "
                            "Включите «Проверять сторонние трекеры», чтобы проверить cookie-баннер "
                            "и зарубежные счётчики."
                        ),
                        "recommendation": "",
                        "evidence": [],
                    }
                )
            )
        else:
            filtered.append(result)
    return filtered


def _unavailable_results(context: SiteContext) -> list[CheckResult]:
    """Сайт недоступен: не выдаём fail, помечаем всё как «не проверено»."""
    reason = context.fetch_error or "Сайт недоступен."
    results: list[CheckResult] = []
    for cls in ALL_CHECKS:
        results.append(
            CheckResult(
                check_id=cls.id,
                title=cls.title,
                category=cls.category,
                status=CheckStatus.SKIP,
                severity=Severity.INFO,
                weight=cls.weight,
                message=(
                    "Проверка не выполнена: сайт недоступен. "
                    f"{reason}"
                ),
                recommendation="",
                error=reason,
            )
        )
    return results


async def analyze(
    url: str,
    options: RunOptions | None = None,
    progress: ProgressCallback | None = None,
    cancelled: CancelCallback | None = None,
) -> ScanResult:
    """Полный цикл: нормализация → сбор контекста → проверки → отчёт."""
    options = options or RunOptions()
    started = time.perf_counter()

    _ensure_not_cancelled(cancelled)
    if progress is not None:
        progress(0.0, "Подготовка…")

    target = normalize_target(url)
    if not target.ok:
        raise ValueError(target.error or "Некорректный адрес сайта")

    if target.is_local:
        from app.services.local_context import build_local_site_context

        context = await build_local_site_context(
            target.value,
            options,
            progress=_scale(progress, 0.0, CONTEXT_SHARE),
            cancelled=cancelled,
        )
    else:
        context = await build_site_context(
            target.value,
            options,
            progress=_scale(progress, 0.0, CONTEXT_SHARE),
            cancelled=cancelled,
        )

    if context.fetch_failed:
        notes = list(context.notes) + list(context.errors)
        if context.fetch_error and context.fetch_error not in notes:
            notes.insert(0, context.fetch_error)
        report = Report(
            url=url,
            final_url=context.url or url,
            score=0,
            results=_unavailable_results(context),
            deep_analysis=context.deep_analysis,
            is_local=context.is_local,
            app_version=__version__,
            duration_ms=int((time.perf_counter() - started) * 1000),
            notes=notes,
        )
        if progress is not None:
            progress(1.0, "Сайт недоступен")
        return ScanResult(report=report, context=context)

    checks = [cls() for cls in ALL_CHECKS]
    results: list[CheckResult] = []
    total = max(1, len(checks))
    for index, check in enumerate(checks):
        _ensure_not_cancelled(cancelled)
        if progress is not None:
            base = CONTEXT_SHARE
            span = 1.0 - CONTEXT_SHARE
            progress(
                base + span * (index / total),
                f"Проверка {index + 1} из {total}: {check.title}",
            )
        results.append(await check.run(context))

    results = apply_option_filters(results, options)

    report = Report(
        url=url,
        final_url=context.url or url,
        score=calculate_score(results),
        results=results,
        deep_analysis=context.deep_analysis,
        is_local=context.is_local,
        app_version=__version__,
        duration_ms=int((time.perf_counter() - started) * 1000),
        notes=list(context.notes) + list(context.errors),
    )
    if progress is not None:
        progress(1.0, "Готово")
    return ScanResult(report=report, context=context)
