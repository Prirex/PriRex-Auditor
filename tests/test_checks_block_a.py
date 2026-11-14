"""Юнит-тесты проверок блока A (152-ФЗ)."""

from __future__ import annotations

import pytest

from app.core.checks.a01_https import HttpsCheck
from app.core.checks.a02_privacy_link import PrivacyLinkCheck
from app.core.checks.a03_privacy_access import PrivacyAccessCheck
from app.core.checks.a04_privacy_content import PrivacyContentCheck
from app.core.checks.a05_forms_consent import FormsConsentCheck
from app.core.checks.a06_consent_prechecked import ConsentPrecheckedCheck
from app.core.checks.a07_separate_consent import SeparateConsentCheck
from app.core.checks.a08_cookie_banner import CookieBannerCheck
from app.core.checks.a09_cookie_categories import CookieCategoriesCheck
from app.core.checks.a10_foreign_trackers import ForeignTrackersCheck
from app.core.checks.a11_pdn_contact import PdnContactCheck
from app.core.checks.a12_rkn_notice import RknNoticeCheck
from app.core.models import Category, CheckStatus, Severity
from tests.helpers import cookie_banner, field, form, https, link, page, tracker

# ---------------------------------------------------------------------------
# Метаданные: id/title/weight/severity — контракт с UI и отчётами
# ---------------------------------------------------------------------------

CHECK_CLASSES = [
    (HttpsCheck, "a01_https", "HTTPS и TLS", 10, Severity.CRITICAL),
    (
        PrivacyLinkCheck,
        "a02_privacy_link",
        "Политика конфиденциальности — наличие",
        9,
        Severity.CRITICAL,
    ),
    (
        PrivacyAccessCheck,
        "a03_privacy_access",
        "Политика — доступность без регистрации",
        5,
        Severity.IMPORTANT,
    ),
    (PrivacyContentCheck, "a04_privacy_content", "Политика — содержание", 7, Severity.IMPORTANT),
    (
        FormsConsentCheck,
        "a05_forms_consent",
        "Формы сбора данных и чекбокс согласия",
        8,
        Severity.CRITICAL,
    ),
    (
        ConsentPrecheckedCheck,
        "a06_consent_prechecked",
        "Чекбокс не предзаполнен",
        4,
        Severity.IMPORTANT,
    ),
    (
        SeparateConsentCheck,
        "a07_separate_consent",
        "Отдельное согласие (не вшито в договор)",
        4,
        Severity.IMPORTANT,
    ),
    (CookieBannerCheck, "a08_cookie_banner", "Cookie-баннер", 5, Severity.IMPORTANT),
    (
        CookieCategoriesCheck,
        "a09_cookie_categories",
        "Категории cookie и кнопка отказа",
        3,
        Severity.IMPORTANT,
    ),
    (
        ForeignTrackersCheck,
        "a10_foreign_trackers",
        "Зарубежные трекеры (риск локализации)",
        3,
        Severity.IMPORTANT,
    ),
    (
        PdnContactCheck,
        "a11_pdn_contact",
        "Контакт для обращений субъектов ПДн",
        5,
        Severity.IMPORTANT,
    ),
    (
        RknNoticeCheck,
        "a12_rkn_notice",
        "Признаки уведомления в РКН",
        2,
        Severity.RECOMMENDATION,
    ),
]


@pytest.mark.parametrize("cls,check_id,title,weight,severity", CHECK_CLASSES)
def test_check_metadata(cls, check_id, title, weight, severity):
    assert cls.id == check_id
    assert cls.title == title
    assert cls.category == Category.FZ152.value
    assert cls.weight == weight
    assert cls.severity is severity
    assert cls.recommendation, "рекомендация должна быть заполнена по-русски"


# ---------------------------------------------------------------------------
# A01. HTTPS и TLS
# ---------------------------------------------------------------------------


async def test_a01_https_pass(make_ctx):
    ctx = make_ctx(https=https(redirects_http_to_https=True))
    result = await HttpsCheck().run(ctx)
    assert result.status is CheckStatus.PASS
    assert "HTTPS" in result.message
    assert "TLSv1.3" in result.message
    assert result.evidence


async def test_a01_https_http_only_fail(make_ctx):
    ctx = make_ctx(https=https(used_https=False, https_available=False))
    result = await HttpsCheck().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert result.severity is Severity.CRITICAL
    assert "HTTPS" in result.message
    assert result.recommendation


