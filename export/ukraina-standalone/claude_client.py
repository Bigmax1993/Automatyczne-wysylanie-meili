# -*- coding: utf-8 -*-
"""Klient Anthropic Messages API — modele hybrydowe (Haiku / Sonnet)."""
from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Callable, Literal

import requests

from scraper_env import get_anthropic_api_key, get_env_value

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
# claude-sonnet-4-20250514 wycofany ~15.06.2026 → 404 na API
DEFAULT_CLAUDE_MODEL_VERIFY = "claude-sonnet-4-6"
DEFAULT_CLAUDE_MODEL_FAST = "claude-haiku-4-5"
# Kompatybilność wsteczna (CLAUDE_MODEL = tier verify)
DEFAULT_CLAUDE_MODEL = DEFAULT_CLAUDE_MODEL_VERIFY
CLAUDE_MODEL_TIER = Literal["fast", "verify"]
CLAUDE_REQUEST_TIMEOUT = 120
CLAUDE_MIN_INTERVAL_SECONDS = 1.2
CLAUDE_API_RETRY_ATTEMPTS = 3
CLAUDE_API_RETRY_WAIT_SECONDS = 20
CLAUDE_DAILY_LIMIT = 3000
CLAUDE_DISCOVERY_RESERVE = 1000
# Domyślnie bez dziennego limitu wywołań (jak SERPER_UNLIMITED).
CLAUDE_UNLIMITED = True


def _truthy_env(raw: str) -> bool:
    return str(raw or "").strip().lower() in ("1", "true", "yes", "tak", "on")


def configure_claude_limits(
    *,
    daily_limit: int | None = None,
    reserve: int | None = None,
    unlimited: bool | None = None,
) -> None:
    global CLAUDE_DAILY_LIMIT, CLAUDE_DISCOVERY_RESERVE, CLAUDE_UNLIMITED
    if daily_limit is not None:
        CLAUDE_DAILY_LIMIT = int(daily_limit)
    if reserve is not None:
        CLAUDE_DISCOVERY_RESERVE = int(reserve)
    if unlimited is not None:
        CLAUDE_UNLIMITED = bool(unlimited)


def is_claude_unlimited() -> bool:
    """Brak dziennego limitu / rezerwy na wywołania Claude."""
    return bool(CLAUDE_UNLIMITED)


if _truthy_env(get_env_value("CLAUDE_UNLIMITED", "")) or _truthy_env(
    get_env_value("DISABLE_CLAUDE_DAILY_LIMIT", "")
):
    CLAUDE_UNLIMITED = True


def get_claude_model_verify() -> str:
    legacy = get_env_value("CLAUDE_MODEL", "")
    explicit = get_env_value("CLAUDE_MODEL_VERIFY", "")
    return explicit or legacy or DEFAULT_CLAUDE_MODEL_VERIFY


def get_claude_model_fast() -> str:
    return get_env_value("CLAUDE_MODEL_FAST", DEFAULT_CLAUDE_MODEL_FAST) or DEFAULT_CLAUDE_MODEL_FAST


def get_claude_model() -> str:
    return get_claude_model_verify()


def resolve_claude_model(
    *,
    model: str | None = None,
    model_tier: CLAUDE_MODEL_TIER | None = None,
) -> str:
    if model:
        return model.strip()
    if model_tier == "fast":
        return get_claude_model_fast()
    return get_claude_model_verify()


def _campaign_today() -> str:
    try:
        from zoneinfo import ZoneInfo

        tz = get_env_value("SCRAPER_TIMEZONE", "Europe/Warsaw")
        return datetime.now(ZoneInfo(tz)).date().isoformat()
    except Exception:
        return date.today().isoformat()


def _claude_rate_bucket(cache: dict | None) -> dict:
    return (cache or {}).setdefault("claude_api", {})


def get_remaining_daily_claude_limit(cache: dict | None) -> tuple[str, int, int]:
    today = _campaign_today()
    daily = (cache or {}).setdefault("claude_daily", {})
    used_today = int(daily.get(today, 0))
    if is_claude_unlimited():
        return today, used_today, CLAUDE_DAILY_LIMIT
    remaining = max(0, CLAUDE_DAILY_LIMIT - used_today)
    return today, used_today, remaining


def increase_daily_claude_counter(cache: dict | None, increment: int = 1) -> None:
    today = _campaign_today()
    daily = (cache or {}).setdefault("claude_daily", {})
    daily[today] = int(daily.get(today, 0)) + int(increment)


