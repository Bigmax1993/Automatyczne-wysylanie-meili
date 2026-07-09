# -*- coding: utf-8 -*-
"""Twardy limit czasu działania scrapera (SCRAPER_MAX_RUNTIME_SECONDS)."""
from __future__ import annotations

import os
import time
from typing import Callable

_SCRAPER_RUN_STARTED_AT: float | None = None


def _parse_max_runtime_seconds() -> int:
    raw = (os.environ.get("SCRAPER_MAX_RUNTIME_SECONDS") or "").strip()
    if not raw:
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


SCRAPER_MAX_RUNTIME_SECONDS = _parse_max_runtime_seconds()


def start_scraper_runtime_clock() -> None:
    global _SCRAPER_RUN_STARTED_AT
    if SCRAPER_MAX_RUNTIME_SECONDS <= 0:
        _SCRAPER_RUN_STARTED_AT = None
        return
    _SCRAPER_RUN_STARTED_AT = time.monotonic()


def scraper_runtime_elapsed_seconds() -> float | None:
    if _SCRAPER_RUN_STARTED_AT is None:
        return None
    return time.monotonic() - _SCRAPER_RUN_STARTED_AT


def is_scraper_runtime_limit_reached() -> bool:
    if SCRAPER_MAX_RUNTIME_SECONDS <= 0 or _SCRAPER_RUN_STARTED_AT is None:
        return False
    elapsed = scraper_runtime_elapsed_seconds()
    return elapsed is not None and elapsed >= SCRAPER_MAX_RUNTIME_SECONDS


def request_stop_on_runtime_limit(
    logger,
    *,
    console_step_fn: Callable[[str], None] | None = None,
) -> bool:
    if not is_scraper_runtime_limit_reached():
        return False
    hours = SCRAPER_MAX_RUNTIME_SECONDS // 3600
    msg = (
        f"Limit czasu scrapera ({SCRAPER_MAX_RUNTIME_SECONDS}s = {hours}h) — zatrzymanie"
    )
    if console_step_fn:
        console_step_fn(msg)
    if logger:
        logger.warning(msg)
    return True


def reset_scraper_runtime_clock_for_tests() -> None:
    global _SCRAPER_RUN_STARTED_AT
    _SCRAPER_RUN_STARTED_AT = None
