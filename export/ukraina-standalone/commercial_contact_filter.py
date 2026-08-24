# -*- coding: utf-8 -*-
"""
Filtr kontaktów komercyjnych (DE): wyklucza urzędy, samorządy, izby, uczelnie, portale.
Używany w kampanii GU DE Ost — tylko firmy prywatne (GmbH/UG/AG …).
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# Dokładne domeny (organizacje, portale, miasta, branżowe stowarzyszenia)
NON_COMMERCIAL_EMAIL_DOMAINS_EXACT = frozenset(
    {
        "leipzig.de",
        "dresden.de",
        "berlin.de",
        "potsdam.de",
        "cottbus.de",
        "chemnitz.de",
        "erfurt.de",
        "halle.de",
        "magdeburg.de",
        "brandenburg.de",
        "visitberlin.de",
        "thueringen-entdecken.de",
        "forst.thueringen.de",
        "dgnb.de",
        "nexxt-change.org",
        "bfw-bund.de",
        "rewe-group.com",
        "funkemedien.de",
        "th24.de",
        "freiepresse.de",
        "funkemedien",
        "wfs.saxony.de",
        "standort-sachsen.de",
        "firmen.standort-sachsen.de",
        "moerfelden-walldorf.de",
        "senatskanzlei.berlin.de",
        "bund.de",
        "bundestag.de",
        "bmwk.de",
        "bmi.bund.de",
        "arbeitsagentur.de",
        "jobcenter-ge.de",
        "europa.eu",
        "gov.de",
        "ibau.de",
        "tgzp.de",
        "ibau.com",
        "hoerbiger.com",  # portal branżowy
    }
)

# Fragment domeny e-mail / URL (urząd, izba, uczelnia, przetargi …)
NON_COMMERCIAL_DOMAIN_MARKERS = (
    "vergabemarktplatz",
    "vergabe.",
    "ausschreibung",
    "evergabe",
    "stadt.",
    ".stadt.",
    "stadt-",
    "gemeinde.",
    "gemeinde-",
    "landkreis",
    "kreis.",
    "kreis-",
    "kreisfreie",
    "amt.",
    "amt-",
    "finanzamt",
    "ministerium",
    "senatskanzlei",
    "landtag.",
    "regierung.",
    "landesverwaltung",
    "verwaltung.",
    "dezernat",
    "rathaus",
    ".gov.",
    ".gov.de",
    "bund.de",
    "bundes",
    "landesamt",
    "landesbehörde",
    "ordnungsamt",
    "bauaufsicht",
    "ihk.",
    "ihk-",
    "hwk.",
    "hwk-",
    "handwerkskammer",
    "handelskammer",
    "wirtschaftsfoerderung",
    "wirtschaftsförderung",
    "wirtschaftsfoerder",
    "investitionsbank",
    "staatsbetrieb",
    "kommunal",
    "uni-",
    ".uni.",
    "universitaet",
    "universität",
    "hochschule",
    "fh-",
    ".fh.",
    "h-da.de",
    "museum.",
    "bibliothek.",
    "forst.",
    "forstamt",
    "naturschutz",
    "umweltamt",
    "agentur-fuer",
    "agentur für",
    "arbeitsagentur",
    "jobcenter",
    "polizei.",
    "justiz.",
    "gericht.",
    "finanzamt",
    "zoll.de",
    "steuerberaterkammer",  # izba zawodowa
    "architektenkammer",
    "ingenieurkammer",
    "tourismus",
    "entdecken.de",
    "wikipedia.",
    "11880.",
    "gelbeseiten.",
    "firmenabc.",
    "europages.",
    "wlw.de",
    "wer-macht-was",  # branżowy katalog IEK
    "wima-ihk",
    "technologiezentrum",  # Gründerzentrum / instytucja
    "gründerzentrum",
    "gruenderzentrum",
    "technologie-und-gruender",
    "innovationscluster",
    "clusterland",
    "pdf-xchange",
    "tracker-software",
    "ibau.",
    "ibau.de",
    "tgzp.",
    "tgzp.de",
    "gründerzentren",
    "gruenderzentren",
    "bauportal",
    "ausschreibungsportal",
    "tender",
    "evergabe-online",
)

# Nazwa / tytuł Serper (bez formy prawnej = często urząd/instytucja)
NON_COMMERCIAL_NAME_MARKERS = (
    "stadt ",
    "stadt,",
    "gemeinde ",
    "landkreis",
    "kreisverwaltung",
    "kreisfreie stadt",
    "amt ",
    "ministerium",
    "senat ",
    "bezirk ",
    "dezernat",
    "rathaus",
    "verwaltung",
    "behörde",
    "behörde",
    "bundesamt",
    "landesamt",
    "finanzamt",
    "bauaufsicht",
    "ordnungsamt",
    "ihk ",
    "ihk-",
    "handelskammer",
    "handwerkskammer",
    "wirtschaftsförderung",
    "wirtschaftsfoerderung",
    "investitionsbank",
    "technologiezentrum",
    "gründerzentrum",
    "gruenderzentrum",
    "hochschule",
    "universität",
    "universitaet",
    "museum ",
    "bibliothek",
    "vergabemarktplatz",
    "ausschreibung",
    "öffentliche ausschreib",
    "öffentlicher auftrag",
    "staatsbetrieb",
    "kommunalunternehmen",
    "einrichtung der ",
    "anstalt des öffentlichen",
    "körperschaft",
    "landesforst",
    "forst thüringen",
    "forstamt",
    "agentur für",
    "arbeitsagentur",
    "jobcenter",
    "europäische union",
    "europa ",
    "stiftung ",  # często fundacje / publiczne
    "verein ",  # stowarzyszenia branżowe
    "verband ",  # BFW, branżowe związki
    "kammer ",  # izby
    "haus der mitteldeutschen wirtschaft",
    "wirtschaftsstandort",
    "hauptstadtregion",
    "mittelstand jobs",
    "firmendatenbank",
    "katalog",
    "mitgliedsunternehmen",
    "potsdamer technologie",
    "technologie- und gründer",
    "technologie- und gruender",
    "ibau",
    "generalunternehmer",  # sam opis bez GmbH — katalog/portal
    "generalbau",
    "komplexe bauleistungen",
    "gewerbebau",
    "baugewerbe ",
    "kaufangebote",
    "akteure",
    "wer macht was",
    "bei kaufland",
    "bei aldi",
    "penny in ",
    "aldi in ",
    "kaufland in ",
    "neuer penny",
    "neubau-rewe",
    "ratisbona baut",
    "baut markt",
)

_COMMERCIAL_LEGAL_FORM = re.compile(
    r"(?:GmbH|UG(?:\s*\(haftungsbeschränkt\))?|AG|GbR|e\.?\s*K\.?|KG|OHG|PartG|Co\.\s*KG|mbH|SE)\b",
    re.IGNORECASE,
)


def _normalize_host(url_or_email: str) -> str:
    text = (url_or_email or "").strip().lower()
    if "@" in text:
        text = text.split("@", 1)[1]
    if "://" in text:
        try:
            text = (urlparse(text).netloc or "").lower()
        except Exception:
            return ""
    if text.startswith("www."):
        text = text[4:]
    return text.split("/", 1)[0].strip()


def is_non_commercial_email(email: str) -> bool:
    """True = urząd/instytucja — nie zbierać, nie wysyłać."""
    low = (email or "").strip().lower()
    if not low or "@" not in low:
        return True
    _, _, domain = low.partition("@")
    domain = domain.strip()
    if not domain:
        return True
    if domain in NON_COMMERCIAL_EMAIL_DOMAINS_EXACT:
        return True
    if any(marker in domain for marker in NON_COMMERCIAL_DOMAIN_MARKERS):
        return True
    # Podstawowe domeny rządowe / edukacyjne
    if domain.endswith((".gov.de", ".bund.de", ".bund.de", ".edu", ".ac.uk")):
        return True
    if re.search(r"\.(stadt|gemeinde|kreis|landkreis)\.", domain):
        return True
    return False


def is_non_commercial_website(url: str) -> bool:
    host = _normalize_host(url)
    if not host:
        return False
    if host in NON_COMMERCIAL_EMAIL_DOMAINS_EXACT:
        return True
    if any(marker in host for marker in NON_COMMERCIAL_DOMAIN_MARKERS):
        return True
    if host.endswith((".gov.de", ".bund.de")):
        return True
    path_low = (url or "").lower()
    if "/pdfs/" in path_low or path_low.endswith(".pdf"):
        if any(
            x in host
            for x in ("stadt", "gemeinde", "landkreis", "vergabe", "bund", "land.")
        ):
            return True
    return False


def is_non_commercial_name(name: str) -> bool:
    text = " ".join((name or "").split()).strip()
    if not text:
        return False
    low = text.lower()
    if any(marker in low for marker in NON_COMMERCIAL_NAME_MARKERS):
        # „Müller Generalunternehmer GmbH“ = firma; samo „Generalunternehmer“ = tytuł/portál
        if _COMMERCIAL_LEGAL_FORM.search(text) and any(
            m in low for m in ("generalunternehmer", "gewerbebau", "generalbau")
        ):
            name_parts = [p for p in re.split(r"\W+", low) if len(p) >= 2]
            if len(name_parts) >= 3:
                return False
        return True
    # Krótkie nazwy bez formy prawnej często = miasto/portal
    if not _COMMERCIAL_LEGAL_FORM.search(text):
        if len(text.split()) <= 3 and any(
            x in low
            for x in (
                "erfurt",
                "leipzig",
                "potsdam",
                "cottbus",
                "chemnitz",
                "dresden",
                "halle",
                "brandenburg",
                "thüringen",
                "sachsen",
                "berlin",
                "gewerbe",
                "referenz",
                "projekt",
                "mittelstand",
            )
        ):
            return True
    return False


def is_non_commercial_contact(
    *,
    email: str = "",
    url: str = "",
    name: str = "",
) -> bool:
    """True = odrzuć (urząd/instytucja/portale — nie firma komercyjna)."""
    if email and is_non_commercial_email(email):
        return True
    if url and is_non_commercial_website(url):
        return True
    if name and is_non_commercial_name(name):
        return True
    return False


_JUNK_SCRAPED_EMAIL_DOMAIN_MARKERS = (
    "akzeptieren",
    "ablehnen",
    "einstellungen",
    "datenschutzhinweisen",
    "enschutzhinweisen",
    "cookie",
    "gdpr",
    "rocketlazyload",
    "rocket-loader",
    "lazyload",
    "foreach",
    "addednodes",
    "mutation",
    "webpack",
    "stylesheet",
    "javascript",
    "svg+xml",
    "image/svg",
    "w3.org",
    "example.com",
    "sentry.io",
)

_JUNK_SCRAPED_EMAIL_LOCAL_MARKERS = (
    "fonts.gst",
    "element.d",
    "mut",
)


def is_junk_scraped_email(email: str) -> bool:
    """Fałszywe trafienia regex (baner cookies, JS w HTML)."""
    low = (email or "").strip().lower()
    if not low or "@" not in low:
        return True
    if "data:" in low or "svg+xml" in low or "image/" in low:
        return True
    local, _, domain = low.partition("@")
    local, domain = local.strip(), domain.strip()
    if not local or not domain or "." not in domain:
        return True
    if any(m in local for m in _JUNK_SCRAPED_EMAIL_LOCAL_MARKERS):
        return True
    if any(m in domain for m in _JUNK_SCRAPED_EMAIL_DOMAIN_MARKERS):
        return True
    if any(m in low for m in ("@a:", "@a.", ".rocket", ".lazy", "unpkg.com")):
        return True
    tld = domain.rsplit(".", 1)[-1]
    if len(local) > 50:
        return True
    if len(tld) > 50 or not re.match(r"^[a-z0-9\-]{2,50}$", tld):
        return True
    if len(local) <= 2 and (len(tld) > 12 or tld in ("akzeptieren", "ablehnen")):
        return True
    if len(local) == 1 and len(domain) > 24:
        return True
    return False


def filter_commercial_emails(candidates: list[str]) -> list[str]:
    out: list[str] = []
    for raw in candidates or []:
        e = (raw or "").strip().lower()
        if not e or "@" not in e:
            continue
        if is_junk_scraped_email(e):
            continue
        if is_non_commercial_email(e):
            continue
        if e not in out:
            out.append(e)
    return out


def _contact_fields_from_cache(place_url: str, info: dict | None) -> tuple[str, str, str]:
    if not isinstance(info, dict):
        return "", (place_url or "").strip(), ""
    email = (info.get("email_target") or "").strip()
    if not email:
        found = (info.get("emails_found") or "").strip()
        if found:
            email = found.split(",")[0].strip()
    url = (place_url or info.get("official_website") or "").strip()
    name = (
        info.get("company_name_clean")
        or info.get("company_name")
        or info.get("company_name_raw")
        or ""
    ).strip()
    return email, url, name


def is_valid_commercial_company_contact(
    *,
    email: str = "",
    url: str = "",
    name: str = "",
) -> bool:
    """
    True = wyłącznie prywatna firma (Bau/GU z własną domeną lub GmbH/UG/AG w nazwie).
    False = urząd, portal, izba, Gründerzentrum, tytuł projektu bez firmy.
    """
    if is_non_commercial_contact(email=email, url=url, name=name):
        return False
    text = " ".join((name or "").split()).strip()
    if _COMMERCIAL_LEGAL_FORM.search(text):
        return True
    email_low = (email or "").strip().lower()
    if not email_low or "@" not in email_low:
        return False
    if is_non_commercial_email(email_low):
        return False
    edom = email_low.split("@", 1)[1]
    host = _normalize_host(url) or edom
    # Własna domena firmy (mail na tej samej domenie co www)
    if host and (edom == host or host.endswith("." + edom) or edom in host):
        edom_root = edom.split(".")[0]
        if len(edom_root) >= 4:
            return True
    if re.search(r"(?:gmbh|bau|ug|ag|gewerbe)", edom):
        return True
    return False


def is_cache_contact_institution(place_url: str, info: dict | None) -> bool:
    """Czy rekord contacts w JSON należy usunąć (nie jest prywatną firmą)."""
    if not isinstance(info, dict):
        return True
    email, url, name = _contact_fields_from_cache(place_url, info)
    return not is_valid_commercial_company_contact(email=email, url=url, name=name)


def is_cache_serper_entry_institution(entry) -> bool:
    if isinstance(entry, dict):
        url = entry.get("url") or entry.get("link") or ""
        title = entry.get("title") or ""
        return is_non_commercial_contact(url=str(url), name=str(title))
    if isinstance(entry, str):
        return is_non_commercial_website(entry)
    return False
