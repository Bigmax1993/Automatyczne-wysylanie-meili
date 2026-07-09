# -*- coding: utf-8 -*-
"""Claude Haiku: czyszczenie wiersza przed eksportem do Excela."""
from __future__ import annotations

import json
import re
from typing import Callable

from claude_client import claude_generate_text
from scraper_env import get_anthropic_api_key

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_claude_row_cleanup_response(text: str) -> dict:
    raw = (text or "").strip()
    match = _JSON_BLOCK_RE.search(raw)
    payload = match.group(0) if match else raw
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("Claude row cleanup: not a JSON object")
    return {
        "company_name_clean": str(data.get("company_name_clean") or "").strip(),
        "address": str(data.get("address") or "").strip(),
        "phone": str(data.get("phone") or "").strip(),
        "website": str(data.get("website") or "").strip(),
        "bundesland": str(data.get("bundesland") or "").strip(),
        "handelsketten": str(data.get("handelsketten") or "").strip(),
        "url": str(data.get("url") or "").strip(),
    }


def claude_cleanup_row_fields(
    prompt: str,
    logger,
    cache: dict | None,
    *,
    on_step: Callable[[str], None] | None = None,
) -> dict | None:
    api_key = get_anthropic_api_key()
    if not api_key:
        return None
    try:
        text, model = claude_generate_text(
            prompt,
            logger,
            api_key,
            cache=cache,
            bypass_daily_limit=True,
            model_tier="fast",
            on_step=on_step,
        )
        logger.info("Claude row cleanup, model=%s", model)
        return parse_claude_row_cleanup_response(text)
    except Exception as exc:
        logger.warning("Claude row cleanup: %s", exc)
        return None
