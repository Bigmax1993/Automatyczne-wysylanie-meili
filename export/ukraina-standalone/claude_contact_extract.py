# -*- coding: utf-8 -*-
"""Claude Sonnet: kontakty z Website-Crawl, gdy Regex nichts findet."""
from __future__ import annotations

from typing import Callable

from claude_client import claude_generate_text
from claude_prompts import build_contact_extract_prompt
from contact_extract_utils import parse_contact_extract_response
from scraper_env import get_anthropic_api_key


def merge_claude_contacts_into_collected(collected: dict, parsed: dict) -> dict:
    """Fügt Claude-Treffer in collected ein (ohne Duplikate)."""
    out = dict(collected)
    emails = list(out.get("emails") or [])
    impressum_emails = list(out.get("impressum_emails") or [])
    phones = list(out.get("phones") or [])

    for e in parsed.get("emails") or []:
        if e and e not in emails:
            emails.append(e)
    for e in parsed.get("impressum_emails") or []:
        if e and e not in impressum_emails:
            impressum_emails.append(e)
        if e and e not in emails:
            emails.append(e)
    for p in parsed.get("phones") or []:
        if p and p not in phones:
            phones.append(p)

    if parsed.get("company_name") and not out.get("company_name"):
        out["company_name"] = parsed["company_name"]

    out["emails"] = emails
    out["impressum_emails"] = impressum_emails
    out["phones"] = phones
    out["claude_contact_reason"] = parsed.get("reason") or ""
    return out


def claude_extract_contacts_from_pages(
    company_name: str,
    website: str,
    page_text: str,
    logger,
    cache: dict | None,
    *,
    cache_key: str = "",
    on_step: Callable[[str], None] | None = None,
) -> dict | None:
    """Sucht E-Mails/Telefone im gecrawlten Seitentext per Claude."""
    api_key = get_anthropic_api_key()
    if not api_key or not (page_text or "").strip():
        return None

    key = cache_key or website or company_name
    extract_cache = (cache or {}).setdefault("claude_contact_extract", {})
    if key in extract_cache:
        cached = extract_cache[key]
        return dict(cached) if isinstance(cached, dict) else None

    prompt = build_contact_extract_prompt(company_name, website, page_text)
    try:
        text, model = claude_generate_text(
            prompt,
            logger,
            api_key,
            cache=cache,
            model_tier="verify",
            on_step=on_step,
        )
        if logger:
            logger.info("Claude contact extract, model=%s, key=%s", model, key[:80])
        parsed = parse_contact_extract_response(text)
        extract_cache[key] = parsed
        return parsed
    except Exception as exc:
        if logger:
            logger.warning("Claude contact extract: %s", exc)
        return None
