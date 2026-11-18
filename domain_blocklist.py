"""
Blokada odbiorców e-mail: domeny i pełne adresy (własne skrzynki, konkurencja).

Pliki (jedna pozycja na linię, linie z # ignorowane):
- domeny: bez @ albo z @ (np. spam.pl) — plik blocked_domains.txt
- pełne adresy: musi zawierać @ (np. ja@gmail.com) — plik blocked_emails.txt
"""

from __future__ import annotations

import logging
import os
import time
from typing import Set

_default_domain_blocklist = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "config",
    "blocked_domains.txt",
)
_default_email_blocklist = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "config",
    "blocked_emails.txt",
)

BLOCKLIST_PATH = os.environ.get("EMAIL_DOMAIN_BLOCKLIST_PATH", _default_domain_blocklist).strip()
EMAIL_BLOCKLIST_PATH = os.environ.get(
    "EMAIL_ADDRESS_BLOCKLIST_PATH", _default_email_blocklist
).strip()

logger = logging.getLogger(__name__)

_domain_cache: dict[str, tuple[float, frozenset[str]]] = {}
_email_cache: dict[str, tuple[float, frozenset[str]]] = {}
_RELOAD_SEC = float(os.environ.get("EMAIL_DOMAIN_BLOCKLIST_RELOAD_SEC", "30"))


def _parse_domain_lines(raw: str) -> Set[str]:
    out: set[str] = set()
    for line in raw.splitlines():
        s = line.strip().lower()
        if not s or s.startswith("#"):
            continue
        s = s.lstrip("@")
        s = s.split()[0] if s else ""
        # Linie z pełnym adresem w pliku domen — traktuj jako domenę po @.
        if "@" in s:
            s = s.split("@", 1)[1]
        if s:
            out.add(s)
    return out


def _parse_email_lines(raw: str) -> Set[str]:
    out: set[str] = set()
    for line in raw.splitlines():
        s = line.strip().lower()
        if not s or s.startswith("#"):
            continue
        s = s.split()[0] if s else ""
        if "@" not in s:
            continue
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
    hit = _domain_cache.get(path)
    if hit and now - hit[0] < _RELOAD_SEC and hit[1] is not None:
        return hit[1]
    try:
        with open(path, encoding="utf-8") as f:
            domains = frozenset(_parse_domain_lines(f.read()))
    except OSError as e:
        logger.warning("Nie można wczytać blocklisty domen %s: %s", path, e)
        domains = frozenset()
    _domain_cache[path] = (now, domains)
    return domains


def load_blocked_emails() -> frozenset[str]:
    path = EMAIL_BLOCKLIST_PATH
    if not path or not os.path.isfile(path):
        return frozenset()
    try:
        os.path.getmtime(path)
    except OSError:
        return frozenset()
    now = time.time()
    hit = _email_cache.get(path)
    if hit and now - hit[0] < _RELOAD_SEC and hit[1] is not None:
        return hit[1]
    try:
        with open(path, encoding="utf-8") as f:
            emails = frozenset(_parse_email_lines(f.read()))
    except OSError as e:
        logger.warning("Nie można wczytać blocklisty adresów %s: %s", path, e)
        emails = frozenset()
    _email_cache[path] = (now, emails)
    return emails


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


def recipient_email_is_blocked(email: str) -> bool:
    e = (email or "").strip().lower()
    if "@" not in e:
        return False
    return e in load_blocked_emails()


def recipient_is_blocked(email: str, *, also_block_sender: str = "") -> bool:
    """Domena, dokładny adres lub (opcjonalnie) ten sam adres co nadawca SMTP."""
    e = (email or "").strip().lower()
    if not e or "@" not in e:
        return False
    if also_block_sender and e == also_block_sender.strip().lower():
        return True
    if recipient_email_is_blocked(e):
        return True
    return recipient_domain_is_blocked(e)


def clear_blocklist_cache() -> None:
    _domain_cache.clear()
    _email_cache.clear()
