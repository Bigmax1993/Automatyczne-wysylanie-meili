"""
Import publicznego profilu firmy z ALEO.com (baza firm KRS/CEIDG) do formatu kontaktów mailera.

ALEO zwykle nie publikuje e-maila firmy — podaj ``--email`` albo ``--company-website``
z ``--enrich-email`` (adres z oficjalnej strony firmy). Wiersz bez e-maila pipeline pominie.

Skrypt czyta tylko publiczny HTML (HTTP albo plik zapisany przez użytkownika).
Przy HTTP 403/429/503 lub stronie bez danych firmy nie obchodzi zabezpieczeń —
kończy z kodem 2 i sugeruje ``--html-file``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

import build_contacts_serpapi as serp
import pipeline_version as pv
from pipeline_logging import setup_logging

logger = logging.getLogger(__name__)
setup_logging("import_company_profile")

PROFILE_FETCH_TIMEOUT = float(os.environ.get("COMPANY_PROFILE_FETCH_TIMEOUT", "15"))
PROFILE_FETCH_MAX_BYTES = int(os.environ.get("COMPANY_PROFILE_FETCH_MAX_BYTES", "1500000"))
PROFILE_USER_AGENT = os.environ.get(
    "COMPANY_PROFILE_USER_AGENT",
    os.environ.get(
        "WEB_FETCH_USER_AGENT",
        "Mozilla/5.0 (compatible; ContactMailer/1.1; job-application-context)",
    ),
)

ALEO_HOST_SUFFIXES = ("aleo.com",)
ALEO_PROFILE_PATH = re.compile(r"^/(?:[a-z]{2,3}/)?(?:firma|company)/[^/]+/?$", re.IGNORECASE)
ALEO_SOURCE_LABEL = "ALEO.com (profil firmy)"

DEFAULT_ROLE_BY_INDUSTRY = (
    (("spedycj", "transport", "logistyk"), "Spedytor"),
)
LEGAL_FORM_ABBREVIATIONS = (
    (re.compile(r"\bSPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ\b", re.IGNORECASE), "sp. z o.o."),
    (re.compile(r"\bSPÓŁKA AKCYJNA\b", re.IGNORECASE), "S.A."),
    (re.compile(r"\bSPÓŁKA KOMANDYTOWA\b", re.IGNORECASE), "sp.k."),
    (re.compile(r"\bSPÓŁKA JAWNA\b", re.IGNORECASE), "sp.j."),
)
NOTES_MAX_PKD = 3


class ProfileFetchBlocked(RuntimeError):
    """Serwis zablokował publiczne pobranie (403 / 429 / 503) — bez obchodzenia."""


class ProfileParseError(ValueError):
    """HTML nie zawiera rozpoznawalnego profilu firmy."""


def is_aleo_company_url(url: str) -> bool:
    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not any(host == s or host.endswith("." + s) for s in ALEO_HOST_SUFFIXES):
        return False
    return bool(ALEO_PROFILE_PATH.match(parsed.path or ""))


def _type_names(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value.split("/")[-1]]
    if isinstance(value, (list, tuple)):
        return [name for item in value for name in _type_names(item)]
    return []


def _walk_jsonld(node: Any) -> Iterable[dict]:
    if isinstance(node, list):
        for item in node:
            yield from _walk_jsonld(item)
    elif isinstance(node, dict):
        yield node
        for key, value in node.items():
            if key != "@context" and isinstance(value, (dict, list)):
                yield from _walk_jsonld(value)


def _jsonld_nodes(soup: BeautifulSoup) -> List[dict]:
    nodes: List[dict] = []
    for script in soup.find_all("script", type=re.compile("ld\\+json", re.IGNORECASE)):
        raw = (script.string or script.get_text() or "").strip()
        try:
            nodes.extend(_walk_jsonld(json.loads(raw)))
        except json.JSONDecodeError:
            continue
    return nodes


_BUSINESS_TYPES = {"LocalBusiness", "Organization", "Corporation"}


def _business_node(nodes: List[dict]) -> Optional[dict]:
    for node in nodes:
        if _BUSINESS_TYPES & set(_type_names(node.get("@type"))):
            return node
    return None


def _breadcrumb_categories(nodes: List[dict]) -> List[str]:
    for node in nodes:
        if "BreadcrumbList" not in _type_names(node.get("@type")):
            continue
        items = sorted(
            (i for i in node.get("itemListElement") or [] if isinstance(i, dict)),
            key=lambda i: i.get("position") or 0,
        )
        names = []
        for item in items:
            inner = item.get("item")
            name = (inner.get("name") if isinstance(inner, dict) else None) or item.get("name")
            if name:
                names.append(str(name).strip())
        return names
    return []


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _registry_rows(soup: BeautifulSoup) -> Dict[str, str]:
    rows: Dict[str, str] = {}
    for row in soup.select(".registry-details__row"):
        label = row.select_one(".registry-details__row__label")
        value = row.select_one(".registry-details__row__value")
        if label is None or value is None:
            continue
        key = _squash(label.get_text(" "))
        if key and key not in rows:
            rows[key] = _squash(value.get_text(" "))
    return rows


def _pkd_codes(soup: BeautifulSoup) -> List[str]:
    codes = []
    for p in soup.select(".pkd-codes__code"):
        text = _squash(p.get_text(" "))
        if text and text not in codes:
            codes.append(text)
    return codes


def _public_email(soup: BeautifulSoup) -> str:
    for a in soup.select("a[href^='mailto:']"):
        email = a.get("href", "")[len("mailto:"):].split("?")[0].strip()
        if serp.EMAIL_RE.fullmatch(email):
            return email
    return ""


def _public_website(soup: BeautifulSoup, rows: Dict[str, str]) -> str:
    for key, value in rows.items():
        if re.search(r"\bwww\b|strona", key, re.IGNORECASE) and value:
            return serp._normalize_url(value.split()[0])
    return ""


def parse_aleo_profile(html: str, url: str = "") -> Dict[str, Any]:
    soup = BeautifulSoup(html or "", "html.parser")
    nodes = _jsonld_nodes(soup)
    business = _business_node(nodes)
    rows = _registry_rows(soup)
    if business is None and not rows:
        raise ProfileParseError("Brak danych firmy (JSON-LD LocalBusiness / dane rejestrowe) w HTML.")
    business = business or {}
    address = business.get("address") if isinstance(business.get("address"), dict) else {}

    legal_name = _squash(
        str(business.get("legalName") or business.get("name") or rows.get("Nazwa pełna") or "")
    )
    if not legal_name:
        raise ProfileParseError("Profil bez nazwy firmy.")

    categories = [c for c in _breadcrumb_categories(nodes) if c]
    return {
        "url": url,
        "legal_name": legal_name,
        "street": _squash(str(address.get("streetAddress") or "")),
        "postal_code": _squash(str(address.get("postalCode") or "")),
        "city": _squash(str(address.get("addressLocality") or "")),
        "address": rows.get("Adres siedziby") or rows.get("Adres rejestrowy") or "",
        "nip": _squash(str(business.get("taxID") or rows.get("NIP") or "")),
        "regon": rows.get("REGON", ""),
        "krs": rows.get("KRS", ""),
        "legal_form": rows.get("Forma prawna", ""),
        "registered_on": rows.get("Data rejestracji w KRS", ""),
        "categories": categories,
        "pkd": _pkd_codes(soup),
        "email": _public_email(soup),
        "website": _public_website(soup, rows),
    }


def short_company_name(legal_name: str) -> str:
    name = _squash(legal_name)
    for pattern, abbreviation in LEGAL_FORM_ABBREVIATIONS:
        name = pattern.sub(abbreviation, name)
    return name


def _title_city(city: str) -> str:
    return "-".join(part.capitalize() for part in _squash(city).lower().split("-"))


def _industry(profile: Dict[str, Any]) -> str:
    categories = profile.get("categories") or []
    if categories:
        return " / ".join(categories[:2])
    pkd = profile.get("pkd") or []
    if pkd:
        return re.sub(r"^[\d.A-Z]+\s*-\s*", "", pkd[0])
    return "(do ustalenia)"


def default_role_for_industry(industry: str) -> str:
    low = (industry or "").lower()
    for hints, role in DEFAULT_ROLE_BY_INDUSTRY:
        if any(h in low for h in hints):
            return role
    return "(do ustalenia)"


def _notes(profile: Dict[str, Any]) -> str:
    parts = []
    ids = [
        f"{label} {profile[key]}"
        for label, key in (("NIP", "nip"), ("KRS", "krs"), ("REGON", "regon"))
        if profile.get(key)
    ]
    if ids:
        parts.append(", ".join(ids))
    if profile.get("address"):
        parts.append(f"Siedziba: {profile['address']}")
    pkd = profile.get("pkd") or []
    if pkd:
        parts.append("PKD: " + "; ".join(pkd[:NOTES_MAX_PKD]))
    if profile.get("url"):
        parts.append(f"Profil: {profile['url']}")
    return ". ".join(parts)


def profile_to_contact_row(
    profile: Dict[str, Any],
    *,
    role: str = "",
    email: str = "",
    website: str = "",
    phone: str = "",
    mode: str = "",
) -> Dict[str, str]:
    industry = _industry(profile)
    site = serp._normalize_url(website) if website else profile.get("website", "")
    if site and serp._is_job_portal_domain(site):
        site = ""
    return {
        "Firma": short_company_name(profile["legal_name"]),
        "Miasto": _title_city(profile.get("city", "")) or "(brak miasta)",
        "Branża": industry,
        "Stanowisko / Rola": role or default_role_for_industry(industry),
        "Strona WWW": site,
        "E-mail rekrutacyjny": (email or profile.get("email") or "").strip(),
        "Tel / Kontakt": phone,
        "Tryb pracy": mode or "(do ustalenia)",
        "Źródło / Portal": ALEO_SOURCE_LABEL,
        "Uwagi": _notes(profile),
    }


def fetch_profile_html(url: str, timeout: float = PROFILE_FETCH_TIMEOUT) -> str:
    try:
        from fetch_throttle import throttle_hostname_before_http

        throttle_hostname_before_http(url)
    except ImportError:
        pass
    headers = {"User-Agent": PROFILE_USER_AGENT, "Accept-Language": "pl-PL,pl;q=0.9"}
    with requests.get(url, timeout=timeout, headers=headers, stream=True) as resp:
        if resp.status_code in (403, 429, 503):
            raise ProfileFetchBlocked(f"HTTP {resp.status_code} dla {url}")
        resp.raise_for_status()
        raw = b""
        for chunk in resp.iter_content(chunk_size=65536):
            raw += chunk
            if len(raw) >= PROFILE_FETCH_MAX_BYTES:
                break
        encoding = resp.encoding or "utf-8"
    return raw.decode(encoding, errors="replace")


def write_rows(rows: List[Dict[str, str]], output: str) -> str:
    df = pd.DataFrame(rows)
    for col in serp.MAILER_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[serp.MAILER_COLUMNS]
    out = os.path.abspath(output)
    parent = os.path.dirname(out)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if out.lower().endswith(".csv"):
        df.to_csv(out, index=False, encoding="utf-8-sig")
    else:
        df.to_excel(out, index=False)
    return out


def _default_output(url: str) -> str:
    slug = os.path.basename(urlparse(url or "").path.rstrip("/")) or "profil"
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", slug)
    return os.path.join(os.path.expanduser("~"), "Documents", "kontakty", f"aleo_{slug}.xlsx")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import profilu firmy z ALEO.com do arkusza kontaktów mailera.",
    )
    parser.add_argument("--version", action="version", version=pv.PIPELINE_VERSION)
    parser.add_argument("--url", required=True, help="Adres profilu, np. https://aleo.com/pl/firma/<slug>")
    parser.add_argument("--html-file", help="Zapisany HTML profilu (zamiast pobierania).")
    parser.add_argument("--output", help="Plik .xlsx lub .csv (domyślnie Documents\\kontakty\\aleo_<slug>.xlsx).")
    parser.add_argument("--role", default="", help="Stanowisko / rola (domyślnie z branży, np. Spedytor).")
    parser.add_argument("--email", default="", help="Publiczny e-mail firmy (ALEO go zwykle nie podaje).")
    parser.add_argument("--company-website", default="", help="Oficjalna strona firmy (nie katalog firm).")
    parser.add_argument("--phone", default="", help="Telefon kontaktowy (nie trafia do treści maila).")
    parser.add_argument("--mode", default="", help="Tryb pracy, np. stacjonarnie / zdalnie.")
    parser.add_argument(
        "--enrich-email",
        action="store_true",
        help="Gdy brak e-maila: szukaj adresu na --company-website (strona główna, /kontakt, /kariera).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.html_file and not is_aleo_company_url(args.url):
        logger.error("To nie wygląda na profil firmy ALEO.com: %s", args.url)
        return 1
    try:
        if args.html_file:
            with open(args.html_file, encoding="utf-8", errors="replace") as f:
                html = f.read()
        else:
            html = fetch_profile_html(args.url)
        profile = parse_aleo_profile(html, args.url)
    except ProfileFetchBlocked as e:
        logger.error("%s — zapisz stronę w przeglądarce i podaj --html-file.", e)
        return 2
    except ProfileParseError as e:
        logger.error("%s Jeśli ALEO pokazało stronę weryfikacji, użyj --html-file.", e)
        return 2
    except requests.RequestException as e:
        logger.error("Nie udało się pobrać profilu: %s", e)
        return 1

    row = profile_to_contact_row(
        profile,
        role=args.role,
        email=args.email,
        website=args.company_website,
        phone=args.phone,
        mode=args.mode,
    )
    if args.enrich_email and not row["E-mail rekrutacyjny"] and row["Strona WWW"]:
        row["E-mail rekrutacyjny"] = serp._extract_recruit_email_from_site(row["Strona WWW"])

    out = write_rows([row], args.output or _default_output(args.url))
    logger.info("Zapisano kontakt %s → %s", row["Firma"], out)
    if not row["E-mail rekrutacyjny"]:
        logger.warning(
            "Brak e-maila dla %s — pipeline pominie ten wiersz. Podaj --email lub "
            "--company-website z --enrich-email.",
            row["Firma"],
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
