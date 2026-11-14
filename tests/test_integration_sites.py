"""Интеграционные тесты на реальных сайтах-эталонах.

По умолчанию ОТКЛЮЧЕНЫ (нужен интернет, сайты меняются и могут блокировать
ботов). Запуск:

    $env:RUN_NETWORK_TESTS = "1"
    python -m pytest tests/test_integration_sites.py -v -s

Проверяем не «правильный процент», а устойчивость к реальному HTML:
сайт без продаж не получает fail по реквизитам, сайт с политикой её находит,
отчёт собирается целиком.
"""

from __future__ import annotations

import os

import pytest

from app.core.engine import analyze
from app.core.models import CheckStatus, RunOptions

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        os.environ.get("RUN_NETWORK_TESTS") != "1",
        reason="нужен интернет: установите RUN_NETWORK_TESTS=1",
    ),
]

CASES = [
    # (адрес, ожидания)
    ("https://example.com", {"no_sales": True, "expect_privacy": False}),
    ("https://habr.com/ru/", {"no_sales": True, "expect_privacy": True}),
    ("https://github.com", {"no_sales": False, "expect_privacy": True}),
]


@pytest.mark.parametrize(("url", "expect"), CASES, ids=[case[0] for case in CASES])
async def test_real_site_scan(url: str, expect: dict) -> None:
    scan = await analyze(url, RunOptions(deep_analysis=False, timeout=25.0))
    report = scan.report

    assert 0 <= report.score <= 100
    assert len(report.results) == 17
    assert all(result.message for result in report.results)

    by_id = {result.check_id: result for result in report.results}
    assert by_id["a01_https"].status in {
        CheckStatus.PASS,
        CheckStatus.WARN,
        CheckStatus.FAIL,
        CheckStatus.SKIP,
    }

    if expect.get("no_sales"):
        # ключевое требование: неприменимое — NA, а не fail
        assert by_id["b13_seller_details"].status is not CheckStatus.FAIL

    if expect.get("expect_privacy"):
        assert by_id["a02_privacy_link"].status in {CheckStatus.PASS, CheckStatus.WARN}
        assert scan.context.privacy_link is not None

    # отчёт не должен быть пустым: применимых проверок всегда есть
    assert report.applicable()
