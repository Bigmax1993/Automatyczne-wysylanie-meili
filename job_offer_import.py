"""
Import pojedynczej oferty pracy (URL z portalu, np. pracuj.pl) do pliku kontaktów pipeline'u.

Wklejony link do ogłoszenia zamieniany jest na wiersz w formacie `MAILER_COLUMNS`
(Firma, Miasto, Stanowisko / Rola, Tryb pracy, Źródło / Portal, Uwagi ...) i dopisywany
do arkusza w katalogu dodatkowych kontaktów (domyślnie `Documents\\kontakty\\Kontakty_oferty.xlsx`).
Dalej plik przetwarza normalnie `clean_validate_send_pipeline.py` (clean → walidacja → wysyłka CV).

Kolejność źródeł danych o ofercie:
1. JSON-LD `JobPosting` ze strony ogłoszenia (tytuł, pracodawca, miasto, typ zatrudnienia),
2. `<title>` / `og:title` strony (np. „Spedytor, Firma Sp. z o.o., Zielona Góra”),
3. sam URL (slug: stanowisko + miasto, id oferty) — gdy portal blokuje pobieranie (403 / CAPTCHA),
4. parametry CLI (`--company`, `--email`, `--website`, ...) nadpisują wszystko powyższe.

Przy blokadzie strony nie obchodzimy zabezpieczeń — wiersz powstaje z URL + parametrów.
"""

from __future__ import annotations

import argparse
import html as html_mod
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse, urlunparse

import pandas as pd

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore[assignment]

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[assignment]

import contact_mailer as cm
from pipeline_logging import setup_logging

logger = logging.getLogger(__name__)

MAILER_COLUMNS = [
    cm.COL_COMPANY,
    cm.COL_CITY,
    cm.COL_INDUSTRY,
    cm.COL_ROLE,
    cm.COL_WEBSITE,
    cm.COL_EMAIL,
    cm.COL_PHONE,
    cm.COL_MODE,
    cm.COL_SOURCE,
    cm.COL_NOTES,
]

OFFER_FETCH_TIMEOUT = float(os.environ.get("OFFER_FETCH_TIMEOUT", "15"))
OFFER_FETCH_USER_AGENT = os.environ.get(
    "OFFER_FETCH_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
)
DEFAULT_OFFERS_FILENAME = "Kontakty_oferty.xlsx"

_KNOWN_PORTALS = {
    "pracuj.pl": "pracuj.pl",
    "justjoin.it": "justjoin.it",
    "nofluffjobs.com": "nofluffjobs.com",
    "rocketjobs.pl": "rocketjobs.pl",
    "theprotocol.it": "theprotocol.it",
    "bulldogjob.pl": "bulldogjob.pl",
    "linkedin.com": "linkedin.com",
    "indeed.com": "indeed.com",
    "olx.pl": "olx.pl",
    "gowork.pl": "gowork.pl",
}

_EMPLOYMENT_TYPE_LABELS = {
    "FULL_TIME": "pełny etat",
    "PART_TIME": "część etatu",
    "CONTRACTOR": "kontrakt B2B",
    "TEMPORARY": "umowa tymczasowa",
    "INTERN": "staż / praktyki",
}

_MODE_TOKENS = (
    ("praca zdalna", "zdalna"),
    ("home office", "zdalna"),
    ("remote", "zdalna"),
    ("praca hybrydowa", "hybrydowa"),
    ("hybrid", "hybrydowa"),
    ("praca stacjonarna", "stacjonarna"),
    ("on-site", "stacjonarna"),
    ("onsite", "stacjonarna"),
)
_MODE_ORDER = ("stacjonarna", "hybrydowa", "zdalna")

_CONTRACT_TOKENS = (
    ("umowa o pracę", "umowa o pracę"),
    ("umowa o prace", "umowa o pracę"),
    ("kontrakt b2b", "kontrakt B2B"),
    ("b2b", "kontrakt B2B"),
    ("umowa zlecenie", "umowa zlecenie"),
    ("umowa o dzieło", "umowa o dzieło"),
)

# Słowa w slugu URL, które nie są częścią miasta (pracuj.pl: „...-zielona-gora,oferta,123”).
_SLUG_STOPWORDS = {"oferta", "praca", "job", "jobs"}

