"""Юнит-тесты проверок блоков B (ЗоЗПП), C (38-ФЗ) и D (техгигиена).

Все проверки синхронные и работают на синтетическом ``SiteContext``:
сеть не используется. ``asyncio_mode=auto`` в pytest.ini позволяет
объявлять тесты как ``async def`` без декораторов.
"""

from __future__ import annotations

from app.core.checks.b13_seller_details import SellerDetailsCheck
from app.core.checks.c14_erid import EridMarkingCheck
from app.core.checks.c15_ad_consent import AdConsentCheck
from app.core.checks.d16_robots_sitemap import RobotsSitemapCheck
from app.core.checks.d17_security_headers import SecurityHeadersCheck
from app.core.models import CheckStatus, RobotsInfo, Severity
from tests.helpers import ad_block, field, form, make_context, robots, sitemap

NA_B13 = (
    "На сайте не обнаружены признаки дистанционной продажи товаров/услуг. "
    "Проверка реквизитов не требуется."
)
NA_C14 = "На странице не обнаружены рекламные блоки. Маркировка ERID не требуется."
NA_C15 = (
    "На сайте не обнаружены формы подписки на рассылку. "
    "Отдельное согласие на рекламу не требуется."
)

ERID = "2VfnxyNqJ3E4F5G6H7J8K9L0M1N2P3Q4"

FULL_UL_TEXT = (
    "ооо «ромашка», огрн 1000000000010, инн 0000000018, "
    "юридический адрес: 101000, г. москва, ул. тестовая, д. 1, "
    "email: info@romashka.ru, тел. +7 (000) 123-45-67"
)


# ---------------------------------------------------------------------------
# B13 — реквизиты продавца
# ---------------------------------------------------------------------------


async def test_b13_no_sales_is_not_applicable():
    """Информационный сайт без продаж — N/A, а не FAIL (прямое требование ТЗ)."""
    ctx = make_context(
        has_prices=False,
        has_buy_buttons=False,
        has_cart=False,
        has_order_form=False,
        has_subscribe_form=True,
        forms=[form(is_subscribe_form=True)],
    )

    res = await SellerDetailsCheck().run(ctx)

    assert res.status is CheckStatus.NOT_APPLICABLE
    assert res.message == NA_B13
    assert res.severity is Severity.INFO


async def test_b13_sales_without_requisites_is_fail():
    ctx = make_context(
        has_buy_buttons=True,
        buy_button_samples=["Купить"],
        html="<html><body><button>Купить</button></body></html>",
        text="купить",
    )

    res = await SellerDetailsCheck().run(ctx)

    assert res.status is CheckStatus.FAIL
    assert res.severity is Severity.CRITICAL
    assert "реквизиты" in res.message.lower()
    assert res.evidence


async def test_b13_full_ul_requisites_is_pass():
    ctx = make_context(
        has_prices=True,
        html=f"<html><body><footer>{FULL_UL_TEXT}</footer></body></html>",
        text=FULL_UL_TEXT,
        footer_text=FULL_UL_TEXT,
    )

    res = await SellerDetailsCheck().run(ctx)

    assert res.status is CheckStatus.PASS
    assert any(e.value == "1000000000010" for e in res.evidence)
    assert any(e.value == "0000000018" for e in res.evidence)
    assert any(e.label == "Адрес" for e in res.evidence)


async def test_b13_partial_requisites_is_warn():
    text = "ооо «ромашка», огрн 1000000000010"
    ctx = make_context(
        has_prices=True,
        html=f"<html><body>{text}</body></html>",
        text=text,
    )

    res = await SellerDetailsCheck().run(ctx)

    assert res.status is CheckStatus.WARN
    assert res.severity is Severity.IMPORTANT
    assert "не хватает" in res.message.lower()
    assert "адрес" in res.message.lower()


async def test_b13_full_ip_requisites_is_pass():
    ogrnip = "100000000000011"
    text = (
        "ип иванов иван иванович, огрнип "
        f"{ogrnip}, email: ip@ivanov.ru"
    )
    ctx = make_context(
        has_order_form=True,
        html=f"<html><body>{text}</body></html>",
        text=text,
        footer_text=text,
    )

    res = await SellerDetailsCheck().run(ctx)

    assert res.status is CheckStatus.PASS
    assert any(e.label == "ОГРНИП" and e.value == ogrnip for e in res.evidence)


# ---------------------------------------------------------------------------
# C14 — маркировка ERID
# ---------------------------------------------------------------------------


