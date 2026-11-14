"""Pydantic-модели приложения.

Здесь описаны три ключевых контракта:
  * ``SiteContext``  — всё, что сборщик контекста узнал о сайте;
  * ``CheckResult``  — результат одной проверки;
  * ``Report``       — итоговый отчёт по сайту.

Проверки (``app/core/checks``) читают ``SiteContext`` и возвращают
``CheckResult``. Такой контракт позволяет тестировать каждую проверку
на синтетическом контексте без сети.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


# ---------------------------------------------------------------------------
# Перечисления
# ---------------------------------------------------------------------------


class CheckStatus(str, Enum):
    """Статус проверки."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"
    NOT_APPLICABLE = "not_applicable"

    @property
    def label_ru(self) -> str:
        return {
            CheckStatus.PASS: "Пройдено",
            CheckStatus.WARN: "Замечание",
            CheckStatus.FAIL: "Нарушение",
            CheckStatus.SKIP: "Не проверено",
            CheckStatus.NOT_APPLICABLE: "Не применимо",
        }[self]


class Severity(str, Enum):
    """Приоритет нарушения."""

    CRITICAL = "critical"
    IMPORTANT = "important"
    RECOMMENDATION = "recommendation"
    INFO = "info"

    @property
    def label_ru(self) -> str:
        return {
            Severity.CRITICAL: "Критично",
            Severity.IMPORTANT: "Важно",
            Severity.RECOMMENDATION: "Рекомендация",
            Severity.INFO: "Информация",
        }[self]

    @property
    def order(self) -> int:
        return {
            Severity.CRITICAL: 0,
            Severity.IMPORTANT: 1,
            Severity.RECOMMENDATION: 2,
            Severity.INFO: 3,
        }[self]


class Category(str, Enum):
    """Блок проверок."""

    FZ152 = "152fz"
    ZOZPP = "zozpp"
    AD = "ad"
    TECH = "tech"

    @property
    def label_ru(self) -> str:
        return CATEGORY_LABELS[self.value]


CATEGORY_LABELS: dict[str, str] = {
    Category.FZ152.value: "152-ФЗ · Персональные данные",
    Category.ZOZPP.value: "ЗоЗПП · Права потребителей",
    Category.AD.value: "38-ФЗ · Реклама",
    Category.TECH.value: "Техническая гигиена",
}

CATEGORY_ORDER: list[str] = [
    Category.FZ152.value,
    Category.ZOZPP.value,
    Category.AD.value,
    Category.TECH.value,
]


# ---------------------------------------------------------------------------
# Подразделы внутри блоков: «наличие/формальности» и «содержание»
# ---------------------------------------------------------------------------


class CheckSection(str, Enum):
    """Подраздел проверки внутри блока."""

    PRESENCE = "presence"
    CONTENT = "content"

    @property
    def label_ru(self) -> str:
        return SECTION_LABELS[self.value]


SECTION_LABELS: dict[str, str] = {
    CheckSection.PRESENCE.value: "Наличие и формальности",
    CheckSection.CONTENT.value: "Содержание и полнота",
}

SECTION_ORDER: list[str] = [
    CheckSection.PRESENCE.value,
    CheckSection.CONTENT.value,
]

#: К какому подразделу относится каждая проверка.
CHECK_SECTIONS: dict[str, str] = {
    "a01_https": "presence",
    "a02_privacy_link": "presence",
    "a03_privacy_access": "presence",
    "a04_privacy_content": "content",
    "a05_forms_consent": "presence",
    "a06_consent_prechecked": "presence",
    "a07_separate_consent": "content",
    "a08_cookie_banner": "presence",
    "a09_cookie_categories": "content",
    "a10_foreign_trackers": "presence",
    "a11_pdn_contact": "presence",
    "a12_rkn_notice": "presence",
    "b13_seller_details": "content",
    "c14_erid": "content",
    "c15_ad_consent": "content",
    "d16_robots_sitemap": "presence",
    "d17_security_headers": "presence",
}


def check_section(check_id: str) -> str:
    """Подраздел проверки (по умолчанию — «наличие»)."""
    return CHECK_SECTIONS.get(check_id, CheckSection.PRESENCE.value)


