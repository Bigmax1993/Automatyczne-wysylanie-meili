"""
Pobieranie publicznej strony WWW → czysty tekst → skrót do JSON kontekstu dla OpenAI.
Oddzielone od modelu: tylko HTTP + parsowanie; model dostaje gotowy fragment.

Włączenie: ENABLE_WEB_PAGE_CONTEXT=1 (domyślnie wyłączone — brak niespodziewanych requestów).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore[assignment]

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[assignment]

WEB_CONTEXT_ENABLED = os.environ.get("ENABLE_WEB_PAGE_CONTEXT", "0").lower() in {
    "1",
    "true",
    "yes",
}
WEB_FETCH_TIMEOUT = float(os.environ.get("WEB_FETCH_TIMEOUT", "10"))
WEB_FETCH_MAX_BYTES = int(os.environ.get("WEB_FETCH_MAX_BYTES", "500000"))
WEB_FETCH_MAX_EXCERPT_CHARS = int(os.environ.get("WEB_FETCH_MAX_EXCERPT_CHARS", "6000"))
WEB_FETCH_MIN_INTERVAL_SEC = float(os.environ.get("WEB_FETCH_MIN_INTERVAL_SEC", "1.5"))
WEB_FETCH_CACHE_TTL_SEC = int(os.environ.get("WEB_FETCH_CACHE_TTL_SEC", "3600"))
WEB_FETCH_CACHE_MAX_URLS = int(os.environ.get("WEB_FETCH_CACHE_MAX_URLS", "256"))
WEB_FETCH_USER_AGENT = os.environ.get(
    "WEB_FETCH_USER_AGENT",
    "Mozilla/5.0 (compatible; ContactMailer/1.1; job-application-context)",
)
WEB_FETCH_NEGATIVE_CACHE_SEC = float(os.environ.get("WEB_FETCH_NEGATIVE_CACHE_SEC", "600"))
WEB_FETCH_HTTP_RETRIES = max(1, int(os.environ.get("WEB_FETCH_HTTP_RETRIES", "3")))

logger = logging.getLogger(__name__)

_last_fetch_monotonic = 0.0
_cache: Dict[str, Tuple[float, str]] = {}
_negative_until: Dict[str, float] = {}


def clear_fetch_cache() -> None:
    """Testy / ręczny reset cache URL → skrót treści."""
    _cache.clear()
    _negative_until.clear()


def _negative_blocks(url: str) -> bool:
    exp = _negative_until.get(url)
    if exp is None:
        return False
    if time.time() >= exp:
        del _negative_until[url]
        return False
    return True


def _negative_mark(url: str) -> None:
    _negative_until[url] = time.time() + WEB_FETCH_NEGATIVE_CACHE_SEC


def _throttle() -> None:
    global _last_fetch_monotonic
    if WEB_FETCH_MIN_INTERVAL_SEC <= 0:
        _last_fetch_monotonic = time.monotonic()
        return
    now = time.monotonic()
    wait = WEB_FETCH_MIN_INTERVAL_SEC - (now - _last_fetch_monotonic)
    if wait > 0:
        time.sleep(wait)
    _last_fetch_monotonic = time.monotonic()


def normalize_fetch_url(website: str) -> Optional[str]:
    u = (website or "").strip()
    low = u.lower()
    if not u or low.startswith("(brak"):
        return None
    if not u.startswith(("http://", "https://")):
        u = "https://" + u.lstrip("/")
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower()
    if not host or host in {"localhost", "127.0.0.1"} or host.endswith(".local"):
        return None
    return u


def _cache_put(url: str, excerpt: str) -> None:
    while len(_cache) >= WEB_FETCH_CACHE_MAX_URLS and _cache:
        oldest_key = min(_cache.items(), key=lambda kv: kv[1][0])[0]
        del _cache[oldest_key]
    _cache[url] = (time.time(), excerpt)


def html_to_clean_text(html: str) -> str:
    if BeautifulSoup is None:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def fetch_page_excerpt(url: str) -> Optional[str]:
    """
    Pobiera HTML, wycina tekst, zwraca skrót lub None przy błędzie / braku treści.
    Respektuje cache TTL i minimalny odstęp między requestami.
    """
    if not WEB_CONTEXT_ENABLED or requests is None or BeautifulSoup is None:
        return None
    norm = normalize_fetch_url(url)
    if not norm:
        return None

    now = time.time()
    if norm in _cache:
        ts, excerpt = _cache[norm]
        if now - ts < WEB_FETCH_CACHE_TTL_SEC:
            return excerpt

    if _negative_blocks(norm):
        return None

    try:
        from fetch_throttle import throttle_hostname_before_http
    except ImportError:
        throttle_hostname_before_http = lambda _u: None

    last_error: Optional[Exception] = None
    for attempt in range(WEB_FETCH_HTTP_RETRIES):
        try:
            throttle_hostname_before_http(norm)
            _throttle()
            with requests.get(
                norm,
                timeout=WEB_FETCH_TIMEOUT,
                headers={"User-Agent": WEB_FETCH_USER_AGENT},
                stream=True,
            ) as resp:
                if resp.status_code >= 400:
                    last_error = RuntimeError(f"HTTP {resp.status_code}")
                    continue
                enc = (resp.encoding or "utf-8").strip() or "utf-8"
                ctype = (resp.headers.get("content-type") or "").lower()
                raw = b""
                for chunk in resp.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    raw += chunk
                    if len(raw) >= WEB_FETCH_MAX_BYTES:
                        break
            if "html" not in ctype and not raw.lstrip()[:500].strip().startswith(
                b"<"
            ):
                last_error = RuntimeError("not html")
                continue
            html = raw.decode(enc, errors="replace")
            text = html_to_clean_text(html)
            if len(text) < 80:
                last_error = RuntimeError("short text")
                continue
            if len(text) > WEB_FETCH_MAX_EXCERPT_CHARS:
                text = text[: WEB_FETCH_MAX_EXCERPT_CHARS - 3].rstrip() + "..."
            _cache_put(norm, text)
            return text
        except Exception as e:
            last_error = e
            time.sleep(min(4.0, 1.0 * (attempt + 1)))
    if last_error is not None:
        _negative_mark(norm)
        logger.debug("fetch_page_excerpt: brak treści dla %s — %s", norm, last_error)
    return None


def append_page_excerpt_to_context_json(
    row_context_json: str,
    website: str,
) -> str:
    """
    Dodaje do obiektu JSON z _build_row_context pole z publicznym skrótem strony (jeśli się uda).
    Przy błędzie parsowania lub braku danych zwraca oryginalny string.
    """
    excerpt = fetch_page_excerpt(website)
    if not excerpt:
        return row_context_json
    try:
        obj: Dict[str, Any] = json.loads(row_context_json)
    except (json.JSONDecodeError, TypeError):
        return row_context_json
    obj["fragment_publicznej_strony_www"] = excerpt
    obj["_web_context_url"] = normalize_fetch_url(website) or website
    return json.dumps(obj, ensure_ascii=False, indent=2)
