"""HTTP-клиент: один GET с ограничением размера, ретраями и данными TLS."""

from __future__ import annotations

import asyncio
import re
import socket
import ssl
import time
from dataclasses import dataclass, field

import httpx

ACCEPT_HEADER = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,*/*;q=0.8"
)
ACCEPT_LANGUAGE = "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"

_CHARSET_RE = re.compile(
    rb"""<meta[^>]+charset\s*=\s*["']?\s*([a-zA-Z0-9_\-]+)""", re.IGNORECASE
)
_XML_ENCODING_RE = re.compile(rb"""<\?xml[^>]+encoding\s*=\s*["']([a-zA-Z0-9_\-]+)""")


@dataclass
class FetchResult:
    """Результат одного запроса — без исключений наружу."""

    requested_url: str = ""
    url: str = ""
    ok: bool = False
    status_code: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    text: str = ""
    content_bytes: int = 0
    truncated: bool = False
    error: str | None = None
    error_kind: str | None = None  # timeout | tls | connect | http | other
    tls_version: str | None = None
    cert_valid: bool = True
    cert_error: str | None = None
    redirects: list[str] = field(default_factory=list)
    http_version: str | None = None
    elapsed: float = 0.0

    @property
    def is_success(self) -> bool:
        return self.ok and self.status_code is not None and 200 <= self.status_code < 400

    @property
    def content_type(self) -> str:
        for key, value in self.headers.items():
            if key.lower() == "content-type":
                return value.lower()
        return ""

    @property
    def is_html(self) -> bool:
        ctype = self.content_type
        if not ctype:
            return True
        return "html" in ctype or "xml" in ctype or "text/plain" in ctype


def decode_html(raw: bytes, content_type: str = "") -> str:
    """Декодирует HTML: сначала заголовок, потом <meta charset>, потом cp1251."""
    candidates: list[str] = []
    match = re.search(r"charset=([a-zA-Z0-9_\-]+)", content_type or "", re.IGNORECASE)
    if match:
        candidates.append(match.group(1))
    head = raw[:4096]
    for pattern in (_CHARSET_RE, _XML_ENCODING_RE):
        found = pattern.search(head)
        if found:
            candidates.append(found.group(1).decode("ascii", "ignore"))
    candidates.extend(["utf-8", "cp1251"])

    seen: set[str] = set()
    for encoding in candidates:
        encoding = encoding.strip().lower()
        if not encoding or encoding in seen:
            continue
        seen.add(encoding)
        try:
            return raw.decode(encoding, errors="strict")
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def classify_error(exc: Exception) -> tuple[str, str]:
    """(kind, человекочитаемое описание) для исключения httpx/ssl."""
    if isinstance(exc, httpx.TimeoutException):
        return "timeout", "Сайт не ответил за отведённое время."
    if isinstance(exc, httpx.ConnectError):
        message = str(exc).lower()
        if "certificate" in message or "ssl" in message or "tls" in message:
            return "tls", "Ошибка TLS-сертификата."
        return "connect", "Не удалось подключиться к сайту."
    if isinstance(exc, httpx.TooManyRedirects):
        return "http", "Слишком много перенаправлений."
    if isinstance(exc, ssl.SSLError):
        return "tls", "Ошибка TLS."
    if isinstance(exc, socket.gaierror):
        return "connect", "Домен не найден."
    return "other", f"{exc.__class__.__name__}: {exc}"


def probe_tls(host: str, port: int = 443, timeout: float = 6.0) -> tuple[str | None, str | None]:
    """Проверяет сертификат и версию TLS отдельным соединением.

    Возвращает (версия TLS | None, ошибка сертификата | None).
    """
    context = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as raw_socket:
            with context.wrap_socket(raw_socket, server_hostname=host) as tls_socket:
                return tls_socket.version(), None
    except ssl.SSLCertVerificationError as exc:
        return None, f"Сертификат не прошёл проверку: {exc.verify_message or exc}"
    except ssl.SSLError as exc:
        return None, f"Ошибка TLS: {exc.reason or exc}"
    except (socket.timeout, TimeoutError):
        return None, "Истекло время ожидания TLS-соединения."
    except OSError as exc:
        return None, f"Не удалось установить TLS-соединение: {exc}"


class HttpClient:
    """Минимальный клиент: только GET, ограничение размера, до 2 попыток."""

    def __init__(
        self,
        timeout: float = 15.0,
        user_agent: str = "",
        max_bytes: int = 5 * 1024 * 1024,
        verify: bool = True,
        max_redirects: int = 6,
    ) -> None:
        self.timeout = max(1.0, float(timeout))
        self.user_agent = user_agent or "Mozilla/5.0 (compatible; PriRexAuditor/1.0)"
        self.max_bytes = max(64 * 1024, int(max_bytes))
        self.verify = verify
        self.max_redirects = max_redirects

    # ------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": ACCEPT_HEADER,
            "Accept-Language": ACCEPT_LANGUAGE,
            "Cache-Control": "no-cache",
        }

    async def fetch(
        self,
        url: str,
        *,
        verify: bool | None = None,
        max_bytes: int | None = None,
        retries: int = 1,
        timeout: float | None = None,
    ) -> FetchResult:
        """GET с ограничением размера; сетевые ошибки возвращаются в результате."""
        starts = time.perf_counter()
        limit = int(max_bytes if max_bytes is not None else self.max_bytes)
        use_verify = self.verify if verify is None else verify
        effective_timeout = max(3.0, float(timeout)) if timeout else self.timeout
        attempt = 0
        last: FetchResult | None = None

        while attempt <= retries:
            attempt += 1
            result = await self._fetch_once(url, use_verify, limit, effective_timeout)
            result.elapsed = time.perf_counter() - starts
            if result.ok or result.error_kind in {"tls", "http"}:
                return result
            last = result
            if attempt <= retries:
                await asyncio.sleep(0.4)
        return last or FetchResult(requested_url=url, url=url, error="Неизвестная ошибка")

    async def _fetch_once(
        self, url: str, verify: bool, limit: int, timeout_seconds: float
    ) -> FetchResult:
        result = FetchResult(requested_url=url, url=url)
        timeout = httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds))
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                verify=verify,
                follow_redirects=True,
                max_redirects=self.max_redirects,
                headers=self._headers(),
                # HTTP/2 выключен намеренно: стабильнее с inspect TLS-объекта и прокси
                trust_env=False,
            ) as client:
                async with client.stream("GET", url) as response:
                    result.status_code = response.status_code
                    result.url = str(response.url)
                    result.headers = {k.lower(): v for k, v in response.headers.items()}
                    result.http_version = response.http_version
                    result.redirects = [str(item.url) for item in response.history]

                    tls_version = self._tls_version(response)
                    if tls_version:
                        result.tls_version = tls_version

                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        if not chunk:
                            continue
                        chunks.append(chunk)
                        total += len(chunk)
                        if total >= limit:
                            result.truncated = True
                            break
                    raw = b"".join(chunks)
                    result.content_bytes = total
                    if response.is_success or response.status_code < 500:
                        result.text = decode_html(raw, response.headers.get("content-type", ""))
                        result.ok = response.status_code < 400
                    else:
                        result.error_kind = "http"
                        result.error = f"Сервер вернул ошибку {response.status_code}."
                        result.text = decode_html(raw, response.headers.get("content-type", ""))
        except Exception as exc:  # noqa: BLE001 - ошибки сети не должны всплывать
            kind, message = classify_error(exc)
            result.ok = False
            result.error_kind = kind
            result.error = message
            if kind == "tls":
                result.cert_valid = False
                result.cert_error = str(exc)
        return result

    @staticmethod
    def _tls_version(response: httpx.Response) -> str | None:
        try:
            stream = response.extensions.get("network_stream")
            if stream is None:
                return None
            ssl_object = stream.get_extra_info("ssl_object")
            if ssl_object is None:
                return None
            return ssl_object.version()
        except Exception:  # noqa: BLE001 - расширение необязательное
            return None


__all__ = [
    "ACCEPT_HEADER",
    "FetchResult",
    "HttpClient",
    "classify_error",
    "decode_html",
    "probe_tls",
]
