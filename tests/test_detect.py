"""Тесты детекторов: URL, регулярки, контрольные суммы, трекеры, ERID."""

from __future__ import annotations

import pytest

from app.core import detect


# ---------------------------------------------------------------------------
# URL
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("example.com", "https://example.com"),
        ("https://example.com/path", "https://example.com/path"),
        ("http://example.com", "http://example.com"),
        ("  example.com/spaces  ", "https://example.com/spaces"),
        ("sub.example.co.uk/a?b=1", "https://sub.example.co.uk/a?b=1"),
    ],
)
def test_normalize_url_ok(raw: str, expected: str) -> None:
    result = detect.normalize_url(raw)
    assert result.ok
    assert result.url == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "ftp://example.com", "какой-то текст", "http://", "http://exa mple.com"],
)
def test_normalize_url_rejects(raw: str) -> None:
    result = detect.normalize_url(raw)
    assert not result.ok
    assert result.error


def test_normalize_url_allows_localhost() -> None:
    result = detect.normalize_url("localhost")
    assert result.ok and result.url == "https://localhost"


def test_domain_and_registrable() -> None:
    assert detect.domain_of("https://www.Example.com/path") == "example.com"
    assert detect.domain_of("https://shop.example.com:8443/") == "shop.example.com"
    assert detect.registrable_domain("shop.example.com") == "example.com"
    assert detect.registrable_domain("www.example.msk.ru") == "example.msk.ru"
    assert detect.registrable_domain("example.com") == "example.com"


def test_links_internal_external() -> None:
    assert detect.is_internal_link("/about", "example.com")
    assert detect.is_internal_link("https://shop.example.com/cart", "example.com")
    assert not detect.is_internal_link("https://other.ru/", "example.com")
    assert not detect.is_internal_link("#anchor", "example.com")
    assert not detect.is_internal_link("mailto:a@b.ru", "example.com")
    assert detect.absolute_link("/privacy/", "https://example.com/shop/") == (
        "https://example.com/privacy/"
    )


# ---------------------------------------------------------------------------
# 152-ФЗ: маркеры и политика
# ---------------------------------------------------------------------------


def test_consent_text_detection() -> None:
    assert detect.is_consent_text("Согласен на обработку персональных данных")
    assert detect.is_consent_text("I agree to the privacy policy")
    assert not detect.is_consent_text("Согласен с условиями оферты")
    assert not detect.is_consent_text("Подписаться на рассылку")


def test_marketing_text_detection() -> None:
    assert detect.is_marketing_text("Согласен получать рекламные рассылки и новости")
    assert detect.is_marketing_text("Хочу получать новости и акции")
    assert not detect.is_marketing_text("Согласен на обработку персональных данных")


def test_privacy_markers() -> None:
    text = (
        "оператор персональных данных, цели обработки, срок хранения, "
        "права субъекта, отзыв согласия, cookie"
    )
    found = detect.privacy_markers_found(text)
    assert len(found) == 7
    assert detect.privacy_markers_found("просто текст") == []


def test_find_privacy_link_prefers_specific() -> None:
    from app.core.models import LinkInfo

    links = [
        LinkInfo(href="https://x.ru/about", text="О компании"),
        LinkInfo(href="https://x.ru/privacy/", text="Политика конфиденциальности"),
        LinkInfo(href="https://x.ru/politika/", text="Политика"),
    ]
    best = detect.find_privacy_link(links)
    assert best is not None and best.href.endswith("/privacy/")
    assert detect.find_privacy_link([LinkInfo(href="/x", text="О нас")]) is None


# ---------------------------------------------------------------------------
# Реквизиты и контакты
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "ogrn", "ogrnip", "inn"),
    [
        ("1000000000010", True, False, False),  # ОГРН Сбербанка
        ("100000000000011", False, True, False),  # ОГРНИП
        ("0000000018", False, False, True),  # ИНН 10
        ("000000000184", False, False, True),  # ИНН 12
        ("1027700132196", False, False, False),  # битая контрольная сумма
        ("12345", False, False, False),
    ],
)
def test_requisite_validators(value: str, ogrn: bool, ogrnip: bool, inn: bool) -> None:
    assert detect.valid_ogrn(value) is ogrn
    assert detect.valid_ogrnip(value) is ogrnip
    assert detect.valid_inn(value) is inn