def section_label(section: str) -> str:
    return SECTION_LABELS.get(section, section)


# ---------------------------------------------------------------------------
# Контекст сайта: вложенные модели
# ---------------------------------------------------------------------------


class HttpsInfo(BaseModel):
    """Данные о HTTPS/TLS."""

    requested_url: str = ""
    final_url: str = ""
    used_https: bool = False
    https_available: bool = False
    cert_valid: bool = True
    cert_error: str | None = None
    tls_version: str | None = None
    redirects_http_to_https: bool = False
    http_redirect_checked: bool = False
    http_status: int | None = None
    error: str | None = None


class LinkInfo(BaseModel):
    """Ссылка, найденная на странице."""

    href: str
    text: str = ""
    aria_label: str = ""
    rel: str = ""
    is_internal: bool = True
    in_footer: bool = False
    in_header: bool = False
    selector: str = ""

    @property
    def haystack(self) -> str:
        return f"{self.text} {self.aria_label} {self.href}".lower()


class ScriptInfo(BaseModel):
    """Скрипт на странице."""

    src: str | None = None
    inline_len: int = 0
    async_: bool = False


class TrackerInfo(BaseModel):
    """Сторонний трекер/скрипт."""

    domain: str
    kind: str = "analytics"  # analytics | advertising | social | other
    foreign: bool = True
    found_in: str = "script"  # script | img | iframe | link | request
    url: str = ""

    @property
    def title_ru(self) -> str:
        names = {
            "analytics": "аналитика",
            "advertising": "рекламный трекер",
            "social": "соцсеть/виджет",
            "other": "сторонний скрипт",
        }
        return names.get(self.kind, "сторонний скрипт")


class FormFieldInfo(BaseModel):
    """Поле ввода."""

    tag: str = "input"
    type: str = "text"
    name: str | None = None
    placeholder: str | None = None
    label_text: str = ""
    selector: str = ""
    required: bool = False
    checked: bool = False

    @property
    def is_personal_data(self) -> bool:
        if self.type in {"email", "tel", "password"}:
            return True
        hint = " ".join(
            x for x in (self.name or "", self.placeholder or "", self.label_text or "") if x
        ).lower()
        markers = (
            "name", "имя", "фио", "фамил", "телефон", "почт", "mail", "email",
            "адрес", "город", "логин", "пароль", "password", "phone", "tel",
        )
        return any(m in hint for m in markers)


class FormInfo(BaseModel):
    """Форма или группа полей."""

    selector: str = ""
    action: str | None = None
    method: str = "get"
    fields: list[FormFieldInfo] = Field(default_factory=list)
    context_text: str = ""  # видимый текст вокруг формы (нижний регистр)
    has_consent_checkbox: bool = False
    consent_checked: bool = False
    consent_text: str | None = None
    has_offer_checkbox: bool = False
    offer_checked: bool = False
    has_marketing_checkbox: bool = False
    marketing_checked: bool = False
    is_order_form: bool = False
    is_subscribe_form: bool = False
    is_standalone_fields: bool = False  # поля вне <form>
    url: str = ""

    @property
    def collects_personal_data(self) -> bool:
        return any(f.is_personal_data for f in self.fields)

    @property
    def has_any_checkbox(self) -> bool:
        return any(f.type in {"checkbox", "radio"} for f in self.fields)


class CookieBannerInfo(BaseModel):
    """Cookie-баннер / модалка согласия."""

    found: bool = False
    text: str = ""
    selector: str = ""
    has_accept: bool = False
    has_reject: bool = False
    has_settings: bool = False
    source: str = ""  # playwright | http | none
    screenshot: str | None = None


class PageInfo(BaseModel):
    """Дополнительно загруженная страница (политика, контакты и т.п.)."""

    key: str = ""
    url: str = ""
    status_code: int | None = None
    ok: bool = False
    title: str = ""
    text: str = ""
    error: str | None = None
    redirected_to_login: bool = False
    has_cookie_wall: bool = False


class RobotsInfo(BaseModel):
    found: bool = False
    status_code: int | None = None
    content: str = ""
    disallow_all: bool = False
    sitemaps: list[str] = Field(default_factory=list)
    error: str | None = None


