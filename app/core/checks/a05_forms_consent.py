"""A05. Формы сбора данных и чекбокс согласия (152-ФЗ, ч. 1 ст. 9).

Ищем формы (и группы полей вне ``<form>``), которые собирают персональные
данные, и проверяем, есть ли в них чекбокс согласия на обработку ПДн.
"""

from __future__ import annotations

from app.core.checks.base import BaseCheck
from app.core.models import Category, CheckResult, FormInfo, Severity, SiteContext


def _fields_summary(form: FormInfo) -> str:
    """Короткое описание полей, из-за которых форма считается сбором ПДн."""
    names: list[str] = []
    for item in form.fields:
        if not item.is_personal_data:
            continue
        hint = item.name or item.placeholder or item.label_text or item.type
        if hint and hint not in names:
            names.append(hint)
    return ", ".join(names[:6])


class FormsConsentCheck(BaseCheck):
    id = "a05_forms_consent"
    title = "Формы сбора данных и чекбокс согласия"
    category = Category.FZ152.value
    weight = 8
    severity = Severity.CRITICAL
    recommendation = (
        "Добавьте в каждую форму сбора персональных данных отдельный чекбокс "
        "«Согласен на обработку персональных данных» со ссылкой на политику. "
        "Согласие должно быть конкретным, предметным и информированным "
        "(ч. 1 ст. 9 152-ФЗ)."
    )

    def evaluate(self, ctx: SiteContext) -> CheckResult:
        forms = [item for item in ctx.forms if item.collects_personal_data]

        if not forms:
            return self.na(
                "На сайте не обнаружены формы сбора персональных данных. "
                "Проверка согласия не требуется."
            )

        broken = [item for item in forms if not item.has_consent_checkbox]
        if broken:
            evidence = []
            parts: list[str] = []
            for item in broken[:5]:
                selector = item.selector or "форма без селектора"
                suffix = " (поля вне <form>)" if item.is_standalone_fields else ""
                fields = _fields_summary(item)
                parts.append(
                    selector + suffix + (f" (поля: {fields})" if fields else "")
                )
                evidence.append(
                    self.ev(
                        "Форма без согласия",
                        selector,
                        selector=item.selector or None,
                        kind="selector",
                    )
                )
                if fields:
                    evidence.append(
                        self.ev(
                            "Поля формы",
                            fields,
                            selector=item.selector or None,
                        )
                    )
            hidden = len(broken) - len(parts)
            if hidden > 0:
                parts.append(f"и ещё {hidden}")

            return self.fail(
                "Форм сбора персональных данных без чекбокса согласия: "
                f"{len(broken)} из {len(forms)}. "
                + "; ".join(parts)
                + ". Персональные данные собираются без согласия субъекта "
                "(ч. 1 ст. 9 152-ФЗ).",
                recommendation=self.recommendation,
                evidence=evidence,
            )

        evidence = [
            self.ev(
                "Форма с чекбоксом согласия",
                item.selector or "форма без селектора",
                selector=item.selector or None,
                kind="selector",
            )
            for item in forms[:5]
        ]
        return self.ok(
            f"Все формы сбора персональных данных ({len(forms)}) содержат чекбокс "
            "согласия на обработку ПДн.",
            recommendation="",
            evidence=evidence,
        )
