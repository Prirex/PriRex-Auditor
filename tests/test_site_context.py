"""Тесты сборщика контекста: разбор HTML + сетевой сбор (без реального интернета)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.models import CheckStatus
from app.services.site_context import (
    _parse_robots,
    _pick_extra_pages,
    banner_from_browser,
    build_selector,
    parse_site_context,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def shop_ctx():
    return parse_site_context(load("shop.html"), "https://lutik.ru/")


@pytest.fixture
def blog_ctx():
    return parse_site_context(load("blog.html"), "https://blog.ru/")


# ---------------------------------------------------------------------------
# Магазин
# ---------------------------------------------------------------------------


def test_shop_basic_fields(shop_ctx) -> None:
    assert "Лютик" in shop_ctx.title
    assert shop_ctx.domain == "lutik.ru"
    assert "телевизоры" in shop_ctx.text
    assert shop_ctx.language == "ru"


def test_shop_sales_signs(shop_ctx) -> None:
    assert shop_ctx.has_prices
    assert any("₽" in sample for sample in shop_ctx.price_samples)
    assert shop_ctx.has_buy_buttons
    assert shop_ctx.has_cart
    assert shop_ctx.has_sales_signs
    assert shop_ctx.has_subscribe_form


def test_shop_privacy_and_contacts(shop_ctx) -> None:
    assert shop_ctx.privacy_link is not None
    assert shop_ctx.privacy_link.href.endswith("/privacy/")
    assert shop_ctx.privacy_link.in_footer
    assert shop_ctx.emails == ["info@lutik.ru"]
    assert shop_ctx.internal_links >= 4


def test_shop_trackers(shop_ctx) -> None:
    domains = {tracker.domain for tracker in shop_ctx.trackers}
    assert "googletagmanager.com" in domains
    assert "mc.yandex.ru" in domains
    foreign = {tracker.domain for tracker in shop_ctx.foreign_trackers}
    assert "googletagmanager.com" in foreign
    assert "mc.yandex.ru" not in foreign


def test_shop_forms_consent(shop_ctx) -> None:
    assert len(shop_ctx.forms) == 2
    order = next(form for form in shop_ctx.forms if form.is_order_form)
    assert order.has_consent_checkbox
    assert not order.consent_checked
    assert order.collects_personal_data
    assert "персональных данных" in (order.consent_text or "")

    subscribe = next(form for form in shop_ctx.forms if form.is_subscribe_form)
    assert subscribe.has_marketing_checkbox
    assert subscribe.marketing_checked
    assert not subscribe.has_consent_checkbox


def test_shop_ad_block_with_erid(shop_ctx) -> None:
    assert shop_ctx.ad_blocks
    block = shop_ctx.ad_blocks[0]
    assert block.has_ad_label
    assert block.has_erid
    assert block.erid_tokens
    assert "2VtzqwXyZabc123" in shop_ctx.erid_tokens


def test_shop_cookie_banner(shop_ctx) -> None:
    banner = shop_ctx.cookie_banner
    assert banner.found
    assert banner.source == "http"
    assert banner.has_accept
    assert banner.has_reject
    assert banner.has_settings


# ---------------------------------------------------------------------------
# Блог без продаж
# ---------------------------------------------------------------------------


def test_blog_has_no_sales(blog_ctx) -> None:
    assert not blog_ctx.has_sales_signs
    assert not blog_ctx.forms
    assert not blog_ctx.trackers
    assert not blog_ctx.ad_blocks
    assert blog_ctx.has_subscribe_form is False
    assert blog_ctx.privacy_link is not None
    assert blog_ctx.emails == ["author@blog.ru"]


def test_empty_html_is_safe() -> None:
    context = parse_site_context("", "https://empty.ru/")
    assert context.html == ""
    assert context.links == []
    assert context.forms == []
    assert context.has_sales_signs is False


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def test_parse_robots() -> None:
    disallow_all, sitemaps = _parse_robots(
        "User-agent: *\nDisallow: /\nSitemap: https://x.ru/sitemap.xml\n"
    )
    assert disallow_all
    assert sitemaps == ["https://x.ru/sitemap.xml"]


def test_parse_robots_partial() -> None:
    disallow_all, sitemaps = _parse_robots("User-agent: *\nDisallow: /admin\n")
    assert not disallow_all
    assert sitemaps == []


def test_pick_extra_pages(shop_ctx) -> None:
    chosen = _pick_extra_pages(shop_ctx, 4)
    assert chosen["privacy"].endswith("/privacy/")
    assert "contacts" in chosen


def test_build_selector() -> None:
    context = parse_site_context(load("shop.html"), "https://lutik.ru/")
    link = next(item for item in context.links if "privacy" in item.href)
    assert link.selector
    assert "a" in link.selector


def test_banner_from_browser() -> None:
    banner = banner_from_browser(
        {
            "text": "Мы используем cookie",
            "position": "fixed",
            "zIndex": 9999,
            "role": "",
            "tag": "DIV",
            "id": "cookie-popup",
            "className": "",
            "buttons": ["Принять", "Отклонить", "Настроить"],
        },
        "/tmp/shot.png",
    )
    assert banner.found
    assert banner.source == "playwright"
    assert banner.has_accept
    assert banner.has_reject
    assert banner.has_settings
    assert banner.selector == "div#cookie-popup"
    assert banner.screenshot == "/tmp/shot.png"


def test_banner_from_browser_ok_is_not_accept() -> None:
    banner = banner_from_browser(
        {"text": "Cookie settings", "buttons": ["Cookie settings"], "tag": "div"}
    )
    assert not banner.has_accept


def test_parse_plain_html_without_headers(shop_ctx) -> None:
    assert shop_ctx.security_headers == {}
    context = parse_site_context(
        load("blog.html"),
        "https://blog.ru/",
        headers={"X-Frame-Options": "DENY"},
    )
    assert context.security_headers["x-frame-options"] == "DENY"
    assert context.security_headers["referrer-policy"] is None