async def test_a01_https_invalid_cert_fail(make_ctx):
    ctx = make_ctx(https=https(cert_valid=False, redirects_http_to_https=True))
    result = await HttpsCheck().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert "сертификат" in result.message.lower()


async def test_a01_https_old_tls_warn(make_ctx):
    ctx = make_ctx(https=https(tls_version="TLSv1.0", redirects_http_to_https=True))
    result = await HttpsCheck().run(ctx)
    assert result.status is CheckStatus.WARN
    assert result.severity is Severity.IMPORTANT
    assert "TLSv1.0" in result.message


async def test_a01_https_no_redirect_fail(make_ctx):
    ctx = make_ctx(https=https(redirects_http_to_https=False))
    result = await HttpsCheck().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert "перенаправ" in result.message


async def test_a01_https_unreachable_site_skip(make_ctx):
    ctx = make_ctx(
        fetch_failed=True,
        fetch_error="Таймаут",
        https=https(used_https=False, https_available=False),
    )
    result = await HttpsCheck().run(ctx)
    assert result.status is CheckStatus.SKIP
    assert "недоступен" in result.message.lower()


# ---------------------------------------------------------------------------
# A02. Политика конфиденциальности — наличие
# ---------------------------------------------------------------------------


async def test_a02_privacy_link_pass(make_ctx):
    ctx = make_ctx(
        privacy_link=link(
            "/privacy/", "Политика конфиденциальности", in_footer=True
        ),
        pages={"privacy": page(text="оператор обрабатывает персональные данные")},
    )
    result = await PrivacyLinkCheck().run(ctx)
    assert result.status is CheckStatus.PASS
    assert "футере" in result.message.lower()
    assert any(item.kind == "url" for item in result.evidence)


async def test_a02_privacy_link_missing_fail(make_ctx):
    ctx = make_ctx()
    result = await PrivacyLinkCheck().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert result.severity is Severity.CRITICAL
    assert "Не найдена ссылка" in result.message


async def test_a02_privacy_page_not_opened_fail(make_ctx):
    ctx = make_ctx(
        privacy_link=link("/privacy/", "Политика", in_footer=True),
        pages={},
    )
    result = await PrivacyLinkCheck().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert result.severity is Severity.IMPORTANT
    assert "не открывается" in result.message


async def test_a02_privacy_link_not_footer_warn(make_ctx):
    ctx = make_ctx(
        privacy_link=link("/privacy/", "Политика", in_footer=False),
        pages={"privacy": page()},
    )
    result = await PrivacyLinkCheck().run(ctx)
    assert result.status is CheckStatus.WARN
    assert result.severity is Severity.IMPORTANT
    assert "не в футере" in result.message


# ---------------------------------------------------------------------------
# A03. Политика — доступность без регистрации
# ---------------------------------------------------------------------------


async def test_a03_privacy_access_pass(make_ctx):
    ctx = make_ctx(pages={"privacy": page()})
    result = await PrivacyAccessCheck().run(ctx)
    assert result.status is CheckStatus.PASS
    assert "без авторизации" in result.message


async def test_a03_privacy_login_wall_fail(make_ctx):
    privacy = page().model_copy(update={"redirected_to_login": True})
    ctx = make_ctx(pages={"privacy": privacy})
    result = await PrivacyAccessCheck().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert "регистрац" in result.message.lower()


async def test_a03_privacy_cookie_wall_fail(make_ctx):
    privacy = page().model_copy(update={"has_cookie_wall": True})
    ctx = make_ctx(pages={"privacy": privacy})
    result = await PrivacyAccessCheck().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert "cookie" in result.message.lower()


async def test_a03_privacy_page_missing_na(make_ctx):
    ctx = make_ctx()
    result = await PrivacyAccessCheck().run(ctx)
    assert result.status is CheckStatus.NOT_APPLICABLE
    assert "не загружена" in result.message


async def test_a03_privacy_page_error_skip(make_ctx):
    ctx = make_ctx(pages={"privacy": page(ok=False, status_code=404)})
    result = await PrivacyAccessCheck().run(ctx)
    assert result.status is CheckStatus.SKIP
    assert "404" in result.message


# ---------------------------------------------------------------------------
# A04. Политика — содержание
# ---------------------------------------------------------------------------


POLICY_FULL = (
    "Оператор обрабатывает персональные данные пользователей. "
    "Цели обработки: оформление заказа. Срок хранения данных — до отзыва. "
    "Права субъекта персональных данных описаны ниже. "
    "Отзыв согласия возможен по email. Сайт использует cookie."
)

