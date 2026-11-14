"""C14. Маркировка интернет-рекламы (ERID, 38-ФЗ).

Применимо только к страницам, где сборщик контекста обнаружил рекламные
блоки. Если рекламы нет — ``not_applicable``, а не ``fail``.
"""

from __future__ import annotations

import re

from app.core.checks.base import BaseCheck
from app.core.detect import (
    AD_LABEL_MARKERS,
    extract_erid_tokens,
    has_any,
)
from app.core.models import (
    AdBlockInfo,
    Category,
    CheckResult,
    Evidence,
    Severity,
    SiteContext,
)

NA_MESSAGE = "На странице не обнаружены рекламные блоки. Маркировка ERID не требуется."

_WS_RE = re.compile(r"\s+")


def _snippet(text: str, limit: int = 120) -> str:
    """Фрагмент текста блока для evidence (до 120 символов)."""
    cleaned = _WS_RE.sub(" ", text or "").strip()
    return cleaned[:limit]


def _has_ad_label(block: AdBlockInfo) -> bool:
    """Пометка о рекламе: флаг сборщика или маркер в тексте блока."""
    return bool(block.has_ad_label or has_any(block.text, AD_LABEL_MARKERS))


def _block_tokens(block: AdBlockInfo) -> list[str]:
    """Токены ERID: из данных сборщика, иначе — из текста блока."""
    tokens = list(block.erid_tokens)
    if not tokens:
        tokens = extract_erid_tokens(block.text)
    return tokens


def _problem_description(has_label: bool, has_token: bool) -> str:
    if not has_label and not has_token:
        return "рекламный блок без пометки «Реклама» и без токена erid"
    if not has_label:
        return "рекламный блок без пометки «Реклама»"
    return "в рекламном блоке есть пометка «Реклама», но нет токена erid"


class EridMarkingCheck(BaseCheck):
    """Проверка пометки «Реклама» и токена erid в рекламных блоках."""

    id = "c14_erid"
    title = "Маркировка интернет-рекламы (ERID)"
    category = Category.AD.value
    weight = 6
    severity = Severity.IMPORTANT
    recommendation = (
        "Для каждого рекламного блока добавьте пометку «Реклама» и токен erid "
        "(в текст, ссылку вида ?erid=… или в атрибуты), как требует ст. 18.1 "
        "38-ФЗ. Маркировка должна быть видна пользователю до перехода по рекламе."
    )

    def evaluate(self, ctx: SiteContext) -> CheckResult:
        if not ctx.ad_blocks:
            return self.na(NA_MESSAGE)

        total = len(ctx.ad_blocks)
        problems: list[tuple[AdBlockInfo, str, list[str]]] = []
        good: list[tuple[AdBlockInfo, list[str]]] = []

        for block in ctx.ad_blocks:
            has_label = _has_ad_label(block)
            tokens = _block_tokens(block)
            has_token = bool(tokens or block.has_erid)
            if has_label and has_token:
                good.append((block, tokens))
            else:
                problems.append(
                    (
                        block,
                        _problem_description(has_label, has_token),
                        tokens,
                    )
                )

        if problems:
            parts: list[str] = []
            for block, description, _tokens in problems[:10]:
                selector = block.selector or "рекламный блок"
                parts.append(f"{description} (селектор: {selector})")
            message = "Нарушена маркировка интернет-рекламы: " + "; ".join(parts) + "."
            if good:
                message += (
                    f" Корректно размечено блоков: {len(good)} из {total}."
                )
            evidence: list[Evidence] = []
            for block, description, tokens in problems[:10]:
                evidence.append(
                    self.ev(
                        description,
                        _snippet(block.text),
                        selector=block.selector or None,
                        kind="selector",
                    )
                )
                if tokens:
                    evidence.append(
                        self.ev(
                            "Найденный ERID",
                            ", ".join(tokens),
                            selector=block.selector or None,
                        )
                    )
            for block, tokens in good[:5]:
                evidence.append(
                    self.ev(
                        "Рекламный блок размечен",
                        _snippet(block.text),
                        selector=block.selector or None,
                        kind="selector",
                    )
                )
                if tokens:
                    evidence.append(
                        self.ev(
                            "Токен erid",
                            ", ".join(tokens),
                            selector=block.selector or None,
                        )
                    )
            return self.fail(
                message,
                severity=Severity.IMPORTANT,
                evidence=evidence,
            )

        evidence = []
        for block, tokens in good:
            evidence.append(
                self.ev(
                    "Рекламный блок с пометкой и ERID",
                    _snippet(block.text),
                    selector=block.selector or None,
                    kind="selector",
                )
            )
            if tokens:
                evidence.append(
                    self.ev(
                        "Токен erid",
                        ", ".join(tokens),
                        selector=block.selector or None,
                    )
                )
        return self.ok(
            f"Все рекламные блоки ({total}) имеют пометку «Реклама» и токен erid.",
            evidence=evidence,
        )
