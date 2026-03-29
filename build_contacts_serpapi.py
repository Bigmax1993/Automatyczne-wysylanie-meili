import argparse
import logging
import os
import re
import sys
import time
from datetime import datetime, date
from typing import Dict, List
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

import pipeline_version as pv
from pipeline_logging import setup_logging

logger = logging.getLogger(__name__)
setup_logging("build_contacts_serpapi")

try:
    from serpapi import GoogleSearch
except Exception:  # pragma: no cover
    GoogleSearch = None  # type: ignore[assignment]


DEFAULT_TARGET_CITIES = ["Wroclaw", "Zielona Gora", "Poznan"]
QUERY_SUFFIXES = ["", "praca", "rekrutacja", "kariera", "oferty pracy", "hr"]

FIRM_KEYWORDS = [
    "Software house data BI",
    "Data analytics consulting",
    "Agencja konsultingowa BI",
]

AGENCY_KEYWORDS = [
    "Agencja outsourcingowa IT",
    "Body leasing IT",
    "Staff augmentation data",
    "Talent marketplace freelance IT",
]
ECOMMERCE_KEYWORDS = [
    "Sklep internetowy e-commerce analityk danych",
    "E-commerce BI analyst",
    "Analityka danych sklep internetowy",
    "E-commerce marketplace Poland",
]

MAILER_COLUMNS = [
    "Firma",
    "Miasto",
    "Branża",
    "Stanowisko / Rola",
    "Strona WWW",
    "E-mail rekrutacyjny",
    "Tel / Kontakt",
    "Tryb pracy",
    "Źródło / Portal",
    "Uwagi",
]
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
JOB_PORTAL_DOMAINS = (
    "pracuj.pl",
    "justjoin.it",
    "nofluffjobs.com",
    "rocketjobs.pl",
    "linkedin.com",
    "glassdoor.com",
    "indeed.com",
    "theprotocol.it",
    "bulldogjob.pl",
    "gowork.pl",
)
CAPTCHA_HINTS = (
    "captcha",
    "recaptcha",
    "verify you are human",
    "are you human",
    "cloudflare",
    "access denied",
    "blocked",
)


