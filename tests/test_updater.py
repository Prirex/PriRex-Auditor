"""Тесты проверки обновлений (без реальной сети — httpx.MockTransport)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.config import AppConfig
from app.updater import (
    UpdateInfo,
    check_for_updates,
    check_for_updates_sync,
    should_check_now,
)
from app.version import REPO_URL, __version__

TAG_URL = "https://github.com/Prirex/PriRex-Auditor/releases/tag/v{tag}"


def _redirect_transport(tag: str, *, fallback_version: str = "9.9.9"):
    """HEAD → 302 на тег, любой GET → version.json (на случай fallback)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(302, headers={"location": TAG_URL.format(tag=tag)})
        return httpx.Response(200, json={"version": fallback_version})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_new_version_available() -> None:
    info = await check_for_updates(
        AppConfig(), "1.0.0", transport=_redirect_transport("1.2.0")
    )
    assert info is not None
    assert isinstance(info, UpdateInfo)
    assert info.available is True
    assert info.latest == "1.2.0"
    assert info.current == "1.0.0"
    assert info.url == f"{REPO_URL}/releases/latest"


@pytest.mark.asyncio
async def test_same_version_is_not_an_update() -> None:
    info = await check_for_updates(
        AppConfig(), "1.0.0", transport=_redirect_transport("1.0.0")
    )
    assert info is not None
    assert info.available is False
    assert info.latest == "1.0.0"
    assert info.current == "1.0.0"


@pytest.mark.asyncio
async def test_older_version_is_not_an_update() -> None:
    info = await check_for_updates(
        AppConfig(), "1.0.0", transport=_redirect_transport("0.9.0")
    )
    assert info is not None
    assert info.available is False


@pytest.mark.asyncio
async def test_current_version_defaults_to_app_version() -> None:
    info = await check_for_updates(
        AppConfig(), transport=_redirect_transport("9.9.9")
    )
    assert info is not None
    assert info.current == __version__


@pytest.mark.asyncio
async def test_network_error_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    info = await check_for_updates(
        AppConfig(), "1.0.0", transport=httpx.MockTransport(handler)
    )
    assert info is None


@pytest.mark.asyncio
async def test_disabled_check_makes_no_requests() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json={"version": "9.9.9"})

    info = await check_for_updates(
        AppConfig(check_updates=False),
        "1.0.0",
        transport=httpx.MockTransport(handler),
    )
    assert info is None
    assert calls["count"] == 0


@pytest.mark.asyncio
async def test_version_json_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(404)
        return httpx.Response(
            200,
            json={
                "version": "1.1.5",
                "url": "https://example.com/download",
                "notes": "Исправления",
            },
        )

    info = await check_for_updates(
        AppConfig(), "1.0.0", transport=httpx.MockTransport(handler)
    )
    assert info is not None
    assert info.available is True
    assert info.latest == "1.1.5"
    assert info.notes == "Исправления"


@pytest.mark.asyncio
async def test_unparseable_version_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(404)
        return httpx.Response(200, json={"version": "release"})

    info = await check_for_updates(
        AppConfig(), "1.0.0", transport=httpx.MockTransport(handler)
    )
    assert info is None


@pytest.mark.asyncio
async def test_head_without_redirect_falls_back_to_version_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(200)  # нет релизов/редиректа
        return httpx.Response(200, json={"version": "2.0.0"})

    info = await check_for_updates(
        AppConfig(), "1.0.0", transport=httpx.MockTransport(handler)
    )
    assert info is not None
    assert info.latest == "2.0.0"
    assert info.available is True


def test_should_check_now_defaults_to_true() -> None:
    assert should_check_now(AppConfig()) is True


def test_should_check_now_respects_disabled() -> None:
    assert should_check_now(AppConfig(check_updates=False)) is False


def test_should_check_now_respects_last_check() -> None:
    config = AppConfig(update_interval_hours=24)
    config.last_update_check = datetime.now(timezone.utc).isoformat()
    assert should_check_now(config) is False

    config.last_update_check = (
        datetime.now(timezone.utc) - timedelta(hours=48)
    ).isoformat()
    assert should_check_now(config) is True


def test_sync_wrapper_disabled_is_fast_and_silent() -> None:
    # Сеть не трогаем: при выключенной настройке функция сразу вернёт None.
    assert check_for_updates_sync(AppConfig(check_updates=False)) is None