async def test_c14_no_ad_blocks_is_not_applicable():
    ctx = make_context(ad_blocks=[])

    res = await EridMarkingCheck().run(ctx)

    assert res.status is CheckStatus.NOT_APPLICABLE
    assert res.message == NA_C14


async def test_c14_block_without_erid_is_fail():
    ctx = make_context(
        ad_blocks=[
            ad_block(
                text="Реклама. Скидка 50%",
                has_ad_label=True,
                erid_tokens=[],
                selector="div.ad-1",
            )
        ]
    )

    res = await EridMarkingCheck().run(ctx)

    assert res.status is CheckStatus.FAIL
    assert res.severity is Severity.IMPORTANT
    assert "erid" in res.message.lower()
    assert "div.ad-1" in res.message
    assert any(e.selector == "div.ad-1" for e in res.evidence)


async def test_c14_block_with_label_and_erid_is_pass():
    ctx = make_context(
        ad_blocks=[
            ad_block(
                text="Реклама. Скидка 50%",
                has_ad_label=True,
                erid_tokens=[ERID],
                selector="div.ad-1",
            )
        ]
    )

    res = await EridMarkingCheck().run(ctx)

    assert res.status is CheckStatus.PASS
    assert any(e.value == ERID for e in res.evidence)


async def test_c14_block_without_ad_label_is_fail():
    ctx = make_context(
        ad_blocks=[
            ad_block(
                text="Купите слона со скидкой",
                has_ad_label=False,
                erid_tokens=[ERID],
                selector="div.promo-1",
            )
        ]
    )

    res = await EridMarkingCheck().run(ctx)

    assert res.status is CheckStatus.FAIL
    assert "пометки «Реклама»" in res.message
    assert "div.promo-1" in res.message


async def test_c14_mixed_blocks_is_fail_and_counts_good():
    ctx = make_context(
        ad_blocks=[
            ad_block(text="Реклама. Ок", has_ad_label=True, erid_tokens=[ERID]),
            ad_block(
                text="Реклама. Без токена",
                has_ad_label=True,
                erid_tokens=[],
                selector="div.ad-2",
            ),
        ]
    )

    res = await EridMarkingCheck().run(ctx)

    assert res.status is CheckStatus.FAIL
    assert "1 из 2" in res.message
    assert "div.ad-2" in res.message


# ---------------------------------------------------------------------------
# C15 — согласие на рекламную рассылку
# ---------------------------------------------------------------------------


async def test_c15_no_subscription_forms_is_not_applicable():
    ctx = make_context(forms=[])

    res = await AdConsentCheck().run(ctx)

    assert res.status is CheckStatus.NOT_APPLICABLE
    assert res.message == NA_C15


async def test_c15_subscription_with_only_pdn_consent_is_fail():
    ctx = make_context(
        has_subscribe_form=True,
        forms=[
            form(
                is_subscribe_form=True,
                has_consent_checkbox=True,
                consent_text="Согласен на обработку персональных данных",
                context_text="Подпишитесь на новости и акции",
                selector="#subscribe",
            )
        ],
    )

    res = await AdConsentCheck().run(ctx)

    assert res.status is CheckStatus.FAIL
    assert res.severity is Severity.IMPORTANT
    assert "ч. 1 ст. 18 38-ФЗ" in res.message
    assert "ПДн" in res.message
    assert any(e.selector == "#subscribe" for e in res.evidence)


async def test_c15_subscription_with_separate_marketing_checkbox_is_pass():
    ctx = make_context(
        has_subscribe_form=True,
        forms=[
            form(
                is_subscribe_form=True,
                has_consent_checkbox=True,
                has_marketing_checkbox=True,
                consent_text="Согласен получать рекламные сообщения",
                context_text="Подпишитесь на новости и акции",
                selector="#subscribe",
            )
        ],
    )

    res = await AdConsentCheck().run(ctx)

    assert res.status is CheckStatus.PASS
    assert any(
        e.label == "Отдельный чекбокс рекламной рассылки" for e in res.evidence
    )


async def test_c15_marketing_context_and_email_field_is_applicable_without_flag():
    ctx = make_context(
        has_subscribe_form=False,
        forms=[
            form(
                is_subscribe_form=False,
                context_text="Подписка на новости и акции",
                fields=[field("email", name="email")],
                selector="form.newsletter",
            )
        ],
    )

    res = await AdConsentCheck().run(ctx)

    assert res.status is CheckStatus.FAIL
    assert "form.newsletter" in res.message


