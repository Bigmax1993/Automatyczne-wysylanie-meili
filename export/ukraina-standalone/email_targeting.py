# -*- coding: utf-8 -*-
"""Ranking adresów e-mail pod zapytania ofertowe (piasek / kruszywa PL)."""
from __future__ import annotations

import re
from urllib.parse import urlparse

try:
    import idna
except ImportError:  # pragma: no cover
    idna = None  # type: ignore

MIN_EMAIL_SCORE_FOR_SEND = 35

# Skrzynki ogólne akceptowane, gdy adres pochodzi ze strony www firmy (np. info@k-in.de).
GENERIC_INQUIRY_LOCAL_PARTS = frozenset(
    {
        "info",
        "kontakt",
        "office",
        "mail",
        "anfrage",
        "anfragen",
        "verkauf",
        "vertrieb",
        "biuro",
        "hello",
        "service",
        "projekt",
    }
)

AGGREGATOR_EMAIL_DOMAINS = frozenset(
    {
        "facebook.com",
        "instagram.com",
        "linkedin.com",
        "gelbeseiten.de",
        "wikipedia.org",
        "google.com",
        "maps.google.com",
        "yellowpages.",
        "firmenabc.",
        "obi.pl",
        "leroymerlin.pl",
        "castorama.pl",
    }
)

_UNSUITABLE_LOCAL_MARKERS = (
    "ochrona",
    "rodo",
    "iod",
    "gdpr",
    "privacy",
    "dpo",
    "newsletter",
    "reklam",
    "complaint",
    "reklamac",
    "hr",
    "karier",
    "jobs",
    "praca",
    "prasa",
    "press",
    "media",
    "faktur",
    "invoice",
    "ksiegow",
    "it",
    "helpdesk",
    "support",
    "noreply",
    "no-reply",
    "donotreply",
    "postmaster",
    "mailer-daemon",
    "abuse",
    "security",
    "bezpieczenstw",
)


def _normalize_website(url: str) -> str:
    if not url:
        return ""
    u = url.strip()
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u


def get_registrable_domain(url: str) -> str:
    try:
        netloc = (urlparse(_normalize_website(url)).netloc or "").lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def _fold_domain_token(value: str) -> str:
    low = (value or "").lower()
    for src, dst in (
        ("ä", "ae"),
        ("ö", "oe"),
        ("ü", "ue"),
        ("ß", "ss"),
        ("é", "e"),
    ):
        low = low.replace(src, dst)
    return re.sub(r"[^a-z0-9]", "", low)


def _decode_idn_hostname(host: str) -> str:
    """Punycode (xn--…) → Unicode, np. bauunternehmen-eichstädt.de."""
    if not host or not idna:
        return host or ""
    labels = (host or "").lower().split(".")
    out: list[str] = []
    for label in labels:
        if not label:
            continue
        try:
            if label.startswith("xn--"):
                out.append(idna.decode(label.encode("ascii")))
            else:
                out.append(label)
        except Exception:
            out.append(label)
    return ".".join(out)


def _website_host_variants(website_url: str) -> list[str]:
    host = get_registrable_domain(website_url)
    if not host:
        return []
    variants = {host, _decode_idn_hostname(host)}
    first_label = host.split(".", 1)[0]
    if first_label.startswith("xn--"):
        variants.add(_decode_idn_hostname(first_label))
    return [v for v in variants if v]


def email_domain_related_to_website(email_domain: str, website_url: str) -> bool:
    """
    Domena maila powiązana ze stroną mimo Punycode / innej TLD
    (np. xn--bauunternehmen-eichstdt-g8b.de ↔ info@eichstaedtbau.de).
    """
    ed = _fold_domain_token((email_domain or "").split(".", 1)[0])
    if len(ed) < 5:
        return False
    for host in _website_host_variants(website_url):
        for token in re.split(r"[-_]", host.split(".", 1)[0]):
            ht = _fold_domain_token(token)
            if len(ht) < 5:
                continue
            if ed == ht or ed in ht or ht in ed:
                return True
            overlap = min(len(ed), len(ht))
            for size in range(overlap, 7, -1):
                for i in range(len(ed) - size + 1):
                    frag = ed[i : i + size]
                    if frag in ht:
                        return True
    return False