POLICY_PARTIAL = (
    "Оператор обрабатывает персональные данные. "
    "Цели обработки: заказы. Срок хранения — 1 год."
)


async def test_a04_privacy_content_pass(make_ctx):
    ctx = make_ctx(pages={"privacy": page(text=POLICY_FULL)})
    result = await PrivacyContentCheck().run(ctx)
    assert result.status is CheckStatus.PASS
    assert "из 7" in result.message


async def test_a04_privacy_content_partial_warn(make_ctx):
    ctx = make_ctx(pages={"privacy": page(text=POLICY_PARTIAL)})
    result = await PrivacyContentCheck().run(ctx)
    assert result.status is CheckStatus.WARN
    assert result.severity is Severity.IMPORTANT
    assert "только 4" in result.message


async def test_a04_privacy_content_poor_fail(make_ctx):
    ctx = make_ctx(
        pages={"privacy": page(text="Оператор обрабатывает персональные данные.")}
    )
    result = await PrivacyContentCheck().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert result.severity is Severity.IMPORTANT


async def test_a04_privacy_content_no_text_skip(make_ctx):
    ctx = make_ctx(pages={"privacy": page(text="")})
    result = await PrivacyContentCheck().run(ctx)
    assert result.status is CheckStatus.SKIP
    assert "Текст политики пуст" in result.message


# ---------------------------------------------------------------------------
# A05. Формы сбора данных и чекбокс согласия
# ---------------------------------------------------------------------------


async def test_a05_forms_without_consent_fail(make_ctx):
    ctx = make_ctx(
        forms=[
            form(
                fields=[field("email", name="email")],
                has_consent_checkbox=False,
                selector="form#subscribe",
            )
        ]
    )
    result = await FormsConsentCheck().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert result.severity is Severity.CRITICAL
    assert "form#subscribe" in result.message
    assert "email" in result.message


async def test_a05_forms_with_consent_pass(make_ctx):
    ctx = make_ctx(forms=[form(has_consent_checkbox=True)])
    result = await FormsConsentCheck().run(ctx)
    assert result.status is CheckStatus.PASS
    assert result.evidence


async def test_a05_no_pd_forms_na(make_ctx):
    ctx = make_ctx(forms=[])
    result = await FormsConsentCheck().run(ctx)
    assert result.status is CheckStatus.NOT_APPLICABLE
    assert "не обнаружены формы" in result.message


async def test_a05_search_form_is_not_pd_na(make_ctx):
    ctx = make_ctx(forms=[form(fields=[field("text", name="search")])])
    result = await FormsConsentCheck().run(ctx)
    assert result.status is CheckStatus.NOT_APPLICABLE


async def test_a05_standalone_fields_without_consent_fail(make_ctx):
    standalone = form(
        fields=[field("tel", name="phone")],
        has_consent_checkbox=False,
        selector="input[name=phone]",
    ).model_copy(update={"is_standalone_fields": True})
    ctx = make_ctx(forms=[standalone])
    result = await FormsConsentCheck().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert "вне <form>" in result.message


# ---------------------------------------------------------------------------
# A06. Чекбокс не предзаполнен
# ---------------------------------------------------------------------------


async def test_a06_consent_prechecked_fail(make_ctx):
    ctx = make_ctx(
        forms=[
            form(
                has_consent_checkbox=True,
                consent_checked=True,
                selector="form#order",
            )
        ]
    )
    result = await ConsentPrecheckedCheck().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert "checked" in result.message
    assert "form#order" in result.message


async def test_a06_consent_not_prechecked_pass(make_ctx):
    ctx = make_ctx(forms=[form(has_consent_checkbox=True, consent_checked=False)])
    result = await ConsentPrecheckedCheck().run(ctx)
    assert result.status is CheckStatus.PASS


async def test_a06_no_consent_checkbox_na(make_ctx):
    ctx = make_ctx(forms=[form(has_consent_checkbox=False)])
    result = await ConsentPrecheckedCheck().run(ctx)
    assert result.status is CheckStatus.NOT_APPLICABLE
    assert "чекбоксы согласия" in result.message


# ---------------------------------------------------------------------------
# A07. Отдельное согласие
# ---------------------------------------------------------------------------