# Miasta wielowyrazowe zapisane w slugu bez polskich znaków → poprawna pisownia.
_SLUG_CITY_FIXES = {
    "zielona gora": "Zielona Góra",
    "gorzow wielkopolski": "Gorzów Wielkopolski",
    "wroclaw": "Wrocław",
    "poznan": "Poznań",
    "krakow": "Kraków",
    "lodz": "Łódź",
    "gdansk": "Gdańsk",
    "bialystok": "Białystok",
    "rzeszow": "Rzeszów",
    "torun": "Toruń",
    "czestochowa": "Częstochowa",
    "bielsko biala": "Bielsko-Biała",
    "warszawa": "Warszawa",
}


@dataclass
class JobOffer:
    url: str
    portal: str = ""
    offer_id: str = ""
    title: str = ""
    company: str = ""
    city: str = ""
    website: str = ""
    email: str = ""
    phone: str = ""
    work_modes: List[str] = field(default_factory=list)
    contracts: List[str] = field(default_factory=list)
    employment_types: List[str] = field(default_factory=list)
    industry: str = ""
    fetch_status: str = "not_fetched"

    def work_mode_label(self) -> str:
        modes = [m for m in _MODE_ORDER if m in self.work_modes]
        if not modes:
            return "(do ustalenia)"
        return "praca " + " / ".join(modes)

    def notes(self) -> str:
        parts = [f"Oferta: {self.url}"]
        if self.contracts:
            parts.append("Umowa: " + ", ".join(dict.fromkeys(self.contracts)))
        elif self.employment_types:
            parts.append("Zatrudnienie: " + ", ".join(dict.fromkeys(self.employment_types)))
        if self.fetch_status not in ("ok", "not_fetched"):
            parts.append(f"Dane z URL (strona: {self.fetch_status})")
        return " | ".join(parts)

    def to_row(self) -> Dict[str, str]:
        return {
            cm.COL_COMPANY: self.company or "(brak nazwy)",
            cm.COL_CITY: self.city or "(brak miasta)",
            cm.COL_INDUSTRY: self.industry,
            cm.COL_ROLE: self.title or "(brak stanowiska)",
            cm.COL_WEBSITE: self.website,
            cm.COL_EMAIL: self.email,
            cm.COL_PHONE: self.phone,
            cm.COL_MODE: self.work_mode_label(),
            cm.COL_SOURCE: self.portal or "ogłoszenie",
            cm.COL_NOTES: self.notes(),
        }


# --------------------------------------------------------------------------- URL

def normalize_offer_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        raise ValueError("Pusty URL oferty")
    if "://" not in u:
        u = "https://" + u.lstrip("/")
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"Niepoprawny URL oferty: {url!r}")
    # Parametry śledzące (utm, ref) nie identyfikują oferty — wycinamy.
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def detect_portal(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    for domain, label in _KNOWN_PORTALS.items():
        if host == domain or host.endswith("." + domain):
            return label
    return host


def _titleize_slug_words(words: Iterable[str]) -> str:
    return " ".join(w.capitalize() for w in words if w)


def parse_offer_url(url: str) -> Dict[str, str]:
    """
    Z samego URL wyciąga: id oferty, stanowisko i miasto (gdy portal koduje je w slugu).

    pracuj.pl: /praca/<stanowisko>-<miasto>,oferta,<id>
    Stanowisko i miasto są rozdzielane heurystycznie (ostatnie 1–2 słowa to miasto),
    więc wynik traktujemy jako fallback.
    """
    out = {"offer_id": "", "title": "", "city": ""}
    parsed = urlparse(url)
    path = parsed.path or ""
    segments = [s for s in path.split("/") if s]
    if not segments:
        return out
    last = segments[-1]
    parts = [p for p in last.split(",") if p]
    slug = parts[0] if parts else ""
    tail = [p for p in parts[1:] if p.lower() not in _SLUG_STOPWORDS]
    for candidate in reversed(tail):
        if re.fullmatch(r"\d{4,}", candidate):
            out["offer_id"] = candidate
            break
    if not out["offer_id"]:
        m = re.search(r"(\d{5,})", last)
        if m:
            out["offer_id"] = m.group(1)

    words = [w for w in re.split(r"[-_]+", slug.lower()) if w and w not in _SLUG_STOPWORDS]
    words = [w for w in words if not re.fullmatch(r"\d+", w)]
    if not words:
        return out

    for size in (2, 1):
        if len(words) > size:
            tail_city = " ".join(words[-size:])
            if tail_city in _SLUG_CITY_FIXES:
                out["city"] = _SLUG_CITY_FIXES[tail_city]
                out["title"] = _titleize_slug_words(words[:-size])
                return out
    if len(words) >= 2:
        out["city"] = _titleize_slug_words(words[-1:])
        out["title"] = _titleize_slug_words(words[:-1])
    else:
        out["title"] = _titleize_slug_words(words)
    return out


# ---------------------------------------------------------------------- parsing

def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _iter_json_ld_objects(soup: Any) -> Iterable[Dict[str, Any]]:
    for tag in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = tag.string or tag.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        stack: List[Any] = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                yield item
                graph = item.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)
            elif isinstance(item, list):
                stack.extend(item)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return _text(value.get("name") or value.get("@value") or "")
    if isinstance(value, list):
        return _text(value[0]) if value else ""
    return html_mod.unescape(str(value)).strip()


