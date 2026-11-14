"""D16. robots.txt и sitemap.xml (техническая гигиена).

Одна проверка объединяет оба файла в один ``CheckResult``. Отсутствие
robots.txt — замечание (warn), отсутствие sitemap.xml оценивается только
на сайтах с более чем 5 внутренними ссылками. Статус ``fail`` не выдаётся.
"""

from __future__ import annotations

from app.core.checks.base import BaseCheck
from app.core.models import Category, CheckResult, Evidence, Severity, SiteContext

_SITEMAP_NA = (
    "sitemap.xml не оценивался: на сайте 5 и менее внутренних ссылок (лендинг)"
)


class RobotsSitemapCheck(BaseCheck):
    """Проверка доступности robots.txt и sitemap.xml."""

    id = "d16_robots_sitemap"
    title = "robots.txt и sitemap.xml"
    category = Category.TECH.value
    weight = 2
    severity = Severity.RECOMMENDATION
    recommendation = (
        "Добавьте в корень сайта robots.txt с корректными директивами User-agent/"
        "Disallow и ссылкой Sitemap: https://ваш-сайт/sitemap.xml. Для сайтов "
        "с большим числом страниц создайте sitemap.xml и обновляйте его."
    )

    def evaluate(self, ctx: SiteContext) -> CheckResult:
        robots_found = bool(ctx.robots.found)
        sitemap_applicable = ctx.internal_links > 5
        sitemap_found = bool(ctx.sitemap.found)

        if ctx.is_local and not robots_found and not sitemap_found:
            return self.na(
                "Локальная папка: robots.txt и sitemap.xml не найдены. "
                "Для локальной проверки эти файлы необязательны — они нужны "
                "опубликованному сайту.",
                evidence=[self.ev("Источник", ctx.local_root or ctx.target_url, kind="url")],
            )

        # --- robots.txt ---
        robots_label = "robots.txt" if ctx.is_local else "/robots.txt"
        if robots_found:
            robots_part = (
                "robots.txt найден в папке"
                if ctx.is_local
                else f"robots.txt доступен ({robots_label})"
            )
            if ctx.robots.disallow_all:
                robots_part += (
                    ", но содержит запрет обхода для всех роботов (Disallow: /)"
                )
        else:
            robots_part = "robots.txt не найден"
        if ctx.robots.error:
            robots_part += f" (ошибка загрузки: {ctx.robots.error})"

        # --- sitemap.xml ---
        if not sitemap_applicable:
            sitemap_part = _SITEMAP_NA
        elif sitemap_found:
            sitemap_url = ctx.sitemap.url or "/sitemap.xml"
            sitemap_part = (
                "sitemap.xml найден в папке"
                if ctx.is_local
                else f"sitemap.xml доступен ({sitemap_url})"
            )
            if ctx.sitemap.url_count:
                sitemap_part += f", адресов в карте: {ctx.sitemap.url_count}"
            if ctx.sitemap.is_index:
                sitemap_part += " (карта-индекс)"
        else:
            sitemap_part = (
                "sitemap.xml не найден "
                f"(внутренних ссылок на сайте: {ctx.internal_links})"
            )
            if ctx.sitemap.error:
                sitemap_part += f" (ошибка загрузки: {ctx.sitemap.error})"

        message = f"{robots_part}. {sitemap_part}."

        evidence: list[Evidence] = []
        if robots_found:
            evidence.append(self.ev("robots.txt", robots_label, kind="url"))
            if ctx.robots.disallow_all:
                evidence.append(self.ev("Директива", "Disallow: /"))
        if sitemap_applicable:
            if sitemap_found:
                evidence.append(
                    self.ev(
                        "sitemap.xml",
                        "sitemap.xml"
                        if ctx.is_local
                        else (ctx.sitemap.url or "/sitemap.xml"),
                        kind="url",
                    )
                )
            evidence.append(
                self.ev("Внутренних ссылок", str(ctx.internal_links), kind="count")
            )

        # fail быть не может: максимум warn.
        if not robots_found:
            return self.warn(
                message,
                severity=Severity.RECOMMENDATION,
                evidence=evidence,
            )
        if sitemap_applicable and not sitemap_found:
            return self.warn(
                message,
                severity=Severity.RECOMMENDATION,
                evidence=evidence,
            )
        return self.ok(message, evidence=evidence)