def is_unsuitable_inquiry_email(email: str) -> bool:
    low = (email or "").strip().lower()
    if not low or "@" not in low:
        return True
    local, _, domain = low.partition("@")
    local = local.strip()
    domain = domain.strip()
    if not local or not domain:
        return True
    if domain in AGGREGATOR_EMAIL_DOMAINS or any(
        domain.endswith("." + agg) for agg in AGGREGATOR_EMAIL_DOMAINS if "." not in agg
    ):
        return True
    if any(marker in local for marker in _UNSUITABLE_LOCAL_MARKERS):
        return True
    if "ochrona" in local and "danych" in local:
        return True
    return False


def score_email_candidate(email: str, website_url: str) -> int:
    low = (email or "").strip().lower()
    if not low or "@" not in low:
        return -999
    if is_unsuitable_inquiry_email(low):
        return -500
    local, _, domain = low.partition("@")
    local = local.strip()
    domain = domain.strip()
    score = 0
    host = get_registrable_domain(website_url)
    if host and (domain == host or domain.endswith("." + host) or host.endswith("." + domain)):
        score += 52
    elif email_domain_related_to_website(domain, website_url):
        score += 46
    for kw, bonus in (
        ("sprzedaz", 28),
        ("handl", 24),
        ("wycen", 22),
        ("ofert", 18),
        ("zapytan", 16),
        ("piasek", 20),
        ("kruszyw", 18),
        ("hurtown", 16),
        ("logisty", 14),
        ("dyspozyt", 14),
        ("transport", 12),
        ("biuro", 10),
        ("kontakt", 8),
        ("info", 6),
        ("office", 6),
    ):
        if kw in local:
            score += bonus
    if any(x in local for x in ("marketing", "newsletter", "media", "prasa", "rekrut")):
        score -= 42
    if re.match(r"^[0-9]+$", local):
        score -= 40
    if len(local) <= 2:
        score -= 25
    return score


def rank_email_candidates(
    candidates: list[str], website_url: str
) -> list[tuple[str, int]]:
    ranked: list[tuple[str, int]] = []
    seen: set[str] = set()
    for raw in candidates:
        email = (raw or "").strip().lower()
        if not email or email in seen or "@" not in email:
            continue
        seen.add(email)
        ranked.append((email, score_email_candidate(email, website_url)))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


def pick_best_email_for_inquiry(
    candidates: list[str], website_url: str
) -> tuple[str, int]:
    ranked = rank_email_candidates(candidates, website_url)
    if not ranked:
        return "", 0
    best, score = ranked[0]
    if score < MIN_EMAIL_SCORE_FOR_SEND or is_unsuitable_inquiry_email(best):
        return "", score
    return best, score


def pick_best_email_from_website_scrape(
    candidates: list[str], website_url: str
) -> tuple[str, int]:
    """
    Luźniejszy wybór dla maili znalezionych na stronie firmy (kampania GU).
    Akceptuje info@ / kontakt@ mimo innej domeny (skrócona marka, np. k-in.de).
    """
    ranked = rank_email_candidates(candidates, website_url)
    if not ranked:
        return "", 0
    best, score = ranked[0]
    if is_unsuitable_inquiry_email(best):
        return "", score
    local = best.split("@", 1)[0].strip().lower()
    if local in GENERIC_INQUIRY_LOCAL_PARTS and score >= 6:
        return best, max(score, MIN_EMAIL_SCORE_FOR_SEND)
    return "", score


def needs_llm_email_arbitration(candidates: list[str], website_url: str) -> bool:
    ranked = rank_email_candidates(candidates, website_url)
    viable = [
        (email, score)
        for email, score in ranked
        if score >= MIN_EMAIL_SCORE_FOR_SEND and not is_unsuitable_inquiry_email(email)
    ]
    if not viable:
        return bool(candidates)
    if len(viable) >= 2:
        top = viable[0][1]
        close = sum(1 for _, score in viable if score >= top - 8)
        if close >= 2:
            return True
    return False


def validate_llm_email_choice(
    choice: str,
    candidates: list[str],
    website_url: str = "",
) -> str:
    picked = (choice or "").strip().lower()
    allowed = {(c or "").strip().lower() for c in candidates if (c or "").strip()}
    if not picked or picked not in allowed:
        return ""
    if is_unsuitable_inquiry_email(picked):
        return ""
    if score_email_candidate(picked, website_url) < MIN_EMAIL_SCORE_FOR_SEND:
        return ""
    return picked