def _clean_html_text(value: str) -> str:
    if not value:
        return ""
    if BeautifulSoup is not None and "<" in value:
        value = BeautifulSoup(value, "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", html_mod.unescape(value)).strip()


def _detect_modes(text: str) -> List[str]:
    hay = text.lower()
    found = [label for token, label in _MODE_TOKENS if token in hay]
    return [m for m in _MODE_ORDER if m in found]


def _detect_contracts(text: str) -> List[str]:
    hay = text.lower()
    found: List[str] = []
    for token, label in _CONTRACT_TOKENS:
        if token in hay and label not in found:
            found.append(label)
    return found


def _apply_job_posting(offer: JobOffer, posting: Dict[str, Any]) -> None:
    offer.title = _clean_html_text(_text(posting.get("title"))) or offer.title
    org = posting.get("hiringOrganization")
    if isinstance(org, dict):
        offer.company = _clean_html_text(_text(org.get("name"))) or offer.company
        same_as = _text(org.get("sameAs") or org.get("url"))
        if same_as and not _is_portal_url(same_as):
            offer.website = offer.website or same_as
        offer.email = offer.email or _text(org.get("email"))
        offer.phone = offer.phone or _text(org.get("telephone"))
    else:
        offer.company = _clean_html_text(_text(org)) or offer.company

    for loc in _as_list(posting.get("jobLocation")):
        if not isinstance(loc, dict):
            continue
        addr = loc.get("address")
        if isinstance(addr, dict):
            city = _text(addr.get("addressLocality"))
            if city:
                offer.city = offer.city or city
                break

    for et in _as_list(posting.get("employmentType")):
        label = _EMPLOYMENT_TYPE_LABELS.get(str(et).upper(), str(et))
        if label and label not in offer.employment_types:
            offer.employment_types.append(label)

    jlt = _text(posting.get("jobLocationType"))
    if jlt.upper() == "TELECOMMUTE" and "zdalna" not in offer.work_modes:
        offer.work_modes.append("zdalna")

    description = _clean_html_text(_text(posting.get("description")))
    industry = _clean_html_text(_text(posting.get("industry")))
    if industry:
        offer.industry = offer.industry or industry
    hay = " ".join([description, _text(posting.get("title")), " ".join(offer.employment_types)])
    for m in _detect_modes(hay):
        if m not in offer.work_modes:
            offer.work_modes.append(m)
    for c in _detect_contracts(hay):
        if c not in offer.contracts:
            offer.contracts.append(c)


_TITLE_SUFFIX_RE = re.compile(r"\s*[-|–]\s*(oferta pracy|praca|pracuj\.pl|job offer).*$", re.I)
_TITLE_PREFIX_RE = re.compile(r"^\s*oferta pracy[:\s]+", re.I)


def parse_title_line(title: str) -> Dict[str, str]:
    """
    „Oferta pracy Spedytor / Spedytorka, Kompas Spedycja Sp. z o. o., Zielona Góra”
    → stanowisko / firma / miasto. Rozdzielanie po ostatnich przecinkach: miasto to
    ostatni człon, firma przedostatni, reszta to stanowisko.
    """
    out = {"title": "", "company": "", "city": ""}
    t = _clean_html_text(title or "")
    t = _TITLE_SUFFIX_RE.sub("", t)
    t = _TITLE_PREFIX_RE.sub("", t).strip()
    if not t:
        return out
    parts = [p.strip() for p in t.split(",") if p.strip()]
    if len(parts) >= 3:
        out["city"] = parts[-1]
        out["company"] = parts[-2]
        out["title"] = ", ".join(parts[:-2])
    elif len(parts) == 2:
        out["title"], out["company"] = parts
    else:
        out["title"] = parts[0]
    return out