async def test_a07_offer_combined_warn(make_ctx):
    ctx = make_ctx(
        forms=[
            form(
                has_consent_checkbox=True,
                consent_text=(
                    "Согласен с условиями оферты и обработкой персональных данных"
                ),
                selector="form#order",
            )
        ]
    )
    result = await SeparateConsentCheck().run(ctx)
    assert result.status is CheckStatus.WARN
    assert result.severity is Severity.IMPORTANT
    assert "оферт" in result.message.lower()


async def test_a07_separate_consent_pass(make_ctx):
    ctx = make_ctx(
        forms=[
            form(
                has_consent_checkbox=True,
                consent_text="Согласен на обработку персональных данных",
            )
        ]
    )
    result = await SeparateConsentCheck().run(ctx)
    assert result.status is CheckStatus.PASS


async def test_a07_single_checkbox_for_two_actions_warn(make_ctx):
    ctx = make_ctx(
        forms=[
            form(
                fields=[
                    field("email", name="email"),
                    field("checkbox", name="agree"),
                ],
                has_consent_checkbox=True,
                has_offer_checkbox=True,
                consent_text="Согласен на обработку персональных данных",
                selector="form#checkout",
            )
        ]
    )
    result = await SeparateConsentCheck().run(ctx)
    assert result.status is CheckStatus.WARN
    assert "form#checkout" in result.message


async def test_a07_no_consent_checkbox_na(make_ctx):
    ctx = make_ctx(forms=[form(has_consent_checkbox=False)])
    result = await SeparateConsentCheck().run(ctx)
    assert result.status is CheckStatus.NOT_APPLICABLE
    assert "чекбоксы согласия" in result.message


# ---------------------------------------------------------------------------
# A08. Cookie-баннер
# ---------------------------------------------------------------------------


async def test_a08_cookie_banner_found_pass(make_ctx):
    ctx = make_ctx(
        trackers=[tracker()],
        cookie_banner=cookie_banner(
            found=True, source="playwright", text="Мы используем cookie"
        ),
    )
    result = await CookieBannerCheck().run(ctx)
    assert result.status is CheckStatus.PASS
    assert "playwright" in result.message
    assert "cookie" in result.message.lower()


async def test_a08_cookie_banner_missing_fail(make_ctx):
    ctx = make_ctx(trackers=[tracker()], deep_analysis=True)
    result = await CookieBannerCheck().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert result.severity is Severity.IMPORTANT
    assert "google-analytics.com" in result.message


async def test_a08_no_deep_analysis_skip(make_ctx):
    ctx = make_ctx(trackers=[tracker()], deep_analysis=False)
    result = await CookieBannerCheck().run(ctx)
    assert result.status is CheckStatus.SKIP
    assert "Глубокий анализ" in result.message


async def test_a08_no_trackers_na(make_ctx):
    ctx = make_ctx(trackers=[], deep_analysis=True)
    result = await CookieBannerCheck().run(ctx)
    assert result.status is CheckStatus.NOT_APPLICABLE
    assert "не обязателен" in result.message


# ---------------------------------------------------------------------------
# A09. Категории cookie и кнопка отказа
# ---------------------------------------------------------------------------


async def test_a09_reject_button_pass(make_ctx):
    ctx = make_ctx(
        cookie_banner=cookie_banner(has_accept=True, has_reject=True)
    )
    result = await CookieCategoriesCheck().run(ctx)
    assert result.status is CheckStatus.PASS
    assert "отказа" in result.message.lower()


async def test_a09_settings_pass(make_ctx):
    ctx = make_ctx(
        cookie_banner=cookie_banner(
            has_accept=False, has_reject=False, has_settings=True
        )
    )
    result = await CookieCategoriesCheck().run(ctx)
    assert result.status is CheckStatus.PASS
    assert "настройки" in result.message.lower()


async def test_a09_only_accept_fail(make_ctx):
    ctx = make_ctx(
        cookie_banner=cookie_banner(
            has_accept=True, has_reject=False, has_settings=False
        )
    )
    result = await CookieCategoriesCheck().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert result.severity is Severity.IMPORTANT
    assert "только кнопка" in result.message


async def test_a09_nothing_recognized_warn(make_ctx):
    ctx = make_ctx(
        cookie_banner=cookie_banner(
            has_accept=False, has_reject=False, has_settings=False
        )
    )
    result = await CookieCategoriesCheck().run(ctx)
    assert result.status is CheckStatus.WARN


