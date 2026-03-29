"""
Domeny odbiorców e-mail, które nie mają dostawać wysyłki (np. własna skrzynka, konkurencja).
Plik: jedna domena na linię (bez @), linie z # ignorowane.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Set

_default_blocklist = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "config",
    "blocked_domains.txt",
)

BLOCKLIST_PATH = os.environ.get("EMAIL_DOMAIN_BLOCKLIST_PATH", _default_blocklist).strip()

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, frozenset[str]]] = {}
_RELOAD_SEC = float(os.environ.get("EMAIL_DOMAIN_BLOCKLIST_RELOAD_SEC", "30"))


def _parse_lines(raw: str) -> Set[str]:
    out: set[str] = set()
    for line in raw.splitlines():
        s = line.strip().lower()
        if not s or s.startswith("#"):
            continue
        s = s.lstrip("@")
        s = s.split()[0] if s else ""
        if s:
            out.add(s)
    return out


def load_blocked_domains() -> frozenset[str]:
    path = BLOCKLIST_PATH
    if not path or not os.path.isfile(path):
        return frozenset()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return frozenset()
    now = time.time()
    hit = _cache.get(path)
    if hit and now - hit[0] < _RELOAD_SEC and hit[1] is not None:
        return hit[1]
    try:
        with open(path, encoding="utf-8") as f:
            domains = frozenset(_parse_lines(f.read()))
    except OSError as e:
        logger.warning("Nie można wczytać blocklisty domen %s: %s", path, e)
        domains = frozenset()
    _cache[path] = (now, domains)
    return domains


def recipient_domain_is_blocked(email: str) -> bool:
    e = (email or "").strip().lower()
    if "@" not in e:
        return False
    dom = e.split("@", 1)[1].strip().lower()
    if not dom:
        return False
    blocked = load_blocked_domains()
    if dom in blocked:
        return True
    for b in blocked:
        if b.startswith("*."):
            suf = b[2:]
            if suf and dom != suf and dom.endswith("." + suf):
                return True
    return False


def clear_blocklist_cache() -> None:
    _cache.clear()
