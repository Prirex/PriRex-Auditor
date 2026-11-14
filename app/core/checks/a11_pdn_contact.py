"""A11. Контакт для обращений субъектов ПДн (152-ФЗ).

Субъект должен иметь возможность обратиться к оператору: email, mailto-ссылка,
форма обратной связи или страница «Контакты».
"""

from __future__ import annotations

from app.core.checks.base import BaseCheck
from app.core.models import Category, CheckResult, FormInfo, Severity, SiteContext

#: Признаки ссылки на страницу контактов.
_CONTACT_LINK_MARKERS: tuple[str, ...] = (
    "контакт",
    "contact",
    "связаться",
    "обратная связь",
    "обратную связь",
    "написать нам",
)

#: Признаки формы обратной связи.
_FEEDBACK_FORM_MARKERS: tuple[str, ...] = (
    "обратн",
    "связ",
    "feedback",
    "contact",
    "вопрос",
    "сообщени",
    "комментар",
    "support",
)


def _is_feedback_form(form: FormInfo) -> bool:
    haystack = " ".join(
        part for part in (form.selector, form.action or "", form.context_text) if part
    ).lower()
    if any(marker in haystack for marker in _FEEDBACK_FORM_MARKERS):
        return True
    hints = " ".join(
        part
        for item in form.fields
        for part in (item.name or "", item.placeholder or "", item.label_text or "")
    ).lower()
    if any(marker in hints for marker in _FEEDBACK_FORM_MARKERS):
        return True
    return any((item.tag or "").lower() == "textarea" for item in form.fields)


class PdnContactCheck(BaseCheck):
    id = "a11_pdn_contact"
    title = "Контакт для обращений субъектов ПДн"
    category = Category.FZ152.value
    weight = 5
    severity = Severity.IMPORTANT
    recommendation = (
        "Опубликуйте контактный email и/или форму обратной связи, а также "
        "страницу «Контакты». Субъект ПДн должен иметь возможность реализовать "
        "права на доступ, уточнение и отзыв согласия (ст. 14, ч. 2 ст. 18.1 152-ФЗ)."
    )

    def evaluate(self, ctx: SiteContext) -> CheckResult:
        channels: list[str] = []
        evidence = []

        def add_channel(channel: str) -> None:
            if channel not in channels:
                channels.append(channel)

        emails = [item for item in ctx.emails if item and "@" in item]
        if emails:
            add_channel("email: " + ", ".join(emails[:3]))
            evidence.append(self.ev("Email на сайте", ", ".join(emails[:5])))

        mailto_links = [
            item
            for item in ctx.links
            if (item.href or "").lower().startswith("mailto:")
        ]
        if mailto_links:
            addresses = [
                item.href.split(":", 1)[1].split("?", 1)[0]
                for item in mailto_links[:3]
            ]
            add_channel("mailto: " + ", ".join(addresses))
            evidence.append(
                self.ev(
                    "Ссылка mailto",
                    mailto_links[0].href,
                    selector=mailto_links[0].selector or None,
                    kind="url",
                )
            )

        contact_page = None
        for key in ("contacts", "contact"):
            candidate = ctx.pages.get(key)
            if candidate is not None and candidate.ok:
                contact_page = candidate
                break
        if contact_page is not None:
            add_channel(f"страница «Контакты»: {contact_page.url or '—'}")
            evidence.append(
                self.ev("Страница «Контакты»", contact_page.url or "—", kind="url")
            )

        contact_links = [
            item
            for item in ctx.links
            if not (item.href or "").lower().startswith("mailto:")
            and any(
                marker
                in f"{item.text} {item.aria_label} {item.href}".lower()
                for marker in _CONTACT_LINK_MARKERS
            )
        ]
        if contact_links:
            add_channel("ссылка на контакты: " + contact_links[0].href)
            evidence.append(
                self.ev(
                    "Ссылка на контакты",
                    contact_links[0].href,
                    selector=contact_links[0].selector or None,
                    kind="url",
                )
            )

        feedback_forms = [
            item
            for item in ctx.forms
            if item.collects_personal_data and _is_feedback_form(item)
        ]
        if feedback_forms:
            selectors = [item.selector or "форма без селектора" for item in feedback_forms[:5]]
            add_channel("форма обратной связи: " + ", ".join(selectors))
            evidence.extend(
                self.ev(
                    "Форма обратной связи",
                    item.selector or "форма без селектора",
                    selector=item.selector or None,
                    kind="selector",
                )
                for item in feedback_forms[:5]
            )

        if not channels:
            return self.fail(
                "На сайте не найден ни один способ обращения субъекта ПДн: нет "
                "email, mailto-ссылки, формы обратной связи и страницы «Контакты». "
                "Субъект не может реализовать права на доступ, уточнение данных "
                "и отзыв согласия.",
                recommendation=self.recommendation,
            )

        return self.ok(
            "Найдены способы обращения субъекта ПДн: " + "; ".join(channels[:6]) + ".",
            recommendation="",
            evidence=evidence,
        )
