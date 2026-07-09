# -*- coding: utf-8 -*-
"""
Okno wysyłki e-mail i strefa czasu — konfiguracja przez zmienne środowiskowe (GitHub Actions, cron, Task Scheduler).

Przykłady:
  DISABLE_SEND_WINDOW=1          → wysyłka o każdej godzinie (zalecane dla CI/cron o 2:00)
  SEND_WINDOW_START_HOUR=0       → od północy
  SEND_WINDOW_END_HOUR=24        → do północy (cała doba)
  SCRAPER_TIMEZONE=Europe/Warsaw → godzina okna wg strefy (nie UTC serwera)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class SendWindowConfig:
    start_hour: int
    end_hour: int
    disabled: bool
    timezone: str


def load_send_window_config() -> SendWindowConfig:
    disabled = _truthy(os.getenv("DISABLE_SEND_WINDOW")) or _truthy(
        os.getenv("SCRAPER_IGNORE_SEND_WINDOW")
    )
    try:
        start = int((os.getenv("SEND_WINDOW_START_HOUR") or "8").strip())
    except ValueError:
        start = 8
    try:
        end = int((os.getenv("SEND_WINDOW_END_HOUR") or "18").strip())
    except ValueError:
        end = 18
    start = max(0, min(23, start))
    end = max(1, min(24, end))
    tz = (os.getenv("SCRAPER_TIMEZONE") or "").strip()
    return SendWindowConfig(
        start_hour=start,
        end_hour=end,
        disabled=disabled,
        timezone=tz,
    )


def current_local_hour(timezone: str = "") -> int:
    tz = (timezone or os.getenv("SCRAPER_TIMEZONE") or "").strip()
    if tz and ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(tz)).hour
        except Exception:
            pass
    return datetime.now().hour


def is_within_send_window(cfg: SendWindowConfig | None = None) -> bool:
    """True = wolno wysyłać maile teraz (wg lokalnej strefy lub DISABLE_SEND_WINDOW)."""
    c = cfg or load_send_window_config()
    if c.disabled:
        return True
    hour = current_local_hour(c.timezone)
    if c.start_hour < c.end_hour:
        return c.start_hour <= hour < c.end_hour
    # Okno przez północ, np. 22–6
    return hour >= c.start_hour or hour < c.end_hour