async def test_a09_no_banner_na(make_ctx):
    ctx = make_ctx()
    result = await CookieCategoriesCheck().run(ctx)
    assert result.status is CheckStatus.NOT_APPLICABLE
    assert "не обнаружен" in result.message


# ---------------------------------------------------------------------------
# A10. Зарубежные трекеры
# ---------------------------------------------------------------------------


async def test_a10_foreign_tracker_warn(make_ctx):
    ctx = make_ctx(trackers=[tracker("www.google-analytics.com")])
    result = await ForeignTrackersCheck().run(ctx)
    assert result.status is CheckStatus.WARN
    assert result.severity is Severity.IMPORTANT
    assert "google-analytics.com" in result.message
    assert "ст. 18" in result.message


async def test_a10_russian_only_trackers_pass(make_ctx):
    ctx = make_ctx(
        trackers=[tracker("mc.yandex.ru", kind="analytics", foreign=False)]
    )
    result = await ForeignTrackersCheck().run(ctx)
    assert result.status is CheckStatus.PASS
    assert "российские" in result.message


async def test_a10_no_trackers_na(make_ctx):
    ctx = make_ctx(trackers=[])
    result = await ForeignTrackersCheck().run(ctx)
    assert result.status is CheckStatus.NOT_APPLICABLE
    assert "не обнаружены" in result.message


# ---------------------------------------------------------------------------
# A11. Контакт для обращений субъектов ПДн
# ---------------------------------------------------------------------------


async def test_a11_email_pass(make_ctx):
    ctx = make_ctx(emails=["privacy@example.com"])
    result = await PdnContactCheck().run(ctx)
    assert result.status is CheckStatus.PASS
    assert "email" in result.message.lower()


async def test_a11_mailto_link_pass(make_ctx):
    ctx = make_ctx(
        links=[link("mailto:privacy@example.com", "Написать нам", in_footer=True)]
    )
    result = await PdnContactCheck().run(ctx)
    assert result.status is CheckStatus.PASS
    assert "mailto" in result.message


async def test_a11_contacts_page_pass(make_ctx):
    ctx = make_ctx(
        pages={
            "contacts": page(
                key="contacts", url="https://example.com/contacts/"
            )
        }
    )
    result = await PdnContactCheck().run(ctx)
    assert result.status is CheckStatus.PASS
    assert "Контакты" in result.message


async def test_a11_feedback_form_pass(make_ctx):
    ctx = make_ctx(
        forms=[
            form(
                fields=[
                    field("email", name="email"),
                    field("text", tag="textarea", name="message"),
                ],
                context_text="форма обратной связи",
                selector="form#feedback",
            )
        ]
    )
    result = await PdnContactCheck().run(ctx)
    assert result.status is CheckStatus.PASS
    assert "обратной связи" in result.message


async def test_a11_no_contacts_fail(make_ctx):
    ctx = make_ctx()
    result = await PdnContactCheck().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert result.severity is Severity.IMPORTANT
    assert "не найден" in result.message


# ---------------------------------------------------------------------------
# A12. Признаки уведомления в РКН
# ---------------------------------------------------------------------------


async def test_a12_rkn_marker_pass(make_ctx):
    ctx = make_ctx(text="мы внесены в реестр операторов персональных данных")
    result = await RknNoticeCheck().run(ctx)
    assert result.status is CheckStatus.PASS
    assert "реестр операторов" in result.message


async def test_a12_no_markers_warn(make_ctx):
    ctx = make_ctx(text="обычный текст без упоминаний регулятора")
    result = await RknNoticeCheck().run(ctx)
    assert result.status is CheckStatus.WARN
    assert result.severity is Severity.RECOMMENDATION
    assert result.status is not CheckStatus.FAIL
    assert "подсказка" in result.message


# ---------------------------------------------------------------------------
# Применимость: сайт без форм и трекеров не должен получать fail по NA-проверкам
# ---------------------------------------------------------------------------


async def test_site_without_forms_and_trackers_no_fail_for_na_checks(make_ctx):
    ctx = make_ctx()
    checks = [
        PrivacyAccessCheck(),
        FormsConsentCheck(),
        ConsentPrecheckedCheck(),
        SeparateConsentCheck(),
        CookieBannerCheck(),
        CookieCategoriesCheck(),
        ForeignTrackersCheck(),
    ]
    results = [await check.run(ctx) for check in checks]
    assert [result.status for result in results] == [
        CheckStatus.NOT_APPLICABLE for _ in checks
    ]
    assert all(result.message for result in results)