def _is_portal_url(url: str) -> bool:
    try:
        return detect_portal(url) in _KNOWN_PORTALS.values()
    except Exception:
        return False


def parse_offer_html(offer: JobOffer, html: str) -> JobOffer:
    """Uzupełnia `offer` danymi ze strony ogłoszenia (JSON-LD → <title>/og:title → tekst)."""
    if BeautifulSoup is None or not html:
        return offer
    soup = BeautifulSoup(html, "html.parser")

    posting: Optional[Dict[str, Any]] = None
    for obj in _iter_json_ld_objects(soup):
        types = [str(t).lower() for t in _as_list(obj.get("@type"))]
        if "jobposting" in types:
            posting = obj
            break
    if posting is not None:
        _apply_job_posting(offer, posting)

    if not (offer.title and offer.company and offer.city):
        og = soup.find("meta", attrs={"property": "og:title"})
        title_text = ""
        if og is not None:
            title_text = og.get("content") or ""
        if not title_text and soup.title is not None:
            title_text = soup.title.get_text() or ""
        if not title_text:
            h1 = soup.find("h1")
            if h1 is not None:
                title_text = h1.get_text(" ")
        parsed = parse_title_line(title_text)
        offer.title = offer.title or parsed["title"]
        offer.company = offer.company or parsed["company"]
        offer.city = offer.city or parsed["city"]

    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()
    page_text = soup.get_text(" ")
    for m in _detect_modes(page_text):
        if m not in offer.work_modes:
            offer.work_modes.append(m)
    for c in _detect_contracts(page_text):
        if c not in offer.contracts:
            offer.contracts.append(c)
    return offer


# ------------------------------------------------------------------------ fetch

def looks_blocked(status_code: int, html: str) -> bool:
    if status_code in (401, 403, 429, 503):
        return True
    low = (html or "").lower()
    return any(h in low for h in ("just a moment", "captcha", "cf-chl", "access denied"))


def fetch_offer_html(url: str, timeout: float = OFFER_FETCH_TIMEOUT) -> tuple[str, str]:
    """Zwraca (html, status): status ∈ {"ok", "blocked", "http <kod>", "error: ..."}."""
    if requests is None:
        return "", "error: brak biblioteki requests"
    try:
        from fetch_throttle import throttle_hostname_before_http

        throttle_hostname_before_http(url)
    except Exception:
        pass
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": OFFER_FETCH_USER_AGENT,
                "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.7",
            },
        )
    except Exception as e:  # pragma: no cover - zależne od sieci
        return "", f"error: {e.__class__.__name__}"
    if looks_blocked(resp.status_code, resp.text):
        return "", "blocked"
    if resp.status_code >= 400:
        return "", f"http {resp.status_code}"
    return resp.text, "ok"


def build_offer(
    url: str,
    *,
    fetch: bool = True,
    overrides: Optional[Dict[str, str]] = None,
    html: Optional[str] = None,
) -> JobOffer:
    norm = normalize_offer_url(url)
    offer = JobOffer(url=norm, portal=detect_portal(norm))
    from_url = parse_offer_url(norm)
    offer.offer_id = from_url["offer_id"]

    if html is None and fetch:
        html, status = fetch_offer_html(norm)
        offer.fetch_status = status
        if status != "ok":
            logger.warning(
                "Nie udało się pobrać strony oferty (%s) — używam danych z URL i parametrów.",
                status,
            )
    elif html is not None:
        offer.fetch_status = "ok"

    if html:
        parse_offer_html(offer, html)

    offer.title = offer.title or from_url["title"]
    offer.city = offer.city or from_url["city"]

    for key, value in (overrides or {}).items():
        value = (value or "").strip()
        if not value:
            continue
        if key == "work_mode":
            offer.work_modes = _detect_modes(value) or offer.work_modes
            if not _detect_modes(value):
                offer.work_modes = [value]
        elif key == "contract":
            offer.contracts = [value]
        elif hasattr(offer, key):
            setattr(offer, key, value)
    return offer


# ----------------------------------------------------------------------- output

def default_output_path() -> str:
    try:
        from clean_validate_send_pipeline import EXTRA_CONTACTS_DIR

        base = EXTRA_CONTACTS_DIR
    except Exception:
        base = os.path.join(os.path.expanduser("~"), "Documents", "kontakty")
    return os.path.join(base, DEFAULT_OFFERS_FILENAME)


