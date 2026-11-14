"""Оценка потенциальных штрафов по выявленным нарушениям.

Суммы берутся из справочника «Критерии проверок» (``assets/methodology.json``,
поля ``fine_individual`` / ``fine_legal``). Модуль не знает про Qt: чистые
функции парсинга и суммирования, которые легко тестировать.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from app.core.models import CheckResult, CheckStatus

#: Статусы, которые считаются «проблемой» для итоговой суммы.
DEFAULT_STATUSES: tuple[CheckStatus, ...] = (CheckStatus.FAIL, CheckStatus.WARN)

#: Маркеры, означающие, что прямого штрафа нет (или норма требует уточнения).
_NO_FINE_MARKERS: tuple[str, ...] = (
    "прямого штрафа нет",
    "штрафа нет",
    "не предусмотрен",
    "нет штрафа",
    "уточнить",
)

_NUMBER_RE = re.compile(r"\d[\d\s\u00a0\u202f]*")


def _to_int(value: str) -> int | None:
    digits = re.sub(r"[\s\u00a0\u202f]", "", value)
    if not digits.isdigit():
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _number(amount: int) -> str:
    """Целое число с пробелами-разделителями: «1 000 000»."""
    return f"{amount:,}".replace(",", " ")


def format_money(amount: int) -> str:
    """Целое число в виде «1 000 000 ₽»."""
    return f"{_number(amount)} ₽"


def _plural(count: int, one: str, few: str, many: str) -> str:
    """Русская форма множественного числа для числа ``count``."""
    remainder_100 = count % 100
    remainder_10 = count % 10
    if 11 <= remainder_100 <= 14:
        return many
    if remainder_10 == 1:
        return one
    if 2 <= remainder_10 <= 4:
        return few
    return many


@dataclass(frozen=True)
class FineRange:
    """Диапазон штрафа: нижняя и верхняя границы (в рублях)."""

    minimum: int = 0
    maximum: int = 0

    @property
    def is_empty(self) -> bool:
        return self.maximum <= 0

    def __add__(self, other: "FineRange") -> "FineRange":
        if not isinstance(other, FineRange):
            return NotImplemented
        return FineRange(
            minimum=self.minimum + other.minimum,
            maximum=self.maximum + other.maximum,
        )

    def format(self) -> str:
        """Человекочитаемый диапазон для интерфейса и отчёта."""
        if self.is_empty:
            return "не предусмотрен"
        if self.minimum <= 0:
            return f"до {format_money(self.maximum)}"
        if self.minimum == self.maximum:
            return format_money(self.maximum)
        return f"от {_number(self.minimum)} до {format_money(self.maximum)}"

    @classmethod
    def parse(cls, text: str) -> "FineRange":
        """Разбирает строку вида «от 1 500 до 3 000 ₽» или «прямого штрафа нет»."""
        raw = (text or "").strip()
        if not raw:
            return cls()
        low = raw.lower()
        if any(marker in low for marker in _NO_FINE_MARKERS) and "₽" not in low:
            return cls()
        numbers: list[int] = []
        for match in _NUMBER_RE.findall(low):
            value = _to_int(match)
            if value is None or value <= 0:
                continue
            numbers.append(value)
            if len(numbers) >= 2:
                break
        if not numbers:
            return cls()
        if len(numbers) == 1:
            # «до N ₽» — нижняя граница неизвестна
            return cls(minimum=0, maximum=numbers[0])
        minimum, maximum = numbers[0], numbers[1]
        if maximum < minimum:
            minimum, maximum = maximum, minimum
        return cls(minimum=minimum, maximum=maximum)


@dataclass
class FineSummary:
    """Итог по сайту: суммы для физлица и юрлица по выявленным нарушениям."""

    individual: FineRange = field(default_factory=FineRange)
    legal: FineRange = field(default_factory=FineRange)
    #: Названия проверок, давших суммы (для пояснения).
    checks: list[str] = field(default_factory=list)
    #: Сколько найденных проблем не имеют прямого штрафа.
    without_fine: int = 0

    @property
    def count(self) -> int:
        return len(self.checks)

    @property
    def has_any(self) -> bool:
        return not self.individual.is_empty or not self.legal.is_empty

    @property
    def total_max(self) -> int:
        return max(self.individual.maximum, self.legal.maximum)

    def note(self) -> str:
        """Короткая оговорка под суммами."""
        if not self.has_any:
            if self.without_fine:
                return (
                    "Прямых административных штрафов за выявленные нарушения "
                    "не предусмотрено — недочёты стоит исправить, но штраф "
                    "возможен только при квалификации последствий."
                )
            return "Нарушений, за которые предусмотрен штраф, не выявлено."
        if self.count == 1:
            headline = (
                "Оценка по 1 выявленному нарушению (если штраф будет назначен)"
            )
        else:
            headline = (
                f"Оценка по {self.count} выявленным нарушениям и замечаниям "
                "(если штраф назначат по каждому)"
            )
        parts = [headline + "."]
        if self.without_fine:
            remark_word = _plural(
                self.without_fine, "замечание", "замечания", "замечаний"
            )
            parts.append(
                f"Ещё {self.without_fine} {remark_word} без прямого штрафа "
                "в сумму не входят."
            )
        parts.append(
            "Ориентировочно по КоАП РФ; итоговый размер определяет орган или суд."
        )
        return " ".join(parts)


Lookup = Callable[[str], object | None]


def _default_lookup(check_id: str) -> object | None:
    try:
        from app.core.content.loader import methodology_for

        return methodology_for(check_id)
    except Exception:  # noqa: BLE001 - справочник не должен ломать расчёт
        return None


def site_fine_summary(
    results: Sequence[CheckResult],
    statuses: Sequence[CheckStatus] = DEFAULT_STATUSES,
    lookup: Lookup | None = None,
) -> FineSummary:
    """Суммирует потенциальные штрафы по проблемным проверкам.

    Учитываются только статусы из ``statuses`` (по умолчанию fail и warn).
    N/A, skip и пройденные проверки в сумму не входят.
    """
    getter = lookup or _default_lookup
    summary = FineSummary()
    for result in results:
        if result.status not in statuses:
            continue
        info = getter(result.check_id)
        if info is None:
            continue
        individual = FineRange.parse(str(getattr(info, "fine_individual", "") or ""))
        legal = FineRange.parse(str(getattr(info, "fine_legal", "") or ""))
        if individual.is_empty and legal.is_empty:
            summary.without_fine += 1
            continue
        summary.individual = summary.individual + individual
        summary.legal = summary.legal + legal
        summary.checks.append(result.title or result.check_id)
    return summary


__all__ = [
    "DEFAULT_STATUSES",
    "FineRange",
    "FineSummary",
    "format_money",
    "site_fine_summary",
]
