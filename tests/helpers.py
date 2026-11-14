"""Конструкторы объектов контекста для юнит-тестов проверок.

Проверки тестируются на синтетическом ``SiteContext`` — без сети и без
Playwright. Хелперы ниже дают короткие вызовы вместо длинных конструкторов.
"""

from __future__ import annotations

from app.core.models import (
    AdBlockInfo,
    CookieBannerInfo,
    FormFieldInfo,
    FormInfo,
    HttpsInfo,
    LinkInfo,
    PageInfo,
    RobotsInfo,
    SitemapInfo,
    SiteContext,
    TrackerInfo,
)


def make_context(url: str = "https://example.com/", **overrides: object) -> SiteContext:
    """Пустой контекст с заполненным адресом; всё остальное — через overrides."""
    base = SiteContext(
        target_url=url,
        url=url,
        domain="example.com",
        status_code=200,
        html="<html><body><h1>Тест</h1></body></html>",
        text="тест",
        footer_text="",
    )
    if overrides:
        base = base.model_copy(update=overrides)
    return base


def link(
    href: str,
    text: str = "",
    *,
    in_footer: bool = False,
    in_header: bool = False,
    is_internal: bool = True,
    selector: str = "footer a",
    aria_label: str = "",
) -> LinkInfo:
    return LinkInfo(
        href=href,
        text=text,
        aria_label=aria_label,
        is_internal=is_internal,
        in_footer=in_footer,
        in_header=in_header,
        selector=selector,
    )


def field(
    type: str = "text",
    *,
    name: str | None = None,
    placeholder: str | None = None,
    label_text: str = "",
    tag: str = "input",
    selector: str = "input",
) -> FormFieldInfo:
    return FormFieldInfo(
        tag=tag,
        type=type,
        name=name,
        placeholder=placeholder,
        label_text=label_text,
        selector=selector,
    )


def form(
    *,
    fields: list[FormFieldInfo] | None = None,
    action: str | None = None,
    method: str = "post",
    context_text: str = "",
    has_consent_checkbox: bool = False,
    consent_checked: bool = False,
    consent_text: str | None = None,
    has_offer_checkbox: bool = False,
    has_marketing_checkbox: bool = False,
    is_order_form: bool = False,
    is_subscribe_form: bool = False,
    selector: str = "form",
) -> FormInfo:
    return FormInfo(
        selector=selector,
        action=action,
        method=method,
        fields=fields
        if fields is not None
        else [field("email", name="email", placeholder="E-mail")],
        context_text=context_text,
        has_consent_checkbox=has_consent_checkbox,
        consent_checked=consent_checked,
        consent_text=consent_text,
        has_offer_checkbox=has_offer_checkbox,
        has_marketing_checkbox=has_marketing_checkbox,
        is_order_form=is_order_form,
        is_subscribe_form=is_subscribe_form,
    )


def tracker(
    domain: str = "www.google-analytics.com",
    *,
    kind: str = "analytics",
    foreign: bool = True,
    found_in: str = "script",
) -> TrackerInfo:
    return TrackerInfo(domain=domain, kind=kind, foreign=foreign, found_in=found_in, url=f"https://{domain}/x.js")


def page(
    key: str = "privacy",
    url: str = "https://example.com/privacy/",
    text: str = "",
    *,
    ok: bool = True,
    status_code: int = 200,
    title: str = "Политика конфиденциальности",
) -> PageInfo:
    return PageInfo(
        key=key,
        url=url,
        status_code=status_code,
        ok=ok,
        title=title,
        text=text,
    )


def ad_block(
    text: str = "реклама",
    *,
    has_ad_label: bool = True,
    erid_tokens: list[str] | None = None,
    selector: str = "div.ad",
) -> AdBlockInfo:
    tokens = erid_tokens or []
    return AdBlockInfo(
        selector=selector,
        text=text,
        has_ad_label=has_ad_label,
        has_erid=bool(tokens),
        erid_tokens=tokens,
    )


def cookie_banner(
    *,
    found: bool = True,
    text: str = "Мы используем cookie",
    has_accept: bool = True,
    has_reject: bool = False,
    has_settings: bool = False,
    source: str = "playwright",
) -> CookieBannerInfo:
    return CookieBannerInfo(
        found=found,
        text=text,
        selector="#cookie-banner",
        has_accept=has_accept,
        has_reject=has_reject,
        has_settings=has_settings,
        source=source,
    )


def https(
    *,
    used_https: bool = True,
    https_available: bool = True,
    cert_valid: bool = True,
    tls_version: str | None = "TLSv1.3",
    redirects_http_to_https: bool = False,
    http_redirect_checked: bool = True,
) -> HttpsInfo:
    return HttpsInfo(
        requested_url="https://example.com/",
        final_url="https://example.com/",
        used_https=used_https,
        https_available=https_available,
        cert_valid=cert_valid,
        tls_version=tls_version,
        redirects_http_to_https=redirects_http_to_https,
        http_redirect_checked=http_redirect_checked,
    )


def robots(*, found: bool = True, disallow_all: bool = False, content: str = "") -> RobotsInfo:
    return RobotsInfo(found=found, status_code=200 if found else 404, content=content, disallow_all=disallow_all)


def sitemap(*, found: bool = True, url_count: int = 0, is_index: bool = False) -> SitemapInfo:
    return SitemapInfo(
        found=found,
        status_code=200 if found else 404,
        url_count=url_count,
        is_index=is_index,
        url="https://example.com/sitemap.xml",
    )
