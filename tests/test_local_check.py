"""Тесты локальной проверки: путь к папке/файлу, разбор и проверки."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.core.engine import analyze
from app.core.models import CheckStatus, RunOptions
from app.services.local_context import build_local_context
from app.services.local_target import (
    LocalTargetError,
    looks_local,
    local_path_from_uri,
    resolve_local_target,
)
from app.services.targets import normalize_target

FIXTURES = Path(__file__).parent / "fixtures"
SHOP_HTML = (FIXTURES / "shop.html").read_text(encoding="utf-8")
BLOG_HTML = (FIXTURES / "blog.html").read_text(encoding="utf-8")

PRIVACY_PAGE = """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<title>Политика обработки персональных данных</title></head><body>
<h1>Политика</h1>
<p>Оператор персональных данных. Цели обработки, срок хранения, права субъекта,
отзыв согласия, cookie — всё описано.</p>
</body></html>"""


def make_site(directory: Path, index_html: str = SHOP_HTML) -> Path:
    """Создаёт локальный сайт с политикой, контактами, robots и sitemap."""
    index = (
        index_html.replace('href="/privacy/"', 'href="/privacy/"')
        .replace('href="/contacts/"', 'href="/contacts/"')
    )
    (directory / "index.html").write_text(index, encoding="utf-8")
    privacy_dir = directory / "privacy"
    privacy_dir.mkdir()
    (privacy_dir / "index.html").write_text(PRIVACY_PAGE, encoding="utf-8")
    contacts_dir = directory / "contacts"
    contacts_dir.mkdir()
    (contacts_dir / "index.html").write_text(
        "<html><body><h1>Контакты</h1><p>info@lutik.ru</p></body></html>",
        encoding="utf-8",
    )
    (directory / "robots.txt").write_text(
        "User-agent: *\nDisallow: /admin\n", encoding="utf-8"
    )
    (directory / "sitemap.xml").write_text(
        "<?xml version='1.0'?><urlset><url><loc>/</loc></url></urlset>",
        encoding="utf-8",
    )
    return directory


# ---------------------------------------------------------------------------
# Распознавание пути
# ---------------------------------------------------------------------------


def test_looks_local() -> None:
    assert looks_local(r"C:\site")
    assert looks_local("D:/site/index.html")
    assert looks_local("file:///C:/site/index.html")
    assert looks_local("\\\\server\\share\\site")
    assert looks_local("./site")
    assert not looks_local("example.com")
    assert not looks_local("https://example.com/site")
    assert not looks_local("")


def test_normalize_target_local(tmp_path: Path) -> None:
    make_site(tmp_path)
    target = normalize_target(str(tmp_path))
    assert target.ok
    assert target.is_local
    assert target.path == tmp_path.resolve()
    assert target.value.endswith("index.html")


def test_normalize_target_local_file(tmp_path: Path) -> None:
    make_site(tmp_path)
    file_path = tmp_path / "index.html"
    target = normalize_target(str(file_path))
    assert target.ok and target.is_local
    assert target.value == str(file_path.resolve())


def test_normalize_target_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-site"
    target = normalize_target(str(missing))
    assert not target.ok
    assert target.is_local
    assert "не найден" in (target.error or "").lower()


def test_normalize_target_url() -> None:
    target = normalize_target("example.com")
    assert target.ok
    assert not target.is_local
    assert target.value == "https://example.com"


def test_resolve_folder_without_html(tmp_path: Path) -> None:
    with pytest.raises(LocalTargetError):
        resolve_local_target(str(tmp_path))


def test_resolve_index_priority(tmp_path: Path) -> None:
    (tmp_path / "about.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    target = resolve_local_target(str(tmp_path))
    assert target.entry.name == "index.html"
    assert target.from_file is False


def test_local_path_from_uri(tmp_path: Path) -> None:
    file_path = tmp_path / "index.html"
    file_path.write_text("<html></html>", encoding="utf-8")
    assert local_path_from_uri(file_path.as_uri()) == file_path.resolve()
    assert local_path_from_uri("https://example.com") is None


# ---------------------------------------------------------------------------
# Сбор контекста
# ---------------------------------------------------------------------------


def test_build_local_context(tmp_path: Path) -> None:
    make_site(tmp_path)
    ctx = build_local_context(
        str(tmp_path), RunOptions(max_pages=4)
    )
    assert ctx.is_local
    assert ctx.local_root == str(tmp_path.resolve())
    assert ctx.url.startswith("file://")
    assert "лютик" in ctx.title.lower()
    # ссылки и подстраницы
    assert ctx.privacy_link is not None
    assert ctx.privacy_link.href.startswith("file://")
    assert "privacy" in ctx.pages
    assert ctx.pages["privacy"].ok
    assert "оператор" in ctx.pages["privacy"].text
    assert "contacts" in ctx.pages
    # robots/sitemap с диска
    assert ctx.robots.found
    assert ctx.sitemap.found
    # глубокий анализ для локальной папки не запускается
    assert ctx.deep_analysis is False
    assert any("локальной папки" in note.lower() for note in ctx.notes)


def test_build_local_context_blog(tmp_path: Path) -> None:
    make_site(tmp_path, index_html=BLOG_HTML)
    ctx = build_local_context(str(tmp_path), RunOptions(max_pages=2))
    assert not ctx.has_sales_signs
    assert not ctx.trackers


def test_local_analyze_report(tmp_path: Path) -> None:
    make_site(tmp_path)
    scan = asyncio.run(
        analyze(str(tmp_path), RunOptions(deep_analysis=False, max_pages=4))
    )
    report = scan.report
    assert report.is_local
    assert len(report.results) == 17
    by_id = {item.check_id: item for item in report.results}
    assert by_id["a01_https"].status is CheckStatus.NOT_APPLICABLE
    assert by_id["d17_security_headers"].status is CheckStatus.NOT_APPLICABLE
    assert by_id["d16_robots_sitemap"].status is CheckStatus.PASS
    assert by_id["b13_seller_details"].status is CheckStatus.PASS
    assert by_id["a02_privacy_link"].status is CheckStatus.PASS
    assert 0 < report.score <= 100
    assert any("локальной папки" in note.lower() for note in report.notes)


def test_local_analyze_without_extras(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        "<html><body><h1>Просто сайт</h1></body></html>", encoding="utf-8"
    )
    report = asyncio.run(analyze(str(tmp_path), RunOptions(deep_analysis=False))).report
    by_id = {item.check_id: item for item in report.results}
    assert by_id["d16_robots_sitemap"].status is CheckStatus.NOT_APPLICABLE
    assert by_id["a05_forms_consent"].status is CheckStatus.NOT_APPLICABLE
    assert by_id["b13_seller_details"].status is CheckStatus.NOT_APPLICABLE


def test_local_analyze_missing_path() -> None:
    with pytest.raises(ValueError):
        asyncio.run(analyze(r"C:\no-such-folder-xyz", RunOptions()))


def test_folder_with_extensionless_html(tmp_path: Path) -> None:
    (tmp_path / "index").write_text(
        "<!DOCTYPE html><html><head><title>Без расширения</title></head>"
        "<body><h1>Сайт</h1></body></html>",
        encoding="utf-8",
    )
    (tmp_path / "about").write_text(
        "<html><body>О компании</body></html>", encoding="utf-8"
    )
    target = resolve_local_target(str(tmp_path))
    assert target.entry.name == "index"
    context = build_local_context(str(tmp_path), RunOptions())
    assert "без расширения" in context.title.lower()
    assert "сайт" in context.text


def test_extensionless_file_input(tmp_path: Path) -> None:
    page = tmp_path / "page"
    page.write_text("<html><body>Страница</body></html>", encoding="utf-8")
    target = resolve_local_target(str(page))
    assert target.from_file is True
    assert target.entry == page.resolve()


def test_reject_non_html_file(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# Просто текст", encoding="utf-8")
    with pytest.raises(LocalTargetError):
        resolve_local_target(str(readme))


def test_folder_error_mentions_path(tmp_path: Path) -> None:
    (tmp_path / "styles.css").write_text("body {}", encoding="utf-8")
    with pytest.raises(LocalTargetError) as error:
        resolve_local_target(str(tmp_path))
    assert str(tmp_path) in str(error.value)
    assert "Файл" in str(error.value)
