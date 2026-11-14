"""Детерминированные детекторы: регулярки, словари и эвристики.

Модуль сознательно не знает ничего о сети и Qt. Всё здесь — чистые функции
над текстом/HTML, поэтому их легко покрывать тестами и переиспользовать
и в сборщике контекста, и в самих проверках.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Текст
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")
_INVISIBLE_TAGS = ("script", "style", "noscript", "template", "svg")


def normalize_text(value: str, limit: int | None = None) -> str:
    """Схлопывает пробелы и приводит к нижнему регистру."""
    text = _WS_RE.sub(" ", (value or "")).strip().lower()
    if limit is not None:
        return text[:limit]
    return text


def collapse_text(value: str, limit: int | None = None) -> str:
    """Схлопывает пробелы, сохраняя регистр (для заголовков и подписей)."""
    text = _WS_RE.sub(" ", (value or "")).strip()
    if limit is not None:
        return text[:limit]
    return text


def has_any(text: str, markers: tuple[str, ...] | list[str]) -> list[str]:
    """Возвращает список найденных маркеров (подстроки в нижнем регистре)."""
    low = (text or "").lower()
    return [m for m in markers if m in low]


def first_marker(text: str, markers: tuple[str, ...] | list[str]) -> str | None:
    found = has_any(text, markers)
    return found[0] if found else None


# ---------------------------------------------------------------------------
# URL
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"^(https?)://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
_DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}(?::\d{1,5})?$")


def _is_ip_host(host: str) -> bool:
    """IPv4/IPv6-адрес в netloc (в т.ч. с портом и в скобках)."""
    import ipaddress

    value = (host or "").strip().lower()
    if value.startswith("["):
        end = value.find("]")
        value = value[1:end] if end > 0 else value[1:]
    elif value.count(":") == 1:
        value = value.split(":", 1)[0]
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


@dataclass
class NormalizedUrl:
    url: str = ""
    error: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.url) and self.error is None


def normalize_url(raw: str) -> NormalizedUrl:
    """Приводит пользовательский ввод к абсолютному http(s)-URL.

    ``example.com`` -> ``https://example.com``; мусор -> понятная ошибка.
    """
    value = (raw or "").strip().strip('"').strip("'")
    if not value:
        return NormalizedUrl(error="Введите адрес сайта")
    if " " in value or "\n" in value or "\t" in value:
        return NormalizedUrl(error="Адрес не должен содержать пробелов")
    if "://" not in value:
        value = "https://" + value.lstrip("/")
    scheme = value.split("://", 1)[0].lower()
    if scheme not in {"http", "https"}:
        return NormalizedUrl(error="Поддерживаются только адреса http:// и https://")
    parsed = urlparse(value)
    host = parsed.netloc
    if not host or "." not in host and host not in {"localhost"}:
        return NormalizedUrl(error="Похоже, адрес указан неверно")
    host_low = host.lower()
    if (
        host_low != "localhost"
        and not _DOMAIN_RE.match(host_low)
        and not _is_ip_host(host_low)
    ):
        return NormalizedUrl(error="Некорректное доменное имя")
    if not _URL_RE.match(value):
        return NormalizedUrl(error="Некорректный адрес сайта")
    return NormalizedUrl(url=value)


def domain_of(url: str) -> str:
    """Хост без www, в нижнем регистре."""
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    host = host.split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def registrable_domain(host: str) -> str:
    """Грубое определение регистрируемого домена (без publicsuffix)."""
    host = (host or "").lower().split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    # двухуровневые зоны вроде example.msk.ru / example.co.uk
    two_level = {
        "msk.ru", "spb.ru", "com.ru", "net.ru", "org.ru", "co.uk", "org.uk",
        "com.ua", "co.kz", "com.by", "co.il", "com.tr",
    }
    tail2 = ".".join(parts[-2:])
    if tail2 in two_level and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def is_internal_link(href: str, site_domain: str) -> bool:
    """Внутренняя ли ссылка относительно домена сайта."""
    if not href:
        return False
    if href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return False
    parsed = urlparse(href)
    if not parsed.netloc:
        return True
    return registrable_domain(parsed.netloc) == registrable_domain(site_domain)


def absolute_link(href: str, base_url: str) -> str:
    if not href:
        return ""
    if href.startswith(("mailto:", "tel:", "javascript:", "data:")):
        return href
    try:
        return urljoin(base_url, href)
    except ValueError:
        return href


def is_same_page(url: str, base_url: str) -> bool:
    a = urlparse(url)
    b = urlparse(base_url)
    return (a.netloc, a.path.rstrip("/")) == (b.netloc, b.path.rstrip("/"))


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------


def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "lxml")


def visible_text(node, limit: int | None = None) -> str:
    """Видимый текст узла без script/style, схлопнутый, в нижнем регистре.

    Всегда работает на копии: исходное дерево BeautifulSoup не изменяется.
    """
    if node is None:
        return ""
    try:
        soup = BeautifulSoup(str(node), "lxml")
        for tag in soup.find_all(_INVISIBLE_TAGS):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
    except Exception:  # pragma: no cover - защита от битого HTML
        text = re.sub(r"<[^>]+>", " ", str(node))
    return normalize_text(text, limit)


def footer_text(soup: BeautifulSoup, limit: int | None = 4000) -> str:
    """Текст футера: <footer> или нижняя часть body."""
    chunks: list[str] = []
    for sel in ("footer", "[class*=footer]", "[id*=footer]", "[class*=подвал]",
                "[id*=podval]", "[class*=bottom]"):
        for tag in soup.select(sel)[:3]:
            t = visible_text(tag)
            if t and t not in chunks:
                chunks.append(t)
    if not chunks and soup.body is not None:
        chunks.append(visible_text(soup.body, 6000)[-1500:])
    return normalize_text(" ".join(chunks), limit)


# ---------------------------------------------------------------------------
# 152-ФЗ: согласия, политика, cookie
# ---------------------------------------------------------------------------

CONSENT_MARKERS: tuple[str, ...] = (
    "соглас", "персональн", "обработк", "политик", "конфиденциальн",
    "privacy", "consent", "personal data", "обработку пдн", "пдн",
)

OFFER_MARKERS: tuple[str, ...] = (
    "оферт", "пользовательск", "услови", "terms", "договор", "правила",
)

MARKETING_MARKERS: tuple[str, ...] = (
    "рекламн", "рассылк", "новост", "акци", "newsletter", "marketing",
    "промо", "promo", "информационн", "спецпредложен",
)

PRIVACY_LINK_MARKERS: tuple[str, ...] = (
    "политика конфиденциальности",
    "политика обработки персональных данных",
    "политика в отношении обработки персональных данных",
    "политика обработки пдн",
    "политика пдн",
    "политика в области обработки",
    "конфиденциальность",
    "privacy policy",
    "privacy-policy",
    "privacypolicy",
    "политика конфиденц",
)

PRIVACY_CONTENT_MARKERS: dict[str, tuple[str, ...]] = {
    "оператор": ("оператор", "data controller", "the controller"),
    "персональные данные": ("персональн", "personal data", "personal information"),
    "цели обработки": (
        "цели обработки",
        "цель обработки",
        "целях обработки",
        "целями обработки",
        "purposes of processing",
        "processing purposes",
        "purposes for",
    ),
    "срок хранения": (
        "срок хранения",
        "сроки хранения",
        "срок обработки",
        "хранятся",
        "retention period",
        "retention",
        "how long we",
    ),
    "права субъекта": (
        "права субъект",
        "право субъект",
        "правах субъект",
        "rights of the data subject",
        "your rights",
        "your privacy rights",
    ),
    "отзыв согласия": (
        "отзыв согласия",
        "отозвать согласие",
        "отзыве согласия",
        "withdraw consent",
        "withdrawal of consent",
        "withdraw your consent",
    ),
    "cookie": ("cookie", "куки"),
}

RKN_MARKERS: tuple[str, ...] = (
    "реестр операторов",
    "роскомнадзор",
    "начале обработки персональных данных",
    "уведомление об обработке",
    "регистрационный номер оператора",
    "оператор персональных данных",
)

COOKIE_BANNER_TEXT_MARKERS: tuple[str, ...] = (
    "cookie", "куки", "cookies", "файлы cookie",
)
COOKIE_BANNER_CONTAINER_MARKERS: tuple[str, ...] = (
    "cookie", "consent", "gdpr", "agree", "privacy-banner", "cookie-banner",
    "cookie-notice", "cookie-popup", "cookie-alert",
)
COOKIE_ACCEPT_MARKERS: tuple[str, ...] = (
    "принять", "согласен", "соглашаюсь", "accept", "agree", "разрешить", "ок", "ok",
)
COOKIE_REJECT_MARKERS: tuple[str, ...] = (
    "отклонить", "отказаться", "только необход", "необходимые",
    "reject", "decline", "отказ", "запретить", "настроить", "настройки",
)


def is_consent_text(text: str) -> bool:
    """Похож ли текст на согласие на обработку ПДн."""
    low = (text or "").lower()
    if not low.strip():
        return False
    pdn = ("персональн", "пдн", "personal data", "обработк", "конфиденциальн", "privacy")
    consent = ("соглас", "consent", "принима", "accept", "agree", "i consent")
    return any(p in low for p in consent) and any(p in low for p in pdn)


def is_offer_text(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in OFFER_MARKERS) and not is_consent_text(low)


def is_marketing_text(text: str) -> bool:
    low = (text or "").lower()
    if not low.strip():
        return False
    marketing = ("рекламн", "рассылк", "новост", "акци", "newsletter", "marketing", "промо", "спецпредложен")
    consent = ("соглас", "хочу получать", "подпис", "получать", "сonsent", "agree", "consent")
    return any(m in low for m in marketing) and any(c in low for c in consent)


def find_privacy_link(links: list, privacy_pages_html: str = "") -> object | None:
    """Ищет ссылку на политику конфиденциальности среди LinkInfo."""
    best = None
    best_score = 0
    for link in links:
        hay = f"{getattr(link, 'text', '')} {getattr(link, 'aria_label', '')} {getattr(link, 'href', '')}".lower()
        hay_decoded = unquote(hay)
        href_low = unquote((getattr(link, "href", "") or "")).lower()
        score = 0
        for marker in PRIVACY_LINK_MARKERS:
            if marker in hay or marker in hay_decoded:
                score = max(score, len(marker))
        # «Политика … персональных данных» с любым порядком слов
        if not score and ("политик" in hay) and ("персональн" in hay or "конфиденц" in hay):
            score = 9
        # типовые слаги в href
        if not score and any(
            key in href_low
            for key in (
                "privacy",
                "politika",
                "policy",
                "konfidencial",
                "confidential",
                "confident",
                "personal-data",
                "personaldata",
                "pdn",
            )
        ):
            score = 8
        if not score and any(k in hay for k in ("политика", "политик")):
            score = 4
        if score > best_score:
            best, best_score = link, score
    return best


def privacy_markers_found(text: str) -> list[str]:
    """Какие из 7 маркеров содержательной политики найдены."""
    low = (text or "").lower()
    found: list[str] = []
    for name, variants in PRIVACY_CONTENT_MARKERS.items():
        if any(v in low for v in variants):
            found.append(name)
    return found


# ---------------------------------------------------------------------------
# Сторонние трекеры
# ---------------------------------------------------------------------------

# domain -> (kind, foreign)
TRACKER_DOMAINS: dict[str, tuple[str, bool]] = {
    # зарубежные — риск локализации (ч. 5 ст. 18 152-ФЗ)
    "google-analytics.com": ("analytics", True),
    "analytics.google.com": ("analytics", True),
    "googletagmanager.com": ("analytics", True),
    "googleadservices.com": ("advertising", True),
    "googlesyndication.com": ("advertising", True),
    "doubleclick.net": ("advertising", True),
    "facebook.net": ("social", True),
    "facebook.com": ("social", True),
    "connect.facebook.net": ("social", True),
    "hotjar.com": ("analytics", True),
    "hotjar.io": ("analytics", True),
    "clarity.ms": ("analytics", True),
    "tiktok.com": ("social", True),
    "analytics.tiktok.com": ("analytics", True),
    "amplitude.com": ("analytics", True),
    "segment.io": ("analytics", True),
    "segment.com": ("analytics", True),
    "mixpanel.com": ("analytics", True),
    "hubspot.com": ("analytics", True),
    "hs-scripts.com": ("analytics", True),
    "intercom.io": ("other", True),
    "criteo.com": ("advertising", True),
    "criteo.net": ("advertising", True),
    "linkedin.com": ("social", True),
    "licdn.com": ("social", True),
    "twitter.com": ("social", True),
    "ads-twitter.com": ("advertising", True),
    "px.ads.linkedin.com": ("advertising", True),
    "youtube.com": ("social", True),
    "ytimg.com": ("social", True),
    "sentry.io": ("other", True),
    "newrelic.com": ("analytics", True),
    "mouseflow.com": ("analytics", True),
    "smartlook.com": ("analytics", True),
    "verify.mail.ru": ("analytics", True),
    # российские сервисы — не считаются «зарубежными»
    "mc.yandex.ru": ("analytics", False),
    "yandex.ru": ("analytics", False),
    "yandex.com": ("analytics", False),
    "an.yandex.ru": ("advertising", False),
    "top-fwz1.mail.ru": ("analytics", False),
    "vk.com": ("social", False),
    "vk.ru": ("social", False),
    "target.my.com": ("advertising", False),
    "ad.mail.ru": ("advertising", False),
    "criteo.ru": ("advertising", False),
    "jivo.ru": ("other", False),
    "jivosite.ru": ("other", False),
    "bitrix24.ru": ("other", False),
}


def tracker_for_host(host: str) -> tuple[str, str, bool] | None:
    """Определяет (домен-владелец, вид, зарубежный) по хосту запроса."""
    host = (host or "").lower().split(":", 1)[0].strip(".")
    if not host:
        return None
    best: tuple[str, str, bool] | None = None
    for domain, (kind, foreign) in TRACKER_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            if best is None or len(domain) > len(best[0]):
                best = (domain, kind, foreign)
    return best


def tracker_for_url(url: str) -> tuple[str, str, bool] | None:
    try:
        host = urlparse(url if "://" in url else "//" + url.lstrip("/")).netloc
    except ValueError:
        return None
    return tracker_for_host(host)


INLINE_TRACKER_PATTERNS: tuple[str, ...] = tuple(TRACKER_DOMAINS)


def trackers_in_inline_script(script_text: str) -> list[tuple[str, str, bool]]:
    """Ищет упоминания трекеров внутри инлайн-скриптов."""
    low = (script_text or "").lower()
    found: list[tuple[str, str, bool]] = []
    for domain, (kind, foreign) in TRACKER_DOMAINS.items():
        if domain in low and (domain, kind, foreign) not in found:
            found.append((domain, kind, foreign))
    return found


# ---------------------------------------------------------------------------
# ЗоЗПП: продажи и реквизиты
# ---------------------------------------------------------------------------

BUY_BUTTON_MARKERS: tuple[str, ...] = (
    "купить", "в корзину", "в корзине", "заказать", "оформить заказ",
    "добавить в корзину", "buy now", "add to cart", "купить сейчас",
    "заказать звонок", "оформить",
)

CART_MARKERS: tuple[str, ...] = (
    "корзина", "корзин", "cart", "basket", "в корзину", "мой заказ",
)

ORDER_FORM_MARKERS: tuple[str, ...] = (
    "оформить заказ", "оформление заказа", "заказ", "checkout",
    "оформить покупку", "оформление покупки",
)

SUBSCRIBE_MARKERS: tuple[str, ...] = (
    "подписаться", "подписка", "рассылк", "newsletter", "subscribe",
    "подписаться на новости", "получать новости", "наши новости",
)

REQUISITE_WORDS: tuple[str, ...] = (
    "огрн", "огрнип", "инн", "кпп", "юридический адрес", "фактический адрес",
    "место нахождения", "полное наименование", "наименование организации",
    "индивидуальный предприниматель", "адрес",
)

_PHONE_RE = re.compile(
    r"(?:\+7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}\b"
)
_EMAIL_RE = re.compile(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", re.IGNORECASE)
#: Заглушки из примеров/шаблонов — не считаем реальными контактами.
_PLACEHOLDER_LOCAL = {
    "you", "your", "user", "username", "name", "email", "test", "example",
    "login", "mail", "your-email", "your.email", "your_name", "yourname",
}
_PLACEHOLDER_DOMAINS = {
    "example.com", "example.org", "example.net", "example.ru",
    "domain.com", "domain.ru", "yourdomain.com", "your-domain.com",
    "mysite.com", "mysite.ru", "site.com", "site.ru", "test.com", "test.ru",
    "company.com", "company.ru", "mail.com",
}
_PRICE_RE = re.compile(
    r"(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d{1,2})?|\d{1,6}(?:[.,]\d{1,2})?)"
    r"\s*(?:₽|руб\.|руб\b|rub\b|р\.)",
    re.IGNORECASE,
)
_OGRN_RE = re.compile(r"(?<!\d)(\d{13})(?!\d)")
_OGRNIP_RE = re.compile(r"(?<!\d)(\d{15})(?!\d)")
_INN10_RE = re.compile(r"(?<!\d)(\d{10})(?!\d)")
_INN12_RE = re.compile(r"(?<!\d)(\d{12})(?!\d)")
_KPP_RE = re.compile(r"(?<!\d)(\d{9})(?!\d)")


def extract_emails(html: str) -> list[str]:
    found: list[str] = []
    for match in _EMAIL_RE.findall(unquote(html or "")):
        email = match.lower()
        if email in found or email.endswith((".png", ".jpg", ".svg", ".webp")):
            continue
        if is_placeholder_email(email):
            continue
        found.append(email)
    return found[:20]


def is_placeholder_email(email: str) -> bool:
    """Отсекает адреса из шаблонов вроде you@domain.com."""
    local, _, domain = email.lower().partition("@")
    if not domain:
        return True
    if local in _PLACEHOLDER_LOCAL:
        return True
    if domain in _PLACEHOLDER_DOMAINS or domain.startswith("example."):
        return True
    return False


def extract_phones(text: str) -> list[str]:
    out: list[str] = []
    for match in _PHONE_RE.findall(text or ""):
        cleaned = re.sub(r"\s+", " ", match).strip()
        if cleaned not in out:
            out.append(cleaned)
    return out[:20]


def extract_prices(text: str) -> list[str]:
    out: list[str] = []
    for match in _PRICE_RE.findall(text or ""):
        cleaned = re.sub(r"\s+", " ", match).strip()
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out[:20]


def valid_ogrn(value: str) -> bool:
    """Контрольное число ОГРН (13 цифр)."""
    if len(value) != 13 or not value.isdigit():
        return False
    try:
        control = int(value[:12]) % 11 % 10
    except ValueError:
        return False
    return control == int(value[12])


def valid_ogrnip(value: str) -> bool:
    """Контрольное число ОГРНИП (15 цифр)."""
    if len(value) != 15 or not value.isdigit():
        return False
    control = int(value[:14]) % 13 % 10
    return control == int(value[14])


def valid_inn(value: str) -> bool:
    """Контрольные числа ИНН (10 или 12 цифр)."""
    if not value.isdigit() or len(value) not in (10, 12):
        return False
    digits = [int(c) for c in value]
    if len(value) == 10:
        weights = (2, 4, 10, 3, 5, 9, 4, 6, 8)
        return sum(d * w for d, w in zip(digits, weights)) % 11 % 10 == digits[9]
    w11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
    w12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
    c11 = sum(d * w for d, w in zip(digits, w11)) % 11 % 10
    c12 = sum(d * w for d, w in zip(digits, w12)) % 11 % 10
    return c11 == digits[10] and c12 == digits[11]


def valid_kpp(value: str) -> bool:
    return len(value) == 9 and value.isdigit()


@dataclass
class Requisites:
    """Найденные реквизиты продавца."""

    ogrn: list[str] = None  # type: ignore[assignment]
    ogrnip: list[str] = None  # type: ignore[assignment]
    inn: list[str] = None  # type: ignore[assignment]
    kpp: list[str] = None  # type: ignore[assignment]
    has_address: bool = False
    has_legal_name: bool = False
    has_email: bool = False
    has_phone: bool = False
    words: list[str] = None  # type: ignore[assignment]
    samples: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.ogrn = self.ogrn or []
        self.ogrnip = self.ogrnip or []
        self.inn = self.inn or []
        self.kpp = self.kpp or []
        self.words = self.words or []
        self.samples = self.samples or []

    @property
    def has_reg_number(self) -> bool:
        return bool(self.ogrn or self.ogrnip)

    @property
    def entity_kind(self) -> str:
        if self.ogrnip:
            return "ИП"
        if self.ogrn:
            return "ЮЛ"
        return "unknown"

    @property
    def summary(self) -> str:
        parts: list[str] = []
        if self.ogrn:
            parts.append(f"ОГРН {self.ogrn[0]}")
        if self.ogrnip:
            parts.append(f"ОГРНИП {self.ogrnip[0]}")
        if self.inn:
            parts.append(f"ИНН {self.inn[0]}")
        if self.kpp:
            parts.append(f"КПП {self.kpp[0]}")
        if self.has_address:
            parts.append("адрес")
        if self.has_legal_name:
            parts.append("наименование")
        if self.has_email:
            parts.append("email")
        if self.has_phone:
            parts.append("телефон")
        return ", ".join(parts)


def extract_requisites(text: str, html: str = "") -> Requisites:
    """Ищет реквизиты продавца в тексте (с проверкой контрольных сумм где можно)."""
    low = (text or "").lower()
    req = Requisites()
    req.words = [w for w in REQUISITE_WORDS if w in low]

    for raw in _OGRNIP_RE.findall(low):
        if valid_ogrnip(raw) and raw not in req.ogrnip:
            req.ogrnip.append(raw)
    for raw in _OGRN_RE.findall(low):
        if valid_ogrn(raw) and raw not in req.ogrn:
            req.ogrn.append(raw)
    for raw in _INN12_RE.findall(low):
        if valid_inn(raw) and raw not in req.inn:
            req.inn.append(raw)
    for raw in _INN10_RE.findall(low):
        if valid_inn(raw) and raw not in req.inn:
            req.inn.append(raw)
    for raw in _KPP_RE.findall(low)[:5]:
        if valid_kpp(raw) and raw not in req.kpp:
            req.kpp.append(raw)

    req.has_address = any(w in low for w in (
        "юридический адрес", "фактический адрес", "адрес:", "адрес ",
        "место нахождения", "адрес места", "г. москва", "город москва",
    ))
    req.has_legal_name = any(w in low for w in (
        "ооо", "оао", "зао", "пао", "ао ", "ип ", "индивидуальный предприниматель",
        "полное наименование", "наименование организации",
    ))
    req.has_email = bool(extract_emails(html or text))
    req.has_phone = bool(extract_phones(text))
    for word in req.words[:6]:
        req.samples.append(word)
    return req


# ---------------------------------------------------------------------------
# 38-ФЗ: реклама и ERID
# ---------------------------------------------------------------------------

AD_LABEL_MARKERS: tuple[str, ...] = (
    "реклама", "партнёрский материал", "партнерский материал",
    "спонсорский материал", "на правах рекламы", "advertising",
    "sponsored", "промо-материал",
)

AD_CONTAINER_MARKERS: tuple[str, ...] = (
    "advert", "ad-", "ads", "banner", "promo", "sponsor", "реклам",
)

_ERID_PARAM_RE = re.compile(r"erid[=:]\s*['\"]?([A-Za-z0-9_\-]{8,64})", re.IGNORECASE)
_ERID_TOKEN_RE = re.compile(r"\b[A-Za-z0-9]{30,40}\b")


def extract_erid_tokens(html: str) -> list[str]:
    """Все похожие на ERID токены: параметр erid=... и «голые» 32-символьные коды."""
    raw = html or ""
    tokens: list[str] = []
    for match in _ERID_PARAM_RE.findall(raw):
        if match not in tokens:
            tokens.append(match)
    low = raw.lower()
    for match in re.finditer(r"erid", low):
        window = raw[max(0, match.start() - 40) : match.start() + 120]
        for token in _ERID_TOKEN_RE.findall(window):
            if token not in tokens and not token.isdigit():
                tokens.append(token)
    return tokens[:20]


def has_erid(html_or_text: str) -> bool:
    return bool(extract_erid_tokens(html_or_text))


# ---------------------------------------------------------------------------
# Техническая гигиена
# ---------------------------------------------------------------------------

SECURITY_HEADERS: dict[str, str] = {
    "x-frame-options": "X-Frame-Options",
    "x-content-type-options": "X-Content-Type-Options",
    "referrer-policy": "Referrer-Policy",
    "content-security-policy": "Content-Security-Policy",
    "strict-transport-security": "Strict-Transport-Security",
    "permissions-policy": "Permissions-Policy",
}


def header_value(headers: dict[str, str], name: str) -> str | None:
    """Регистронезависимый поиск заголовка."""
    low = name.lower()
    for key, value in (headers or {}).items():
        if key.lower() == low:
            return value
    return None


def csp_has_frame_ancestors(csp: str | None) -> bool:
    return bool(csp) and "frame-ancestors" in (csp or "").lower()


# ---------------------------------------------------------------------------
# Ответы/ошибки
# ---------------------------------------------------------------------------


def friendly_http_error(exc: Exception) -> str:
    """Человеческое описание сетевой ошибки."""
    if isinstance(exc, httpx.TimeoutException):
        return "Сайт не ответил за отведённое время. Увеличьте таймаут в настройках."
    if isinstance(exc, httpx.ConnectError):
        text = str(exc).lower()
        if "name or service not known" in text or "getaddrinfo" in text or "nodename" in text:
            return "Не удалось найти сайт по этому адресу. Проверьте домен."
        if "certificate" in text or "ssl" in text:
            return "Ошибка TLS-сертификата. Сайт может быть недоступен или сертификат недействителен."
        return "Не удалось подключиться к сайту. Возможно, он недоступен или блокирует подключения."
    if isinstance(exc, httpx.TooManyRedirects):
        return "Сайт перенаправляет по кругу. Проверьте адрес."
    if isinstance(exc, httpx.HTTPError):
        return f"Сетевая ошибка: {exc.__class__.__name__}."
    return f"Ошибка: {exc}"


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("Б", "КБ", "МБ"):
        if size < 1024 or unit == "МБ":
            return f"{size:.1f} {unit}" if unit != "Б" else f"{int(size)} Б"
        size /= 1024
    return f"{size:.1f} МБ"
