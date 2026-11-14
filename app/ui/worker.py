"""Фоновый воркер сканирования сайта.

Вся сеть и Playwright живут в этом QThread — UI-поток никогда не блокируется.
Импорт оркестратора сделан *локальным*: модули ``app.services.site_context``
и проверки пишутся параллельно, и UI обязан собираться/тестироваться даже
если их ещё нет в рабочем дереве.
"""

from __future__ import annotations

import asyncio
import threading

from PySide6.QtCore import QObject, QThread, Signal

from app.core.models import RunOptions

__all__ = ["ScanWorker"]


class ScanWorker(QThread):
    """Один запуск ``analyze()`` в отдельном потоке."""

    #: Прогресс: доля 0..1 и текст текущего шага.
    progress = Signal(float, str)
    #: Успех: объект ``ScanResult`` (report + context).
    finished_ok = Signal(object)
    #: Человекочитаемое описание ошибки.
    failed = Signal(str)
    #: Пользователь нажал «Отмена».
    cancelled = Signal()

    def __init__(
        self,
        url: str,
        options: RunOptions,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._url = url
        self._options = options
        self._cancel_event = threading.Event()

    # ------------------------------------------------------------------
    def cancel(self) -> None:
        """Потокобезопасно просит оркестратор остановиться."""
        self._cancel_event.set()

    def is_cancelled(self) -> bool:
        """Возвращает ``True``, если запрошена отмена."""
        return self._cancel_event.is_set()

    # ------------------------------------------------------------------
    def run(self) -> None:  # noqa: D401 - Qt API
        """Точка входа потока: ``asyncio.run(analyze(...))``."""
        try:
            # Локальный импорт: сайт-контекст и проверки могут появиться позже.
            from app.core.detect import friendly_http_error
            from app.core.engine.orchestrator import ScanCancelled, analyze
        except ImportError as exc:  # pragma: no cover - зависит от сборки проекта
            self.failed.emit(f"Не удалось загрузить модуль проверок: {exc}")
            return

        def _progress(fraction: float, message: str) -> None:
            self.progress.emit(float(fraction), str(message))

        try:
            result = asyncio.run(
                analyze(
                    self._url,
                    self._options,
                    progress=_progress,
                    cancelled=self._cancel_event.is_set,
                )
            )
        except ScanCancelled:
            self.cancelled.emit()
            return
        except Exception as exc:  # noqa: BLE001 - любую сетевую ошибку показываем текстом
            self.failed.emit(friendly_http_error(exc))
            return

        if self._cancel_event.is_set():
            self.cancelled.emit()
            return
        self.finished_ok.emit(result)
