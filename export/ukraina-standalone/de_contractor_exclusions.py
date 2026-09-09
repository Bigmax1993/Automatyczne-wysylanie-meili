# -*- coding: utf-8 -*-
"""
Wykluczeni kontrahenci (lista MFG / Izabela Nowicka) — scrapery DE nie zbierają,
nie eksportują i nie wysyłają do tych firm.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# Nazwy / fragmenty (znormalizowane dopasowanie substring)
EXCLUDED_NAME_MARKERS: tuple[str, ...] = (
    "action deutschland",
    "action switzerland",
    "wach bud",
    "wach-bud",
    "grotz bauunternehmung",
    "grötz bauunternehmung",
    "hghi baumanagement",
    "komobex inel",
    "komobex-inel",
    "projekt kraft",
    "bauunternehmen frank eichstadt",
    "bauunternehmen frank eichstädt",
    "bob gmbh",
    "fuste polska",
    "grabo projektbau",
    "grabo projekt",
    "igb construct",
    "kessler bau",
    "keßler bau",
    "kiz gmbh",
    "moderner fliesenboden",
    "mfg moderner fliesenboden",
    "muller co ingenieurbau",
    "müller co ingenieurbau",
    "ratisbona",
    "riveto import",
    "schoofs baumanagement",
    "schoofs baumarkt",
    "ubs investment foundation",
    "vic zos",
    "vic-zos",
    "werner nagel",
    "wynajem samochodu",
    "aldi grundbesitz",
    "aldi grundstucksgesellschaft",
    "aldi grundstücksgesellschaft",
    "aldi se",
    "aldi grund",
    "domizil immobilien",
    "duhm projektbau",
    "flowcraft",
    "opel projektbau",
    "pekabex",
    "weemploy",
    "neula gmbh",
    "xpress bau",
    "slb stadt und landbau",
    "slb bautzen",
    "obag hochbau",
    "bauprojekt dresden",
    "kultbau",
    "max wiessner",
    "vobau gmbh",
    "freund bauunternehmung",
    "best bernauer stadtmarketing",
    "neubau edeka in halle",
    "gug hochbau",
    "ruba hausbau",
    "ruba-hausbau",
    "saale ausbau",
    "ausbau senftenberg",
    "plus hochbau",
    "gudat bau",
    "baugeschaft konrad",
    "baugeschäft konrad",
    "bbf bau",
    "tief und hochbau",
    "tief- und hochbau",
    "tief und anlagenbau",
    "tief- und anlagenbau",
    "firma ogolnobudowlana",
    "firma ogólnobudowlana",
    "hghi",
    "moderner fliesen",
    "mfg fliesen",
)

EXCLUDED_EMAIL_DOMAINS_EXACT: frozenset[str] = frozenset(
    {
        "neula.de",
        "xpress-bau.de",
        "ostbau.de",
        "slb-bautzen.de",
        "obag-bautzen.de",
        "bauprojekt-dresden.de",
        "eichstaedtbau.de",
        "mfg-fliesen.de",
        "office.mfg-fliesen.de",
        "komobex.pl",
        "wach-bud.pl",
        "fuste.pl",
        "pekabex.pl",
        "riveto.cz",
        "weemploy.pl",
    }
)

EXCLUDED_DOMAIN_FRAGMENTS: tuple[str, ...] = (
    "hi-heute.de",
    "neula.de",
    "xpress-bau",
    "slb-bautzen",
    "obag-bautzen",
    "bauprojekt-dresden",
    "eichstaedtbau",
    "eichstdt",
    "mfg-fliesen",
    "modernerfliesenboden",
    "komobex",
    "wach-bud",
    "fuste.",
    "pekabex",
    "riveto.",
    "weemploy",
    "aldi.",
    "action.com",
    "schoofs.",
    "ratisbona",
    "grabo-projekt",
    "grotz.",
    "groetz.",
    "kessler-bau",
    "werner-nagel",
    "maxwiessner",
    "kultbau",
    "vobau",
    "gudat-bau",
    "bbf-bau",
    "plus-hochbau",
    "freund-bau",
)


def _normalize_match_text(*parts: str) -> str:
    blob = " ".join((p or "").strip() for p in parts if (p or "").strip()).lower()
    for src, dst in (
        ("ä", "ae"),
        ("ö", "oe"),
        ("ü", "ue"),
        ("ß", "ss"),
        ("é", "e"),
        ("&", " und "),
    ):
        blob = blob.replace(src, dst)
    blob = re.sub(r"[^a-z0-9@.\-]+", " ", blob)
    return " ".join(blob.split())


def _website_host(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    try:
        host = (urlparse(u).netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def is_excluded_kontrahent(
    *,
    name: str = "",
    url: str = "",
    email: str = "",
) -> tuple[bool, str]:
    """
    True = kontrahent z listy wykluczeń (nie szukać, nie mailować).
    Zwraca (bool, krótki powód).
    """
    email_low = (email or "").strip().lower()
    if email_low and "@" in email_low:
        dom = email_low.split("@", 1)[1]
        if dom in EXCLUDED_EMAIL_DOMAINS_EXACT:
            return True, f"email_domain:{dom}"
        for frag in EXCLUDED_DOMAIN_FRAGMENTS:
            if frag in dom:
                return True, f"email_domain_frag:{frag}"

    host = _website_host(url)
    if host:
        if host in EXCLUDED_EMAIL_DOMAINS_EXACT:
            return True, f"www_host:{host}"
        for frag in EXCLUDED_DOMAIN_FRAGMENTS:
            if frag in host:
                return True, f"www_frag:{frag}"

    norm = _normalize_match_text(name, url, email)
    if not norm:
        return False, ""
    for marker in EXCLUDED_NAME_MARKERS:
        if marker in norm:
            return True, f"name:{marker}"
    return False, ""


def contact_info_excluded(info: dict | None, place_url: str = "") -> bool:
    if not isinstance(info, dict):
        return False
    email = (info.get("email_target") or "").strip()
    if not email and info.get("emails_found"):
        email = str(info.get("emails_found")).split(",")[0].strip()
    name = (
        info.get("company_name_clean")
        or info.get("company_name")
        or info.get("company_name_raw")
        or ""
    )
    url = (place_url or info.get("official_website") or "").strip()
    excluded, _ = is_excluded_kontrahent(name=name, url=url, email=email)
    return excluded
