# -*- coding: utf-8 -*-
"""Wykrywanie Cloudflare / WAF / CAPTCHA — pomijanie stron zamiast retry."""
from __future__ import annotations

import re
from typing import Any


class PageAccessBlocked(Exception):
    """Strona chroniona (Cloudflare itp.) — bez ponawiania żądań."""


# Kody HTTP typowe dla Cloudflare i podobnych reverse proxy
WAF_HTTP_STATUS_CODES = frozenset(
    {
        401,
        403,
        429,
        503,
        520,
        521,
        522,
        523,
        524,
        525,
        526,
        527,
        530,
    }
)

_WAF_STRONG_HTML_MARKERS = (
    "cf-browser-verification",
    "challenge-platform",
    "cdn-cgi/challenge",
    "checking your browser",
    "just a moment",
    "enable javascript and cookies",
    "attention required! | cloudflare",
    "ray id:",
    "__cf_chl",
    "cf-chl-bypass",
    "perimeterx",
    "datadome",
    "incapsula incident",
    "sucuri website firewall",
    "distilnetworks",
    "bot protection",
)

_WAF_WEAK_HTML_MARKERS = (
    "cloudflare",
    "captcha",
    "hcaptcha",
    "recaptcha",
    "turnstile",
    "access denied",
    "forbidden",
    "ddos protection",
)

_WAF_ERROR_TEXT_MARKERS = (
    "cloudflare",
    "servererror",
    "522",
    "521",
    "520",
    "captcha",
    "too many requests",
    "access denied",
    "forbidden",
    "bot detected",
    "waf",
)


def _status_from_response(response: Any) -> int | None:
    if response is None:
        return None
    code = getattr(response, "status_code", None)
    return int(code) if code is not None else None


def _status_from_exception(exc: BaseException) -> int | None:
    resp = getattr(exc, "response", None)
    code = _status_from_response(resp)
    if code is not None:
        return code
    text = str(exc).lower()
    m = re.search(
        r"\b(401|403|429|503|520|521|522|523|524|525|526|527|530)\b",
        text,
    )
    return int(m.group(1)) if m else None


def _headers_blob(response: Any) -> str:
    if response is None:
        return ""
    try:
        items = getattr(response, "headers", None)
        if items is None:
            return ""
        return " ".join(f"{k}:{v}" for k, v in items.items()).lower()
    except Exception:
        return ""


def is_waf_html(html: str) -> bool:
    """Treść wygląda na stronę blokady / weryfikacji, nie na normalną witrynę."""
    if not html:
        return False
    sample = html[:80000].lower()
    if any(m in sample for m in _WAF_STRONG_HTML_MARKERS):
        return True
    if len(html) < 80:
        return False
    weak = sum(1 for m in _WAF_WEAK_HTML_MARKERS if m in sample)
    return weak >= 2 and len(html) < 20000


def is_waf_blocked(
    *,
    exc: BaseException | None = None,
    response: Any = None,
    html: str | None = None,
) -> bool:
    if response is not None:
        status = _status_from_response(response)
        if status in WAF_HTTP_STATUS_CODES:
            return True
        hdr = _headers_blob(response)
        if "cloudflare" in hdr or "cf-ray" in hdr or "cf-mitigated" in hdr:
            if status is None or status >= 400:
                return True
        body = html if html is not None else getattr(response, "text", "") or ""
        if body and is_waf_html(body):
            return True

    if exc is not None:
        status = _status_from_exception(exc)
        if status in WAF_HTTP_STATUS_CODES:
            return True
        low = str(exc).lower()
        if any(m in low for m in _WAF_ERROR_TEXT_MARKERS):
            if status in WAF_HTTP_STATUS_CODES or status in (403, 429, 503) or status is None:
                if "522" in low or "521" in low or "520" in low or "cloudflare" in low:
                    return True
                if status in WAF_HTTP_STATUS_CODES:
                    return True

    if html and is_waf_html(html):
        return True
    return False


def waf_block_reason(
    *,
    exc: BaseException | None = None,
    response: Any = None,
    html: str | None = None,
) -> str:
    status = _status_from_response(response) or (
        _status_from_exception(exc) if exc else None
    )
    if status in WAF_HTTP_STATUS_CODES:
        return f"http_{status}"
    if html and is_waf_html(html):
        return "waf_html"
    if exc is not None:
        low = str(exc).lower()
        if "522" in low:
            return "cloudflare_522"
        if "cloudflare" in low:
            return "cloudflare"
    hdr = _headers_blob(response)
    if "cloudflare" in hdr or "cf-ray" in hdr:
        return "cloudflare_headers"
    return "waf_blocked"
