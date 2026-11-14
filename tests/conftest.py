"""Общие фикстуры тестов."""

from __future__ import annotations

import pytest

from tests.helpers import make_context


@pytest.fixture
def make_ctx():
    """Фабрика SiteContext: ``ctx = make_ctx(forms=[...], text="...")``."""

    def factory(url: str = "https://example.com/", **overrides: object):
        return make_context(url, **overrides)

    return factory
