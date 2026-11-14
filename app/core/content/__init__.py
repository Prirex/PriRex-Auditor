"""Справочные данные приложения: методология проверок и описание работы."""

from app.core.content.loader import (
    how_it_works_error,
    load_how_it_works,
    load_methodology,
    methodology_error,
    methodology_for,
    methodology_updated_at,
)
from app.core.content.models import (
    HowItWorks,
    HowItWorksSection,
    Methodology,
    MethodologyBlock,
    MethodologyCheck,
)

__all__ = [
    "HowItWorks",
    "HowItWorksSection",
    "Methodology",
    "MethodologyBlock",
    "MethodologyCheck",
    "how_it_works_error",
    "load_how_it_works",
    "load_methodology",
    "methodology_error",
    "methodology_for",
    "methodology_updated_at",
]
