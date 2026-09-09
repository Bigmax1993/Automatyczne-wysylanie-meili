# -*- coding: utf-8 -*-
"""Claude Sonnet: weryfikacja strony — postawalcy materiałów budowlanych UA."""
from __future__ import annotations

from typing import Callable

from claude_client import claude_generate_text
from ua_page_verify import (
    apply_page_verdict,
    build_page_verify_prompt,
    hard_reject_page_context,
    parse_page_verify_response,
)
from ua_materialy_supplier_filter import is_generalunternehmer
from scraper_env import get_anthropic_api_key


def claude_verify_company_page(
    company_name: str,
    website: str,
    page_text: str,
    logger,
    cache: dict | None,
    *,
    cache_key: str = "",
    serper_blob: str = "",
    require_generalunternehmer: bool = True,
    require_small_firm: bool = False,
    on_step: Callable[[str], None] | None = None,
) -> dict | None:
    api_key = get_anthropic_api_key()
    if not api_key:
        return None

    verify_cache = (cache or {}).setdefault("claude_page_verify", {})
    if not verify_cache and cache_key:
        legacy = (cache or {}).get("gemini_page_verify") or {}
        if cache_key in legacy:
            verify_cache[cache_key] = dict(legacy[cache_key])
    if cache_key and cache_key in verify_cache:
        return dict(verify_cache[cache_key])

    hard, hard_reason = hard_reject_page_context(
        url=website, name=company_name, page_text=page_text
    )
    if hard:
        out = {
            "verified": False,
            "verification_reason": hard_reason,
            "retail_chains": [],
            "claude": {},
        }
        if cache_key:
            verify_cache[cache_key] = out
        return out

    pages_crawled = (page_text or "").count("=== http")
    prompt = build_page_verify_prompt(
        company_name,
        website,
        page_text,
        serper_blob=serper_blob,
        pages_crawled=pages_crawled,
    )
    try:
        text, model = claude_generate_text(
            prompt, logger, api_key, cache=cache, model_tier="verify", on_step=on_step
        )
        logger.info("Claude page verify UA, model=%s", model)
        parsed = parse_page_verify_response(text)
    except Exception as exc:
        logger.warning("Claude page verify UA: %s", exc)
        return None

    verified, reason, chains = apply_page_verdict(
        parsed,
        page_text=page_text,
        serper_blob=serper_blob,
        require_generalunternehmer=require_generalunternehmer,
        require_small_firm=require_small_firm,
    )
    supplier_ok, supplier_marker = is_generalunternehmer(
        " ".join([page_text, serper_blob, " ".join(parsed.get("matched_gu_keywords") or [])])
    )
    out = {
        "verified": verified,
        "verification_reason": reason,
        "retail_chains": chains,
        "is_gu": supplier_ok,
        "gu_marker": supplier_marker,
        "is_small_firm": bool(parsed.get("is_small_firm")),
        "claude": parsed,
    }
    if cache_key:
        verify_cache[cache_key] = out
    return out
