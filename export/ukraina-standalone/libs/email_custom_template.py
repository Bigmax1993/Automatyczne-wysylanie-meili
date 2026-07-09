# -*- coding: utf-8 -*-
"""
Własna treść zapytania ofertowego z GUI → dopracowanie Claude per firma.
Nie dotyczy maili przypominających (scraper_email_replies.build_reminder_email).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from claude_client import claude_generate_text
from claude_prompts import build_custom_email_prompt_uk
from scraper_env import get_anthropic_api_key


def build_custom_draft_prompt(
    draft: str,
    company_name: str,
    lang: str = "pl",
    *,
    city_name: str = "",
    delivery_address: str = "",
) -> str:
    draft = (draft or "").strip()
    if lang not in ("uk", "ua"):
        lang = "uk"
    return build_custom_email_prompt_uk(
        draft,
        company_name,
        city_name=city_name,
        delivery_address=delivery_address,
    )


def parse_llm_email_json(text: str, fallback_subject: str) -> tuple[str, str]:
    match = re.search(r"\{.*\}", text or "", flags=re.DOTALL)
    raw = match.group(0) if match else (text or "")
    parsed = json.loads(raw)
    subject = str(parsed.get("subject") or fallback_subject).strip()
    body = str(parsed.get("body") or "").strip()
    if not body:
        raise ValueError("Claude zwróciło pusty body")
    return subject, body


def claude_generate_text_simple(
    prompt: str, logger: logging.Logger | None = None
) -> tuple[str, str]:
    api_key = get_anthropic_api_key()
    if not api_key:
        raise RuntimeError("Brak ANTHROPIC_API_KEY")
    text, model = claude_generate_text(
        prompt,
        logger or logging.getLogger("email_custom_template"),
        api_key,
        cache=None,
        bypass_daily_limit=True,
    )
    return text, model


def beautify_custom_email_draft(
    draft: str,
    company_name: str,
    lang: str = "pl",
    *,
    fallback_subject: str = "",
    city_name: str = "",
    delivery_address: str = "",
    logger: logging.Logger | None = None,
) -> tuple[str, str]:
    """
    Dopracowuje wklejoną treść pod konkretną firmę (zapytania ofertowe).
    """
    draft = (draft or "").strip()
    if not draft:
        raise ValueError("Pusta treść szablonu")
    if not fallback_subject:
        if lang == "de":
            fallback_subject = f"Preisanfrage – {company_name}"
        elif lang == "uk":
            fallback_subject = f"Запит щодо постачання будматеріалів — {company_name}"
        else:
            fallback_subject = f"Zapytanie ofertowe – {company_name}"
    prompt = build_custom_draft_prompt(
        draft,
        company_name,
        lang,
        city_name=city_name,
        delivery_address=delivery_address,
    )
    text, model = claude_generate_text_simple(prompt, logger=logger)
    if logger:
        logger.info(f"Claude (własny szablon), model: {model}")
    return parse_llm_email_json(text, fallback_subject)


def fallback_email_without_llm(
    draft: str, company_name: str, fallback_subject: str
) -> tuple[str, str]:
    """Gdy brak API — wstaw nazwę firmy w pierwszej linii kontekstu."""
    body = draft.strip()
    if company_name and company_name not in body:
        body = f"{body}\n\n(Firma: {company_name})"
    return fallback_subject, body


def inquiry_try_custom(
    *,
    use_custom: bool,
    custom_draft: str,
    company_name: str,
    lang: str,
    logger: logging.Logger,
    subject_hint: str,
    email_context: dict[str, Any] | None = None,
    on_step: Any = None,
) -> tuple[str, str] | None:
    """
    Jeśli włączony własny szablon — zwraca (subject, body) z Claude.
    Jeśli nie — zwraca None (scraper używa standardowego generatora).
    Nie dotyczy przypomnień e-mail.
    """
    draft = (custom_draft or "").strip()
    if not use_custom or not draft:
        return None
    if on_step:
        on_step(f"E-mail z własnego szablonu (Claude, {lang}): {company_name}")
    ctx = email_context or {}
    city_name = str(ctx.get("city_name") or ctx.get("city") or "")
    delivery_address = str(ctx.get("delivery_address") or "")
    try:
        return beautify_custom_email_draft(
            draft,
            company_name,
            lang,
            fallback_subject=subject_hint,
            city_name=city_name,
            delivery_address=delivery_address,
            logger=logger,
        )
    except Exception as e:
        logger.warning(f"Claude (własny szablon) fallback: {e}")
        if get_anthropic_api_key():
            raise
        return fallback_email_without_llm(draft, company_name, subject_hint)