class SitemapInfo(BaseModel):
    found: bool = False
    status_code: int | None = None
    url: str = ""
    url_count: int = 0
    is_index: bool = False
    error: str | None = None


class AdBlockInfo(BaseModel):
    """Рекламный блок на странице."""

    selector: str = ""
    text: str = ""
    has_ad_label: bool = False
    has_erid: bool = False
    erid_tokens: list[str] = Field(default_factory=list)


class SiteContext(BaseModel):
    """Всё, что сборщик узнал о сайте. Входные данные для всех проверок."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # --- базовая информация ---
    target_url: str = ""
    url: str = ""
    domain: str = ""
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status_code: int | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    html: str = ""
    text: str = ""  # видимый текст главной страницы, нижний регистр
    footer_text: str = ""  # видимый текст <footer>/низа страницы, нижний регистр
    title: str = ""
    language: str | None = None

    # --- техническое ---
    https: HttpsInfo = Field(default_factory=HttpsInfo)
    robots: RobotsInfo = Field(default_factory=RobotsInfo)
    sitemap: SitemapInfo = Field(default_factory=SitemapInfo)
    security_headers: dict[str, str | None] = Field(default_factory=dict)

    # --- содержимое ---
    links: list[LinkInfo] = Field(default_factory=list)
    scripts: list[ScriptInfo] = Field(default_factory=list)
    trackers: list[TrackerInfo] = Field(default_factory=list)
    forms: list[FormInfo] = Field(default_factory=list)
    pages: dict[str, PageInfo] = Field(default_factory=dict)
    privacy_link: LinkInfo | None = None
    cookie_banner: CookieBannerInfo = Field(default_factory=CookieBannerInfo)
    ad_blocks: list[AdBlockInfo] = Field(default_factory=list)
    erid_tokens: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)

    # --- признаки, вычисленные сборщиком ---
    has_prices: bool = False
    price_samples: list[str] = Field(default_factory=list)
    has_buy_buttons: bool = False
    buy_button_samples: list[str] = Field(default_factory=list)
    has_cart: bool = False
    has_order_form: bool = False
    has_subscribe_form: bool = False
    has_consent_checkbox: bool = False
    consent_checked: bool = False
    internal_links: int = 0
    external_links: int = 0

    # --- служебное ---
    deep_analysis: bool = False
    is_local: bool = False
    local_root: str = ""
    screenshots: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    fetch_failed: bool = False
    fetch_error: str | None = None

    _soup: Any = PrivateAttr(default=None)

    # ------------------------------------------------------------------
    # Помощники для проверок
    # ------------------------------------------------------------------
    @property
    def soup(self) -> Any:
        """BeautifulSoup-дерево главной страницы (лениво)."""
        if self._soup is None:
            from bs4 import BeautifulSoup

            self._soup = BeautifulSoup(self.html or "", "lxml")
        return self._soup

    def all_text(self, include_pages: bool = True) -> str:
        """Весь видимый текст: главная + загруженные страницы."""
        parts = [self.text, self.footer_text]
        if include_pages:
            parts.extend(p.text for p in self.pages.values())
        return "\n".join(p for p in parts if p)

    def page(self, key: str) -> PageInfo | None:
        return self.pages.get(key)

    @property
    def foreign_trackers(self) -> list[TrackerInfo]:
        return [t for t in self.trackers if t.foreign]

    @property
    def personal_data_forms(self) -> list[FormInfo]:
        return [f for f in self.forms if f.collects_personal_data]

    @property
    def consent_forms(self) -> list[FormInfo]:
        return [f for f in self.forms if f.has_consent_checkbox]

    @property
    def has_sales_signs(self) -> bool:
        return bool(
            self.has_prices
            or self.has_buy_buttons
            or self.has_cart
            or self.has_order_form
        )

    def note(self, message: str) -> None:
        if message not in self.notes:
            self.notes.append(message)


# ---------------------------------------------------------------------------
# Результаты
# ---------------------------------------------------------------------------


class Evidence(BaseModel):
    """Ссылка на конкретное место/факт, подтверждающий вывод проверки."""

    kind: str = "text"  # text | selector | url | header | screenshot | count
    label: str = ""
    value: str = ""
    selector: str | None = None

    @property
    def is_empty(self) -> bool:
        return not (self.value or "").strip()


class CheckResult(BaseModel):
    """Результат одной проверки."""

    check_id: str = ""
    title: str = ""
    category: str = Category.FZ152.value
    status: CheckStatus = CheckStatus.SKIP
    severity: Severity = Severity.INFO
    weight: int = 1
    message: str = ""
    recommendation: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    duration_ms: int = 0
    error: str | None = None

    @property
    def affects_score(self) -> bool:
        return self.status in (
            CheckStatus.PASS,
            CheckStatus.WARN,
            CheckStatus.FAIL,
        )

    @property
    def is_not_applicable(self) -> bool:
        return self.status is CheckStatus.NOT_APPLICABLE

    @property
    def status_label(self) -> str:
        return self.status.label_ru


class Report(BaseModel):
    """Итоговый отчёт по одному сайту."""

    url: str = ""
    final_url: str = ""
    scanned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    score: int = 0
    results: list[CheckResult] = Field(default_factory=list)
    deep_analysis: bool = False
    is_local: bool = False
    app_version: str = ""
    duration_ms: int = 0
    notes: list[str] = Field(default_factory=list)

    # ------------------------------------------------------------------
    def by_status(self, status: CheckStatus) -> list[CheckResult]:
        return [r for r in self.results if r.status is status]

    def applicable(self) -> list[CheckResult]:
        return [r for r in self.results if r.affects_score]

    def not_applicable(self) -> list[CheckResult]:
        return self.by_status(CheckStatus.NOT_APPLICABLE)

    def skipped(self) -> list[CheckResult]:
        return self.by_status(CheckStatus.SKIP)

    def problems(self) -> list[CheckResult]:
        items = [r for r in self.results if r.status in (CheckStatus.FAIL, CheckStatus.WARN)]
        return sorted(items, key=lambda r: (r.status is CheckStatus.WARN, r.severity.order))

    def counts(self) -> dict[str, int]:
        out = {s.value: 0 for s in CheckStatus}
        for r in self.results:
            out[r.status.value] += 1
        return out

    def grouped(self) -> list[tuple[str, list[CheckResult]]]:
        """Проверки, сгруппированные по блокам в фиксированном порядке."""
        groups: dict[str, list[CheckResult]] = {}
        for r in self.results:
            groups.setdefault(r.category, []).append(r)
        ordered: list[tuple[str, list[CheckResult]]] = []
        for cat in CATEGORY_ORDER:
            if cat in groups:
                ordered.append((cat, groups[cat]))
        for cat, items in groups.items():
            if cat not in CATEGORY_ORDER:
                ordered.append((cat, items))
        return ordered

    def grouped_by_section(
        self,
    ) -> list[tuple[str, list[tuple[str, list[CheckResult]]]]]:
        """Блок → подразделы («Наличие и формальности» / «Содержание»)."""
        result: list[tuple[str, list[tuple[str, list[CheckResult]]]]] = []
        for category, items in self.grouped():
            buckets: dict[str, list[CheckResult]] = {}
            for item in items:
                buckets.setdefault(check_section(item.check_id), []).append(item)
            sections: list[tuple[str, list[CheckResult]]] = [
                (section, buckets[section]) for section in SECTION_ORDER if section in buckets
            ]
            for section, bucket in buckets.items():
                if section not in SECTION_ORDER:
                    sections.append((section, bucket))
            result.append((category, sections))
        return result

    def score_breakdown(self) -> dict[str, int]:
        """Вклад блоков: сколько проверок пройдено/всего."""
        out: dict[str, int] = {}
        for cat, items in self.grouped():
            out[cat] = len([r for r in items if r.affects_score])
        return out


# ---------------------------------------------------------------------------
# Опции запуска проверки
# ---------------------------------------------------------------------------


class RunOptions(BaseModel):
    """Опции одного запуска (UI-чекбоксы + настройки)."""

    deep_analysis: bool = True
    check_trackers: bool = True
    show_na: bool = True
    timeout: float = 15.0
    user_agent: str = ""
    max_html_bytes: int = 5 * 1024 * 1024
    max_pages: int = 4
    save_screenshots: bool = True
    screenshot_dir: str | None = None
    language: str = "ru"
    allow_http_fallback: bool = True