def _serp_daily_limit_enabled() -> bool:
    v = (os.environ.get("SERPAPI_DAILY_LIMIT_ENABLED") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _serp_run_state_path() -> str:
    p = (os.environ.get("SERPAPI_RUN_STATE_PATH") or "").strip()
    if p:
        return os.path.abspath(p)
    return os.path.abspath(
        os.path.join(os.path.expanduser("~"), "Documents", "kontakty", ".serpapi_last_run_date")
    )


def _read_serp_last_run_date(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _write_serp_last_run_date(path: str, d: date) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(d.isoformat() + "\n")


def _should_skip_serp_today() -> bool:
    if not _serp_daily_limit_enabled():
        return False
    today = datetime.now().date().isoformat()
    return _read_serp_last_run_date(_serp_run_state_path()) == today


def _domain(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower().replace("www.", "")
    return netloc.strip()


def _is_job_portal_domain(value: str) -> bool:
    d = _domain(value) if "://" in value else value.lower().replace("www.", "")
    return any(d.endswith(portal) for portal in JOB_PORTAL_DOMAINS)


def _looks_like_captcha_or_block(status_code: int, html: str) -> bool:
    if status_code in (403, 429, 503):
        return True
    txt = (html or "").lower()
    return any(hint in txt for hint in CAPTCHA_HINTS)


def _clean_company_name(text: str) -> str:
    if not text:
        return ""
    cleaned = re.split(r"\s[\-|–|:]\s", text)[0]
    return cleaned.strip()


def _record_key(name: str, website: str) -> str:
    d = _domain(website)
    if d:
        return d
    return re.sub(r"\s+", " ", name.lower()).strip()


def _normalize_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if not u.startswith(("http://", "https://")):
        return f"https://{u}"
    return u


def _extract_email_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.select("a[href^='mailto:']"):
        href = a.get("href", "")
        email = href.replace("mailto:", "").split("?")[0].strip()
        if EMAIL_RE.fullmatch(email):
            return email
    match = EMAIL_RE.search(soup.get_text(" ", strip=True))
    return match.group(0) if match else ""


def _extract_recruit_email_from_site(base_url: str, timeout: float = 8.0) -> str:
    root = _normalize_url(base_url)
    if not root:
        return ""

    candidates = [root]
    for slug in ("kontakt", "contact", "kariera", "careers", "rekrutacja"):
        candidates.append(root.rstrip("/") + f"/{slug}")

    headers = {"User-Agent": "Mozilla/5.0 (compatible; ContactBuilder/1.0)"}
    for url in candidates:
        try:
            try:
                from fetch_throttle import throttle_hostname_before_http

                throttle_hostname_before_http(url)
            except Exception:
                pass
            resp = requests.get(url, timeout=timeout, headers=headers)
            if _looks_like_captcha_or_block(resp.status_code, resp.text):
                # Legal and safe fallback: skip blocked pages.
                continue
            if resp.status_code >= 400:
                continue
            email = _extract_email_from_html(resp.text)
            if email:
                return email
        except Exception:
            continue
    return ""


def _row(
    company: str,
    city: str,
    website: str,
    phone: str,
    category: str,
    source_query: str,
    source_kind: str,
) -> Dict[str, str]:
    return {
        "Firma": company or "(brak nazwy)",
        "Miasto": city or "(brak miasta)",
        "Branża": category,
        "Stanowisko / Rola": "Data Analyst / BI",
        "Strona WWW": website,
        "E-mail rekrutacyjny": "",
        "Tel / Kontakt": phone,
        "Tryb pracy": "(do ustalenia)",
        "Źródło / Portal": f"SerpAPI/{source_kind}",
        "Uwagi": source_query,
    }


def _extract_organic(result: dict, category: str, query: str, city: str) -> Dict[str, str]:
    title = result.get("title", "")
    link = result.get("link", "")
    company = _clean_company_name(title) or _domain(link)
    website = "" if _is_job_portal_domain(link) else link
    return _row(company, city, website, "", category, query, "organic")


def _extract_local(result: dict, category: str, query: str, city: str) -> Dict[str, str]:
    company = result.get("title", "")
    website = result.get("website", "")
    if _is_job_portal_domain(website):
        website = ""
    phone = result.get("phone", "")
    local_city = city
    address = result.get("address", "")
    if address and city == "Polska":
        local_city = address.split(",")[-1].strip()
    return _row(company, local_city, website, phone, category, query, "local")


def _iter_local_results(data: dict) -> List[dict]:
    local = data.get("local_results", [])
    if isinstance(local, list):
        return local
    if isinstance(local, dict):
        places = local.get("places")
        if isinstance(places, list):
            return places
    places_results = data.get("places_results", [])
    if isinstance(places_results, list):
        return places_results
    return []


def _query_serpapi(api_key: str, query: str, start: int, num: int) -> dict:
    if GoogleSearch is None:
        raise RuntimeError(
            "Brak biblioteki serpapi. Zainstaluj: pip install google-search-results"
        )
    search = GoogleSearch(
        {
            "engine": "google",
            "q": query,
            "hl": "pl",
            "gl": "pl",
            "num": num,
            "start": start,
            "api_key": api_key,
        }
    )
    return search.get_dict()


def _find_company_website(api_key: str, company: str, city: str) -> str:
    if not company:
        return ""
    query = f"{company} {city} oficjalna strona www"
    data = _query_serpapi(api_key, query, start=0, num=10)
    for result in data.get("organic_results", []):
        link = result.get("link", "")
        if link and not _is_job_portal_domain(link):
            return _normalize_url(link)
    return ""


def _find_public_contact_page(api_key: str, company: str, city: str) -> str:
    if not company:
        return ""
    query = f"{company} {city} kontakt email"
    data = _query_serpapi(api_key, query, start=0, num=10)
    for result in data.get("organic_results", []):
        link = result.get("link", "")
        if link and not _is_job_portal_domain(link):
            return _normalize_url(link)
    return ""


def collect_group(
    api_key: str,
    group_name: str,
    keywords: List[str],
    cities: List[str],
    target_count: int,
    max_requests: int,
    request_sleep_s: float,
    pages_per_query: int,
    num_per_request: int,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    seen = set()
    requests = 0
    city_scope = list(cities)

    for keyword in keywords:
        for city in city_scope:
            if len(rows) >= target_count or requests >= max_requests:
                break

            query_variants = [f"{keyword} {city} {suffix}".strip() for suffix in QUERY_SUFFIXES]
            for query in query_variants:
                if len(rows) >= target_count or requests >= max_requests:
                    break

                for page in range(0, pages_per_query):
                    if len(rows) >= target_count or requests >= max_requests:
                        break

                    start = page * num_per_request
                    data = _query_serpapi(api_key, query, start, num=num_per_request)
                    requests += 1
                    if data.get("error"):
                        logger.warning(
                            "[%s] SerpAPI error for '%s': %s",
                            group_name,
                            query,
                            data.get("error"),
                        )
                        break

                    for local in _iter_local_results(data):
                        row = _extract_local(local, keyword, query, city)
                        key = _record_key(row["Firma"], row["Strona WWW"])
                        if key and key not in seen:
                            seen.add(key)
                            rows.append(row)
                            if len(rows) >= target_count:
                                break

                    if len(rows) < target_count:
                        for organic in data.get("organic_results", []):
                            row = _extract_organic(organic, keyword, query, city)
                            key = _record_key(row["Firma"], row["Strona WWW"])
                            if key and key not in seen:
                                seen.add(key)
                                rows.append(row)
                                if len(rows) >= target_count:
                                    break

                    time.sleep(request_sleep_s)

    logger.info(
        "[%s] zebrano: %s / %s, zapytań: %s",
        group_name,
        len(rows),
        target_count,
        requests,
    )
    return rows[:target_count]


def main() -> None:
    parser = argparse.ArgumentParser(description="Zbieranie firm i agencji przez SerpAPI")
    parser.add_argument(
        "--version",
        action="version",
        version=f"build_contacts_serpapi {pv.PIPELINE_VERSION}",
    )
    parser.add_argument("--firm-target", type=int, default=1000)
    parser.add_argument("--agency-target", type=int, default=1000)
    parser.add_argument("--ecommerce-target", type=int, default=1000)
    parser.add_argument(
        "--cities",
        default="Wroclaw,Zielona Gora,Poznan",
        help="Lista miast rozdzielona przecinkami",
    )
    parser.add_argument("--max-requests-per-group", type=int, default=250)
    parser.add_argument("--pages-per-query", type=int, default=4)
    parser.add_argument("--num-per-request", type=int, default=20)
    parser.add_argument("--sleep", type=float, default=0.25)
    parser.add_argument(
        "--no-discover-websites",
        action="store_true",
        help="Nie wyszukuj osobno oficjalnych stron firm/agencji",
    )
    parser.add_argument(
        "--enrich-email",
        action="store_true",
        help="Probuj pobrac e-mail z witryny firmy przez requests + BeautifulSoup",
    )
    parser.add_argument(
        "--output",
        default=os.path.join(
            os.path.expanduser("~"),
            "Documents",
            f"Kontakty_serpapi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        ),
    )
    args = parser.parse_args()

    if _should_skip_serp_today():
        logger.warning(
            "[SerpAPI] Dzienny limit: zapisano juz uruchomienie na dzis — pomijam zbieranie "
            "(plik stanu: %s). Uzyj istniejacego Excela lub folderu kontakty.",
            _serp_run_state_path(),
        )
        raise SystemExit(2)

    api_key = os.environ.get("SERPAPI_API_KEY", "")
    if not api_key:
        logger.warning(
            "[SerpAPI] Brak SERPAPI_API_KEY — pomijam zbieranie. Pipeline uzyje pliku z outputu "
            "lub najnowszego .xlsx/.xls/.csv z folderu kontakty."
        )
        raise SystemExit(2)

    if GoogleSearch is None:
        logger.warning(
            "[SerpAPI] Brak pakietu google-search-results — pomijam zbieranie "
            "(pip install google-search-results)."
        )
        raise SystemExit(2)
    cities = [c.strip() for c in args.cities.split(",") if c.strip()]
    if not cities:
        cities = DEFAULT_TARGET_CITIES

    firm_rows = collect_group(
        api_key=api_key,
        group_name="firmy",
        keywords=FIRM_KEYWORDS,
        cities=cities,
        target_count=args.firm_target,
        max_requests=args.max_requests_per_group,
        request_sleep_s=args.sleep,
        pages_per_query=args.pages_per_query,
        num_per_request=args.num_per_request,
    )
    agency_rows = collect_group(
        api_key=api_key,
        group_name="agencje",
        keywords=AGENCY_KEYWORDS,
        cities=cities,
        target_count=args.agency_target,
        max_requests=args.max_requests_per_group,
        request_sleep_s=args.sleep,
        pages_per_query=args.pages_per_query,
        num_per_request=args.num_per_request,
    )
    ecommerce_rows = collect_group(
        api_key=api_key,
        group_name="ecommerce",
        keywords=ECOMMERCE_KEYWORDS,
        cities=cities,
        target_count=args.ecommerce_target,
        max_requests=args.max_requests_per_group,
        request_sleep_s=args.sleep,
        pages_per_query=args.pages_per_query,
        num_per_request=args.num_per_request,
    )
    for row in ecommerce_rows:
        row["Branża"] = "Sklep internetowy / e-commerce"
        row["Uwagi"] = (row.get("Uwagi", "") + " | Oferta współpracy B2B").strip(" |")

    all_rows = firm_rows + agency_rows + ecommerce_rows
    if not args.no_discover_websites:
        cache: Dict[str, str] = {}
        for i, row in enumerate(all_rows):
            current = row.get("Strona WWW", "")
            if current and not _is_job_portal_domain(current):
                continue
            key = f"{row.get('Firma','')}|{row.get('Miasto','')}".lower().strip()
            if key in cache:
                row["Strona WWW"] = cache[key]
                continue
            discovered = _find_company_website(
                api_key=api_key,
                company=row.get("Firma", ""),
                city=row.get("Miasto", ""),
            )
            cache[key] = discovered
            row["Strona WWW"] = discovered
            if i % 50 == 0 and i > 0:
                logger.info("Website discovery: %s/%s", i, len(all_rows))
            time.sleep(args.sleep)

    if args.enrich_email:
        for i, row in enumerate(all_rows):
            if row.get("E-mail rekrutacyjny"):
                continue
            site = row.get("Strona WWW", "")
            if not site:
                site = _find_public_contact_page(
                    api_key=api_key,
                    company=row.get("Firma", ""),
                    city=row.get("Miasto", ""),
                )
                row["Strona WWW"] = site
            row["E-mail rekrutacyjny"] = _extract_recruit_email_from_site(site)
            if i % 50 == 0 and i > 0:
                logger.info("Email enrichment: %s/%s", i, len(all_rows))

    df = pd.DataFrame(all_rows)
    for col in MAILER_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[MAILER_COLUMNS]
    df.to_excel(args.output, index=False)
    try:
        from json_data_backup import maybe_backup_dataframe

        maybe_backup_dataframe(df, args.output, reason="serpapi_build")
    except Exception:
        logger.exception("Kopia JSON po zapisie SerpAPI Excel nie powiodła się")

    if _serp_daily_limit_enabled():
        _write_serp_last_run_date(_serp_run_state_path(), datetime.now().date())

    logger.info("Zapisano: %s", args.output)
    logger.info("Łącznie rekordów: %s", len(df))


if __name__ == "__main__":
    main()
