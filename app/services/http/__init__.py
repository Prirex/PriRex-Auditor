"""HTTP-слой: клиент, декодирование, ошибки."""

from app.services.http.client import (
    FetchResult,
    HttpClient,
    classify_error,
    decode_html,
    probe_tls,
)

__all__ = ["FetchResult", "HttpClient", "classify_error", "decode_html", "probe_tls"]
