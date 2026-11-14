"""Валидация справочных JSON: методология проверок и «Как работает приложение».

Тесты офлайновые: читают файлы напрямую из ``assets``, валидируют их
pydantic-моделями и сверяют набор проверок с реальным реестром приложения.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.checks import ALL_CHECKS
from app.core.content import (
    HowItWorks,
    Methodology,
    load_how_it_works,
    load_methodology,
    methodology_updated_at,
)
from app.core.content.loader import reload
from app.core.content.models import APPLICABILITY_VALUES

ROOT = Path(__file__).resolve().parents[1]
METHODOLOGY_PATH = ROOT / "assets" / "methodology.json"
HOW_IT_WORKS_PATH = ROOT / "assets" / "how_it_works.json"

EXPECTED_CHECK_IDS = [f"4.{number}" for number in range(1, 18)]
EXPECTED_BLOCK_LAYOUT = {"A": 12, "B": 1, "C": 2, "D": 2}
EXPECTED_SECTION_IDS = [
    "what_it_does",
    "technologies",
    "how_scan_works",
    "sees_vs_not",
    "limitations",
    "security",
    "faq",
]


def read_json(path: Path) -> tuple[str, dict]:
    """Сырой текст и разобранный JSON (кириллица — без экранирования)."""
    assert path.is_file(), f"Нет файла {path}"
    raw = path.read_text(encoding="utf-8")
    assert raw.strip(), f"Пустой файл {path.name}"
    assert not raw.startswith("\ufeff"), f"В {path.name} есть BOM"
    return raw, json.loads(raw)


def load_methodology_model() -> Methodology:
    _, data = read_json(METHODOLOGY_PATH)
    return Methodology(**data)


def load_how_it_works_model() -> HowItWorks:
    _, data = read_json(HOW_IT_WORKS_PATH)
    return HowItWorks(**data)


# ---------------------------------------------------------------------------
# Структура и валидация
# ---------------------------------------------------------------------------


def test_methodology_json_is_valid() -> None:
    methodology = load_methodology_model()
    assert methodology.version == "1.0"
    assert methodology.updated_at == "14.11.2026"
    assert methodology.intro.strip()
    assert len(methodology.blocks) == 4


def test_how_it_works_json_is_valid() -> None:
    how_it_works = load_how_it_works_model()
    assert how_it_works.version == "1.0"
    assert how_it_works.updated_at == "14.11.2026"
    assert len(how_it_works.sections) == 7


def test_methodology_has_all_17_checks_in_order() -> None:
    methodology = load_methodology_model()
    checks = methodology.all_checks()

    assert len(checks) == 17
    assert [check.id for check in checks] == EXPECTED_CHECK_IDS

    check_ids = [check.check_id for check in checks]
    assert len(check_ids) == len(set(check_ids)), "check_id должны быть уникальны"
    assert set(check_ids) == {check.id for check in ALL_CHECKS}


def test_methodology_blocks_match_expected_layout() -> None:
    methodology = load_methodology_model()
    blocks = {block.id: block for block in methodology.blocks}

    assert list(blocks) == ["A", "B", "C", "D"], "Порядок блоков A → B → C → D"
    assert {block_id: len(block.checks) for block_id, block in blocks.items()} == (
        EXPECTED_BLOCK_LAYOUT
    )


@pytest.mark.parametrize("block_id", ["A", "B", "C", "D"])
def test_methodology_block_checks_are_valid(block_id: str) -> None:
    methodology = load_methodology_model()
    block = next(block for block in methodology.blocks if block.id == block_id)

    for check in block.checks:
        assert check.id.strip()
        assert check.check_id.strip()
        assert check.title.strip()
        assert check.what.strip()
        assert check.applicability_note.strip()
        assert check.legal_basis, f"{check.id}: пустой legal_basis"
        assert all(item.strip() for item in check.legal_basis)

        assert check.applicability in set(APPLICABILITY_VALUES), (
            f"{check.id}: неизвестная применимость {check.applicability!r}"
        )

        assert 2 <= len(check.violations) <= 5, f"{check.id}: нужно 2–5 нарушений"
        assert all(item.strip() for item in check.violations)
        assert 2 <= len(check.normal) <= 4, f"{check.id}: нужно 2–4 пункта нормы"
        assert all(item.strip() for item in check.normal)
        assert 2 <= len(check.recommendation) <= 4, (
            f"{check.id}: нужно 2–4 рекомендации"
        )
        assert all(item.strip() for item in check.recommendation)

        if check.applicability == "always":
            assert check.not_applicable_note is None, (
                f"{check.id}: для always not_applicable_note должен быть null"
            )
        else:
            assert check.not_applicable_note, (
                f"{check.id}: для условной проверки нужен not_applicable_note"
            )

        for field in ("title", "what", "applicability_note"):
            assert "\n" not in getattr(check, field), (
                f"{check.id}: перенос строки в поле {field}"
            )


def test_methodology_fine_fields_are_complete() -> None:
    methodology = load_methodology_model()

    for check in methodology.all_checks():
        for field in ("fine_individual", "fine_legal", "fine_basis", "fine_note"):
            value = getattr(check, field)
            assert isinstance(value, str), f"{check.id}: {field} должен быть строкой"
            assert value.strip(), f"{check.id}: пустое поле {field}"

        for field in ("fine_individual", "fine_legal"):
            value = getattr(check, field)
            assert "₽" in value or "прямого штрафа нет" in value.lower(), (
                f"{check.id}: в {field} нужна сумма в рублях или прямая пометка "
                "об отсутствии штрафа"
            )


def test_how_it_works_sections_are_complete() -> None:
    how_it_works = load_how_it_works_model()

    assert [section.id for section in how_it_works.sections] == EXPECTED_SECTION_IDS
    for section in how_it_works.sections:
        assert section.title.strip()
        assert section.content_md.strip(), f"{section.id}: пустой content_md"
        assert len(section.content_md.strip()) > 150, (
            f"{section.id}: content_md слишком короткий"
        )


# ---------------------------------------------------------------------------
# Загрузчик приложения
# ---------------------------------------------------------------------------


def test_loader_reads_both_assets() -> None:
    reload()

    assert load_methodology() is not None
    assert load_how_it_works() is not None
    assert methodology_updated_at() == "14.11.2026"


def test_loader_reads_fine_fields() -> None:
    reload()
    methodology = load_methodology()
    assert methodology is not None

    for check in methodology.all_checks():
        assert check.fine_individual.strip()
        assert check.fine_legal.strip()
        assert check.fine_basis.strip()
        assert check.fine_note.strip()


# ---------------------------------------------------------------------------
# Качество данных
# ---------------------------------------------------------------------------


def iter_strings(value: object):
    """Все строки внутри разобранного JSON (рекурсивно)."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)


def test_json_has_no_placeholders_or_broken_layout() -> None:
    for path in (METHODOLOGY_PATH, HOW_IT_WORKS_PATH):
        raw, data = read_json(path)
        low = raw.lower()

        assert "todo" not in low, f"{path.name}: остался TODO"
        assert "заглушка" not in low, f"{path.name}: осталась заглушка"
        assert "\n\n\n" not in raw, f"{path.name}: двойная пустая строка в JSON"

        for text in iter_strings(data):
            assert "todo" not in text.lower(), f"{path.name}: TODO в тексте"
            assert "заглушка" not in text.lower(), f"{path.name}: заглушка в тексте"
            assert "\n\n\n" not in text, f"{path.name}: три переноса строки подряд"
