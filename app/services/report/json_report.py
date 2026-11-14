"""Экспорт отчёта в JSON — для интеграций и собственных инструментов.

Отдаём полный ``model_dump(mode="json")`` отчёта плюс служебные поля
``generated_by``, ``disclaimer`` и ссылки на методологию. Файл читаемый:
``ensure_ascii=False``, ``indent=2``.
"""

from __future__ import annotations

import json

from app.core.models import Report
from app.services.report.common import (
    DISCLAIMER_TEXT,
    methodology_id,
    methodology_updated_at,
    report_meta,
)


def build_json(report: Report) -> str:
    """Сериализовать отчёт в JSON-строку (UTF-8, кириллица как есть)."""
    meta = report_meta(report)
    payload = report.model_dump(mode="json")
    payload["generated_by"] = meta.generated_by
    payload["disclaimer"] = DISCLAIMER_TEXT
    payload["methodology_updated_at"] = methodology_updated_at()

    results = payload.get("results")
    if isinstance(results, list):
        for item, result in zip(results, report.results):
            if not isinstance(item, dict):
                continue
            number = methodology_id(result.check_id)
            if number:
                item["methodology_id"] = number
    return json.dumps(payload, ensure_ascii=False, indent=2)


__all__ = ["build_json"]
