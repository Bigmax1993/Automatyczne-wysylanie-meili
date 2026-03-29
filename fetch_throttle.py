"""Odstępy między żądaniami HTTP per host (domena), żeby nie bombardować jednej sieci."""

from __future__ import annotations

import os
import time
from urllib.parse import urlparse

WEB_FETCH_MIN_INTERVAL_PER_HOST_SEC = float(
    os.environ.get("WEB_FETCH_MIN_INTERVAL_PER_HOST_SEC", "2")
)

_host_last_monotonic: dict[str, float] = {}


def clear_host_throttle() -> None:
    _host_last_monotonic.clear()


def throttle_hostname_before_http(url: str) -> None:
    if WEB_FETCH_MIN_INTERVAL_PER_HOST_SEC <= 0:
        return
    host = (urlparse(url).hostname or "").lower().strip(".")
    if not host:
        return
    now = time.monotonic()
    last = _host_last_monotonic.get(host, 0.0)
    wait = WEB_FETCH_MIN_INTERVAL_PER_HOST_SEC - (now - last)
    if wait > 0:
        time.sleep(wait)
    _host_last_monotonic[host] = time.monotonic()
