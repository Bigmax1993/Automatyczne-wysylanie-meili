# -*- coding: utf-8 -*-
"""Claude: spersonalizowane zapytania mailowe UA (ukraiński) per firma."""
from __future__ import annotations

import json
import re
from typing import Callable

from claude_client import claude_generate_text
from email_custom_template import parse_llm_email_json
from scraper_env import get_anthropic_api_key
from ua_claude_prompts import build_personalized_inquiry_email_prompt_uk
from ua_materialy_inquiry_email_uk import build_inquiry_signature_uk


def _contact_blob(contact_info: dict | None) -> dict[str, str]:
    info = contact_info or {}
    return {
        "company_name": str(
            info.get("company_name_clean")
            or info.get("company_name")
            or info.get("nazwa")
            or ""
        ).strip(),
        "website": str(
            info.get("official_website") or info.get("www") or info.get("url") or ""
        ).strip(),
        "oblast": str(info.get("bundesland") or info.get("oblast") or "").strip(),
        "address": str(
            info.get("full_address") or info.get("adres") or info.get("address") or ""
        ).strip(),
        "materials": str(info.get("retail_chains_found") or "").strip(),
        "page_snippet": str(info.get("page_snippet") or info.get("snippet") or "").strip(),
        "phone": str(info.get("phones_found") or info.get("phone") or "").strip(),
    }


def claude_generate_inquiry_email_ua(
    company_name: str,
    logger,
    cache: dict | None,
    *,
    contact_info: dict | None = None,
    cache_key: str = "",
    style_hint: str = "",
    on_step: Callable[[str], None] | None = None,
) -> tuple[str, str] | None:
    """
    Pełna personalizacja maila B2B po ukraińsku. Zwraca (subject, body) lub None.
    Wynik cache'owany w cache['claude_inquiry_email'].
    """
    api_key = get_anthropic_api_key()
    if not api_key:
        return None

    key = (cache_key or _contact_blob(contact_info).get("website") or company_name).strip()
    if not key:
        key = (company_name or "firma").strip()

    mail_cache = (cache or {}).setdefault("claude_inquiry_email", {})
    if key in mail_cache:
        cached = mail_cache[key]
        if isinstance(cached, dict):
            subj = str(cached.get("subject") or "").strip()
            body = str(cached.get("body") or "").strip()
            if subj and body:
                return subj, body

    ctx = _contact_blob(contact_info)
    display_name = ctx["company_name"] or (company_name or "").strip() or "Постачальник"
    prompt = build_personalized_inquiry_email_prompt_uk(
        company_name=display_name,
        website=ctx["website"],
        oblast=ctx["oblast"],
        address=ctx["address"],
        materials=ctx["materials"],
        page_snippet=ctx["page_snippet"],
        style_hint=style_hint,
    )
    try:
        text, model = claude_generate_text(
            prompt,
            logger,
            api_key,
            cache=cache,
            model_tier="verify",
            on_step=on_step,
            bypass_daily_limit=True,
        )
        logger.info("Claude inquiry email UA, model=%s, key=%s", model, key[:80])
        fallback_subject = f"Запит щодо постачання будматеріалів — {display_name}"
        subject, body = parse_llm_email_json(text, fallback_subject)
        signature = build_inquiry_signature_uk()
        if signature and signature not in body:
            body = body.rstrip() + "\n\n" + signature
        from ua_materialy_inquiry_email_uk import (
            strip_de_campaign_branding,
            strip_german_phones_from_text,
        )

        body = strip_german_phones_from_text(body)
        body = strip_de_campaign_branding(body)
        mail_cache[key] = {"subject": subject, "body": body, "model": model}
        return subject, body
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        logger.warning("Claude inquiry email UA parse error: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Claude inquiry email UA: %s", exc)
        return None