# ---------------------------------------------------------------------------
# D16 — robots.txt и sitemap.xml
# ---------------------------------------------------------------------------


async def test_d16_robots_and_sitemap_present_is_pass():
    ctx = make_context(
        internal_links=10,
        robots=robots(found=True, content="User-agent: *\nAllow: /"),
        sitemap=sitemap(found=True, url_count=42),
    )

    res = await RobotsSitemapCheck().run(ctx)

    assert res.status is CheckStatus.PASS
    assert "robots.txt доступен" in res.message
    assert "sitemap.xml доступен" in res.message
    assert any(e.value == "/robots.txt" for e in res.evidence)


async def test_d16_nothing_found_is_warn():
    ctx = make_context(
        internal_links=10,
        robots=robots(found=False),
        sitemap=sitemap(found=False),
    )

    res = await RobotsSitemapCheck().run(ctx)

    assert res.status is CheckStatus.WARN
    assert res.severity is Severity.RECOMMENDATION
    assert "robots.txt не найден" in res.message
    assert "sitemap.xml не найден" in res.message


async def test_d16_few_internal_links_sitemap_not_evaluated():
    ctx = make_context(
        internal_links=3,
        robots=robots(found=True),
        sitemap=sitemap(found=True, url_count=3),
    )

    res = await RobotsSitemapCheck().run(ctx)

    assert res.status is CheckStatus.PASS
    assert (
        "sitemap.xml не оценивался: на сайте 5 и менее внутренних ссылок "
        "(лендинг)" in res.message
    )


async def test_d16_robots_present_but_sitemap_missing_is_warn():
    ctx = make_context(
        internal_links=10,
        robots=robots(found=True),
        sitemap=sitemap(found=False),
    )

    res = await RobotsSitemapCheck().run(ctx)

    assert res.status is CheckStatus.WARN
    assert "robots.txt доступен" in res.message
    assert "sitemap.xml не найден" in res.message


async def test_d16_disallow_all_is_mentioned():
    ctx = make_context(
        internal_links=10,
        robots=robots(found=True, disallow_all=True, content="User-agent: *\nDisallow: /"),
        sitemap=sitemap(found=True),
    )

    res = await RobotsSitemapCheck().run(ctx)

    assert res.status is CheckStatus.PASS
    assert "Disallow: /" in res.message


async def test_d16_robots_error_is_mentioned():
    ctx = make_context(
        internal_links=10,
        robots=RobotsInfo(found=False, error="Timeout"),
        sitemap=sitemap(found=True),
    )

    res = await RobotsSitemapCheck().run(ctx)

    assert res.status is CheckStatus.WARN
    assert "Timeout" in res.message


# ---------------------------------------------------------------------------
# D17 — заголовки безопасности
# ---------------------------------------------------------------------------


async def test_d17_all_headers_is_pass():
    ctx = make_context(
        security_headers={
            "x-frame-options": "SAMEORIGIN",
            "content-security-policy": "default-src 'self'; frame-ancestors 'self'",
            "x-content-type-options": "nosniff",
            "referrer-policy": "strict-origin-when-cross-origin",
        }
    )

    res = await SecurityHeadersCheck().run(ctx)

    assert res.status is CheckStatus.PASS
    assert len([e for e in res.evidence if e.kind == "header"]) >= 4


async def test_d17_no_headers_is_important_warn():
    ctx = make_context(security_headers={})

    res = await SecurityHeadersCheck().run(ctx)

    assert res.status is CheckStatus.WARN
    assert res.severity is Severity.IMPORTANT
    assert "кликджекинга" in res.message
    assert "MIME-sniffing" in res.message


async def test_d17_csp_frame_ancestors_replaces_x_frame_options():
    ctx = make_context(
        security_headers={
            "content-security-policy": "frame-ancestors 'self'",
            "x-content-type-options": "nosniff",
            "referrer-policy": "no-referrer",
        }
    )

    res = await SecurityHeadersCheck().run(ctx)

    assert res.status is CheckStatus.PASS


async def test_d17_partial_headers_is_warn_with_missing_list():
    ctx = make_context(security_headers={"x-frame-options": "DENY"})

    res = await SecurityHeadersCheck().run(ctx)

    assert res.status is CheckStatus.WARN
    assert res.severity is Severity.RECOMMENDATION
    assert "X-Content-Type-Options: nosniff" in res.message
    assert "Referrer-Policy" in res.message