def test_extract_requisites() -> None:
    text = (
        "ООО «Ромашка», ОГРН 1000000000010, ИНН 0000000018, "
        "юридический адрес: г. Москва, ул. Тверская, 1, тел. +7 495 123-45-67"
    )
    req = detect.extract_requisites(text, "<a href='mailto:info@romashka.ru'>")
    assert req.ogrn == ["1000000000010"]
    assert req.inn == ["0000000018"]
    assert req.has_address
    assert req.has_legal_name
    assert req.has_email
    assert req.has_phone
    assert req.entity_kind == "ЮЛ"
    assert "ОГРН 1000000000010" in req.summary


def test_extract_requisites_empty() -> None:
    req = detect.extract_requisites("Просто текст без реквизитов")
    assert not req.has_reg_number
    assert req.entity_kind == "unknown"


def test_contact_extraction_filters_placeholders() -> None:
    html = (
        '<a href="mailto:info@shop.ru">info@shop.ru</a>'
        '<a href="mailto:you@domain.com">you@domain.com</a>'
        '<a href="mailto:user@example.com">user@example.com</a>'
    )
    emails = detect.extract_emails(html)
    assert emails == ["info@shop.ru"]
    assert detect.extract_phones("Звоните: +7 (000) 123-45-67") == ["+7 (000) 123-45-67"]


def test_extract_prices() -> None:
    assert detect.extract_prices("Цена 59 990 ₽") == ["59 990 ₽"]
    assert detect.extract_prices("всего 1 200 руб.") == ["1 200 руб."]
    assert detect.extract_prices("без цен") == []


# ---------------------------------------------------------------------------
# Реклама / ERID
# ---------------------------------------------------------------------------


def test_extract_erid_tokens() -> None:
    html = 'Реклама <a href="https://partner.ru/x?erid=2VtzqwXyZabc123">ссылка</a>'
    tokens = detect.extract_erid_tokens(html)
    assert "2VtzqwXyZabc123" in tokens
    assert detect.has_erid(html)
    assert not detect.has_erid("обычная страница без меток")


# ---------------------------------------------------------------------------
# Трекеры
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "domains", "foreign"),
    [
        ("https://www.googletagmanager.com/gtm.js", ("googletagmanager.com",), True),
        ("https://mc.yandex.ru/metrika/tag.js", ("mc.yandex.ru",), False),
        ("https://connect.facebook.net/en_US/fbevents.js", ("facebook.net", "connect.facebook.net"), True),
        ("https://example.com/app.js", (), None),
    ],
)
def test_tracker_for_url(url: str, domains: tuple[str, ...], foreign: bool | None) -> None:
    info = detect.tracker_for_url(url)
    if not domains:
        assert info is None
    else:
        assert info is not None
        assert info[0] in domains
        assert info[2] is foreign


def test_trackers_in_inline_script() -> None:
    found = detect.trackers_in_inline_script("var x='https://www.google-analytics.com/analytics.js'")
    assert any(item[0] == "google-analytics.com" for item in found)


# ---------------------------------------------------------------------------
# Заголовки безопасности и ошибки
# ---------------------------------------------------------------------------


def test_header_lookup_case_insensitive() -> None:
    headers = {"X-Frame-Options": "SAMEORIGIN", "content-type": "text/html"}
    assert detect.header_value(headers, "x-frame-options") == "SAMEORIGIN"
    assert detect.header_value(headers, "Referrer-Policy") is None
    assert detect.csp_has_frame_ancestors("default-src 'self'; frame-ancestors 'none'")
    assert not detect.csp_has_frame_ancestors("default-src 'self'")


def test_friendly_http_error() -> None:
    import httpx

    message = detect.friendly_http_error(httpx.ConnectTimeout("timeout"))
    assert "время" in message.lower()
    message = detect.friendly_http_error(httpx.ConnectError("getaddrinfo failed"))
    assert "домен" in message.lower() or "найти" in message.lower()
    assert detect.human_size(2048) == "2.0 КБ"
