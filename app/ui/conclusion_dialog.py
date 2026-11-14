"""Немодальное окно «Заключение: что изменить для 100%».

Показывает план улучшений по убыванию потерянных баллов
(``app.core.engine.scoring.improvement_plan``), позволяет скопировать
план в буфер обмена как Markdown-чек-лист. Стилизация — через objectName
из ``assets/theme.qss``; собственных ``setStyleSheet`` нет.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.engine.scoring import (
    improvement_plan,
    lost_points,
    total_points,
)
from app.core.models import CheckResult, CheckStatus, Report
from app.i18n import tr, trf
from app.ui.icons import status_pixmap

__all__ = ["ConclusionDialog"]


def _format_points(value: float) -> str:
    """``0.5`` → «0,5» не нужен: ТЗ показывает точку; целые — без ``.0``."""
    rounded = round(float(value), 2)
    if abs(rounded - round(rounded)) < 1e-9:
        return str(int(round(rounded)))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def _points_word(value: float) -> str:
    """Согласование слова «балл» с числом."""
    if abs(float(value) - round(float(value))) > 1e-9:
        return tr("балла")
    whole = int(round(float(value)))
    if whole % 10 == 1 and whole % 100 != 11:
        return tr("балл")
    if 2 <= whole % 10 <= 4 and not 12 <= whole % 100 <= 14:
        return tr("балла")
    return tr("баллов")


class ConclusionDialog(QDialog):
    """Окно «Заключение»: приоритетный план исправлений."""

    def __init__(
        self,
        report: Report,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._report = report
        #: Пары (проверка, потерянные баллы) по убыванию влияния.
        #: При 100% список пуст — вместо него показывается итоговая фраза.
        self.items: list[tuple[CheckResult, float]] = (
            [] if report.score >= 100 else improvement_plan(report.results)
        )
        self.total_points: int = total_points(report.results)
        self.item_frames: list[QFrame] = []

        self.setObjectName("ConclusionDialog")
        self.setWindowTitle(tr("Заключение"))
        self.setModal(False)
        self.setWindowFlag(
            Qt.WindowType.WindowContextHelpButtonHint, False
        )
        self.resize(720, 640)
        self.setMinimumSize(600, 480)

        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(10)

        title = QLabel(tr("Заключение: что изменить для 100%"), self)
        title.setObjectName("ConclusionTitle")
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        layout.addWidget(title)

        hint = QLabel(self._hint_text(), self)
        hint.setObjectName("ConclusionHint")
        hint.setTextFormat(Qt.TextFormat.PlainText)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        layout.addWidget(self.scroll, 1)

        self.content = QWidget(self.scroll)
        self._content_layout = QVBoxLayout(self.content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(8)
        self.scroll.setWidget(self.content)

        if self._report.score >= 100:
            done = QLabel(
                tr(
                    "Все применимые проверки пройдены — сайт соответствует "
                    "проверяемым требованиям."
                ),
                self.content,
            )
            done.setObjectName("InfoBody")
            done.setTextFormat(Qt.TextFormat.PlainText)
            done.setWordWrap(True)
            self._content_layout.addWidget(done)
        else:
            for result, lost in self.items:
                self._add_item(result, lost)
        self._content_layout.addStretch(1)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(8)

        self.copy_button = QPushButton(tr("Копировать план"), self)
        self.copy_button.setObjectName("GhostButton")
        self.copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_button.setEnabled(bool(self.items))
        self.copy_button.clicked.connect(self.copy_plan)
        bottom.addWidget(self.copy_button, 0)

        bottom.addStretch(1)

        self.close_button = QPushButton(tr("Закрыть"), self)
        self.close_button.setObjectName("PrimaryButton")
        self.close_button.setMinimumWidth(112)
        self.close_button.setDefault(True)
        self.close_button.clicked.connect(self.accept)
        bottom.addWidget(self.close_button, 0)

        layout.addLayout(bottom)

    # ------------------------------------------------------------------
    def _hint_text(self) -> str:
        score = int(self._report.score)
        if score >= 100:
            return tr(
                "Текущий результат: 100%. Все применимые проверки пройдены. "
                "N/A и «не проверено» не влияют на оценку."
            )
        lost = sum(
            lost_points(result) for result in self._report.results
        )
        lost_text = _format_points(lost)
        word = _points_word(lost)
        return trf(
            "Текущий результат: {score}%. До 100% не хватает {lost} {word} "
            "из {total}. N/A и «не проверено» не влияют на оценку.",
            score=score,
            lost=lost_text,
            word=word,
            total=self.total_points,
        )

    def _add_item(self, result: CheckResult, lost: float) -> None:
        frame = QFrame(self.content)
        frame.setObjectName("ConclusionItem")
        frame.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(12, 10, 12, 10)
        frame_layout.setSpacing(5)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)

        icon = QLabel(frame)
        icon.setFixedSize(18, 18)
        pixmap = status_pixmap(result.status, 18)
        if not pixmap.isNull():
            icon.setPixmap(pixmap)
        head.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        title = QLabel(result.title or result.check_id, frame)
        title.setObjectName("ConclusionItemTitle")
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        head.addWidget(title, 1)

        badge = QLabel(tr(result.severity.label_ru), frame)
        badge.setObjectName("PillBadge")
        badge.setTextFormat(Qt.TextFormat.PlainText)
        badge.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
        )
        head.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        frame_layout.addLayout(head)

        text = QLabel(self._item_text(result), frame)
        text.setObjectName("ConclusionItemText")
        text.setTextFormat(Qt.TextFormat.PlainText)
        text.setWordWrap(True)
        text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        frame_layout.addWidget(text)

        # Исправление — отдельным салатовым блоком, как в панели деталей.
        recommendation = (result.recommendation or "").strip()
        if recommendation:
            fix = QLabel(f"{tr('Как исправить')}: {recommendation}", frame)
            fix.setObjectName("DetailRecommendation")
            fix.setTextFormat(Qt.TextFormat.PlainText)
            fix.setWordWrap(True)
            fix.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            frame_layout.addWidget(fix)

        gain_text = trf(
            "−{points} {word} из {total}",
            points=_format_points(lost),
            word=_points_word(lost),
            total=self.total_points,
        )
        gain = QLabel(gain_text, frame)
        gain.setObjectName("ConclusionGain")
        gain.setTextFormat(Qt.TextFormat.PlainText)
        frame_layout.addWidget(gain)

        self._content_layout.addWidget(frame)
        self.item_frames.append(frame)

    @staticmethod
    def _item_text(result: CheckResult) -> str:
        message = (result.message or "").strip()
        if message:
            return message
        return tr("Устраните замечание, чтобы повысить оценку.")

    # ------------------------------------------------------------------
    def plan_markdown(self) -> str:
        """Markdown-чек-лист «- [ ] (Критично) Название — что сделать»."""
        lines: list[str] = []
        for result, _lost in self.items:
            if result.status not in (CheckStatus.FAIL, CheckStatus.WARN):
                continue
            title = result.title or result.check_id
            recommendation = (result.recommendation or "").strip()
            if recommendation:
                action = f"{tr('Как исправить')}: {recommendation}"
            else:
                action = (
                    result.message
                    or tr("Устраните замечание, чтобы повысить оценку.")
                )
            action = " ".join(action.split())
            severity = tr(result.severity.label_ru)
            lines.append(f"- [ ] ({severity}) {title} — {action}")
        return "\n".join(lines)

    def copy_plan(self) -> str:
        """Копирует план в буфер обмена; возвращает скопированный текст."""
        text = self.plan_markdown()
        if text:
            QGuiApplication.clipboard().setText(text)
        return text
