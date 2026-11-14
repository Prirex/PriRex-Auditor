"""Подсчёт процента соответствия."""

from __future__ import annotations

from collections.abc import Sequence

from app.core.models import CheckResult, CheckStatus
#: Сколько «очков» даёт каждый статус применимой проверки.
STATUS_POINTS: dict[CheckStatus, float] = {
    CheckStatus.PASS: 1.0,
    CheckStatus.WARN: 0.5,
    CheckStatus.FAIL: 0.0,
}

GRADE_THRESHOLDS: list[tuple[int, str, str]] = [
    (90, "Отличное соответствие", "Формальные требования в основном соблюдены."),
    (75, "Хорошее соответствие", "Есть замечания, которые стоит устранить."),
    (60, "Умеренное соответствие", "Несколько важных требований не выполнено."),
    (40, "Много замечаний", "Значительная часть требований не выполнена."),
    (0, "Высокий риск", "Есть критические нарушения — нужна доработка сайта."),
]


def calculate_score(results: Sequence[CheckResult]) -> int:
    """Взвешенный процент: учитываются только применимые проверки (pass/warn/fail)."""
    total_weight = 0
    earned = 0.0
    for result in results:
        if not result.affects_score:
            continue
        weight = max(0, int(result.weight))
        if weight == 0:
            continue
        total_weight += weight
        earned += weight * STATUS_POINTS.get(result.status, 0.0)
    if total_weight == 0:
        # всё «не применимо» — формально претензий нет
        return 100
    return max(0, min(100, int(round(100.0 * earned / total_weight))))


def score_grade(score: int) -> tuple[str, str]:
    """Заголовок и пояснение для процента."""
    for threshold, title, hint in GRADE_THRESHOLDS:
        if score >= threshold:
            return title, hint
    return GRADE_THRESHOLDS[-1][1], GRADE_THRESHOLDS[-1][2]


def total_points(results: Sequence[CheckResult]) -> int:
    """Максимум баллов: сумма весов применимых проверок."""
    return sum(max(0, int(result.weight)) for result in results if result.affects_score)


def lost_points(result: CheckResult) -> float:
    """Сколько баллов теряется из-за статуса проверки."""
    if not result.affects_score or result.weight <= 0:
        return 0.0
    return float(result.weight) * (1.0 - STATUS_POINTS.get(result.status, 0.0))


def improvement_plan(results: Sequence[CheckResult]) -> list[tuple[CheckResult, float]]:
    """Что мешает 100%: пары (проверка, потерянные баллы), по убыванию влияния."""
    items = [(result, lost_points(result)) for result in results]
    items = [(result, lost) for result, lost in items if lost > 0]
    items.sort(key=lambda pair: (-pair[1], pair[0].severity.order))
    return items
