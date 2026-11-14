"""Pydantic-модели справочных данных: методология и «Как работает приложение».

Тексты живут в JSON (``assets/methodology.json``, ``assets/how_it_works.json``),
а не в коде. Модели валидируют файлы при загрузке; битый файл не роняет
приложение — раздел просто показывает «описание временно недоступно».
"""

from __future__ import annotations

from pydantic import BaseModel, Field

#: Известные значения поля applicability.
APPLICABILITY_VALUES: tuple[str, ...] = (
    "always",
    "sales",
    "ads",
    "subscribe_forms",
    "trackers",
    "consent_checkbox",
    "cookie_banner",
    "privacy_page",
    "policy_loaded",
)


class MethodologyCheck(BaseModel):
    """Описание одной проверки в справочнике «Критерии проверок»."""

    id: str  # «4.2» — номер по ТЗ
    check_id: str = ""  # «a02_privacy_link» — реальный id проверки
    title: str
    applicability: str = "always"
    applicability_note: str = ""
    what: str = ""
    legal_basis: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
    normal: list[str] = Field(default_factory=list)
    not_applicable_note: str | None = None
    recommendation: list[str] = Field(default_factory=list)
    # Потенциальная административная ответственность (оценка по КоАП РФ).
    fine_individual: str = ""
    fine_legal: str = ""
    fine_basis: str = ""
    fine_note: str = ""

    @property
    def has_fines(self) -> bool:
        return bool(self.fine_individual or self.fine_legal)

    def fine_rows(self) -> list[tuple[str, str]]:
        """Пары «для кого → сумма» для блока штрафа."""
        rows: list[tuple[str, str]] = []
        if self.fine_individual:
            rows.append(("Для физлица", self.fine_individual))
        if self.fine_legal:
            rows.append(("Для юрлица", self.fine_legal))
        return rows

    @property
    def legal_basis_text(self) -> str:
        if not self.legal_basis:
            return "Норма: требует уточнения юристом"
        if all(item.strip().lower() in {"уточнить", "?"} for item in self.legal_basis):
            return "Норма: требует уточнения юристом"
        return "; ".join(self.legal_basis)

    def as_markdown(self) -> str:
        """Полное описание в Markdown (для «Копировать описание» и отчёта)."""
        lines = [f"## {self.id}. {self.title}", ""]
        if self.applicability_note:
            lines += [f"**Применимость:** {self.applicability_note}", ""]
        if self.what:
            lines += ["**Что проверяется.** " + self.what, ""]
        if self.legal_basis:
            lines += [f"**Правовое основание:** {self.legal_basis_text}", ""]
        if self.violations:
            lines.append("**Что считается нарушением:**")
            lines += [f"- {item}" for item in self.violations]
            lines.append("")
        if self.normal:
            lines.append("**Что считается нормой:**")
            lines += [f"- {item}" for item in self.normal]
            lines.append("")
        if self.not_applicable_note:
            lines += [f"**Когда не применимо (N/A):** {self.not_applicable_note}", ""]
        if self.has_fines:
            lines.append("**Потенциальная сумма штрафа:**")
            fines: list[str] = []
            if self.fine_individual:
                fines.append(f"для физлица — {self.fine_individual}")
            if self.fine_legal:
                fines.append(f"для юрлица — {self.fine_legal}")
            lines += [f"- {item}" for item in fines]
            if self.fine_basis:
                lines.append(f"- основание: {self.fine_basis}")
            lines.append("")
        if self.recommendation:
            lines.append("**Рекомендация по исправлению:**")
            lines += [f"- {item}" for item in self.recommendation]
            lines.append("")
        return "\n".join(lines).strip() + "\n"


class MethodologyBlock(BaseModel):
    """Блок проверок (A — 152-ФЗ, B — ЗоЗПП, C — реклама, D — технологии)."""

    id: str
    title: str
    checks: list[MethodologyCheck] = Field(default_factory=list)


class Methodology(BaseModel):
    """Справочник по методологии проверок."""

    version: str = "1.0"
    updated_at: str = ""  # «14.11.2026» — дата актуальности текстов
    intro: str = ""
    blocks: list[MethodologyBlock] = Field(default_factory=list)

    def all_checks(self) -> list[MethodologyCheck]:
        return [check for block in self.blocks for check in block.checks]

    def find(self, key: str) -> MethodologyCheck | None:
        """Ищет проверку по номеру («4.2») или по id проверки («a02_privacy_link»)."""
        if not key:
            return None
        key = key.strip()
        for check in self.all_checks():
            if key in {check.id, check.check_id}:
                return check
        return None

    def block_for(self, check: MethodologyCheck) -> MethodologyBlock | None:
        for block in self.blocks:
            if check in block.checks:
                return block
        return None

    def missing_check_ids(self, expected: list[str]) -> list[str]:
        """Каких реальных проверок нет в методологии."""
        present = {check.check_id for check in self.all_checks()}
        return [check_id for check_id in expected if check_id not in present]


class HowItWorksSection(BaseModel):
    """Раздел окна «Как работает приложение»."""

    id: str
    title: str
    content_md: str = ""


class HowItWorks(BaseModel):
    """Описание механики работы приложения."""

    version: str = "1.0"
    updated_at: str = ""
    sections: list[HowItWorksSection] = Field(default_factory=list)

    def find(self, section_id: str) -> HowItWorksSection | None:
        for section in self.sections:
            if section.id == section_id:
                return section
        return None


__all__ = [
    "APPLICABILITY_VALUES",
    "HowItWorks",
    "HowItWorksSection",
    "Methodology",
    "MethodologyBlock",
    "MethodologyCheck",
]
