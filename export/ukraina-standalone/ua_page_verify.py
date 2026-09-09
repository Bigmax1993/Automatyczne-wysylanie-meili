# -*- coding: utf-8 -*-
"""Weryfikacja strony www — postawalcy materiałów budowlanych UA."""
from __future__ import annotations

import json
import re

from ua_campaign_keyword_profile import REJECT_PRIMARY_ROLES
from ua_claude_prompts import build_page_verify_prompt as _build_page_verify_prompt
from ua_materialy_supplier_filter import (
    REQUIRED_RETAIL_CHAIN_KEYWORDS,
    detect_required_retail_chains,
    has_market_project_evidence_on_website,
    has_store_shell_build_evidence,
    is_excluded_non_gu_role,
    is_generalunternehmer,
    is_interior_fitout_specialist,
    is_media_publisher_contact,
    is_retail_store_operator_contact,
    qualifies_as_gu_for_campaign,
)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)
_REJECT_ROLES_NORMALIZED = {r.lower() for r in REJECT_PRIMARY_ROLES}


def hard_reject_page_context(
    *,
    url: str = "",
    name: str = "",
    page_text: str = "",
) -> tuple[bool, str]:
    blob = " ".join([name, url, page_text]).lower()
    if is_retail_store_operator_contact(url=url, text=blob):
        return True, "marketplace_ogloszenia"
    if is_media_publisher_contact(url=url, name=name, text=blob):
        return True, "mediaportal"
    if is_excluded_non_gu_role(blob):
        return True, "excluded_non_supplier_role"
    interior, interior_reason = is_interior_fitout_specialist(blob)
    if interior:
        return True, interior_reason
    return False, ""


def build_page_verify_prompt(
    company_name: str,
    website: str,
    page_text: str,
    *,
    max_chars: int = 8000,
    serper_blob: str = "",
    pages_crawled: int = 0,
) -> str:
    return _build_page_verify_prompt(
        company_name,
        website,
        page_text,
        max_chars=max_chars,
        serper_blob=serper_blob,
        pages_crawled=pages_crawled,
    )


def parse_page_verify_response(text: str) -> dict:
    raw = (text or "").strip()
    match = _JSON_BLOCK_RE.search(raw)
    payload = match.group(0) if match else raw
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("Page verify: not a JSON object")

    def _list(key: str) -> list[str]:
        val = data.get(key) or []
        if not isinstance(val, list):
            return []
        return [str(x).strip() for x in val if str(x).strip()]

    return {
        "matched_gu_keywords": _list("matched_gu_keywords"),
        "matched_retail_keywords": _list("matched_retail_keywords"),
        "matched_chains": [c.lower() for c in _list("matched_chains")],
        "matched_negative_keywords": _list("matched_negative_keywords"),
        "is_gu": bool(data.get("is_gu")),
        "has_retail_context": bool(data.get("has_retail_context")),
        "is_small_firm": bool(data.get("is_small_firm")),
        "primary_role": str(data.get("primary_role") or "").strip(),
        "reason": str(data.get("reason") or "").strip(),
    }


def apply_page_verdict(
    llm: dict,
    *,
    page_text: str,
    serper_blob: str = "",
    require_generalunternehmer: bool = True,
    require_small_firm: bool = False,
) -> tuple[bool, str, list[str]]:
    blob = " ".join([page_text or "", serper_blob or ""]).lower()
    hard, hard_reason = hard_reject_page_context(page_text=blob)
    if hard:
        return False, hard_reason, []

    neg = llm.get("matched_negative_keywords") or []
    if neg:
        return False, f"claude_negative:{neg[0]}", llm.get("matched_chains") or []

    role = (llm.get("primary_role") or "").strip()
    if role and role.lower() in _REJECT_ROLES_NORMALIZED:
        return False, f"claude_role:{role}", llm.get("matched_chains") or []

    supplier_ok, _marker = qualifies_as_gu_for_campaign(blob)
    if not llm.get("is_gu") and not supplier_ok:
        return False, "claude_kein_lieferant", llm.get("matched_chains") or []

    if require_generalunternehmer:
        supplier_text, _ = is_generalunternehmer(blob)
        supplier_json = bool(llm.get("matched_gu_keywords"))
        if not supplier_text and not supplier_json and not supplier_ok:
            return False, "kein_material_lieferant", llm.get("matched_chains") or []

    has_materials = bool(llm.get("has_retail_context")) or has_market_project_evidence_on_website(
        blob
    )
    if not has_materials:
        return False, "claude_kein_materialkontext", llm.get("matched_chains") or []

    llm_categories = [
        c.lower()
        for c in (llm.get("matched_chains") or [])
        if c and c.lower() in set(REQUIRED_RETAIL_CHAIN_KEYWORDS)
    ]
    blob_categories = detect_required_retail_chains(blob)
    chains = list(dict.fromkeys(llm_categories + blob_categories))

    if not has_store_shell_build_evidence(blob) and not chains:
        return False, "kein_katalog_oder_kategorie", chains

    if require_small_firm and not llm.get("is_small_firm"):
        return False, "claude_kein_kleinunternehmen", chains

    reason = (llm.get("reason") or "claude_material_supplier").strip()
    return True, f"claude:{reason[:120]}", chains
