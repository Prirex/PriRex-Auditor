"""Тесты движка: скоринг, опции запуска, оркестратор, интеграция с проверками."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core.engine import orchestrator
from app.core.engine.orchestrator import (
    _unavailable_results,
    analyze,
    apply_option_filters,
)
from app.core.engine.scoring import calculate_score, score_grade
from app.core.errors import ScanCancelled
from app.core.models import (
    CheckResult,
    CheckStatus,
    Report,
    RunOptions,
    Severity,
    SiteContext,
)
from app.services.site_context import parse_site_context

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def result(
    status: CheckStatus,
    weight: int = 1,
    check_id: str = "x",
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        title=check_id,
        status=status,
        weight=weight,
        severity=Severity.IMPORTANT,
    )


# ---------------------------------------------------------------------------
# Скоринг
# ---------------------------------------------------------------------------


def test_score_empty_is_100() -> None:
    assert calculate_score([]) == 100


def test_score_all_pass() -> None:
    assert calculate_score([result(CheckStatus.PASS, 5), result(CheckStatus.PASS, 3)]) == 100


def test_score_half() -> None:
    assert calculate_score([result(CheckStatus.PASS, 2), result(CheckStatus.FAIL, 2)]) == 50


def test_score_warning_counts_half() -> None:
    # pass(1) + warn(1) = 1.5 / 2 = 75
    assert calculate_score([result(CheckStatus.PASS, 1), result(CheckStatus.WARN, 1)]) == 75


def test_score_ignores_not_applicable_and_skip() -> None:
    results = [
        result(CheckStatus.PASS, 3),
        result(CheckStatus.NOT_APPLICABLE, 10),
        result(CheckStatus.SKIP, 10),
        result(CheckStatus.FAIL, 1),
    ]
    # 3 / 4 = 75
    assert calculate_score(results) == 75


def test_score_ignores_zero_weight() -> None:
    assert calculate_score([result(CheckStatus.PASS, 1), result(CheckStatus.FAIL, 0)]) == 100


def test_score_all_not_applicable() -> None:
    assert calculate_score([result(CheckStatus.NOT_APPLICABLE, 5)]) == 100


def test_score_grade_titles() -> None:
    assert score_grade(95)[0] == "Отличное соответствие"
    assert score_grade(80)[0] == "Хорошее соответствие"
    assert score_grade(65)[0] == "Умеренное соответствие"
    assert score_grade(45)[0] == "Много замечаний"
    assert score_grade(10)[0] == "Высокий риск"


# ---------------------------------------------------------------------------
# Опции запуска и недоступный сайт
# ---------------------------------------------------------------------------


def test_option_filters_disable_trackers() -> None:
    results = [
        CheckResult(check_id="a08_cookie_banner", title="x", status=CheckStatus.FAIL),
        CheckResult(check_id="a10_foreign_trackers", title="y", status=CheckStatus.WARN),
        CheckResult(check_id="a01_https", title="z", status=CheckStatus.PASS),
    ]
    filtered = apply_option_filters(results, RunOptions(check_trackers=False))
    by_id = {item.check_id: item for item in filtered}
    assert by_id["a08_cookie_banner"].status is CheckStatus.SKIP
    assert by_id["a10_foreign_trackers"].status is CheckStatus.SKIP
    assert by_id["a01_https"].status is CheckStatus.PASS
    assert "отключена" in by_id["a10_foreign_trackers"].message


def test_option_filters_keep_results_when_enabled() -> None:
    results = [CheckResult(check_id="a10_foreign_trackers", title="y", status=CheckStatus.WARN)]
    filtered = apply_option_filters(results, RunOptions(check_trackers=True))
    assert filtered[0].status is CheckStatus.WARN


def test_unavailable_results_all_skipped() -> None:
    context = SiteContext(fetch_failed=True, fetch_error="Сайт не отвечает")
    results = _unavailable_results(context)
    assert results
    assert all(item.status is CheckStatus.SKIP for item in results)
    assert all("Сайт не отвечает" in item.message for item in results)


# ---------------------------------------------------------------------------
# Интеграция: все проверки на разобранном HTML
# ---------------------------------------------------------------------------


async def run_all_checks(context: SiteContext) -> dict[str, CheckResult]:
    from app.core.checks import create_checks

    out: dict[str, CheckResult] = {}
    for check in create_checks():
        out[check.id] = await check.run(context)
    return out


async def test_shop_without_network() -> None:
    context = parse_site_context(load("shop.html"), "https://lutik.ru/")
    results = await run_all_checks(context)
    assert len(results) == 17
    assert set(results) >= {
        "a01_https",
        "a05_forms_consent",
        "a06_consent_prechecked",
        "b13_seller_details",
        "c14_erid",
        "c15_ad_consent",
        "d16_robots_sitemap",
        "d17_security_headers",
    }
    # реквизиты есть → ЗоЗПП пройден
    assert results["b13_seller_details"].status is CheckStatus.PASS
    # реклама с пометкой и erid → пройдено
    assert results["c14_erid"].status is CheckStatus.PASS
    # подписка с отдельным рекламным чекбоксом → пройдено
    assert results["c15_ad_consent"].status is CheckStatus.PASS
    # чекбокс согласия не предзаполнен
    assert results["a06_consent_prechecked"].status is CheckStatus.PASS
    # форма подписки собирает e-mail без согласия на ПДн → нарушение
    assert results["a05_forms_consent"].status is CheckStatus.FAIL
    # cookie-баннер найден, категории и отказ есть
    assert results["a08_cookie_banner"].status is CheckStatus.PASS
    assert results["a09_cookie_categories"].status is CheckStatus.PASS
    # сторонние трекеры есть → предупреждение о локализации
    assert results["a10_foreign_trackers"].status is CheckStatus.WARN

    report = Report(
        url=context.url,
        score=calculate_score(list(results.values())),
        results=list(results.values()),
    )
    assert 0 < report.score < 100
    assert report.counts()["pass"] > 0
    assert dict(report.grouped()).keys() == {
        "152fz",
        "zozpp",
        "ad",
        "tech",
    }


async def test_blog_not_applicable_not_fail() -> None:
    """Ключевое требование ТЗ: неприменимое — NA, а не fail."""
    context = parse_site_context(load("blog.html"), "https://blog.ru/")
    results = await run_all_checks(context)
    for check_id in ("b13_seller_details", "c14_erid", "c15_ad_consent"):
        assert results[check_id].status is CheckStatus.NOT_APPLICABLE, check_id
        assert results[check_id].message
    for check_id in ("a05_forms_consent", "a06_consent_prechecked", "a07_separate_consent"):
        assert results[check_id].status is CheckStatus.NOT_APPLICABLE, check_id
    # нет трекеров → cookie-баннер и трекеры неприменимы
    assert results["a08_cookie_banner"].status is CheckStatus.NOT_APPLICABLE
    assert results["a10_foreign_trackers"].status is CheckStatus.NOT_APPLICABLE
    # контакты есть, robots/sitemap не загружались (сеть не нужна) → не падаем
    assert results["a11_pdn_contact"].status is CheckStatus.PASS


# ---------------------------------------------------------------------------
# Оркестратор с подменённым сборщиком контекста
# ---------------------------------------------------------------------------


def test_analyze_uses_builder(monkeypatch) -> None:
    context = parse_site_context(load("shop.html"), "https://lutik.ru/")
    context.https.used_https = True
    context.https.https_available = True
    context.robots.found = True

    async def fake_builder(url, options, progress=None, cancelled=None):
        return context

    monkeypatch.setattr(orchestrator, "build_site_context", fake_builder)

    steps: list[tuple[float, str]] = []
    scan = asyncio.run(
        analyze("https://lutik.ru/", RunOptions(deep_analysis=False), progress=lambda f, m: steps.append((f, m)))
    )
    assert scan.report.results
    assert len(scan.report.results) == 17
    assert scan.context is context
    assert steps[0][0] == 0.0
    assert steps[-1][0] == 1.0
    assert any("Проверка" in message for _, message in steps)


def test_analyze_fetch_failed(monkeypatch) -> None:
    context = SiteContext(
        target_url="https://down.ru/",
        url="https://down.ru/",
        fetch_failed=True,
        fetch_error="Не удалось подключиться к сайту.",
    )

    async def fake_builder(url, options, progress=None, cancelled=None):
        return context

    monkeypatch.setattr(orchestrator, "build_site_context", fake_builder)
    scan = asyncio.run(analyze("https://down.ru/", RunOptions()))
    assert scan.report.score == 0
    assert all(item.status is CheckStatus.SKIP for item in scan.report.results)
    assert any("Не удалось подключиться" in note for note in scan.report.notes)


def test_analyze_cancelled(monkeypatch) -> None:
    async def fake_builder(url, options, progress=None, cancelled=None):
        raise ScanCancelled()

    monkeypatch.setattr(orchestrator, "build_site_context", fake_builder)
    with pytest.raises(ScanCancelled):
        asyncio.run(analyze("https://lutik.ru/", RunOptions(), cancelled=lambda: True))


def test_report_helpers() -> None:
    results = [
        CheckResult(check_id="a", title="A", status=CheckStatus.PASS, category="152fz"),
        CheckResult(check_id="b", title="B", status=CheckStatus.FAIL, category="152fz"),
        CheckResult(check_id="c", title="C", status=CheckStatus.NOT_APPLICABLE, category="zozpp"),
        CheckResult(check_id="d", title="D", status=CheckStatus.SKIP, category="tech"),
    ]
    report = Report(
        url="https://x.ru",
        scanned_at=datetime.now(timezone.utc),
        score=50,
        results=results,
    )
    assert [item.check_id for item in report.not_applicable()] == ["c"]
    assert [item.check_id for item in report.skipped()] == ["d"]
    assert [item.check_id for item in report.problems()] == ["b"]
    counts = report.counts()
    assert counts["pass"] == 1 and counts["fail"] == 1
    assert [cat for cat, _ in report.grouped()] == ["152fz", "zozpp", "tech"]
