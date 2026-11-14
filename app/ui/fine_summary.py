"""Карточка «Итого по сайту: возможные штрафы».

Показывает суммарный потенциальный штраф по всем выявленным нарушениям и
замечаниям — отдельно для физического и юридического лица. Стоит внизу правой
колонки, под панелью деталей, и всегда виден после проверки.
"""

from __future__ import annotations

from html import escape as html_escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from app.core.engine.fines import FineSummary, site_fine_summary
from app.core.models import Report
from app.i18n import tr
from app.ui.theme import PALETTE


class FineSummaryCard(QFrame):
    """Итоговая сумма штрафов по сайту (физлицо и юрлицо)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(5)

        self.title_label = QLabel(tr("ИТОГО ПО САЙТУ: ВОЗМОЖНЫЕ ШТРАФЫ"), self)
        self.title_label.setObjectName("InfoSectionLabel")
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.title_label)

        self.individual_label = QLabel(self)
        self.individual_label.setObjectName("DetailMuted")
        self.individual_label.setTextFormat(Qt.TextFormat.RichText)
        self.individual_label.setWordWrap(True)
        self.individual_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.individual_label)

        self.legal_label = QLabel(self)
        self.legal_label.setObjectName("DetailMuted")
        self.legal_label.setTextFormat(Qt.TextFormat.RichText)
        self.legal_label.setWordWrap(True)
        self.legal_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.legal_label)

        self.note_label = QLabel(self)
        self.note_label.setObjectName("Hint")
        self.note_label.setTextFormat(Qt.TextFormat.RichText)
        self.note_label.setWordWrap(True)
        layout.addWidget(self.note_label)

        self._summary: FineSummary | None = None
        self.set_report(None)

    # ------------------------------------------------------------------
    @property
    def summary(self) -> FineSummary | None:
        """Последний рассчитанный итог (для тестов и отчётов)."""
        return self._summary

    def set_report(
        self,
        report: Report | None,
        summary: FineSummary | None = None,
    ) -> None:
        """Пересчитывает и показывает итог; без отчёта карточка скрыта."""
        if report is None:
            self._summary = None
            self.hide()
            return

        data = summary if summary is not None else site_fine_summary(report.results)
        self._summary = data

        amount_color = PALETTE.get("fail", "#B87A6E")
        caption_color = PALETTE["text_muted"]

        def row_html(caption: str, amount: str) -> str:
            return (
                f'<span style="color:{caption_color};">{html_escape(caption)}'
                "</span>"
                f'<span style="color:{amount_color};font-weight:600;">'
                f"{html_escape(amount)}</span>"
            )

        self.individual_label.setText(
            row_html(tr("Для физлица — "), data.individual.format())
        )
        self.legal_label.setText(row_html(tr("Для юрлица — "), data.legal.format()))
        self.note_label.setText(
            f'<span style="font-size:10px;color:{PALETTE["text_dim"]};">'
            f"{html_escape(data.note())}</span>"
        )
        if data.checks:
            self.setToolTip(
                tr("Учтены проверки") + ": " + "; ".join(data.checks)
            )
        else:
            self.setToolTip("")
        self.show()


__all__ = ["FineSummaryCard"]
