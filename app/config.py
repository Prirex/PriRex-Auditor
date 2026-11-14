"""Настройки приложения: pydantic-модель + JSON-хранилище в %APPDATA%."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from app.core.models import RunOptions
from app.paths import config_path, default_report_dir

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 "
    "PriRexAuditor/1.0 (+https://github.com/Prirex/PriRex-Auditor)"
)

LANGUAGES = {"ru": "Русский", "en": "English"}


class AppConfig(BaseModel):
    """Пользовательские настройки. Сохраняются в config.json."""

    # Проверка
    timeout: float = Field(default=15.0, ge=3.0, le=120.0)
    user_agent: str = DEFAULT_USER_AGENT
    deep_analysis: bool = True
    check_trackers: bool = True
    show_na: bool = True
    verify_tls: bool = True
    follow_redirects: bool = True

    # Ограничения
    max_html_bytes: int = Field(default=5 * 1024 * 1024, ge=256 * 1024, le=40 * 1024 * 1024)
    max_pages: int = Field(default=4, ge=0, le=12)
    save_screenshots: bool = True

    # Отчёты
    report_dir: str = Field(default_factory=lambda: str(default_report_dir()))

    # Обновления
    check_updates: bool = True
    update_interval_hours: int = Field(default=24, ge=1, le=720)
    last_update_check: str | None = None

    # Поддержка автора (Boosty)
    boosty_ask_confirm: bool = False

    # Интерфейс
    language: str = "ru"
    window_geometry: str | None = None
    window_state: str | None = None
    last_url: str = ""

    @field_validator("language")
    @classmethod
    def _check_language(cls, value: str) -> str:
        return value if value in LANGUAGES else "ru"

    @field_validator("timeout")
    @classmethod
    def _round_timeout(cls, value: float) -> float:
        return round(float(value), 1)

    # ------------------------------------------------------------------
    def to_run_options(self, screenshot_dir: str | None = None) -> RunOptions:
        return RunOptions(
            deep_analysis=self.deep_analysis,
            check_trackers=self.check_trackers,
            show_na=self.show_na,
            timeout=self.timeout,
            user_agent=self.user_agent or DEFAULT_USER_AGENT,
            max_html_bytes=self.max_html_bytes,
            max_pages=self.max_pages,
            save_screenshots=self.save_screenshots,
            screenshot_dir=screenshot_dir,
            language=self.language,
            allow_http_fallback=True,
        )

    def mark_update_checked(self) -> None:
        self.last_update_check = datetime.now(timezone.utc).isoformat()

    def update_is_due(self) -> bool:
        if not self.check_updates:
            return False
        if not self.last_update_check:
            return True
        try:
            last = datetime.fromisoformat(self.last_update_check)
        except ValueError:
            return True
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        return age_hours >= self.update_interval_hours


class ConfigManager:
    """Загрузка/сохранение ``AppConfig`` в JSON."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else config_path()
        self.config = self.load()

    # ------------------------------------------------------------------
    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> AppConfig:
        if not self._path.exists():
            return AppConfig()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return AppConfig()
        if not isinstance(raw, dict):
            return AppConfig()
        try:
            return AppConfig(**raw)
        except Exception:  # noqa: BLE001 - битый конфиг не должен ломать запуск
            return AppConfig()

    def save(self, config: AppConfig | None = None) -> None:
        if config is not None:
            self.config = config
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.config.model_dump(mode="json")
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)

    def update(self, **values: object) -> AppConfig:
        self.config = self.config.model_copy(update=values)
        self.save()
        return self.config

    def reset(self) -> AppConfig:
        self.config = AppConfig()
        self.save()
        return self.config


_MANAGER: ConfigManager | None = None


def get_config_manager() -> ConfigManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = ConfigManager()
    return _MANAGER


def get_config() -> AppConfig:
    return get_config_manager().config
