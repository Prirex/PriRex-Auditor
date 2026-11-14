"""Тесты расчёта потенциальных штрафов по сайту."""

from __future__ import annotations

import pytest

from app.core.engine.fines import (
    FineRange,
    FineSummary,
    format_money,
    site_fine_summary,
)
from app.core.models import CheckResult, CheckStatus, Severity


class FakeMethodology:
    """Минимальный двойник MethodologyCheck для тестов."""

    def __init__(self, individual: str, legal: str) -> None:
        self.fine_individual = individual
        self.fine_legal = legal


def result(
    check_id: str,
    status: CheckStatus,
    title: str = "",
    weight: int = 1,
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        title=title or check_id,
        status=status,
        severity=Severity.IMPORTANT,
        weight=weight,
    )


# ---------------------------------------------------------------------------
# Парсинг сумм
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("от 1 500 до 3 000 ₽", FineRange(1500, 3000)),
        ("от 30 000 до 60 000 ₽", FineRange(30000, 60000)),
        ("от 1 000 000 до 6 000 000 ₽", FineRange(1000000, 6000000)),
        ("до 3 000 ₽", FineRange(0, 3000)),
        ("3 000 ₽", FineRange(0, 3000)),
        ("прямого штрафа нет", FineRange()),
        ("уточнить", FineRange()),
        ("", FineRange()),
        ("—", FineRange()),
    ],
)
def test_parse_fine(text: str, expected: FineRange) -> None:
    assert FineRange.parse(text) == expected


def test_parse_spaces_and_dash() -> None:
    assert FineRange.parse("от 1\u00a0500 до 3\u202f000 ₽") == FineRange(1500, 3000)
    assert FineRange.parse("1 500–3 000 ₽") == FineRange(1500, 3000)


def test_format_range() -> None:
    assert FineRange(1500, 3000).format() == "от 1 500 до 3 000 ₽"
    assert FineRange(0, 3000).format() == "до 3 000 ₽"
    assert FineRange(5000, 5000).format() == "5 000 ₽"
    assert FineRange().format() == "не предусмотрен"
    assert format_money(1000000) == "1 000 000 ₽"


def test_add_ranges() -> None:
    assert FineRange(100, 200) + FineRange(300, 400) == FineRange(400, 600)
    assert FineRange() + FineRange(100, 200) == FineRange(100, 200)


# ---------------------------------------------------------------------------
# Суммирование по проверкам
# ---------------------------------------------------------------------------


def test_summary_uses_only_problems() -> None:
    lookup = {
        "a02": FakeMethodology("от 1 500 до 3 000 ₽", "от 30 000 до 60 000 ₽"),
        "a05": FakeMethodology("от 10 000 до 15 000 ₽", "от 300 000 до 700 000 ₽"),
        "a01": FakeMethodology("прямого штрафа нет", "прямого штрафа нет"),
    }
    results = [
        result("a02", CheckStatus.FAIL, "Политика"),
        result("a05", CheckStatus.WARN, "Формы"),
        result("a01", CheckStatus.PASS, "HTTPS"),
        result("a04", CheckStatus.NOT_APPLICABLE, "Содержание"),
        result("a08", CheckStatus.SKIP, "Cookie"),
    ]
    summary = site_fine_summary(results, lookup=lambda key: lookup.get(key))
    assert summary.individual == FineRange(11500, 18000)
    assert summary.legal == FineRange(330000, 760000)
    assert summary.count == 2
    assert summary.has_any


def test_summary_counts_checks_without_direct_fine() -> None:
    lookup = {"a01": FakeMethodology("прямого штрафа нет", "прямого штрафа нет")}
    results = [result("a01", CheckStatus.FAIL)]
    summary = site_fine_summary(results, lookup=lambda key: lookup.get(key))
    assert not summary.has_any
    assert summary.without_fine == 1
    assert "не предусмотрено" in summary.note()


def test_summary_individual_only() -> None:
    lookup = {"b13": FakeMethodology("прямого штрафа нет", "от 5 000 до 10 000 ₽")}
    summary = site_fine_summary(
        [result("b13", CheckStatus.WARN)], lookup=lambda key: lookup.get(key)
    )
    assert summary.individual.is_empty
    assert summary.legal == FineRange(5000, 10000)
    assert summary.individual.format() == "не предусмотрен"
    assert summary.count == 1


def test_summary_without_methodology() -> None:
    summary = site_fine_summary(
        [result("unknown", CheckStatus.FAIL)], lookup=lambda key: None
    )
    assert not summary.has_any
    assert summary.count == 0
    assert summary.without_fine == 0


def test_summary_empty_results() -> None:
    summary = site_fine_summary([], lookup=lambda key: None)
    assert not summary.has_any
    assert "не выявлено" in summary.note()


def test_summary_note_mentions_court() -> None:
    lookup = {"a02": FakeMethodology("от 1 500 до 3 000 ₽", "от 30 000 до 60 000 ₽")}
    summary = site_fine_summary(
        [result("a02", CheckStatus.FAIL)], lookup=lambda key: lookup.get(key)
    )
    note = summary.note()
    assert "КоАП" in note
    assert "суд" in note
    assert "1 выявленному" in note


def test_summary_totals_maximum() -> None:
    summary = FineSummary(
        individual=FineRange(11500, 18000), legal=FineRange(330000, 760000)
    )
    assert summary.total_max == 760000