def _read_existing(path: str) -> pd.DataFrame:
    if not os.path.isfile(path):
        return pd.DataFrame(columns=MAILER_COLUMNS)
    low = path.lower()
    if low.endswith(".csv"):
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    else:
        df = pd.read_excel(path, dtype=str).fillna("")
    for col in MAILER_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df


def _row_already_present(df: pd.DataFrame, offer: JobOffer) -> bool:
    if df.empty:
        return False
    notes = df[cm.COL_NOTES].astype(str)
    if notes.str.contains(re.escape(offer.url), regex=True).any():
        return True
    if offer.offer_id and offer.portal:
        pat = rf"{re.escape(offer.portal)}.*\b{re.escape(offer.offer_id)}\b"
        if notes.str.contains(pat, regex=True).any():
            return True
    return False


def append_offer_to_contacts(offer: JobOffer, path: str, *, allow_duplicate: bool = False) -> bool:
    """Dopisuje wiersz oferty do xlsx/csv. Zwraca False, gdy oferta już była w pliku."""
    df = _read_existing(path)
    if not allow_duplicate and _row_already_present(df, offer):
        return False
    row = offer.to_row()
    new_df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    ordered = MAILER_COLUMNS + [c for c in new_df.columns if c not in MAILER_COLUMNS]
    new_df = new_df[ordered].fillna("")
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    if path.lower().endswith(".csv"):
        new_df.to_csv(path, index=False, encoding="utf-8-sig")
    else:
        new_df.to_excel(path, index=False)
    return True


# -------------------------------------------------------------------------- CLI

def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Dodaje ogłoszenie o pracę (URL, np. pracuj.pl) jako kontakt do pliku "
            "w katalogu dodatkowych kontaktów pipeline'u."
        )
    )
    parser.add_argument("url", help="Adres ogłoszenia, np. https://www.pracuj.pl/praca/...,oferta,123")
    parser.add_argument("--output", "-o", default="", help="Plik .xlsx/.csv (domyślnie Documents/kontakty/Kontakty_oferty.xlsx)")
    parser.add_argument("--company", default="", help="Nadpisz nazwę firmy")
    parser.add_argument("--city", default="", help="Nadpisz miasto")
    parser.add_argument("--role", default="", help="Nadpisz stanowisko")
    parser.add_argument("--website", default="", help="Strona WWW pracodawcy (do pobrania e-maila, FETCH_EMAIL_FROM_WEBSITE=1)")
    parser.add_argument("--email", default="", help="E-mail rekrutacyjny (gdy znany)")
    parser.add_argument("--phone", default="", help="Telefon / kontakt")
    parser.add_argument("--industry", default="", help="Branża")
    parser.add_argument("--work-mode", default="", help="Tryb pracy (np. 'praca zdalna / hybrydowa')")
    parser.add_argument("--contract", default="", help="Forma zatrudnienia (np. 'umowa o pracę')")
    parser.add_argument("--no-fetch", action="store_true", help="Nie pobieraj strony — tylko URL + parametry")
    parser.add_argument("--allow-duplicate", action="store_true", help="Dopisz nawet jeśli oferta już jest w pliku")
    parser.add_argument("--dry-run", action="store_true", help="Tylko pokaż wiersz, nic nie zapisuj")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    setup_logging("job_offer_import")
    args = _parse_args(argv)
    overrides = {
        "company": args.company,
        "city": args.city,
        "title": args.role,
        "website": args.website,
        "email": args.email,
        "phone": args.phone,
        "industry": args.industry,
        "work_mode": args.work_mode,
        "contract": args.contract,
    }
    try:
        offer = build_offer(args.url, fetch=not args.no_fetch, overrides=overrides)
    except ValueError as e:
        logger.error("%s", e)
        return 2

    if not offer.email and not offer.website:
        logger.warning(
            "Brak e-maila i strony WWW — pipeline oznaczy wiersz „Brak e-maila”. "
            "Dodaj --email lub --website (z FETCH_EMAIL_FROM_WEBSITE=1)."
        )
    row = offer.to_row()
    print(json.dumps(row, ensure_ascii=False, indent=2))

    if args.dry_run:
        return 0

    out_path = args.output.strip() or default_output_path()
    added = append_offer_to_contacts(offer, out_path, allow_duplicate=args.allow_duplicate)
    if added:
        logger.info("Dopisano ofertę do: %s", out_path)
    else:
        logger.info("Oferta już jest w pliku %s — pominięto.", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
