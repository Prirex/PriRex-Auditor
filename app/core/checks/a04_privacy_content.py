"""A04. Политика — содержание (152-ФЗ, ст. 18.1).

Эвристика по 7 ключевым разделам политики: оператор, персональные данные,
цели обработки, срок хранения, права субъекта, отзыв согласия, cookie.
>= 5 маркеров — pass, 3–4 — warn, < 3 — fail. Без текста — skip.
"""

from __future__ import annotations

from app.core.checks.base import BaseCheck
from app.core.detect import (
    PRIVACY_CONTENT_MARKERS,
    normalize_text,
    privacy_markers_found,
)
from app.core.models import Category, CheckResult, Severity, SiteContext


class PrivacyContentCheck(BaseCheck):
    id = "a04_privacy_content"
    title = "Политика — содержание"
    category = Category.FZ152.value
    weight = 7
    severity = Severity.IMPORTANT
    recommendation = (
        "Приведите политику в соответствие со ст. 18.1 152-ФЗ: укажите оператора, "
        "цели и сроки обработки, права субъекта, порядок отзыва согласия и "
        "использование cookie."
    )

    def evaluate(self, ctx: SiteContext) -> CheckResult:
        page = ctx.pages.get("privacy")
        if page is None:
            return self.skip(
                "Страница политики не загружена — проверить содержание политики нельзя."
            )

        text = (page.text or "").strip()
        if not text:
            return self.skip(
                "Текст политики пуст или не извлечён — проверить содержание политики "
                "нельзя.",
                evidence=[
                    self.ev("Страница политики", page.url or "—", kind="url"),
                ],
            )

        found = privacy_markers_found(text)
        missing = [name for name in PRIVACY_CONTENT_MARKERS if name not in found]
        evidence = [
            self.ev(
                "Найденные разделы",
                ", ".join(found) if found else "ничего не найдено",
            ),
            self.ev(
                "Отсутствующие разделы",
                ", ".join(missing) if missing else "нет",
            ),
            self.ev("Страница политики", page.url or "—", kind="url"),
            self.ev("Фрагмент политики", normalize_text(text, 300)),
        ]

        count = len(found)
        missing_text = ", ".join(missing) if missing else "нет"

        if count >= 5:
            return self.ok(
                f"В тексте политики найдены ключевые разделы ({count} из 7): "
                f"{', '.join(found)}."
                + (f" Не найдены: {missing_text}." if missing else ""),
                recommendation="",
                evidence=evidence,
            )

        if count >= 3:
            return self.warn(
                f"В политике найдено только {count} из 7 ключевых разделов: "
                f"{', '.join(found)}. Не хватает: {missing_text}.",
                severity=Severity.IMPORTANT,
                recommendation=(
                    "Дополните политику отсутствующими разделами: "
                    f"{missing_text} (ст. 18.1 152-ФЗ)."
                ),
                evidence=evidence,
            )

        return self.fail(
            f"Политика содержит лишь {count} из 7 ключевых разделов"
            + (f" ({', '.join(found)})" if found else " (ни одного маркера)")
            + f". Отсутствуют: {missing_text}. Содержание политики недостаточно "
            "для информирования субъекта ПДн.",
            recommendation=self.recommendation,
            evidence=evidence,
        )
