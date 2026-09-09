# -*- coding: utf-8 -*-
"""Przygotowanie tekstu crawla dla Claude (sortowanie URL, nagłówek, dowody)."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from website_full_crawl import WebsiteCrawlResult

_VERIFY_URL_TIERS: tuple[tuple[str, ...], ...] = (
    (
        "referenz",
        "projekt",
        "portfolio",
        "realisierung",
        "bauprojekt",
        "karriere",
        "stellen",
        "jobs",
        "career",
    ),
    ("unternehmen", "ueber-uns", "über-uns", "about", "wir"),
    (
        "einzelhandel",
        "filial",
        "retail",
        "supermarkt",
        "gewerbe",
        "discounter",
        "markt",
        "ladenbau",
    ),
    ("impressum", "kontakt", "contact"),
)

_CONTACT_URL_TIERS: tuple[tuple[str, ...], ...] = (
    ("impressum", "kontakt", "contact", "datenschutz", "anschrift"),
    ("unternehmen", "ueber-uns", "über-uns", "about"),
    ("referenz", "projekt", "portfolio"),
)

_EVIDENCE_KEYWORDS = (
    "referenz",
    "projekt",
    "portfolio",
    "auftraggeber",
    "netto",
    "rewe",
    "aldi",
    "lidl",
    "kaufland",
    "penny",
    "edeka",
    "einzelhandel",
    "retail",
    "filial",
    "supermarkt",
    "discounter",
    "generalunternehmer",
    "filialbau",
    "neubau",
    "umbau",
    "galerie",
    "realisierung",
    "karriere",
)

CRAWL_SECTION_MAX_CHARS = 2000


def sort_crawl_urls_for_claude(urls: list[str], *, purpose: str = "verify") -> list[str]:
    """Kolejność sekcji w prompcie: verify=referenzen/karriere, contact=impressum."""
    tiers = _CONTACT_URL_TIERS if purpose == "contact" else _VERIFY_URL_TIERS

    def _score(url: str) -> tuple[int, str]:
        low = (url or "").lower()
        for tier, patterns in enumerate(tiers):
            if any(p in low for p in patterns):
                return (tier, low)
        path = (urlparse(url).path or "/").strip("/")
        if not path:
            return (len(tiers), low)
        return (len(tiers) + 1, low)

    return sorted(urls, key=_score)


def truncate_crawl_section_text(text: str, *, max_chars: int = CRAWL_SECTION_MAX_CHARS) -> str:
    raw = (text or "").strip()
    if len(raw) <= max_chars:
        return raw
    return raw[: max_chars - 3] + "..."


def extract_crawl_section_urls(page_text: str, *, limit: int = 8) -> list[str]:
    if "=== http" not in (page_text or ""):
        return []
    return re.findall(r"=== (https?://\S+) ===", page_text)[:limit]


def build_claude_context_header(
    company_name: str,
    website: str,
    *,
    serper_blob: str = "",
    pages_crawled: int = 0,
    priority_urls: list[str] | None = None,
) -> str:
    lines = [
        f"FIRMA: {company_name}",
        f"WEBSITE: {website}",
    ]
    serper = (serper_blob or "").strip()
    if serper:
        lines.append(f"SERPER-KONTEXT: {serper[:800]}")
    if pages_crawled:
        lines.append(f"SEITEN IM CRAWL: {pages_crawled}")
    if priority_urls:
        site = (website or "").rstrip("/")
        short_parts: list[str] = []
        for url in priority_urls[:8]:
            path = (url or "").replace(site, "").strip("/") or "/"
            short_parts.append(path)
        lines.append(f"PRIORITAETS-URLS: {', '.join(short_parts)}")
    return "\n".join(lines)


def build_automatic_evidence_excerpt(page_text: str, *, max_lines: int = 30) -> str:
    """Krótkie linie z crawl-a pasujące do retail/GU — na górze promptu verify."""
    raw = (page_text or "").strip()
    if not raw:
        return "(keine)"

    lines: list[str] = []
    seen: set[str] = set()

    def _maybe_add(prefix: str, fragment: str) -> None:
        frag = " ".join(fragment.split()).strip()
        if len(frag) < 12:
            return
        low = frag.lower()
        if not any(k in low for k in _EVIDENCE_KEYWORDS):
            return
        key = frag[:120]
        if key in seen:
            return
        seen.add(key)
        lines.append(f"• {prefix}{frag[:240]}")

    if "=== http" in raw:
        sections = re.split(r"(?=\n=== https?://)", "\n" + raw)
        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue
            m = re.match(r"=== (https?://\S+) ===\s*(.*)", sec, re.DOTALL)
            if not m:
                continue
            url, body = m.group(1), m.group(2)
            for part in re.split(r"[\n\r]+", body):
                _maybe_add(f"[{url}] ", part)
                if len(lines) >= max_lines:
                    break
            if len(lines) >= max_lines:
                break
    else:
        for part in re.split(r"[\n\r.!?]+", raw):
            _maybe_add("", part)
            if len(lines) >= max_lines:
                break

    return "\n".join(lines) if lines else "(keine automatischen Treffer)"


def format_crawl_text_for_claude(
    result: WebsiteCrawlResult,
    *,
    purpose: str = "verify",
    per_section_max_chars: int = CRAWL_SECTION_MAX_CHARS,
) -> str:
    """Tekst crawla: sortowanie URL + limit znaków na sekcję."""
    urls = sort_crawl_urls_for_claude(result.urls_visited, purpose=purpose)
    parts: list[str] = []
    for url in urls:
        page = result.pages.get(url) or {}
        text = truncate_crawl_section_text(
            page.get("page_text") or "", max_chars=per_section_max_chars
        )
        if text:
            parts.append(f"=== {url} ===\n{text}")
    return "\n\n".join(parts)
