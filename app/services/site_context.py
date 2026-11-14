"""Сбор контекста сайта: HTTP + BeautifulSoup, при возможности — Playwright.

Модуль разделён на две части:

* ``parse_site_context(html, url)`` — чистая функция разбора HTML. На ней
  построены тесты и проверки (никакой сети);
* ``build_site_context(url, options)`` — асинхронный оркестратор загрузки:
  HTTPS/TLS, страница, robots.txt/sitemap.xml, подстраницы (политика,
  контакты, оферта), глубокий анализ через Chromium.

Только GET-запросы, только чтение. Никаких действий, изменяющих сайт.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from bs4 import Tag

from app.core import detect
from app.core.errors import ScanCancelled
from app.core.models import (
    AdBlockInfo,
    CookieBannerInfo,
    FormFieldInfo,
    FormInfo,
    HttpsInfo,
    LinkInfo,
    PageInfo,
    RobotsInfo,
    ScriptInfo,
    SiteContext,
    SitemapInfo,
    TrackerInfo,
)
from app.paths import screenshots_dir
from app.services.browser.session import BrowserSession, browser_available
from app.services.http.client import HttpClient, probe_tls

ProgressCallback = Callable[[float, str], None]
CancelCallback = Callable[[], bool]

#: Поля SiteContext, которые заполняются разбором HTML.
CONTENT_FIELDS: tuple[str, ...] = (
    "html",
    "text",
    "footer_text",
    "title",
    "language",
    "links",
    "scripts",
    "trackers",
    "forms",
    "ad_blocks",
    "erid_tokens",
    "emails",
    "phones",
    "has_prices",
    "price_samples",
    "has_buy_buttons",
    "buy_button_samples",
    "has_cart",
    "has_order_form",
    "has_subscribe_form",
    "has_consent_checkbox",
    "consent_checked",
    "internal_links",
    "external_links",
    "privacy_link",
    "cookie_banner",
)

MAX_LINKS = 2000
MAX_TEXT = 300_000
_SKIP_INPUT_TYPES = {
    "hidden",
    "submit",
    "button",
    "reset",
    "image",
    "file",
    "range",
    "color",
    "date",
    "time",
    "number",
}

_ACCEPT_RE = re.compile(
    r"(?<![a-zа-яё])(принять|принимаю|принимаем|согласен|соглашаюсь|accept|agree|ок|ok)(?![a-zа-яё])",
    re.IGNORECASE,
)
_REJECT_RE = re.compile(
    r"(отклон|отказа|только необход|необходимые|reject|decline|запретить|отказ)",
    re.IGNORECASE,
)
_SETTINGS_RE = re.compile(
    r"(настро|параметр|settings|manage|подробнее|конфигур)", re.IGNORECASE
)
_AD_TOKEN_MARKERS = {
    "ad",
    "ads",
    "adv",
    "advert",
    "advertising",
    "banner",
    "banners",
    "promo",
    "promos",
    "sponsor",
    "sponsored",
    "reklama",
    "adslot",
    "adunit",
}


# ---------------------------------------------------------------------------
# Мелкие помощники разбора HTML
# ---------------------------------------------------------------------------


def build_selector(element: Tag, max_depth: int = 4) -> str:
    """Короткий CSS-селектор до элемента (для ссылок в отчёте)."""
    parts: list[str] = []
    node: Tag | None = element
    depth = 0
    while node is not None and depth < max_depth:
        name = getattr(node, "name", None)
        if not name or name in {"html", "[document]"}:
            break
        identifier = node.get("id") if hasattr(node, "get") else None
        if identifier:
            parts.append(f"{name}#{identifier}")
            break
        classes = []
        try:
            classes = [c for c in (node.get("class") or []) if c and " " not in c]
        except AttributeError:
            classes = []
        if classes and len(classes[0]) <= 40:
            parts.append(f"{name}.{classes[0]}")
        else:
            parts.append(name)
        node = node.parent if isinstance(node.parent, Tag) else None
        depth += 1
    return " > ".join(reversed(parts))[:120]


def _ancestor_matches(element: Tag, names: tuple[str, ...], depth: int = 6) -> bool:
    node: Tag | None = element
    steps = 0
    while node is not None and steps < depth:
        if getattr(node, "name", "") in names:
            return True
        try:
            classes = " ".join(node.get("class") or []).lower()
            identifier = (node.get("id") or "").lower()
        except AttributeError:
            classes, identifier = "", ""
        hay = f"{classes} {identifier}"
        if any(marker in hay for marker in names):
            return True
        node = node.parent if isinstance(node.parent, Tag) else None
        steps += 1
    return False


def _in_footer(element: Tag) -> bool:
    return _ancestor_matches(element, ("footer", "подвал", "podval", "bottom"))


def _in_header(element: Tag) -> bool:
    return _ancestor_matches(element, ("header", "nav", "шапка", "topbar", "top-menu"))


def label_for(input_element: Tag) -> str:
    """Текст подписи для поля: label[for], родительский label, aria-label, title."""
    try:
        identifier = input_element.get("id")
        root = input_element.find_parent()
        soup = input_element
        while getattr(soup, "parent", None) is not None:
            soup = soup.parent
        if identifier:
            tag = soup.find("label", attrs={"for": identifier}) if hasattr(soup, "find") else None
            if tag is not None:
                text = detect.visible_text(tag, 220)
                if text:
                    return text
        parent_label = input_element.find_parent("label")
        if parent_label is not None:
            text = detect.visible_text(parent_label, 220)
            if text:
                return text
        for attribute in ("aria-label", "title", "placeholder"):
            value = input_element.get(attribute)
            if value:
                return detect.normalize_text(value, 220)
        # текст ближайшего контейнера — как последний шанс
        container = input_element.find_parent(["div", "p", "td", "li", "form"])
        if container is not None:
            return detect.visible_text(container, 220)
    except Exception:  # noqa: BLE001 - разбор чужого HTML не должен падать
        return ""
    return ""


def _context_text(element: Tag, limit: int = 700) -> str:
    """Видимый текст вокруг элемента (для распознавания чекбоксов согласия)."""
    node: Tag | None = element
    steps = 0
    while node is not None and steps < 5:
        text = detect.visible_text(node, limit + 200)
        if text and len(text) <= limit:
            return text
        node = node.parent if isinstance(node.parent, Tag) else None
        steps += 1
    return detect.visible_text(element, limit)


def _field_from_input(element: Tag) -> FormFieldInfo:
    name = (element.name or "input").lower()
    input_type = (element.get("type") or ("text" if name == "input" else name)).lower()
    return FormFieldInfo(
        tag=name,
        type=input_type,
        name=element.get("name"),
        placeholder=element.get("placeholder"),
        label_text=label_for(element),
        selector=build_selector(element),
        required=element.has_attr("required"),
        checked=element.has_attr("checked"),
    )


def _classify_checkbox(field: FormFieldInfo) -> str | None:
    text = field.label_text or ""
    if detect.is_consent_text(text):
        return "consent"
    if detect.is_marketing_text(text):
        return "marketing"
    if detect.is_offer_text(text):
        return "offer"
    return None


# ---------------------------------------------------------------------------
# Извлечение данных
# ---------------------------------------------------------------------------


def extract_links(
    soup,
    base_url: str,
    domain: str,
    local_root: Path | str | None = None,
) -> list[LinkInfo]:
    anchors = soup.find_all("a", href=True)
    # ссылки футера важны для проверок политики/контактов даже на «длинных» страницах
    footer_anchors = [anchor for anchor in anchors if _in_footer(anchor)]
    selected = anchors[:MAX_LINKS]
    known = {id(anchor) for anchor in selected}
    for anchor in footer_anchors:
        if id(anchor) not in known:
            selected.append(anchor)
            known.add(id(anchor))

    links: list[LinkInfo] = []
    for anchor in selected:
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "data:", "tel:")):
            continue
        if local_root is not None and href.startswith("/") and not href.startswith("//"):
            # локальная папка: абсолютный путь сайта = путь от корня папки
            try:
                absolute = (Path(local_root) / href.lstrip("/")).as_uri()
            except OSError:
                absolute = ""
        else:
            absolute = detect.absolute_link(href, base_url)
        if not absolute:
            continue
        if absolute.startswith("mailto:"):
            links.append(
                LinkInfo(
                    href=absolute,
                    text=detect.visible_text(anchor, 120),
                    aria_label=detect.normalize_text(anchor.get("aria-label") or "", 120),
                    is_internal=True,
                    in_footer=_in_footer(anchor),
                    in_header=_in_header(anchor),
                    selector=build_selector(anchor),
                )
            )
            continue
        if not absolute.startswith(("http://", "https://", "file://")):
            continue
        links.append(
            LinkInfo(
                href=absolute,
                text=detect.visible_text(anchor, 160),
                aria_label=detect.normalize_text(anchor.get("aria-label") or "", 120),
                rel=detect.normalize_text(anchor.get("rel") and " ".join(anchor.get("rel")) or "", 60),
                is_internal=detect.is_internal_link(absolute, domain),
                in_footer=_in_footer(anchor),
                in_header=_in_header(anchor),
                selector=build_selector(anchor),
            )
        )
    return links


def extract_scripts(soup) -> list[ScriptInfo]:
    scripts: list[ScriptInfo] = []
    for tag in soup.find_all("script"):
        source = tag.get("src")
        inline = tag.string or tag.get_text() or ""
        scripts.append(
            ScriptInfo(
                src=detect.absolute_link(source, "") if source else None,
                inline_len=len(inline),
                async_=tag.has_attr("async"),
            )
        )
    return scripts


def extract_trackers(soup) -> list[TrackerInfo]:
    found: dict[str, TrackerInfo] = {}

    def add(url: str, found_in: str) -> None:
        info = detect.tracker_for_url(url)
        if not info:
            return
        domain, kind, foreign = info
        if domain in found:
            return
        found[domain] = TrackerInfo(
            domain=domain,
            kind=kind,
            foreign=foreign,
            found_in=found_in,
            url=url[:300],
        )

    for tag in soup.find_all(["script", "iframe", "img", "link", "embed", "object"]):
        source = (
            tag.get("src")
            or tag.get("href")
            or tag.get("data-src")
            or tag.get("data-lazy-src")
        )
        if source and isinstance(source, str):
            add(source, tag.name)

    for tag in soup.find_all("script"):
        inline = tag.string or tag.get_text() or ""
        if not inline:
            continue
        for domain, kind, foreign in detect.trackers_in_inline_script(inline):
            if domain in found:
                continue
            found[domain] = TrackerInfo(
                domain=domain, kind=kind, foreign=foreign, found_in="inline", url=""
            )
    return list(found.values())


def extract_forms(soup, base_url: str) -> list[FormInfo]:
    forms: list[FormInfo] = []
    form_elements = soup.find_all("form")

    for form in form_elements[:40]:
        fields: list[FormFieldInfo] = []
        for element in form.find_all(["input", "textarea", "select"]):
            field = _field_from_input(element)
            if field.type in _SKIP_INPUT_TYPES:
                continue
            fields.append(field)
        if not fields:
            continue

        context_text = _context_text(form)
        info = FormInfo(
            selector=build_selector(form),
            action=form.get("action"),
            method=(form.get("method") or "get").lower(),
            fields=fields,
            context_text=context_text,
            url=base_url,
        )
        _fill_form_flags(info, context_text)
        forms.append(info)

    # Поля вне <form> (AJAX-формы, поиск, подписка в футере)
    standalone: list[FormFieldInfo] = []
    standalone_context = ""
    for element in soup.find_all(["input", "textarea"]):
        if element.find_parent("form") is not None:
            continue
        field = _field_from_input(element)
        if field.type in _SKIP_INPUT_TYPES:
            continue
        if field.type in {"checkbox", "radio"}:
            if _classify_checkbox(field) is None:
                continue
        elif not field.is_personal_data:
            continue
        if not standalone:
            standalone_context = _context_text(element)
        standalone.append(field)

    if standalone:
        context_text = standalone_context or detect.visible_text(soup.body, 700)
        info = FormInfo(
            selector="body (поля без <form>)",
            fields=standalone,
            context_text=context_text,
            url=base_url,
            is_standalone_fields=True,
        )
        _fill_form_flags(info, context_text)
        forms.append(info)

    return forms


def _fill_form_flags(info: FormInfo, context_text: str) -> None:
    context_low = (context_text or "").lower()
    for field in info.fields:
        if field.type not in {"checkbox", "radio"}:
            continue
        kind = _classify_checkbox(field)
        if kind == "consent":
            info.has_consent_checkbox = True
            info.consent_checked = info.consent_checked or field.checked
            info.consent_text = info.consent_text or field.label_text
        elif kind == "marketing":
            info.has_marketing_checkbox = True
            info.marketing_checked = info.marketing_checked or field.checked
        elif kind == "offer":
            info.has_offer_checkbox = True
            info.offer_checked = info.offer_checked or field.checked

    is_order = any(
        marker in (info.action or "").lower()
        for marker in ("order", "checkout", "cart", "zakaz", "oformit", "buy")
    ) or any(marker in context_low for marker in detect.ORDER_FORM_MARKERS)
    info.is_order_form = bool(is_order)

    has_email = any(f.type == "email" for f in info.fields)
    subscribe = any(marker in context_low for marker in detect.SUBSCRIBE_MARKERS)
    info.is_subscribe_form = bool(subscribe and has_email)


def extract_ad_blocks(soup, url: str = "") -> list[AdBlockInfo]:
    """Рекламные блоки: по классам/идам и по явным пометкам «Реклама»."""
    domain = detect.domain_of(url) if url else ""
    candidates: list[Tag] = []
    block_tags = ["div", "section", "aside", "article", "li", "figure"]

    for element in soup.find_all(block_tags):
        try:
            class_id = " ".join(element.get("class") or []) + " " + (element.get("id") or "")
        except AttributeError:
            continue
        if _ad_class_hint(class_id):
            candidates.append(element)

    label_pattern = re.compile(
        "|".join(re.escape(marker) for marker in detect.AD_LABEL_MARKERS), re.IGNORECASE
    )
    for text_node in soup.find_all(string=label_pattern)[:40]:
        parent = text_node.parent
        for _ in range(3):
            if parent is None or getattr(parent, "name", None) in (None, "body", "html"):
                break
            if parent.name in ("div", "section", "aside", "article", "li", "figure", "p"):
                candidates.append(parent)
                break
            parent = parent.parent

    blocks: list[AdBlockInfo] = []
    seen: set[str] = set()
    seen_text: set[str] = set()

    for element in candidates:
        text = detect.visible_text(element, 3000)
        if not text or len(text) < 15 or len(text) > 2500:
            continue
        has_label = any(marker in text for marker in detect.AD_LABEL_MARKERS)
        if not has_label and not element.find():
            continue
        links = element.find_all("a", href=True)
        if not links:
            continue
        if not has_label:
            if _ancestor_matches(element, ("footer", "nav", "header"), depth=3):
                continue
            # Блок «по классу» без пометки — реклама только если ведёт на внешний сайт.
            if domain:
                external = [
                    anchor
                    for anchor in links
                    if not detect.is_internal_link(anchor.get("href") or "", domain)
                ]
                if not external:
                    continue
        selector = build_selector(element)
        if not selector or selector in seen:
            continue
        text_key = text[:80]
        if text_key in seen_text:
            continue
        seen.add(selector)
        seen_text.add(text_key)
        fragment = str(element)[:20000]
        tokens = detect.extract_erid_tokens(fragment)
        blocks.append(
            AdBlockInfo(
                selector=selector,
                text=text[:220],
                has_ad_label=has_label,
                has_erid=bool(tokens),
                erid_tokens=tokens,
            )
        )
        if len(blocks) >= 8:
            break
    return blocks


def _ad_class_hint(class_id: str) -> bool:
    tokens = set(re.split(r"[^a-z0-9а-яё]+", " ".join(class_id.lower().split())))
    for token in tokens:
        if not token:
            continue
        if token in _AD_TOKEN_MARKERS:
            return True
        if token.startswith(("advert", "advertisement", "banner", "promo", "sponsor")):
            return True
    return False


def extract_cookie_banner(soup) -> CookieBannerInfo:
    """HTTP-эвристика баннера (без JS): ищем контейнер с текстом про cookie."""
    for element in soup.find_all(["div", "section", "aside", "dialog", "footer"]):
        try:
            class_id = " ".join(element.get("class") or []) + " " + (element.get("id") or "")
        except AttributeError:
            continue
        low = class_id.lower()
        if not any(marker in low for marker in detect.COOKIE_BANNER_CONTAINER_MARKERS):
            continue
        text = detect.visible_text(element, 900)
        if not text or not any(marker in text for marker in detect.COOKIE_BANNER_TEXT_MARKERS):
            continue
        buttons = " | ".join(
            detect.visible_text(button, 60)
            for button in element.find_all(["button", "a", "input"])
        )
        return CookieBannerInfo(
            found=True,
            text=text[:500],
            selector=build_selector(element),
            has_accept=bool(_ACCEPT_RE.search(buttons)),
            has_reject=bool(_REJECT_RE.search(buttons)),
            has_settings=bool(_SETTINGS_RE.search(buttons)),
            source="http",
        )
    return CookieBannerInfo(found=False, source="http")


def banner_from_browser(data: dict, screenshot: str | None = None) -> CookieBannerInfo:
    """Преобразует результат JS-поиска баннера в модель."""
    text = detect.normalize_text(str(data.get("text") or ""), 700)
    buttons = " | ".join(
        detect.normalize_text(str(button)) for button in (data.get("buttons") or [])
    )
    has_reject = bool(_REJECT_RE.search(buttons))
    has_accept = bool(_ACCEPT_RE.search(buttons)) and not has_reject
    if has_reject and _ACCEPT_RE.search(buttons):
        has_accept = True
    selector_parts = [str(data.get("tag") or "").lower()]
    if data.get("id"):
        selector_parts.append(f"#{data.get('id')}")
    elif data.get("className"):
        selector_parts.append(f".{str(data['className']).split()[0]}")
    selector = "".join(part for part in selector_parts if part)
    return CookieBannerInfo(
        found=True,
        text=text,
        selector=selector,
        has_accept=has_accept,
        has_reject=has_reject,
        has_settings=bool(_SETTINGS_RE.search(buttons)),
        source="playwright",
        screenshot=screenshot,
    )


def _sales_flags(soup, text: str, forms: list[FormInfo]) -> dict[str, object]:
    prices = detect.extract_prices(text)
    buy_samples: list[str] = []
    for element in soup.find_all(["button", "a", "input"]):
        candidate = (
            detect.visible_text(element, 60)
            if element.name != "input"
            else detect.normalize_text(element.get("value") or "", 60)
        )
        if not candidate:
            continue
        if any(marker in candidate for marker in detect.BUY_BUTTON_MARKERS):
            if candidate not in buy_samples:
                buy_samples.append(candidate)
        if len(buy_samples) >= 10:
            break
    cart = any(marker in text for marker in detect.CART_MARKERS)
    order_form = any(form.is_order_form for form in forms)
    subscribe = any(form.is_subscribe_form for form in forms)
    return {
        "has_prices": bool(prices),
        "price_samples": prices[:10],
        "has_buy_buttons": bool(buy_samples),
        "buy_button_samples": buy_samples[:10],
        "has_cart": cart,
        "has_order_form": order_form,
        "has_subscribe_form": subscribe,
    }


# ---------------------------------------------------------------------------
# Чистый разбор HTML
# ---------------------------------------------------------------------------


def parse_site_context(
    html: str,
    url: str,
    *,
    status_code: int | None = None,
    headers: dict[str, str] | None = None,
    deep_analysis: bool = False,
    local_root: Path | str | None = None,
) -> SiteContext:
    """Разбирает HTML в SiteContext. Без сети — удобно для тестов."""
    domain = detect.domain_of(url)
    context = SiteContext(
        target_url=url,
        url=url,
        domain=domain,
        status_code=status_code,
        headers={k.lower(): v for k, v in (headers or {}).items()},
        html=html or "",
        deep_analysis=deep_analysis,
    )

    soup = detect.make_soup(html)
    context.title = detect.collapse_text(soup.title.get_text() if soup.title else "", 300)
    html_tag = soup.find("html")
    if html_tag is not None and html_tag.get("lang"):
        context.language = str(html_tag.get("lang"))[:16]

    context.text = detect.visible_text(soup, MAX_TEXT)
    context.footer_text = detect.footer_text(soup)

    context.links = extract_links(soup, url, domain, local_root)
    internal = [link for link in context.links if link.is_internal and link.href.startswith("http")]
    context.internal_links = len(internal)
    context.external_links = len(
        [link for link in context.links if not link.is_internal and link.href.startswith("http")]
    )

    context.scripts = extract_scripts(soup)
    context.trackers = extract_trackers(soup)
    context.forms = extract_forms(soup, url)
    context.ad_blocks = extract_ad_blocks(soup, url)
    context.erid_tokens = detect.extract_erid_tokens(html)
    context.emails = detect.extract_emails(html)
    context.phones = detect.extract_phones(context.text)
    context.privacy_link = detect.find_privacy_link(context.links)
    context.cookie_banner = extract_cookie_banner(soup)

    flags = _sales_flags(soup, context.text, context.forms)
    for name, value in flags.items():
        setattr(context, name, value)

    context.has_consent_checkbox = any(form.has_consent_checkbox for form in context.forms)
    context.consent_checked = any(form.consent_checked for form in context.forms)

    if context.headers:
        context.security_headers = {
            name: detect.header_value(context.headers, name)
            for name in detect.SECURITY_HEADERS
        }
    return context


def _copy_content(target: SiteContext, source: SiteContext) -> None:
    for name in CONTENT_FIELDS:
        setattr(target, name, getattr(source, name))


def _merge_trackers(target: SiteContext, extra: list[TrackerInfo]) -> None:
    existing = {tracker.domain for tracker in target.trackers}
    for tracker in extra:
        if tracker.domain in existing:
            continue
        target.trackers.append(tracker)
        existing.add(tracker.domain)


# ---------------------------------------------------------------------------
# Сетевая часть
# ---------------------------------------------------------------------------


def _check_cancel(cancelled: CancelCallback | None) -> None:
    if cancelled is not None and cancelled():
        raise ScanCancelled()


def _report(progress: ProgressCallback | None, fraction: float, message: str) -> None:
    if progress is not None:
        progress(fraction, message)


def _http_url(url: str) -> str:
    return "http://" + url.split("://", 1)[-1]


def _https_url(url: str) -> str:
    return "https://" + url.split("://", 1)[-1]


def _origin(url: str) -> str:
    """Схема + домен: robots.txt и sitemap.xml всегда лежат в корне домена."""
    parsed = urlparse(url or "")
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _parse_robots(content: str) -> tuple[bool, list[str]]:
    disallow_all = False
    sitemaps: list[str] = []
    agents: list[str] = []
    for raw_line in (content or "").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            agents.append(value.lower())
        elif key == "disallow":
            if value == "/" and ("*" in agents or not agents):
                disallow_all = True
        elif key == "sitemap" and value:
            sitemaps.append(value)
    return disallow_all, sitemaps


def _count_sitemap_urls(content: str) -> tuple[int, bool]:
    low = (content or "").lower()
    return low.count("<loc>"), "<sitemapindex" in low


async def _fetch_robots(client: HttpClient, context: SiteContext) -> RobotsInfo:
    origin = _origin(context.url)
    if not origin:
        return RobotsInfo(found=False)
    robots_url = f"{origin}/robots.txt"
    result = await client.fetch(robots_url, max_bytes=512 * 1024, retries=0)
    info = RobotsInfo(status_code=result.status_code, error=result.error)
    if not result.ok or not result.text.strip():
        return info
    info.found = True
    info.content = result.text[:100_000]
    info.disallow_all, info.sitemaps = _parse_robots(info.content)
    return info


async def _fetch_sitemap(
    client: HttpClient, context: SiteContext, robots: RobotsInfo
) -> SitemapInfo:
    candidates: list[str] = list(robots.sitemaps)
    origin = _origin(context.url)
    if origin:
        candidates.append(f"{origin}/sitemap.xml")
    for candidate in candidates[:3]:
        if not candidate.startswith(("http://", "https://")):
            continue
        result = await client.fetch(candidate, max_bytes=2 * 1024 * 1024, retries=0)
        info = SitemapInfo(url=candidate, status_code=result.status_code, error=result.error)
        if not result.ok or not result.text.strip():
            continue
        count, is_index = _count_sitemap_urls(result.text)
        info.found = True
        info.url_count = count
        info.is_index = is_index
        return info
    return SitemapInfo(found=False, url=candidates[0] if candidates else "")


def _pick_extra_pages(context: SiteContext, limit: int) -> dict[str, str]:
    chosen: dict[str, str] = {}
    if context.privacy_link is not None and context.privacy_link.href.startswith("http"):
        chosen["privacy"] = context.privacy_link.href

    groups: dict[str, tuple[str, ...]] = {
        "contacts": (
            "контакт",
            "contact",
            "связаться",
            "обратная связь",
            "обратную связь",
            "feedback",
            "поддержк",
            "support",
            "о компании",
            "about",
        ),
        "offer": ("оферт", "условия", "terms", "правила", "договор", "agreement"),
    }
    for key, markers in groups.items():
        if key in chosen:
            continue
        for link in context.links:
            if not link.is_internal or not link.href.startswith("http"):
                continue
            haystack = f"{link.text} {link.href}".lower()
            if any(marker in haystack for marker in markers):
                chosen[key] = link.href
                break

    main = context.url.rstrip("/")
    unique: dict[str, str] = {}
    for key, url in chosen.items():
        if url.rstrip("/") == main:
            continue
        if url in unique.values():
            continue
        unique[key] = url
    return dict(list(unique.items())[: max(0, limit)])


def _looks_like_login(url: str, soup) -> bool:
    path = urlparse(url).path.lower()
    if any(marker in path for marker in ("login", "signin", "sign-in", "auth", "vhod", "войти")):
        if soup.find("input", attrs={"type": "password"}) is not None:
            return True
    password = soup.find("input", attrs={"type": "password"})
    if password is None:
        return False
    text = detect.visible_text(soup.body, 3000) if soup.body is not None else ""
    return any(marker in text for marker in ("войти", "вход", "авторизоваться", "login", "sign in"))


async def _fetch_extra_pages(
    client: HttpClient,
    context: SiteContext,
    options,
    cancelled: CancelCallback | None,
) -> dict[str, PageInfo]:
    pages: dict[str, PageInfo] = {}
    targets = _pick_extra_pages(context, int(options.max_pages))
    for index, (key, url) in enumerate(targets.items()):
        _check_cancel(cancelled)
        _report(None, 0, "")
        result = await client.fetch(
            url, max_bytes=min(options.max_html_bytes, 2 * 1024 * 1024), retries=0
        )
        page = PageInfo(
            key=key,
            url=result.url or url,
            status_code=result.status_code,
            ok=result.ok,
            error=result.error,
        )
        if result.ok and result.text:
            soup = detect.make_soup(result.text)
            page.title = detect.collapse_text(
                soup.title.get_text() if soup.title else "", 200
            )
            page.text = detect.visible_text(soup, 60_000)
            page.redirected_to_login = _looks_like_login(result.url or url, soup)
            banner = extract_cookie_banner(soup)
            page.has_cookie_wall = bool(banner.found and len(page.text) < 1500)
        pages[key] = page
    return pages


async def _deep_analysis(
    context: SiteContext,
    options,
    cancelled: CancelCallback | None,
) -> None:
    """Playwright: рендер, cookie-баннер, скриншот, сторонние запросы."""
    if not browser_available():
        context.note(
            "Playwright не установлен — глубокий анализ не выполнен, "
            "динамические элементы не проверены."
        )
        return

    _check_cancel(cancelled)
    session = BrowserSession(
        timeout=options.timeout,
        user_agent=options.user_agent,
        screenshot_dir=options.screenshot_dir or screenshots_dir(),
        save_screenshots=options.save_screenshots,
    )
    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", context.domain or "site")[:60]
    browser = await session.capture(context.url, name=f"{safe_name}-main")

    if not browser.ok:
        context.note(
            "Глубокий анализ не выполнен: "
            + (browser.error or "неизвестная причина")
            + " Проверялись только статические данные."
        )
        return

    context.deep_analysis = True
    if browser.screenshot:
        context.screenshots["main"] = browser.screenshot

    if browser.cookie_banner:
        context.cookie_banner = banner_from_browser(
            browser.cookie_banner, browser.screenshot
        )

    if browser.html:
        rendered = parse_site_context(
            browser.html,
            browser.final_url or context.url,
            status_code=context.status_code,
            headers=context.headers,
            deep_analysis=True,
        )
        trackers_from_html = context.trackers
        _copy_content(context, rendered)
        _merge_trackers(context, trackers_from_html)

    network_trackers: list[TrackerInfo] = []
    for request_url in browser.requests[:400]:
        info = detect.tracker_for_url(request_url)
        if not info:
            continue
        domain, kind, foreign = info
        network_trackers.append(
            TrackerInfo(
                domain=domain,
                kind=kind,
                foreign=foreign,
                found_in="request",
                url=request_url[:300],
            )
        )
    _merge_trackers(context, network_trackers)

    if browser.challenge:
        context.note(
            "Сайт отдаёт антибот-проверку (Cloudflare/DDoS-Guard) — "
            "часть динамических данных недоступна."
        )
    if browser.note and not browser.challenge:
        context.note(browser.note)


async def build_site_context(
    url: str,
    options,
    progress: ProgressCallback | None = None,
    cancelled: CancelCallback | None = None,
) -> SiteContext:
    """Полный сбор контекста по адресу сайта."""
    normalized = detect.normalize_url(url)
    if not normalized.ok:
        raise ValueError(normalized.error or "Некорректный адрес сайта")

    target = normalized.url
    domain = detect.domain_of(target)
    context = SiteContext(target_url=target, url=target, domain=domain)

    client = HttpClient(
        timeout=options.timeout,
        user_agent=options.user_agent,
        max_bytes=options.max_html_bytes,
        verify=True,
    )

    # --- 1. Загрузка страницы + TLS ---------------------------------------
    _check_cancel(cancelled)
    _report(progress, 0.06, "Загрузка страницы…")
    fetch = await client.fetch(target)
    cert_valid = fetch.cert_valid
    cert_error = fetch.cert_error
    used_insecure_fallback = False

    if not fetch.ok and fetch.error_kind == "tls":
        _check_cancel(cancelled)
        _report(progress, 0.1, "Сертификат не прошёл проверку — пробуем без проверки TLS…")
        insecure = await client.fetch(target, verify=False)
        if insecure.ok:
            fetch = insecure
            cert_valid = False
            used_insecure_fallback = True
        else:
            cert_error = cert_error or insecure.error

    if not fetch.ok and target.startswith("https://") and options.allow_http_fallback:
        _check_cancel(cancelled)
        _report(progress, 0.12, "HTTPS недоступен — пробуем HTTP…")
        http_fetch = await client.fetch(_http_url(target), verify=False)
        if http_fetch.ok:
            fetch = http_fetch
            context.note("Сайт не открывается по HTTPS — проверка выполнена по HTTP.")
        else:
            cert_error = cert_error or http_fetch.error

    if used_insecure_fallback:
        context.note(
            "Сертификат сайта не прошёл проверку — страница загружена с отключённой "
            "проверкой TLS (только чтение, ничего не отправлялось)."
        )

    https_info = HttpsInfo(
        requested_url=target,
        final_url=fetch.url or target,
        used_https=(fetch.url or target).startswith("https://"),
        https_available=(fetch.ok and (fetch.url or target).startswith("https://")),
        cert_valid=cert_valid,
        cert_error=cert_error,
        tls_version=fetch.tls_version,
        redirects_http_to_https=(
            target.startswith("http://") and (fetch.url or "").startswith("https://")
        ),
        http_status=fetch.status_code,
        error=fetch.error,
    )

    # Если по HTTPS не пускает или сайт открыт по HTTP — уточняем TLS отдельно.
    probe_timeout = min(10.0, float(options.timeout))
    if fetch.ok and not https_info.used_https:
        https_url = _https_url(target)
        _check_cancel(cancelled)
        probe = await client.fetch(
            https_url, max_bytes=128 * 1024, retries=0, timeout=probe_timeout
        )
        https_info.https_available = probe.ok
        if probe.ok:
            https_info.tls_version = probe.tls_version or https_info.tls_version
    if fetch.ok and https_info.used_https:
        # Проверяем, перенаправляет ли http:// на https:// (для проверки a01).
        _check_cancel(cancelled)
        _report(progress, 0.16, "Проверка перенаправления HTTP → HTTPS…")
        http_probe = await client.fetch(
            _http_url(context.url or target),
            max_bytes=128 * 1024,
            retries=0,
            verify=False,
            timeout=probe_timeout,
        )
        if http_probe.ok:
            https_info.http_redirect_checked = True
            https_info.redirects_http_to_https = (http_probe.url or "").startswith("https://")
    if fetch.ok and https_info.used_https and not https_info.tls_version:
        version, tls_error = await asyncio.to_thread(
            probe_tls, domain, 443, min(8.0, float(options.timeout))
        )
        https_info.tls_version = version
        if tls_error and https_info.cert_valid:
            https_info.cert_valid = False
            https_info.cert_error = tls_error

    if not fetch.ok:
        context.fetch_failed = True
        context.fetch_error = fetch.error or "Сайт недоступен."
        context.https = https_info
        context.security_headers = {}
        context.note(f"Сайт недоступен: {context.fetch_error}")
        _report(progress, 1.0, "Сайт недоступен")
        return context

    context.url = fetch.url or target
    context.domain = detect.domain_of(context.url) or domain
    context.status_code = fetch.status_code
    context.headers = fetch.headers
    context.https = https_info
    context.security_headers = {
        name: detect.header_value(fetch.headers, name) for name in detect.SECURITY_HEADERS
    }
    if fetch.truncated:
        context.note(
            "Страница больше лимита загрузки — разобрана только часть HTML."
        )

    # --- 2. Разбор HTML ----------------------------------------------------
    _check_cancel(cancelled)
    _report(progress, 0.2, "Разбор HTML…")
    base = parse_site_context(
        fetch.text,
        context.url,
        status_code=fetch.status_code,
        headers=fetch.headers,
    )
    _copy_content(context, base)
    if not context.html.strip():
        context.fetch_failed = True
        context.fetch_error = (
            "По адресу открывается не HTML-страница. Укажите адрес сайта, а не файла."
        )
        context.note(context.fetch_error)
        _report(progress, 1.0, "Не HTML-страница")
        return context

    # --- 3. robots.txt и sitemap.xml --------------------------------------
    _check_cancel(cancelled)
    _report(progress, 0.32, "Проверка robots.txt и sitemap.xml…")
    context.robots = await _fetch_robots(client, context)
    context.sitemap = await _fetch_sitemap(client, context, context.robots)

    # --- 4. Подстраницы: политика, контакты, оферта ------------------------
    _check_cancel(cancelled)
    _report(progress, 0.4, "Загрузка политики и подстраниц…")
    if int(options.max_pages) > 0:
        if context.robots.disallow_all:
            context.note(
                "robots.txt запрещает обход — дополнительные страницы не загружались "
                "(главная страница проверена)."
            )
        else:
            context.pages = await _fetch_extra_pages(client, context, options, cancelled)

    # --- 5. Глубокий анализ (Playwright) ----------------------------------
    if options.deep_analysis:
        _check_cancel(cancelled)
        _report(progress, 0.55, "Глубокий анализ (Chromium)…")
        await _deep_analysis(context, options, cancelled)
    else:
        context.note(
            "Глубокий анализ отключён — динамические элементы и cookie-баннер "
            "проверены только по статическому HTML."
        )

    # --- 6. Итоговые флаги ------------------------------------------------
    _check_cancel(cancelled)
    _report(progress, 0.95, "Подготовка отчёта…")
    context.has_consent_checkbox = any(form.has_consent_checkbox for form in context.forms)
    context.consent_checked = any(form.consent_checked for form in context.forms)
    if context.internal_links == 0:
        context.internal_links = len(
            [link for link in context.links if link.is_internal and link.href.startswith("http")]
        )
    _report(progress, 1.0, "Контекст собран")
    return context


__all__ = [
    "CONTENT_FIELDS",
    "banner_from_browser",
    "build_site_context",
    "build_selector",
    "extract_ad_blocks",
    "extract_cookie_banner",
    "extract_forms",
    "extract_links",
    "extract_scripts",
    "extract_trackers",
    "parse_site_context",
]
