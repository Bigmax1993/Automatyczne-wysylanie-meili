"""
Import publicznego ogłoszenia o pracę (OLX, Pracuj.pl) do formatu kontaktów mailera.

Skrypt czyta tylko publiczny HTML (HTTP albo plik zapisany przez użytkownika).
Przy CAPTCHA / HTTP 403/429 / Cloudflare nie obchodzi zabezpieczeń — kończy
z czytelnym błędem i sugeruje ``--html-file``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

import build_contacts_serpapi as serp
import pipeline_version as pv
from pipeline_logging import setup_logging

logger = logging.getLogger(__name__)
setup_logging("import_job_listing")

LISTING_FETCH_TIMEOUT = float(os.environ.get("JOB_LISTING_FETCH_TIMEOUT", "15"))
LISTING_FETCH_MAX_BYTES = int(os.environ.get("JOB_LISTING_FETCH_MAX_BYTES", "800000"))
LISTING_NOTES_MAX_CHARS = int(os.environ.get("JOB_LISTING_NOTES_MAX_CHARS", "2500"))
LISTING_USER_AGENT = os.environ.get(
    "JOB_LISTING_USER_AGENT",
    os.environ.get(
        "WEB_FETCH_USER_AGENT",
        "Mozilla/5.0 (compatible; ContactMailer/1.1; job-application-context)",
    ),
)

OLX_HOST_SUFFIXES = ("olx.pl", "olx.com")
PRACUJ_HOST_SUFFIXES = ("pracuj.pl",)
PHONE_RE = re.compile(
    r"(?:\+48[\s\-]*)?(?:\d[\s\-]*){8,11}\d",
    re.UNICODE,
)
SALARY_LINE_RE = re.compile(
    r"(\d[\d\s]{1,}\d)\s*[–\-]\s*(\d[\d\s]{1,}\d)\s*zł[^\n]{0,60}",
    re.IGNORECASE,
)
VOIVODESHIPS = {
    "dolnośląskie",
    "kujawsko-pomorskie",
    "lubelskie",
    "lubuskie",
    "łódzkie",
    "małopolskie",
    "mazowieckie",
    "opolskie",
    "podkarpackie",
    "podlaskie",
    "pomorskie",
    "śląskie",
    "świętokrzyskie",
    "warmińsko-mazurskie",
    "wielkopolskie",
    "zachodniopomorskie",
}
WORK_MODE_PHRASES = (
    "praca stacjonarna",
    "praca zdalna",
    "praca hybrydowa",
    "home office",
)
CONTRACT_PHRASES = (
    "umowa o pracę",
    "kontrakt b2b",
    "umowa zlecenie",
    "umowa o dzieło",
    "samozatrudnienie",
)
INDUSTRY_HINTS = (
    (
        ("spedyc", "transport", "logistyk", "tsl", "przewoź", "przewoz"),
        "Spedycja / transport / logistyka",
    ),
    (("opiekun", "opiekuń", "opieka", "pflege"), "Opieka / usługi opiekuńcze"),
    (("biurow", "administr", "koordynator"), "Administracja / biuro"),
)
EMPLOYMENT_TYPE_PL = {
    "FULL_TIME": "Pełny etat",
    "PART_TIME": "Część etatu",
    "CONTRACTOR": "B2B / samozatrudnienie",
    "TEMPORARY": "Umowa zlecenie",
    "INTERN": "Staż / praktyki",
    "VOLUNTEER": "Wolontariat",
    "PER_DIEM": "Dorywczo",
    "OTHER": "",
}


class ListingFetchBlocked(RuntimeError):
    """Portal zablokował publiczne pobranie (CAPTCHA / 403 / 429) — bez obchodzenia."""


class ListingParseError(ValueError):
    """HTML nie zawiera rozpoznawalnego ogłoszenia."""


def _host_matches(url: str, suffixes: Tuple[str, ...]) -> bool:
    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "").lower().lstrip("www.")
    if not host:
        return False
    return any(host == s or host.endswith("." + s) for s in suffixes)


def is_olx_listing_url(url: str) -> bool:
    return _host_matches(url, OLX_HOST_SUFFIXES)


def is_pracuj_listing_url(url: str) -> bool:
    return _host_matches(url, PRACUJ_HOST_SUFFIXES)


def listing_source_name(url: str) -> str:
    if is_pracuj_listing_url(url):
        return "pracuj.pl"
    if is_olx_listing_url(url):
        return "olx.pl"
    return serp._domain(url) or "ogłoszenie"


def listing_id_from_url(url: str) -> str:
    raw = (url or "").strip()
    match = re.search(r"oferta[,/](\d{5,})", raw, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"ID([A-Za-z0-9]+)", raw)
    return match.group(1) if match else ""


def default_contacts_output(url: str) -> str:
    if is_pracuj_listing_url(url):
        name = "pracuj_listing.xlsx"
    elif is_olx_listing_url(url):
        name = "olx_listing.xlsx"
    else:
        name = "job_listing.xlsx"
    return os.path.join(os.path.expanduser("~"), "Documents", "kontakty", name)


def _type_names(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.split("/")[-1]]
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for item in value:
            out.extend(_type_names(item))
        return out
    return []


def _is_job_posting(obj: Any) -> bool:
    return isinstance(obj, dict) and "JobPosting" in _type_names(obj.get("@type"))


def _walk_jsonld(node: Any) -> Iterable[dict]:
    if isinstance(node, list):
        for item in node:
            yield from _walk_jsonld(item)
        return
    if not isinstance(node, dict):
        return
    if _is_job_posting(node):
        yield node
    graph = node.get("@graph")
    if graph is not None:
        yield from _walk_jsonld(graph)
    for key, value in node.items():
        if key in {"@graph", "@context"}:
            continue
        if isinstance(value, (dict, list)):
            yield from _walk_jsonld(value)


def _parse_json_scripts(html: str) -> List[Any]:
    soup = BeautifulSoup(html, "html.parser")
    blobs: List[Any] = []
    for script in soup.find_all("script"):
        stype = (script.get("type") or "").lower()
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        if "ld+json" in stype or raw[:1] in "{[":
            try:
                blobs.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return blobs


def extract_job_posting_jsonld(html: str) -> Optional[dict]:
    for blob in _parse_json_scripts(html):
        for posting in _walk_jsonld(blob):
            return posting
    return None


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, dict):
            nested = _first_text(
                value.get("name"),
                value.get("value"),
                value.get("text"),
                value.get("@value"),
            )
            if nested:
                return nested
            continue
        if isinstance(value, list):
            nested = _first_text(*value)
            if nested:
                return nested
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _identifier_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list) and value:
        return _identifier_value(value[0])
    if isinstance(value, dict):
        return _first_text(
            value.get("value"),
            value.get("@value"),
            value.get("text"),
            value.get("name"),
        )
    return _first_text(value)


def _city_without_voivodeship(city: str) -> str:
    raw = re.sub(r"\s+", " ", (city or "").strip())
    if not raw:
        return ""
    parts = [p for p in re.split(r"[\s,]+", raw) if p]
    if len(parts) >= 2 and parts[-1].lower() in VOIVODESHIPS:
        return " ".join(parts[:-1]).strip(" ,")
    return raw


def _parse_pracuj_document_title(title: str) -> Tuple[str, str, str]:
    raw = re.sub(r"\s+[•|].*$", "", (title or "").strip())
    raw = re.sub(r"^Oferta pracy\s+", "", raw, flags=re.IGNORECASE).strip()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) >= 3:
        return parts[0], ",".join(parts[1:-1]).strip(), parts[-1]
    if len(parts) == 2:
        return parts[0], parts[1], ""
    return raw, "", ""


def _infer_industry(title: str, description: str, explicit: str = "") -> str:
    if explicit:
        return explicit
    hay = f"{title} {description}".lower()
    for tokens, label in INDUSTRY_HINTS:
        if any(tok in hay for tok in tokens):
            return label
    return "(do ustalenia)"


def _phrases_from_text(text: str, phrases: Tuple[str, ...]) -> List[str]:
    hay = (text or "").lower()
    found: List[str] = []
    for phrase in phrases:
        if phrase in hay:
            found.append(phrase)
    return found


def _work_mode_from_text(text: str) -> str:
    return ", ".join(_phrases_from_text(text, WORK_MODE_PHRASES))


def _contract_from_text(text: str) -> str:
    found = _phrases_from_text(text, CONTRACT_PHRASES)
    pretty = []
    for item in found:
        if item == "kontrakt b2b":
            pretty.append("kontrakt B2B")
        else:
            pretty.append(item)
    return ", ".join(pretty)


def _salary_lines_from_text(text: str) -> List[str]:
    found: List[str] = []
    seen = set()
    for match in SALARY_LINE_RE.finditer(text or ""):
        line = re.sub(r"\s+", " ", match.group(0)).strip()
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(line)
        if len(found) >= 4:
            break
    return found


def _company_without_o_firmie(company: str) -> str:
    raw = (company or "").strip()
    return re.sub(r"\s+O firmie\s*$", "", raw, flags=re.IGNORECASE).strip()


def _html_to_text(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if "<" in raw and ">" in raw:
        try:
            from web_page_context import html_to_clean_text

            cleaned = html_to_clean_text(raw)
            if cleaned:
                return cleaned
        except Exception:
            soup = BeautifulSoup(raw, "html.parser")
            return soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", raw).strip()


def _organization_name(org: Any) -> str:
    if isinstance(org, list) and org:
        org = org[0]
    if isinstance(org, dict):
        return _first_text(org.get("name"), org.get("legalName"))
    return _first_text(org)


def _candidate_urls(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: List[str] = []
        for item in value:
            out.extend(_candidate_urls(item))
        return out
    if isinstance(value, dict):
        return _candidate_urls(
            [value.get("url"), value.get("sameAs"), value.get("name"), value.get("@id")]
        )
    text = str(value).strip()
    if not text:
        return []
    if text.startswith(("http://", "https://")) or (
        "." in text and " " not in text and not text.startswith("@")
    ):
        return [text]
    return []


def _organization_url(org: Any) -> str:
    if isinstance(org, list) and org:
        org = org[0]
    if not isinstance(org, dict):
        return ""
    for cand in _candidate_urls(
        [org.get("url"), org.get("sameAs"), org.get("identifier")]
    ):
        norm = serp._normalize_url(cand)
        if norm and not serp._is_job_portal_domain(norm):
            return norm
    return ""


def _address_parts(posting: dict) -> Tuple[str, str]:
    loc = posting.get("jobLocation")
    if isinstance(loc, list) and loc:
        loc = loc[0]
    if not isinstance(loc, dict):
        return "", ""
    addr = loc.get("address") or loc
    if isinstance(addr, list) and addr:
        addr = addr[0]
    if not isinstance(addr, dict):
        return _first_text(loc.get("name")), ""
    city = _first_text(
        addr.get("addressLocality"),
        addr.get("addressRegion"),
        loc.get("name"),
    )
    street = _first_text(
        addr.get("streetAddress"),
        addr.get("postalCode"),
    )
    postal = _first_text(addr.get("postalCode"))
    if postal and postal not in street:
        street = f"{street}, {postal}".strip(", ")
    return city, street


def _format_salary(posting: dict) -> str:
    salary = posting.get("baseSalary")
    if isinstance(salary, list) and salary:
        salary = salary[0]
    if not isinstance(salary, dict):
        return _first_text(salary)
    currency = _first_text(salary.get("currency"), "PLN")
    value = salary.get("value")
    if isinstance(value, list) and value:
        value = value[0]
    min_v = max_v = unit = ""
    if isinstance(value, dict):
        min_v = _first_text(value.get("minValue"), value.get("value"))
        max_v = _first_text(value.get("maxValue"), min_v)
        unit = _first_text(value.get("unitText"))
    else:
        min_v = max_v = _first_text(value)
    if not min_v:
        return ""
    amount = min_v if min_v == max_v or not max_v else f"{min_v} - {max_v}"
    unit_pl = {
        "MONTH": "mies.",
        "YEAR": "rok",
        "HOUR": "godz.",
        "WEEK": "tydz.",
        "DAY": "dzień",
    }.get(unit.upper(), unit.lower() if unit else "mies.")
    cur = "zł" if currency.upper() in {"PLN", "ZL", "ZŁ"} else currency
    return f"{amount} {cur} / {unit_pl}".strip()


def _format_employment_type(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts = [_format_employment_type(v) for v in value]
        return ", ".join(p for p in parts if p)
    raw = str(value).strip()
    if not raw:
        return ""
    key = raw.upper().replace(" ", "_")
    return EMPLOYMENT_TYPE_PL.get(key, raw)


def _visible_labeled_field(text: str, label: str) -> str:
    pattern = re.compile(
        rf"{re.escape(label)}\s*[:\-]?\s*[\r\n]+\s*(.+)",
        re.IGNORECASE,
    )
    match = pattern.search(text or "")
    if not match:
        return ""
    line = match.group(1).strip()
    return re.split(r"[\r\n]+", line, maxsplit=1)[0].strip()


def _extract_phones(text: str, listing_id: str = "") -> str:
    found: List[str] = []
    seen = set()
    for match in PHONE_RE.finditer(text or ""):
        digits = re.sub(r"\D+", "", match.group(0))
        if listing_id and digits == re.sub(r"\D+", "", listing_id):
            continue
        if len(digits) < 9 or len(digits) > 11:
            continue
        if digits in seen:
            continue
        seen.add(digits)
        found.append(re.sub(r"\s+", " ", match.group(0)).strip())
        if len(found) >= 3:
            break
    return ", ".join(found)


def _attr_text(soup: BeautifulSoup, **attrs: str) -> str:
    node = soup.find(attrs=attrs)
    return node.get_text(" ", strip=True) if node else ""


def _pracuj_section_text(soup: BeautifulSoup) -> str:
    parts: List[str] = []
    for heading in (
        "Twój zakres obowiązków",
        "Nasze wymagania",
        "To oferujemy",
    ):
        node = soup.find(string=re.compile(rf"^{re.escape(heading)}$", re.IGNORECASE))
        if not node:
            continue
        block = node.find_parent()
        if block is None:
            continue
        text = block.get_text("\n", strip=True)
        sibling = block.find_next_sibling()
        if sibling:
            extra = sibling.get_text("\n", strip=True)
            if extra:
                text = f"{text}\n{extra}"
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _fallback_from_html(html: str) -> Dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    for selector in (
        {"name": "h1", "attrs": {"data-cy": "ad_title"}},
        {"name": "h1", "attrs": {"data-test": "text-positionName"}},
        {"name": "h1"},
    ):
        node = soup.find(**selector) if "attrs" in selector else soup.find(selector["name"])
        if node:
            title = node.get_text(" ", strip=True)
            if title:
                break
    if not title:
        og = soup.find("meta", attrs={"property": "og:title"})
        title = (og.get("content") or "").strip() if og else ""
        title = re.sub(r"\s+[•|].*$", "", title).strip()

    parsed_title, parsed_company, parsed_city = ("", "", "")
    if title.lower().startswith("oferta pracy") or (title.count(",") >= 2):
        parsed_title, parsed_company, parsed_city = _parse_pracuj_document_title(title)
        if parsed_title:
            title = parsed_title

    desc_node = soup.find(attrs={"data-cy": "ad_description"}) or soup.find(
        attrs={"data-test": "section-description"}
    )
    description = desc_node.get_text("\n", strip=True) if desc_node else ""
    if not description:
        description = _pracuj_section_text(soup)
    if not description:
        ogd = soup.find("meta", attrs={"property": "og:description"})
        description = (ogd.get("content") or "").strip() if ogd else ""

    company = ""
    for attrs in (
        {"data-cy": "seller-name"},
        {"data-testid": "seller-name"},
        {"data-test": "text-employerName"},
    ):
        company = _attr_text(soup, **attrs)
        if company:
            break
    if not company:
        company = parsed_company
    company = _company_without_o_firmie(company)

    city = _city_without_voivodeship(
        _attr_text(soup, **{"data-test": "text-workplaces"}) or parsed_city
    )
    visible = soup.get_text("\n", strip=True)
    return {
        "title": title,
        "company": company,
        "description": description,
        "city": city,
        "contract": _contract_from_text(visible),
        "salary": "; ".join(_salary_lines_from_text(visible)),
        "work_mode": _work_mode_from_text(visible),
        "visible_text": visible,
    }


def parse_job_listing_html(html: str, source_url: str) -> Dict[str, str]:
    """Zwraca wiersz w kolumnach mailera albo rzuca ListingParseError."""
    posting = extract_job_posting_jsonld(html) or {}
    fallback = _fallback_from_html(html)
    visible = fallback.get("visible_text") or ""

    title = _first_text(posting.get("title"), fallback.get("title"))
    if title.lower().startswith("oferta pracy"):
        title, _, _ = _parse_pracuj_document_title(title)
    if not title:
        raise ListingParseError("Nie znaleziono tytułu ogłoszenia w HTML.")

    company = _company_without_o_firmie(
        _organization_name(posting.get("hiringOrganization"))
        or fallback.get("company", "")
    )
    if not company:
        company = "(brak nazwy)"

    city, street = _address_parts(posting)
    if not city:
        city = (
            fallback.get("city")
            or _visible_labeled_field(visible, "Lokalizacja")
            or "(brak miasta)"
        )
        if "," in city:
            city = city.split(",")[-1].strip()
    city = _city_without_voivodeship(city) or city

    description = _html_to_text(
        _first_text(posting.get("description"), fallback.get("description"))
    )
    salary = _format_salary(posting)
    extra_salaries = _salary_lines_from_text(visible)
    if not salary:
        salary = (
            fallback.get("salary")
            or _visible_labeled_field(visible, "Wynagrodzenie")
            or (extra_salaries[0] if extra_salaries else "")
        )

    mode = _format_employment_type(posting.get("employmentType"))
    if not mode:
        mode = _visible_labeled_field(visible, "Wymiar pracy")
    work_mode = fallback.get("work_mode") or _work_mode_from_text(visible)
    if work_mode:
        mode = ", ".join(part for part in (mode, work_mode) if part)
    if not mode:
        mode = "(do ustalenia)"

    contract = (
        _visible_labeled_field(visible, "Typ umowy")
        or fallback.get("contract")
        or _contract_from_text(visible)
    )
    listing_id = _identifier_value(posting.get("identifier")) or _first_text(
        posting.get("id")
    )
    if not listing_id:
        listing_id = listing_id_from_url(source_url)
    id_match = re.search(r"ID[:\s-]*([A-Za-z0-9]+)", visible, re.IGNORECASE)
    if not listing_id and id_match:
        listing_id = id_match.group(1)

    website = _organization_url(posting.get("hiringOrganization"))
    website = serp._normalize_url(website) if website else ""
    if website and serp._is_job_portal_domain(website):
        website = ""

    email = serp._extract_email_from_html(html)
    if not email and description:
        match = serp.EMAIL_RE.search(description)
        email = match.group(0) if match else ""
    phone = _extract_phones(f"{description}\n{visible}", listing_id=listing_id)

    industry = _infer_industry(
        title,
        description,
        explicit=_first_text(posting.get("industry")),
    )

    source = listing_source_name(source_url)

    notes_parts = []
    if source_url:
        notes_parts.append(f"Źródło ogłoszenia: {source_url}")
    if listing_id:
        notes_parts.append(f"ID ogłoszenia: {listing_id}")
    if salary:
        notes_parts.append(f"Wynagrodzenie: {salary}")
    extra_salary_notes = [s for s in extra_salaries if s and s not in salary]
    if extra_salary_notes:
        notes_parts.append("Inne stawki z ogłoszenia: " + "; ".join(extra_salary_notes))
    if contract:
        notes_parts.append(f"Typ umowy: {contract}")
    if street:
        notes_parts.append(f"Adres: {street}")
    if description:
        notes_parts.append("Opis oferty:\n" + description)
    notes = "\n".join(notes_parts).strip()
    if len(notes) > LISTING_NOTES_MAX_CHARS:
        notes = notes[: LISTING_NOTES_MAX_CHARS - 3].rstrip() + "..."

    row = {col: "" for col in serp.MAILER_COLUMNS}
    row["Firma"] = company
    row["Miasto"] = city
    row["Branża"] = industry
    row["Stanowisko / Rola"] = title
    row["Strona WWW"] = website
    row["E-mail rekrutacyjny"] = email
    row["Tel / Kontakt"] = phone
    row["Tryb pracy"] = mode
    row["Źródło / Portal"] = source
    row["Uwagi"] = notes
    return row


def fetch_public_listing_html(url: str) -> str:
    """Pobiera publiczny HTML. Przy blokadzie rzuca ListingFetchBlocked."""
    norm = serp._normalize_url(url)
    if not norm:
        raise ListingParseError("Brak URL ogłoszenia.")
    try:
        from fetch_throttle import throttle_hostname_before_http

        throttle_hostname_before_http(norm)
    except Exception:
        pass
    headers = {"User-Agent": LISTING_USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    try:
        with requests.get(
            norm,
            timeout=LISTING_FETCH_TIMEOUT,
            headers=headers,
            stream=True,
        ) as resp:
            body = b""
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                body += chunk
                if len(body) >= LISTING_FETCH_MAX_BYTES:
                    break
            text = body.decode(resp.encoding or "utf-8", errors="replace")
            if serp._looks_like_captcha_or_block(resp.status_code, text):
                raise ListingFetchBlocked(
                    f"Portal zablokował pobranie ogłoszenia (HTTP {resp.status_code}). "
                    "Nie obchodzę CAPTCHA/WAF — zapisz publiczny HTML oferty i użyj --html-file."
                )
            if resp.status_code >= 400:
                raise ListingFetchBlocked(
                    f"Nie udało się pobrać ogłoszenia (HTTP {resp.status_code}). "
                    "Użyj --html-file z publicznym HTML."
                )
            return text
    except ListingFetchBlocked:
        raise
    except Exception as exc:
        raise ListingFetchBlocked(
            f"Błąd pobierania ogłoszenia: {exc}. Użyj --html-file z publicznym HTML."
        ) from exc


def apply_overrides(
    row: Dict[str, str],
    company_website: str = "",
    email: str = "",
) -> Dict[str, str]:
    site = (company_website or "").strip()
    if site:
        row["Strona WWW"] = serp._normalize_url(site)
        if serp._is_job_portal_domain(row["Strona WWW"]):
            row["Strona WWW"] = ""
    mail = (email or "").strip()
    if mail:
        row["E-mail rekrutacyjny"] = mail
    return row


def enrich_email_from_company_site(row: Dict[str, str]) -> Dict[str, str]:
    if row.get("E-mail rekrutacyjny"):
        return row
    site = row.get("Strona WWW") or ""
    if not site or serp._is_job_portal_domain(site):
        return row
    found = serp._extract_recruit_email_from_site(site)
    if found:
        row["E-mail rekrutacyjny"] = found
    return row


def write_contacts(rows: List[Dict[str, str]], output_path: str) -> str:
    path = os.path.abspath(output_path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    df = pd.DataFrame(rows)
    for col in serp.MAILER_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[serp.MAILER_COLUMNS]
    lower = path.lower()
    if lower.endswith(".csv"):
        df.to_csv(path, index=False, encoding="utf-8-sig")
    else:
        df.to_excel(path, index=False)
    try:
        from json_data_backup import maybe_backup_dataframe

        maybe_backup_dataframe(df, path, reason="import_job_listing")
    except Exception:
        logger.exception("Kopia JSON po imporcie ogłoszenia nie powiodła się")
    return path


def import_listing(
    url: str,
    html: Optional[str] = None,
    company_website: str = "",
    email: str = "",
    enrich_email: bool = False,
) -> Dict[str, str]:
    source_html = html if html is not None else fetch_public_listing_html(url)
    row = parse_job_listing_html(source_html, url)
    row = apply_overrides(row, company_website=company_website, email=email)
    if enrich_email:
        row = enrich_email_from_company_site(row)
    return row


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Import publicznego ogłoszenia o pracę (OLX / Pracuj.pl, JSON-LD / HTML) "
            "do arkusza kontaktów mailera."
        )
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"import_job_listing {pv.PIPELINE_VERSION}",
    )
    parser.add_argument(
        "--url",
        required=True,
        help=(
            "Publiczny URL ogłoszenia "
            "(np. https://www.pracuj.pl/praca/..., https://www.olx.pl/oferta/praca/...)"
        ),
    )
    parser.add_argument(
        "--html-file",
        default="",
        help="Zapisany publiczny HTML oferty (gdy portal blokuje pobranie z datacenter).",
    )
    parser.add_argument(
        "--company-website",
        default="",
        help="Oficjalna strona firmy (nie portal ogłoszeń). Używana do kolumny Strona WWW.",
    )
    parser.add_argument(
        "--email",
        default="",
        help="Opcjonalny e-mail rekrutacyjny, gdy nie ma go w ogłoszeniu.",
    )
    parser.add_argument(
        "--enrich-email",
        action="store_true",
        help="Gdy brak e-maila, spróbuj odczytać mailto ze strony firmy (--company-website).",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Ścieżka .xlsx albo .csv (domyślnie Documents/kontakty/<portal>_listing.xlsx)",
    )
    args = parser.parse_args(argv)
    output = (args.output or "").strip() or default_contacts_output(args.url)

    html: Optional[str] = None
    html_file = (args.html_file or "").strip()
    if html_file:
        with open(html_file, encoding="utf-8") as f:
            html = f.read()

    try:
        row = import_listing(
            url=args.url,
            html=html,
            company_website=args.company_website,
            email=args.email,
            enrich_email=args.enrich_email,
        )
    except ListingFetchBlocked as exc:
        logger.warning("%s", exc)
        return 2
    except (ListingParseError, OSError) as exc:
        logger.error("%s", exc)
        return 1

    path = write_contacts([row], output)
    logger.info("Zapisano kontakt z ogłoszenia: %s", path)
    logger.info(
        "Firma=%s | Rola=%s | Miasto=%s | E-mail=%s | WWW=%s",
        row.get("Firma"),
        row.get("Stanowisko / Rola"),
        row.get("Miasto"),
        row.get("E-mail rekrutacyjny") or "(brak)",
        row.get("Strona WWW") or "(brak)",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
