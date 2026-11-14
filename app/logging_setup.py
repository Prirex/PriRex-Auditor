"""Логирование через loguru: файл в %APPDATA% и консоль при запуске из исходников."""

from __future__ import annotations

import sys

from loguru import logger

from app.paths import log_dir

_configured = False


def setup_logging(debug: bool = False, console: bool | None = None) -> None:
    """Настраивает loguru один раз за процесс."""
    global _configured
    if _configured:
        return
    _configured = True

    logger.remove()
    level = "DEBUG" if debug else "INFO"
    logger.add(
        log_dir() / "app.log",
        level=level,
        rotation="1 MB",
        retention=5,
        encoding="utf-8",
        enqueue=True,
        backtrace=False,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{line} | {message}",
    )
    if console is None:
        console = not getattr(sys, "frozen", False)
    if console:
        logger.add(
            sys.stderr,
            level=level,
            colorize=True,
            format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}",
        )


__all__ = ["logger", "setup_logging"]
