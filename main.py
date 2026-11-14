"""Точка входа приложения «PriRex Auditor».

Запуск из исходников:
    python main.py

Сборка exe: см. build.ps1 / «PriRex Auditor.spec» (PyInstaller --onefile --windowed).
"""

from __future__ import annotations

import sys
import traceback


def _set_windows_app_id() -> None:
    """Отдельная иконка/группа в панели задач Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "PriRex.Auditor.App.1"
        )
    except Exception:  # noqa: BLE001 - некритично
        pass


def _install_excepthook() -> None:
    """Логирует необработанные исключения, не давая UI упасть молча."""
    from loguru import logger

    def hook(exc_type, exc_value, exc_tb):  # noqa: ANN001 - сигнатура sys.excepthook
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.opt(exception=(exc_type, exc_value, exc_tb)).error(
            "Необработанное исключение"
        )
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance() is not None:
                detail = "".join(traceback.format_exception_only(exc_type, exc_value)).strip()
                QMessageBox.critical(
                    None,
                    "Непредвиденная ошибка",
                    "Приложение столкнулось с ошибкой, но продолжает работу.\n\n"
                    f"{detail}\n\nПодробности записаны в журнал приложения.",
                )
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = hook


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)

    from app.logging_setup import setup_logging
    from app.version import APP_NAME, APP_TITLE, __version__

    debug = "--debug" in argv or "-d" in argv
    setup_logging(debug=debug)
    _set_windows_app_id()
    _install_excepthook()

    from PySide6.QtWidgets import QApplication

    from app.i18n import set_language
    from app.ui.icons import app_icon
    from app.ui.theme import apply_theme

    application = QApplication(argv)
    application.setApplicationName(APP_NAME)
    application.setApplicationVersion(__version__)
    application.setOrganizationName("PriRex")
    application.setOrganizationDomain("github.com/Prirex")
    application.setWindowIcon(app_icon())

    from app.config import get_config
    from app.logging_setup import logger

    try:
        set_language(get_config().language)
    except Exception:  # noqa: BLE001 - конфиг не должен мешать запуску
        logger.debug("Не удалось прочитать язык из настроек")

    apply_theme(application)

    from app.ui.main_window import MainWindow

    window = MainWindow()
    window.setWindowTitle(APP_TITLE)

    if "--selftest" in argv:
        # Проверка сборки: окно создаётся, тема и ресурсы на месте — выходим без exec.
        application.processEvents()
        window.close()
        logger.info("SELFTEST OK")
        print("SELFTEST OK")
        return 0

    window.show()
    logger.info("Приложение запущено, версия {}", __version__)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