def is_claude_limit_reached_today(cache: dict | None) -> bool:
    if is_claude_unlimited():
        return False
    _, _, remaining = get_remaining_daily_claude_limit(cache)
    return remaining <= CLAUDE_DISCOVERY_RESERVE


def is_claude_rate_limited(cache: dict | None) -> bool:
    bucket = _claude_rate_bucket(cache)
    until = float(bucket.get("cooldown_until") or 0)
    return until > time.time()


def mark_claude_rate_limited(cache: dict | None, logger: logging.Logger | None = None) -> None:
    bucket = _claude_rate_bucket(cache)
    bucket["cooldown_until"] = time.time() + 90
    if logger:
        logger.warning("Claude API: cooldown 90s (rate limit)")


def wait_for_claude_slot(cache: dict | None) -> None:
    bucket = _claude_rate_bucket(cache)
    last = float(bucket.get("last_call_at") or 0)
    wait = CLAUDE_MIN_INTERVAL_SECONDS - (time.time() - last)
    if wait > 0:
        time.sleep(wait)
    bucket["last_call_at"] = time.time()


def _is_rate_limit_error(err: Exception) -> bool:
    text = str(err).lower()
    if "429" in text or "rate" in text:
        return True
    resp = getattr(err, "response", None)
    return resp is not None and getattr(resp, "status_code", None) == 429


def _should_retry_claude_api_call(err: Exception) -> bool:
    """Ponów przy błędzie HTTP/sieci (nie przy braku klucza / limicie dziennym)."""
    return isinstance(err, requests.RequestException)


def claude_generate_text(
    prompt: str,
    logger: logging.Logger,
    api_key: str | None = None,
    cache: dict | None = None,
    *,
    max_tokens: int = 4096,
    bypass_daily_limit: bool = False,
    model: str | None = None,
    model_tier: CLAUDE_MODEL_TIER | None = None,
    on_step: Callable[[str], None] | None = None,
) -> tuple[str, str]:
    """Zwraca (text, model). model_tier: fast=Haiku, verify=Sonnet (domyslnie)."""
    key = (api_key or get_anthropic_api_key()).strip()
    if not key:
        raise RuntimeError("Brak ANTHROPIC_API_KEY")
    if is_claude_rate_limited(cache):
        raise RuntimeError("Claude API w cooldown (rate limit)")
    skip_daily_limit = bypass_daily_limit or is_claude_unlimited()
    if not skip_daily_limit and is_claude_limit_reached_today(cache):
        _, used, remaining = get_remaining_daily_claude_limit(cache)
        raise RuntimeError(
            f"Claude Tageslimit-Reserve erreicht ({_campaign_today()}: "
            f"genutzt={used}, rest={remaining}, reserve={CLAUDE_DISCOVERY_RESERVE}, "
            f"max={CLAUDE_DAILY_LIMIT})"
        )

    model = resolve_claude_model(model=model, model_tier=model_tier)
    headers = {
        "x-api-key": key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    data: dict | None = None
    last_exc: Exception | None = None
    for attempt in range(1, CLAUDE_API_RETRY_ATTEMPTS + 1):
        try:
            wait_for_claude_slot(cache)
            resp = requests.post(
                ANTHROPIC_MESSAGES_URL,
                headers=headers,
                json=payload,
                timeout=CLAUDE_REQUEST_TIMEOUT,
            )
            if resp.status_code == 429:
                mark_claude_rate_limited(cache, logger)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as exc:
            last_exc = exc
            if _is_rate_limit_error(exc):
                mark_claude_rate_limited(cache, logger)
            if (
                attempt >= CLAUDE_API_RETRY_ATTEMPTS
                or not _should_retry_claude_api_call(exc)
            ):
                raise
            logger.warning(
                "Claude API: błąd (próba %s/%s): %s — ponowienie za %ss",
                attempt,
                CLAUDE_API_RETRY_ATTEMPTS,
                exc,
                CLAUDE_API_RETRY_WAIT_SECONDS,
            )
            time.sleep(CLAUDE_API_RETRY_WAIT_SECONDS)
    if data is None:
        raise last_exc or RuntimeError("Claude API: brak odpowiedzi po ponowieniach")

    if not skip_daily_limit:
        increase_daily_claude_counter(cache, 1)
    blocks = data.get("content") or []
    text = ""
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text += str(block.get("text") or "")
    if not text.strip():
        raise RuntimeError("Claude: pusta odpowiedź")
    if on_step:
        on_step(f"Claude: {model}")
    return text.strip(), model
