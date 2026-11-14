"""Обёртка над Playwright (Chromium): рендер, cookie-баннер, скриншот, запросы.

Если Playwright не установлен или браузер не запускается — возвращаем
результат с ``ok=False`` и понятным пояснением, а приложение продолжает работу
на HTTP + BeautifulSoup (см. раздел 6 ТЗ).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from app.paths import screenshots_dir

#: JS-поиск cookie-баннера: фиксированный/липкий слой с текстом про cookie.
COOKIE_BANNER_JS = """
() => {
  const markers = ["cookie", "куки", "cookies", "согласие на обработку",
                   "файлы cookie", "используем cookie"];
  const results = [];
  const nodes = document.querySelectorAll("body *");
  for (const el of nodes) {
    if (el.children && el.children.length > 80) continue;
    const text = (el.innerText || "").trim();
    if (!text || text.length < 10 || text.length > 1200) continue;
    const low = text.toLowerCase();
    if (!markers.some((m) => low.includes(m))) continue;
    const style = window.getComputedStyle(el);
    const position = style.position;
    const zIndex = parseInt(style.zIndex || "0", 10) || 0;
    const role = (el.getAttribute("role") || "").toLowerCase();
    const rect = el.getBoundingClientRect();
    if (rect.width < 180 || rect.height < 36) continue;
    const fixedLike = position === "fixed" || position === "sticky" || zIndex >= 100;
    const dialogLike = role === "dialog" || role === "alertdialog";
    if (!fixedLike && !dialogLike) continue;
    const buttons = Array.from(
      el.querySelectorAll("button, a, input[type=button], input[type=submit], [role=button]")
    ).map((b) => ((b.innerText || b.value || b.getAttribute("aria-label") || "").trim()))
     .filter((t) => t && t.length <= 60)
     .slice(0, 16);
    results.push({
      text: text.slice(0, 700),
      position: position,
      zIndex: zIndex,
      role: role,
      tag: el.tagName,
      id: el.id || "",
      className: (typeof el.className === "string" ? el.className : "").slice(0, 200),
      buttons: buttons,
    });
  }
  return results.slice(0, 6);
}
"""

#: Признаки антибот-проверки (обходить нельзя — только сообщить).
CHALLENGE_TITLES = (
    "just a moment",
    "attention required",
    "проверка безопасности",
    "checking your browser",
    "ddos-guard",
    "access denied",
)


@dataclass
class BrowserResult:
    """Что удалось узнать через настоящий браузер."""

    ok: bool = False
    error: str | None = None
    browser: str = ""
    final_url: str = ""
    html: str = ""
    requests: list[str] = field(default_factory=list)
    cookie_banner: dict | None = None
    screenshot: str | None = None
    title: str = ""
    challenge: bool = False
    note: str = ""


class BrowserSession:
    """Один запуск Chromium для одной страницы."""

    def __init__(
        self,
        timeout: float = 15.0,
        user_agent: str = "",
        screenshot_dir: Path | str | None = None,
        save_screenshots: bool = True,
        ignore_https_errors: bool = True,
    ) -> None:
        self.timeout = max(5.0, float(timeout))
        self.user_agent = user_agent
        self.screenshot_dir = Path(screenshot_dir) if screenshot_dir else screenshots_dir()
        self.save_screenshots = save_screenshots
        self.ignore_https_errors = ignore_https_errors

    # ------------------------------------------------------------------
    async def capture(self, url: str, name: str = "main") -> BrowserResult:
        """Открывает URL в Chromium и собирает динамические данные."""
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:  # noqa: BLE001 - Playwright необязателен
            return BrowserResult(
                ok=False,
                error=f"Playwright не установлен или недоступен: {exc}",
            )

        try:
            return await asyncio.wait_for(
                self._capture(async_playwright, url, name),
                timeout=self.timeout + 25,
            )
        except asyncio.TimeoutError:
            return BrowserResult(
                ok=False,
                error="Браузер не успел загрузить страницу (таймаут глубокого анализа).",
            )
        except Exception as exc:  # noqa: BLE001
            return BrowserResult(ok=False, error=f"Ошибка глубокого анализа: {exc}")

    # ------------------------------------------------------------------
    async def _capture(self, async_playwright, url: str, name: str) -> BrowserResult:
        result = BrowserResult()
        async with async_playwright() as playwright_api:
            browser = None
            launch_errors: list[str] = []
            for channel in (None, "chrome", "msedge"):
                try:
                    kwargs: dict[str, object] = {
                        "headless": True,
                        "args": [
                            "--no-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-blink-features=AutomationControlled",
                            "--disable-gpu",
                        ],
                    }
                    if channel:
                        kwargs["channel"] = channel
                    browser = await playwright_api.chromium.launch(**kwargs)
                    result.browser = channel or "chromium"
                    break
                except Exception as exc:  # noqa: BLE001 - пробуем следующий канал
                    launch_errors.append(f"{channel or 'chromium'}: {str(exc).splitlines()[0][:120]}")
            if browser is None:
                result.error = (
                    "Не удалось запустить браузер для глубокого анализа. "
                    "Установите Chromium: `python -m playwright install chromium`. "
                    + (" | ".join(launch_errors[:2]) if launch_errors else "")
                )
                return result

            context = None
            try:
                context = await browser.new_context(
                    viewport={"width": 1366, "height": 900},
                    user_agent=self.user_agent or None,
                    locale="ru-RU",
                    timezone_id="Europe/Moscow",
                    ignore_https_errors=self.ignore_https_errors,
                    java_script_enabled=True,
                )
                page = await context.new_page()
                requests: list[str] = []

                def _on_request(request) -> None:
                    try:
                        if len(requests) < 400:
                            requests.append(request.url)
                    except Exception:  # noqa: BLE001
                        pass

                page.on("request", _on_request)
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=int(self.timeout * 1000),
                )
                if response is not None and response.status >= 500:
                    result.note = f"Сервер вернул {response.status} при загрузке в браузере."

                # Даём шанс появиться баннерам/виджетам и дочитаться скриптам.
                await page.wait_for_timeout(1600)

                result.final_url = page.url
                result.title = (await page.title()) or ""
                lowered_title = result.title.lower()
                result.challenge = any(marker in lowered_title for marker in CHALLENGE_TITLES)

                try:
                    result.html = await page.content()
                except Exception:  # noqa: BLE001
                    result.html = ""

                try:
                    candidates = await page.evaluate(COOKIE_BANNER_JS)
                except Exception:  # noqa: BLE001
                    candidates = []
                if candidates:
                    result.cookie_banner = self._pick_banner(candidates)

                if self.save_screenshots:
                    result.screenshot = await self._screenshot(page, name)

                result.requests = requests
                result.ok = bool(result.html)
                if result.challenge:
                    result.note = (
                        "Сайт показывает антибот-проверку (Cloudflare/DDoS-Guard). "
                        "Динамическая часть проверена не полностью."
                    )
                return result
            finally:
                if context is not None:
                    try:
                        await context.close()
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    await browser.close()
                except Exception:  # noqa: BLE001
                    pass

    # ------------------------------------------------------------------
    @staticmethod
    def _pick_banner(candidates: list[dict]) -> dict:
        """Выбирает наиболее «баннерный» кандидат."""
        best = candidates[0]
        best_score = -1
        for candidate in candidates:
            score = 0
            if candidate.get("buttons"):
                score += 3
            if candidate.get("position") in ("fixed", "sticky"):
                score += 2
            text = candidate.get("text", "").lower()
            if "cookie" in text or "куки" in text:
                score += 2
            if candidate.get("role") in ("dialog", "alertdialog"):
                score += 1
            if score > best_score:
                best, best_score = candidate, score
        return best

    async def _screenshot(self, page, name: str) -> str | None:
        try:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)
            path = self.screenshot_dir / f"{name}.png"
            await page.screenshot(path=str(path), full_page=False)
            return str(path)
        except Exception:  # noqa: BLE001
            return None


def browser_available() -> bool:
    """Установлен ли пакет Playwright (без запуска браузера)."""
    try:
        import playwright  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


__all__ = ["BrowserResult", "BrowserSession", "browser_available", "COOKIE_BANNER_JS"]
