# -*- coding: utf-8 -*-
"""
Serper API – UA: hurtownie / składy / producenci materiałów budowlanych (GU), którzy stawiają sklepy/markety (Neubau, Filialbau)
lub robią przebudowy/umbau i modernizację filii (Rewe, Aldi, Kaufland, Netto, Penny, Edeka).
Nicht: Einzelhandels-Märkte als Betreiber, keine Urzędy/Portale.
E-mail UA (ukraiński) przez yagmail/Gmail w tym module (send_email_ua_materialy).
Discovery: Serper. www: pełny crawl domeny (requests+BS4) → Claude verify → kontakty z tego samego crawlu (regex/mailto). Przed Excel: Claude cleanup.
Bez Selenium / Google Maps. Baner cookie: Playwright (tylko „Akceptuj”).
Jupyter Lab: komórka 1 = %pip install …, komórka 2 = ten plik, komórka 3 = run_in_jupyter(…).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_campaign = Path(__file__).resolve().parent
CAMPAIGN_DIR = _campaign
_repo = _campaign
for _p in (_campaign / "libs", _campaign):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import kanbud_bootstrap as _kanbud_bootstrap

_kanbud_bootstrap.ensure_import_paths(_campaign)

from campaign_data_paths import campaign_output_paths

_paths = campaign_output_paths(_campaign, "ua_materialy")
_DATA_ROOT = _paths["data_root"]

from scraper_web_config import (
    CLAUDE_UNLIMITED,
    ENABLE_CLAUDE_CONTACT_EXTRACT,
    ENABLE_CLAUDE_DISCOVERY_TERMS,
    ENABLE_CLAUDE_INQUIRY_EMAIL,
    ENABLE_CLAUDE_PAGE_VERIFY,
    ENABLE_CLAUDE_ROW_CLEANUP,
    ENABLE_PLAYWRIGHT_COOKIE_CONSENT,
)

# Kontakte www: regex + mailto; przy braku email_target — Claude na tekście crawla.
from playwright_cookie_consent import apply_playwright_cookie_fallback
from ua_oblast_keywords import (
    DE_OST_PLACE_MARKERS,
    DE_OST_REGION_KEYWORDS,
    DE_OST_RURAL_HINTS,
    LARGE_COMPANY_DOMAINS_EXTRA,
    LARGE_COMPANY_NAME_MARKERS_EXTRA,
    RETAIL_BUILD_KEYWORDS,
    RETAIL_CHAIN_KEYWORDS,
    REQUIRED_RETAIL_CHAIN_KEYWORDS,
    RETAIL_HOCHBAU_CORE_KEYWORDS,
    RETAIL_TRADE_ACTIVITY_KEYWORDS,
    IMPRESSUM_GUESS_PATHS,
    RETAIL_CONTACT_LINK_KEYWORDS,
    GU_ROLE_KEYWORDS,
    RETAIL_REFERENCE_KEYWORDS,
    RETAIL_URL_PRIORITY_KEYWORDS,
    SERPER_DISCOVERY_BROAD_TERMS,
    SERPER_DISCOVERY_LANDKREIS_TERMS,
    SERPER_DISCOVERY_PLACES_TERMS,
    SERPER_DISCOVERY_FALLBACK_TERMS,
    SERPER_DISCOVERY_REGION_SUFFIX,
    SERPER_DISCOVERY_TERMS,
    configure_campaign_bundeslaender,
    DEFAULT_ACTIVE_BUNDESLAENDER,
    CAMPAIGN_ACTIVE_BUNDESLAENDER as _KW_ACTIVE_BL,
    SERPER_NEGATIVE_TERMS,
    SERPER_POSITIVE_TERMS,
    SMALL_COMPANY_DISCOVERY_TERMS_EXTRA,
    SMALL_COMPANY_PAGE_MARKERS_EXTRA,
)

CAMPAIGN_ACTIVE_BUNDESLAENDER = list(_KW_ACTIVE_BL)


def apply_ua_run_config_extras(module, data: dict) -> None:
    """run_config.json: landy, limity, Claude discovery/verify."""
    if data.get("active_bundeslaender"):
        lands = data["active_bundeslaender"]
        if isinstance(lands, str):
            lands = [lands]
        configure_campaign_bundeslaender(module, list(lands))
    if data.get("min_contacts_target") is not None:
        try:
            module.MIN_CONTACTS_TARGET = int(data["min_contacts_target"])
        except (TypeError, ValueError):
            pass
    if "geo_filter_enabled" in data and not bool(data["geo_filter_enabled"]):
        module.ENABLE_REGION_PLZ_FILTER = False
        module.ENABLE_DISTANCE_FROM_REGION_KM = False
        module.ENABLE_PLZ_PREFIX_REGION_MATCH = False
    _bool_keys = (
        "enable_claude_discovery_terms",
        "enable_claude_page_verify",
        "enable_claude_contact_extract",
        "enable_claude_row_cleanup",
        "enable_claude_inquiry_email",
        "require_generalunternehmer",
        "require_market_projects_in_portfolio",
        "require_website_references_or_portfolio",
        "serper_unlimited",
        "claude_unlimited",
    )
    normalized_data = dict(data)
    for key in _bool_keys:
        if key in normalized_data:
            attr = key.upper()
            if hasattr(module, attr):
                setattr(module, attr, bool(normalized_data[key]))
    if "require_generalunternehmer" in data:
        rsf = getattr(module, "_retail_store_builder_filter", None)
        if rsf is not None:
            rsf.REQUIRE_GENERALUNTERNEHMER = bool(data["require_generalunternehmer"])
    if data.get("rotation_start_date"):
        os.environ.setdefault(
            "UA_OBLAST_ROTATION_START",
            str(data["rotation_start_date"]).strip(),
        )
    _int_keys = (
        ("serper_daily_limit", "SERPER_DAILY_LIMIT"),
        ("claude_discovery_max_rounds", "CLAUDE_DISCOVERY_MAX_ROUNDS"),
        ("claude_discovery_terms_per_round", "CLAUDE_DISCOVERY_TERMS_PER_ROUND"),
        ("serper_discovery_reserve", "SERPER_DISCOVERY_RESERVE"),
        ("claude_daily_limit", "CLAUDE_DAILY_LIMIT"),
        ("claude_discovery_reserve", "CLAUDE_DISCOVERY_RESERVE"),
        ("claude_discovery_min_gain", "CLAUDE_DISCOVERY_MIN_GAIN"),
        ("claude_discovery_cache_days", "CLAUDE_DISCOVERY_CACHE_DAYS"),
    )
    for json_key, attr in _int_keys:
        if json_key in normalized_data and hasattr(module, attr):
            try:
                setattr(module, attr, int(normalized_data[json_key]))
            except (TypeError, ValueError):
                pass
    if (
        "claude_daily_limit" in normalized_data
        or "claude_discovery_reserve" in normalized_data
        or "claude_unlimited" in normalized_data
    ):
        from claude_client import configure_claude_limits

        configure_claude_limits(
            daily_limit=normalized_data.get("claude_daily_limit"),
            reserve=normalized_data.get("claude_discovery_reserve"),
            unlimited=normalized_data.get("claude_unlimited"),
        )


import csv
import hashlib
import json
import logging
import math
import random
import re
import subprocess
import time
from datetime import date, datetime, timedelta
from urllib.parse import unquote, urljoin, urlparse

from polish_text import (
    normalize_unicode_text,
    sanitize_email_body,
    sanitize_special_text,
    setup_script_logging,
)
from scraper_env import (
    ENV_GMAIL_APP_PASSWORD,
    ENV_GMAIL_SENDER_NAME,
    ENV_GMAIL_USER,
    get_anthropic_api_key,
    get_env_value,
    get_serper_api_key,
)
from scraper_runtime_limit import (
    SCRAPER_MAX_RUNTIME_SECONDS,
    is_scraper_runtime_limit_reached,
    request_stop_on_runtime_limit,
    start_scraper_runtime_clock,
)
from scraper_email_replies import (
    ReplySyncConfig,
    mark_email_sent,
    merge_export_row,
    write_excel_with_reply_styles,
)
from de_contractor_exclusions import (
    contact_info_excluded,
    is_excluded_kontrahent,
)
from commercial_contact_filter import (
    filter_commercial_emails,
    is_junk_scraped_email,
    is_cache_contact_institution,
    is_cache_serper_entry_institution,
    is_non_commercial_contact,
    is_non_commercial_email,
    is_non_commercial_name,
    is_non_commercial_website,
    is_valid_commercial_company_contact,
)
from contact_extract_utils import normalize_email_contact, normalize_phone_contact
from ua_materialy_supplier_filter import (
    detect_required_retail_chains,
    has_retail_references_or_portfolio,
    has_required_retail_chain_mention,
    portfolio_negates_market_projects,
    is_cache_contact_not_store_builder,
    is_generalunternehmer,
    qualifies_as_gu_for_campaign,
    is_loose_serper_discovery_candidate,
    is_serper_only_pending_candidate,
    is_media_publisher_contact,
    is_retail_store_operator_contact,
    is_valid_retail_store_builder_contact,
    mentions_retail_store_build_activity,
    mentions_retail_store_build_activity_core,
)
import ua_materialy_supplier_filter as _retail_store_builder_filter

# Przy zapisie cache: usuń urzędy/instytucje z contacts (+ serper/LLM powiązane)
ENABLE_CACHE_PURGE_INSTITUTIONS = True
from email_targeting import (
    AGGREGATOR_EMAIL_DOMAINS,
    MIN_EMAIL_SCORE_FOR_SEND,
    get_registrable_domain,
    is_unsuitable_inquiry_email,
    pick_best_email_for_inquiry,
    pick_best_email_from_website_scrape,
    rank_email_candidates,
    score_email_candidate,
)

import requests
from bs4 import BeautifulSoup  # pyright: ignore[reportMissingModuleSource]

# =========================
# KONFIGURATION – UA materiały budowlane (hurtownie / składy)
# =========================
# Wyniki: Google Drive (KANBUD_GOOGLE_DRIVE_GU_PATH) lub folder kampanii — patrz campaign_data_paths.py
OUTPUT_DIR = _paths["output_dir"]
OUTPUT_FILE = _paths["output_file"]
CACHE_FILE = _paths["cache_file"]
LOG_FILE = _paths["log_file"]

# Serper – frazy i słowniki: de_gu_keywords.py (GU Hochbau Einzelhandel)
MIN_CONTACTS_TARGET = 150
MIN_VERIFIED_CONTACTS_ROTATION = 20
DISCOVERY_MIN_PENDING_GHA_FAIL = 5
SERPER_CANDIDATES_TARGET = 80
SERPER_DISCOVERY_EMPTY_CACHE_DAYS = 7
PENDING_WWW_VERIFY_REASON = "pending_www_verify"
CAMPAIGN_TIMEZONE = os.environ.get("SCRAPER_TIMEZONE", "Europe/Warsaw")

# Geo: bundesweit (Filter PLZ/Distanz aus; center nur für Hilfsfunktionen)
REGION_CENTER_LAT = 48.3794
REGION_CENTER_LON = 31.1656
MAX_DISTANCE_FROM_REGION_KM = 9999
# Grobe Bounding-Box Deutschland (optional)
DE_DE_BBOX_LAT_MIN = 47.25
DE_DE_BBOX_LAT_MAX = 55.10
DE_DE_BBOX_LON_MIN = 5.85
DE_DE_BBOX_LON_MAX = 15.05

AUTO_ENRICH_CONTACTS = True
# True: Serper/www nie pomijają URL-i już w contacts JSON — zawsze ponowne wzbogacanie
DISCOVERY_IGNORE_CONTACT_CACHE = True
# True: do Excela także firmy bez e-mail (po www-verify / Filialbau)
EXPORT_PIPELINE_ROWS_WITHOUT_EMAIL = True
STEP_LOG_WITH_TIMESTAMP = True

SERPER_API_URL = "https://google.serper.dev/search"
SERPER_PLACES_API_URL = "https://google.serper.dev/places"
SERPER_COUNTRY = "ua"
SERPER_LANGUAGE = "uk"
SERPER_TIMEOUT = 20
SERPER_DAILY_LIMIT = 1000
_serper_limit_env = (os.environ.get("SERPER_DAILY_LIMIT") or "").strip()
if _serper_limit_env:
    try:
        SERPER_DAILY_LIMIT = int(_serper_limit_env)
    except ValueError:
        pass
# True lub env SERPER_UNLIMITED=1 → brak dziennego limitu
SERPER_UNLIMITED = False
FORCE_SERPER_LOOKUP = True
SERPER_DISCOVERY_RESULTS_PER_TERM = 30
COUNTRY_RESTRICTION = "UA"
ENABLE_REGION_PLZ_FILTER = False
ENABLE_DISTANCE_FROM_REGION_KM = False
ENABLE_PLZ_PREFIX_REGION_MATCH = False
REQUEST_TIMEOUT = 20
MAX_CONTACT_LINKS = 6
# Osobny budżet na Impressum — tam często jest jedyny prawidłowy info@
MAX_IMPRESSUM_GUESS_FETCH = 6
HTTP_RETRY_ATTEMPTS = 3
HTTP_BACKOFF_SECONDS = 1.5
PAGE_SNIPPET_MAX_CHARS = 3500

ENABLE_AUTO_EMAIL = True
# Własny szablon z GUI (Claude dopracowuje per firma); nie dotyczy przypomnień
CUSTOM_EMAIL_DRAFT = ""
USE_CUSTOM_EMAIL_TEMPLATE = False
CUSTOM_EMAIL_LANG = "uk"
CUSTOM_EMAIL_CITY = "Україна"
CUSTOM_EMAIL_CONTEXT: dict = {}
EMAIL_SUBJECT_TEMPLATE = "Запит щодо постачання будівельних матеріалів"
# Obligatorischer Betreff (word-for-word; bez zmian przez LLM)
FIXED_EMAIL_SUBJECT_UK = EMAIL_SUBJECT_TEMPLATE
BACKGROUND_ONLY_DEFAULT = True
DAILY_EMAIL_LIMIT = 300
EMAIL_PER_DOMAIN_DAILY_LIMIT = 2
from scraper_schedule_config import load_send_window_config, is_within_send_window as _schedule_within_send_window

_SEND_WINDOW_CFG = load_send_window_config()
SEND_WINDOW_START_HOUR = _SEND_WINDOW_CFG.start_hour
SEND_WINDOW_END_HOUR = _SEND_WINDOW_CFG.end_hour
SEND_WINDOW_DISABLED = _SEND_WINDOW_CFG.disabled
SUBJECT_VARIANTS = [FIXED_EMAIL_SUBJECT_UK]
PROMPT_VARIANTS = [
    "Офіційний діловий стиль, конкретно і по суті.",
    "Природний B2B-стиль — як лист від менеджера закупівель, без канцеляризмів.",
    "Коротко й професійно, з акцентом на асортимент і оптові умови.",
]
EMAIL_SEND_DELAY_MIN_SECONDS = 22
EMAIL_SEND_DELAY_MAX_SECONDS = 58
EMAIL_SPAMMY_TERMS = [
    "gratis",
    "darmowy",
    "promocja",
    "rabat",
    "pilne",
    "kliknij",
    "super okazja",
    "wyprzedaż",
    "безкоштовно",
    "акція",
    "терміново",
    "клікніть",
    "знижка",
    "kostenlos",
    "sonderangebot",
]
SERPER_BAD_DOMAINS = [
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "gelbeseiten.",
    "11880.com",
    "11880.",
    "wikipedia.org",
    "vergabemarktplatz",
    "stadt.de",
    "gemeinde.",
    "landkreis",
    "ihk.",
    "ihk.de",
    "hwk.",
    "bund.de",
    "visitberlin",
    "thueringen-entdecken",
    "forst.thueringen",
    "standort-sachsen",
    "wirtschaftsfoerderung",
    "senatskanzlei",
    "leipzig.de",
    "dgnb.de",
    "nexxt-change",
    "arbeitsagentur",
    "uni-",
    ".uni.",
    "hochschule",
    "gruenderzentrum",
    "gründerzentrum",
    "ibau.",
    "ibau.de",
    "tgzp.",
    "tgzp.de",
    "shop.rewe",
    "filialfinder",
    "aldi-sued.de",
    "aldi-nord.de",
    "penny.de",
    "kaufland.de",
    "lidl.de",
    "netto-online",
]
# Silne obce TLD — odrzucenie tylko domeny, nie słów w snippetcie Google
_FOREIGN_TLD_SUFFIXES = (
    ".ru",
    ".by",
    ".pl",
    ".de",
    ".ro",
    ".md",
)
# Geo / Serper – de_gu_keywords.py
UA_COUNTRY_HINTS = [
    "україна",
    "ukraine",
    "украина",
    ".ua/",
    "київ",
    "kyiv",
    "львів",
    "lviv",
    "одеса",
    "odesa",
    "харків",
    "kharkiv",
]
DE_EAST_PLZ_PREFIXES = frozenset({
    "01", "02", "03", "04", "06", "07", "08", "09",
    "14", "15", "16", "17", "18", "19",
    "37", "38", "39", "98", "99",
})
SUPPRESSED_EMAIL_LOCALPARTS = {
    "noreply",
    "no-reply",
    "do-not-reply",
    "donotreply",
    "mailer-daemon",
    "postmaster",
}
EXPORT_COLUMNS = [
    "Firmenname",
    "Adresse",
    "Obwód",
    "Telefon",
    "E-Mail",
    "Webseite",
    "Kategorie_materialow",
    "WWW_geprueft",
    "Kleinunternehmen",
]
UA_OBLASTS = [
    "Kyiv", "Kyivska", "Lvivska", "Odeska", "Kharkivska", "Dnipropetrovska",
    "Zaporizka", "Vinnytska", "Poltavska", "Cherkaska", "Zhytomyrska",
    "Rivnenska", "Volyn", "Ternopilska", "Ivano-Frankivska", "Chernivetska",
    "Zakarpatska", "Khmelnytska", "Chernihivska", "Sumska", "Mykolaivska",
    "Kirovohradska", "Khersonska", "Donetska", "Luhanska",
]

# Kontext Anfrage (Referenz im Code; Mailtext = fester Block unten)
INQUIRY_REGION_UA = "Україна"
MATERIAL_CATEGORIES_UA = "цемент, пісок, щебінь, цегла, блок, арматура, утеплювач"
DELIVERY_ADDRESS_UA = "Україна"

# Tylko Generalunternehmer (GU) — nie sam Ladenbau ani ogólne Bauunternehmen
REQUIRE_GENERALUNTERNEHMER = True
_retail_store_builder_filter.REQUIRE_GENERALUNTERNEHMER = REQUIRE_GENERALUNTERNEHMER

# Weryfikacja www: GU/Filialbau + Neubau/Umbau + obowiązkowy dowód projektów marketów
REQUIRE_WEBSITE_RETAIL_VERIFICATION = True
REQUIRE_WEBSITE_REFERENCES_OR_PORTFOLIO = False
REQUIRE_MARKET_PROJECTS_IN_PORTFOLIO = False
# Tylko małe firmy (Kleinunternehmen) — duże koncerny odrzucane
REQUIRE_SMALL_FIRM = False
# Obowiązkowa wzmianka o Aldi, Rewe, Edeka, Lidl, Netto lub Penny na stronie
REQUIRE_NAMED_RETAIL_CHAIN = False
CLAUDE_DISCOVERY_MAX_ROUNDS = 3
CLAUDE_DISCOVERY_TERMS_PER_ROUND = 8
SERPER_DISCOVERY_RESERVE = 333
CLAUDE_DAILY_LIMIT = 3000
CLAUDE_DISCOVERY_RESERVE = 1000
def _env_truthy(raw: str) -> bool:
    return str(raw or "").strip().lower() in ("1", "true", "yes", "tak", "on")


_claude_unlimited_env = (os.environ.get("CLAUDE_UNLIMITED") or "").strip()
if _claude_unlimited_env:
    CLAUDE_UNLIMITED = _env_truthy(_claude_unlimited_env)
_disable_claude_limit_env = (os.environ.get("DISABLE_CLAUDE_DAILY_LIMIT") or "").strip()
if _disable_claude_limit_env and _env_truthy(_disable_claude_limit_env):
    CLAUDE_UNLIMITED = True
_claude_limit_env = (os.environ.get("CLAUDE_DAILY_LIMIT") or "").strip()
if _claude_limit_env:
    try:
        CLAUDE_DAILY_LIMIT = int(_claude_limit_env)
    except ValueError:
        pass
_claude_reserve_env = (os.environ.get("CLAUDE_DISCOVERY_RESERVE") or "").strip()
if _claude_reserve_env:
    try:
        CLAUDE_DISCOVERY_RESERVE = int(_claude_reserve_env)
    except ValueError:
        pass

def _sync_claude_limits_from_module() -> None:
    from claude_client import configure_claude_limits

    configure_claude_limits(
        daily_limit=CLAUDE_DAILY_LIMIT,
        reserve=CLAUDE_DISCOVERY_RESERVE,
        unlimited=CLAUDE_UNLIMITED,
    )


_sync_claude_limits_from_module()
CLAUDE_DISCOVERY_MIN_GAIN = 1
CLAUDE_DISCOVERY_CACHE_DAYS = 7
# Pełny crawl domeny przed Claude (limit w website_full_crawl.MAX_SITE_CRAWL_PAGES)
MAX_PAGES_FOR_RETAIL_VERIFICATION = 8  # legacy — testy / kompatybilność
ENABLE_SERPER_PLACES_ENDPOINT = True
LARGE_COMPANY_DOMAINS = frozenset(
    {
        "strabag.com",
        "hochtief.de",
        "zech-group.com",
        "bilfinger.com",
        "porr-group.com",
        "wolffmueller.de",
        "diringer.de",
        "goldbeck.de",
        "implenia.com",
        "bauholding-strabag",
        "turnerconstruction",
        "skanska.",
        "bouygues",
    }
) | LARGE_COMPANY_DOMAINS_EXTRA
LARGE_COMPANY_NAME_MARKERS = (
    "strabag",
    "hochtief",
    "bilfinger",
    "porr ",
    "porr.",
    "goldbeck",
    "implenia",
    "zech group",
    "zech bau",
    "wolff & müller",
    "wolff und mueller",
    "diringer",
    "konzerngesellschaft",
    "konzern ",
    "ag holding",
    " se ",
    " gmbh & co. kg",  # alone not enough — combined with other signals
    "europäischer marktführer",
    "weltmarktführer",
    *LARGE_COMPANY_NAME_MARKERS_EXTRA,
)
LARGE_COMPANY_PAGE_MARKERS = (
    "weltweit tätig",
    "weltweit",
    "international tätig",
    "konzern",
    "börsennotiert",
    "aktionär",
    "mitarbeiter weltweit",
    "über 1.000 mitarbeiter",
    "über 1000 mitarbeiter",
    "mehr als 500 mitarbeiter",
    "tausend mitarbeiter",
    "global player",
    "tochtergesellschaft der",
)
_STRONG_LARGE_PAGE_MARKERS = (
    "konzern",
    "börsennotiert",
    "weltweit tätig",
    "global player",
    "tochtergesellschaft der",
    "mitarbeiter weltweit",
    "über 1.000 mitarbeiter",
    "über 1000 mitarbeiter",
)
# Faza 4: regionalny GU z podaną liczbą pracowników poniżej progu — nie traktuj jak koncern
REGIONAL_GU_EMPLOYEE_WHITELIST_MAX = 499
_REGIONAL_GU_CONTEXT_MARKERS = (
    "generalunternehmer",
    "filialbau",
    "ladenbau",
    "supermarktbau",
    "einzelhandelsbau",
    "marktbau",
    "handelsbau",
    " gu ",
)
_REGIONAL_GU_REGIONAL_MARKERS = (
    "regional",
    "familienunternehmen",
    "familienbetrieb",
    "inhabergeführt",
    "inhabergefuehrt",
    "meisterbetrieb",
    "mittelständ",
    "mittelstaend",
    "vor ort",
    "kleinunternehmen",
)
_STRONG_KONZERN_OVERRIDE_MARKERS = (
    "konzern",
    "börsennotiert",
    "weltweit tätig",
    "global player",
    "tochtergesellschaft der",
    "mitarbeiter weltweit",
    "europäischer marktführer",
    "weltmarktführer",
)
_EMPLOYEE_COUNT_PATTERNS = (
    re.compile(
        r"(?:über|ueber|mehr als|ca\.?|rund|etwa)\s*(\d{1,4})\s+mitarbeiter",
        re.I,
    ),
    re.compile(r"(\d{1,4})\s+mitarbeiter(?:innen)?\b", re.I),
    re.compile(r"belegschaft\s*(?:von|:)?\s*(\d{1,4})\b", re.I),
)
SMALL_COMPANY_PAGE_MARKERS = (
    "familienunternehmen",
    "familienbetrieb",
    "inhabergeführt",
    "inhabergefuehrt",
    "meisterbetrieb",
    "mittelständ",
    "mittelstaend",
    "regional tätig",
    "regional taetig",
    "vor ort",
    "kleinunternehmen",
    "handwerks",
    *SMALL_COMPANY_PAGE_MARKERS_EXTRA,
)
SMALL_COMPANY_DISCOVERY_TERMS = (
    "mittelstand",
    "familienunternehmen",
    "regional",
    "meisterbetrieb",
    "klein",
    "inhabergeführt",
    *SMALL_COMPANY_DISCOVERY_TERMS_EXTRA,
)


from ua_materialy_inquiry_email_uk import FIXED_MATERIAL_INQUIRY_UK, build_fixed_material_inquiry_uk
ENABLE_EMAIL_ATTACHMENT = False
UA_EMAIL_ALLOW_ATTACHMENTS = False


def _ost_gu_truthy(raw: str) -> bool:
    return str(raw or "").strip().lower() in ("1", "true", "yes", "tak", "on")


def is_serper_unlimited() -> bool:
    """Pełny pipeline: wykorzystaj Serper bez dziennego limitu (env lub run_config)."""
    if SERPER_UNLIMITED:
        return True
    import os

    return _ost_gu_truthy(os.getenv("SERPER_UNLIMITED", "")) or _ost_gu_truthy(
        os.getenv("DISABLE_SERPER_DAILY_LIMIT", "")
    )


def get_email_attachments_ua_materialy(logger: logging.Logger | None = None) -> list[str]:
    """Kampania UA — zawsze bez załączników (tylko treść maila)."""
    _ = logger
    if ENABLE_EMAIL_ATTACHMENT or UA_EMAIL_ALLOW_ATTACHMENTS:
        logger and logger.warning(
            "UA materialy: załączniki wyłączone — ignoruję ENABLE_EMAIL_ATTACHMENT"
        )
    return []


def console_step(message: str) -> None:
    if STEP_LOG_WITH_TIMESTAMP:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] [SCHRITT] {message}", flush=True)
    else:
        print(f"[SCHRITT] {message}", flush=True)


def is_running_in_jupyter() -> bool:
    try:
        from IPython.core.getipython import get_ipython

        shell = get_ipython()
        if shell is None:
            return False
        return shell.__class__.__name__ == "ZMQInteractiveShell"
    except Exception:
        return False


def wait_for_user_confirmation(message: str, jupyter_mode: bool = False) -> None:
    print(message)
    if jupyter_mode:
        print("In Jupyter: Beliebige Eingabe und Enter zum Fortfahren.")
    try:
        input("> ")
    except EOFError:
        print("Kein interaktives stdin. Warte 15 Sekunden und fahre fort.")
        time.sleep(15)


def setup_logging() -> logging.Logger:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return setup_script_logging("ua_materialy_scraper", LOG_FILE)


def save_csv(rows, path: Path) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        "fraza",
        "nazwa",
        "ocena",
        "liczba_opinii",
        "kategoria",
        "adres",
        "full_address",
        "status",
        "telefon",
        "www",
        "url",
        "lat_center",
        "lon_center",
    ]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def build_excel_info_sheet_rows() -> list[dict]:
    """Arkusz Info w Excelu — zasady zapisu (append, nie pełna przebudowa)."""
    return [
        {
            "Temat": "Tryb zapisu Excel",
            "Wartość": (
                "APPEND — pipeline dopisuje nowe firmy i aktualizuje istniejące wiersze "
                "(po www/url). Nie przebudowuje pliku od zera przy każdym uruchomieniu."
            ),
        },
        {
            "Temat": "Start każdego runu",
            "Wartość": (
                "Scraper ładuje istniejący plik Excel (arkusz Kontakte), potem dopisuje "
                "nowe wiersze z discovery / backfill / cache JSON."
            ),
        },
        {
            "Temat": "Czego nie robić ręcznie",
            "Wartość": (
                "Nie kasuj wszystkich wierszy w Kontakte — przy pustym Excelu i pustym "
                "cache pipeline nie odtworzy historii. Edycja pojedynczych wierszy OK."
            ),
        },
        {
            "Temat": "--rebuild-from-cache",
            "Wartość": (
                "Scala wiersze z JSON cache + istniejący Excel (merge po URL). "
                "Gdy contacts=0 w cache — zachowuje dotychczasowe wiersze z Excela."
            ),
        },
        {
            "Temat": "Arkusze",
            "Wartość": "Info (ten arkusz) | Kontakte (firmy) | Wojewodztwa (podsumowanie landów)",
        },
        {
            "Temat": "Cache JSON",
            "Wartość": (
                "Osobny plik de_gu_bauunternehmen_cache.json — kumulacja tygodniowa; "
                "reset cache ≠ kasowanie Excela (chyba że świadomie usuniesz plik .xlsx)."
            ),
        },
    ]


def save_excel(rows, path: Path, logger: logging.Logger, cache=None) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        rows_for_excel = rows
        if (
            logger is not None
            and cache is not None
            and is_row_llm_cleanup_enabled()
        ):
            label = "Claude"
            console_step(
                f"{label}: Bereinigung vor Excel ({len(rows)} Zeilen)…"
            )
            rows_for_excel = [
                enrich_row_with_llm_cleanup(dict(r), logger, cache)
                for r in rows
            ]
        export_rows = build_export_rows(
            rows_for_excel, logger=logger, cache=cache
        )
        state_rows = build_bundesland_rows(rows_for_excel)
        if cache is None:
            cache = {}
        cfg = ReplySyncConfig(
            cache_path=CACHE_FILE,
            xlsx_path=path,
            lang="uk",
            campaign_id="ua_materialy",
        )
        try:
            write_excel_with_reply_styles(
                path,
                {
                    "Info": build_excel_info_sheet_rows(),
                    "Kontakte": export_rows,
                    "Wojewodztwa": state_rows,
                },
                cache,
                cfg,
                logger,
            )
        except PermissionError:
            alt = path.with_name(f"{path.stem}_export{path.suffix}")
            logger.warning(
                "Excel gesperrt (%s) – speichere nach: %s", path, alt
            )
            print(
                f"[EXCEL] Plik otwarty w Excelu — zapisano kopię: {alt}"
            )
            cfg_alt = ReplySyncConfig(
                cache_path=CACHE_FILE,
                xlsx_path=alt,
                lang="uk",
                campaign_id="ua_materialy",
            )
            write_excel_with_reply_styles(
                alt,
                {
                    "Info": build_excel_info_sheet_rows(),
                    "Kontakte": export_rows,
                    "Wojewodztwa": state_rows,
                },
                cache,
                cfg_alt,
                logger,
            )
    except ImportError as e:
        logger.error(
            "pandas/openpyxl fehlen. Installieren: pip install pandas openpyxl"
        )
        raise e


def extract_bundesland(row: dict) -> str:
    explicit = (row.get("bundesland") or "").strip()
    if explicit:
        return explicit
    text = " ".join(
        x for x in [(row.get("full_address") or ""), (row.get("adres") or "")] if x
    ).lower()
    for state in UA_OBLASTS:
        if state.lower() in text:
            return state
    mapping = (
        ("brandenburg", "Brandenburg"),
        ("sachsen-anhalt", "Sachsen-Anhalt"),
        ("sachsen", "Sachsen"),
        ("thüringen", "Thueringen"),
        ("thueringen", "Thueringen"),
    )
    for key, val in mapping:
        if key in text:
            return val
    plz_list = extract_plz_from_text(text)
    if plz_list:
        prefix = plz_list[0][:2]
        plz_state = {
            "01": "Sachsen",
            "02": "Sachsen",
            "03": "Brandenburg",
            "04": "Sachsen",
            "06": "Sachsen-Anhalt",
            "07": "Sachsen",
            "08": "Sachsen",
            "09": "Sachsen",
            "14": "Brandenburg",
            "15": "Brandenburg",
            "16": "Brandenburg",
            "17": "Brandenburg",
            "18": "Brandenburg",
            "19": "Brandenburg",
            "37": "Thueringen",
            "38": "Sachsen-Anhalt",
            "39": "Sachsen-Anhalt",
            "98": "Thueringen",
            "99": "Thueringen",
        }
        if prefix in plz_state:
            return plz_state[prefix]
    return ""


def sanitize_log_url(url: str) -> str:
    if not url:
        return url
    return re.sub(r"key=[^&\s]+", "key=***", url)


def _is_rate_limit_error(err: Exception) -> bool:
    text = str(err).lower()
    if "429" in text or "too many requests" in text or "resource exhausted" in text:
        return True
    status = getattr(getattr(err, "response", None), "status_code", None)
    return status == 429


_SERPER_QUOTA_ERROR_MARKERS = (
    "402",
    "payment required",
    "not enough credit",
    "insufficient credit",
    "no credits",
    "out of credits",
    "credit balance",
    "credits exhausted",
    "quota exceeded",
    "ran out of credits",
)


def _is_serper_quota_error(err: Exception) -> bool:
    """True gdy Serper odrzuca zapytanie z powodu braku kredytów (nie dziennego limitu)."""
    text = str(err).lower()
    if any(m in text for m in _SERPER_QUOTA_ERROR_MARKERS):
        return True
    resp = getattr(err, "response", None)
    if resp is None:
        return False
    status = getattr(resp, "status_code", None)
    if status == 402:
        return True
    try:
        body = resp.json()
        if not isinstance(body, dict):
            return False
        msg = str(body.get("message") or body.get("error") or "").lower()
        if any(x in msg for x in ("credit", "balance", "payment", "quota")):
            return status in (402, 403, 400) or "credit" in msg
    except Exception:
        pass
    return False


def is_serper_api_exhausted(cache: dict | None) -> bool:
    """Kredyty Serper wyczerpane dziś — nie wysyłaj kolejnych zapytań API."""
    if not cache:
        return False
    today = campaign_today()
    flags = cache.get("serper_api_exhausted") or {}
    return bool(flags.get(today))


def mark_serper_api_exhausted(cache: dict, reason: str = "") -> None:
    today = campaign_today()
    cache.setdefault("serper_api_exhausted", {})[today] = (
        reason or "credits_exhausted"
    )[:240]
    mark_serper_limit_reached_today(cache)
    console_step(
        "Serper API: brak kredytów — zatrzymuję discovery, "
        "pipeline przechodzi dalej z zebranymi danymi."
    )


def handle_serper_api_failure(
    cache: dict, err: Exception, logger: logging.Logger
) -> bool:
    """True = wyczerpane kredyty API (nie kontynuuj Serper w tym runie)."""
    if _is_serper_quota_error(err):
        mark_serper_api_exhausted(cache, str(err)[:240])
        logger.warning("Serper API quota exhausted: %s", err)
        return True
    return False


# Faza 6: e.K. / GbR — małe GU bez GmbH (bez fałszywego trafienia e.Kfm.)
_COMPANY_LEGAL_FORM_PATTERN = (
    r"(?:GmbH|UG(?:\s*\(haftungsbeschränkt\))?|AG|"
    r"GbR\.?|"
    r"e\.?\s*K\.(?=\s|$)|"
    r"e\.?\s*K(?=\s|$)|"
    r"KG|OHG|PartG|Co\.\s*KG|mbH|SE|SE\s*&\s*Co\.\s*KG)"
)

# Harte Ablehnung für Excel/LLM-Cleanup — kein Firmenname (PDF, Portale, Städte, SEO, Software …)
_COMPANY_NAME_HARD_REJECT_MARKERS = (
    "[pdf]",
    "pdf]",
    "pdf-",
    "pdf ",
    "pdf.",
    "xchange",
    "pdf-xchange",
    "tracker software",
    "öffentlich nicht",
    "nichtöffentlich",
    "vergabemarktplatz",
    "ausschreibung",
    "vergabe",
    "11880",
    "gelbeseiten",
    "firmenabc",
    "wikipedia",
    "nexxt-change",
    "visitberlin",
    "stadt leipzig",
    "dezernat",
    "senatskanzlei",
    "wirtschaftsförderung",
    "ihk ",
    "handelskammer",
    "top 100",
    "top 10",
    "10 beste",
    "katalog",
    "referenzen ::",
    "referenzen:",
    "gewerbebau",
    "gewerbestandort",
    "gewerbefläch",
    "generalunternehmer",
    "bau von gebäuden",
    "unternehmen in ",
    "unternehmen kaufen",
    "öffentliche ausschreib",
    "mitgliedsunternehmen",
    "akteure",
    "kaufangebote",
    "haus der ",
    "wirtschaftsstandort",
    "hauptstadtregion",
    "mittelstand",
    "jobs bei",
    "stellenangebot",
    "newsletter",
    "presse@",
    "http://",
    "https://",
    ".de/pdfs/",
    "/pdfs/",
    "seite 1 von",
    "anlage 2",
    "auswirkungsanalyse",
    "widget/de",
    "planungsplan",
    "vermarktungsplan",
    "adobe",
    "microsoft",
    "word ",
    "excel ",
)

_COMPANY_NAME_SOFT_REJECT_IF_NO_LEGAL_FORM = (
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
    "aldi in ",
    "penny in ",
    "kaufland in ",
    "rewe markt",
    "neuer penny",
    "neubau-rewe",
    "filiale",
    "markt für",
    "baut markt",
    "investieren in",
    "go-lausitz",
)


def _company_name_has_legal_form(name: str) -> bool:
    return bool(re.search(_COMPANY_LEGAL_FORM_PATTERN, name or "", re.IGNORECASE))


def is_rejected_company_name_for_export(
    name: str, website: str = "", email: str = ""
) -> bool:
    """True = kein gültiger GU-Firmenname für Excel/Outreach."""
    if is_excluded_kontrahent(name=name, url=website, email=email)[0]:
        return True
    text = " ".join((name or "").split()).strip()
    if not text or len(text) < 4:
        return True
    low = text.lower()
    if re.match(r"^[\W\d_]+$", text):
        return True
    if any(m in low for m in _COMPANY_NAME_HARD_REJECT_MARKERS):
        return True
    if (website or "").lower().find("/pdfs/") >= 0 or (website or "").lower().endswith(".pdf"):
        return True
    email_low = (email or "").lower()
    if email_low and any(
        x in email_low
        for x in (
            "pdf-xchange",
            "xchange",
            "vergabe",
            "wfs.saxony",
            "visitberlin",
            "leipzig.de",
            "senatskanzlei",
            "forst.thueringen",
            "funkemedien",
            "th24.de",
            "rewe-group.com",
        )
    ):
        return True
    if not _company_name_has_legal_form(text):
        if any(m in low for m in _COMPANY_NAME_SOFT_REJECT_IF_NO_LEGAL_FORM):
            return True
        if len(text.split()) <= 2 and not re.search(r"[&\.\-]", text):
            return True
    if text.count(":") >= 2 or text.startswith("["):
        return True
    return False


def finalize_company_name_for_export(
    llm_name: str,
    *,
    fallback_raw: str,
    website: str = "",
    email: str = "",
) -> str:
    """Nach LLM-Cleanup: nur Name+Rechtsform, sonst Impressum/Domain-Fallback."""
    website = website_base_url(website) if website else ""
    candidates: list[str] = []
    if should_prefer_domain_company_name(fallback_raw, website):
        candidates.append(derive_name_from_website(website))
    candidates.extend(
        (
            sanitize_special_text(llm_name or ""),
            clean_company_name(fallback_raw, website),
            derive_name_from_website(website),
        )
    )
    for candidate in candidates:
        name = " ".join((candidate or "").split()).strip(" :|–—")
        if not name or is_rejected_company_name_for_export(name, website, email):
            continue
        if _company_name_has_legal_form(name):
            return name
    return ""


def build_claude_row_cleanup_prompt(
    *,
    company: str,
    address: str,
    phone: str,
    email: str,
    website: str,
    states: str,
    handelsketten: str = "",
    url: str = "",
) -> str:
    from ua_claude_prompts import build_row_cleanup_prompt

    return build_row_cleanup_prompt(
        company=company,
        address=address,
        phone=phone,
        email=email,
        website=website,
        states=states,
        handelsketten=handelsketten,
        url=url,
    )


def row_cleanup_fallback(
    row: dict, company: str, address: str, phone: str, email: str, website: str
) -> dict:
    bundesland = extract_bundesland(row)
    return {
        "company_name_clean": company,
        "address": address,
        "phone": phone,
        "email": email,
        "website": website,
        "bundesland": bundesland,
        "_fallback": True,
    }


def apply_row_enrichment_to_row(row: dict, llm_result: dict) -> None:
    """LLM czyści nazwę/adres/telefon — e-mail zostaje z pick_best kontaktów."""
    company = llm_result.get("company_name_clean") or row.get("nazwa") or ""
    row["company_name_clean"] = company
    row["nazwa"] = company
    row["adres"] = llm_result.get("address", row.get("adres", ""))
    row["full_address"] = row["adres"]
    row["telefon"] = llm_result.get("phone", row.get("telefon", ""))
    website = llm_result.get("website", row.get("official_website", ""))
    row["official_website"] = website
    row["www"] = normalize_website(website) or row.get("www", "")
    row["bundesland"] = llm_result.get("bundesland", row.get("bundesland", ""))
    if llm_result.get("handelsketten"):
        row["retail_chains_found"] = format_handelsketten_for_excel(
            llm_result.get("handelsketten")
        )
    if llm_result.get("url"):
        row["url"] = website_base_url(llm_result.get("url")) or row.get("url", "")


def format_handelsketten_for_excel(raw: str) -> str:
    parts: list[str] = []
    for item in re.split(r"[,;/|]+", raw or ""):
        chain = item.strip().lower()
        if chain and chain not in parts:
            parts.append(chain)
    return ", ".join(parts)


def finalize_row_for_excel_tables(row: dict) -> dict:
    """Po Claude + regex: spójne pola pod arkusze Kontakte i Wojewodztwa."""
    website = normalize_website(
        (row.get("official_website") or row.get("www") or "").strip()
    )
    if website:
        row["official_website"] = website
        row["www"] = website
    url = website_base_url((row.get("url") or website or "").strip())
    if url:
        row["url"] = url
    row["adres"] = sanitize_special_text(row.get("adres") or row.get("full_address") or "")
    row["full_address"] = row["adres"]
    phone = (row.get("telefon") or "").strip()
    if "," in phone:
        phone = phone.split(",", 1)[0].strip()
    norm_phone = _normalize_href_phone(phone)
    row["telefon"] = norm_phone or phone
    row["retail_chains_found"] = format_handelsketten_for_excel(
        row.get("retail_chains_found") or ""
    )
    if row.get("bundesland") not in UA_OBLASTS:
        row["bundesland"] = extract_bundesland(row)
    return row


def row_to_excel_kontakte_columns(row: dict, email: str = "") -> dict:
    """Mapuje wiersz pipeline na kolumny arkusza Kontakte."""
    row = finalize_row_for_excel_tables(dict(row))
    mail = (email or row.get("email_target") or "").strip()
    website = (row.get("official_website") or row.get("www") or "").strip()
    return {
        "Nazwa firmy": (row.get("company_name_clean") or row.get("nazwa") or "").strip(),
        "Adres": (row.get("adres") or row.get("full_address") or "").strip(),
        "Obwód": (row.get("bundesland") or row.get("discovery_bundesland") or "").strip(),
        "Telefon": (row.get("telefon") or "").strip(),
        "E-mail": mail,
        "Strona www": website,
        "URL": (row.get("url") or website_base_url(website) or "").strip(),
        "Kategorie_materialow": (row.get("retail_chains_found") or "").strip(),
    }


def row_to_excel_wojewodztwa_columns(row: dict) -> dict:
    """Mapuje wiersz pipeline na kolumny arkusza Wojewodztwa."""
    row = finalize_row_for_excel_tables(dict(row))
    return {
        "Nazwa firmy": (row.get("company_name_clean") or row.get("nazwa") or "").strip(),
        "Obwód": (row.get("bundesland") or row.get("discovery_bundesland") or "").strip(),
        "Adres": (row.get("adres") or row.get("full_address") or "").strip(),
        "Strona www": (row.get("official_website") or row.get("www") or "").strip(),
        "URL": (row.get("url") or "").strip(),
    }


def is_row_llm_cleanup_enabled() -> bool:
    return bool(ENABLE_CLAUDE_ROW_CLEANUP)


def enrich_row_with_llm_cleanup(
    row: dict, logger: logging.Logger, cache: dict
) -> dict:
    return enrich_row_with_claude_cleanup(row, logger, cache)


def enrich_row_with_claude_cleanup(row: dict, logger: logging.Logger, cache: dict) -> dict:
    claude_cache = cache.setdefault("claude_row_enrichment", {})
    cache_key = (
        (row.get("url") or "").strip()
        or f"{(row.get('nazwa') or '').strip()}|{(row.get('www') or '').strip()}"
    )
    address = sanitize_special_text(row.get("full_address") or row.get("adres") or "")
    phone = sanitize_special_text(row.get("phones_found") or row.get("telefon") or "")
    email = (row.get("email_target") or "").strip()
    website = sanitize_special_text(row.get("official_website") or row.get("www") or "")
    company = sanitize_special_text(
        row.get("company_name_clean") or row.get("nazwa") or row.get("company_name_raw") or ""
    )
    if cache_key and cache_key in claude_cache:
        apply_row_enrichment_to_row(row, claude_cache[cache_key])
        row = apply_regex_row_contact_cleanup(row)
        return finalize_row_for_excel_tables(row)
    if cache_key and cache_key in (cache.get("gemini_row_enrichment") or {}):
        legacy = (cache.get("gemini_row_enrichment") or {}).get(cache_key)
        if isinstance(legacy, dict):
            claude_cache[cache_key] = dict(legacy)
            apply_row_enrichment_to_row(row, claude_cache[cache_key])
        row = apply_regex_row_contact_cleanup(row)
        return finalize_row_for_excel_tables(row)

    row["company_name_clean"] = company
    row["nazwa"] = company
    row["adres"] = address
    row["telefon"] = phone
    row["official_website"] = website

    if not ENABLE_CLAUDE_ROW_CLEANUP:
        row["bundesland"] = extract_bundesland(row)
        row = apply_regex_row_contact_cleanup(row)
        return finalize_row_for_excel_tables(row)

    api_key = get_anthropic_api_key()
    from claude_row_cleanup import claude_cleanup_row_fields

    if not api_key:
        fallback = row_cleanup_fallback(row, company, address, phone, email, website)
        apply_row_enrichment_to_row(row, fallback)
        if cache_key:
            claude_cache[cache_key] = fallback
        row = apply_regex_row_contact_cleanup(row)
        return finalize_row_for_excel_tables(row)

    states = ", ".join(UA_OBLASTS)
    prompt = build_claude_row_cleanup_prompt(
        company=company,
        address=address,
        phone=phone,
        email=email,
        website=website,
        states=states,
        handelsketten=(row.get("retail_chains_found") or "").strip(),
        url=(row.get("url") or website or "").strip(),
    )
    parsed = claude_cleanup_row_fields(prompt, logger, cache)
    if not parsed:
        fallback = row_cleanup_fallback(row, company, address, phone, email, website)
        apply_row_enrichment_to_row(row, fallback)
        if cache_key:
            claude_cache[cache_key] = fallback
        row = apply_regex_row_contact_cleanup(row)
        return finalize_row_for_excel_tables(row)

    cleaned_name = finalize_company_name_for_export(
        parsed.get("company_name_clean", ""),
        fallback_raw=company,
        website=website,
        email=email,
    )
    claude_result = {
        "company_name_clean": cleaned_name,
        "address": sanitize_special_text(parsed.get("address", address)) or address,
        "phone": sanitize_special_text(parsed.get("phone", phone)) or phone,
        "website": sanitize_special_text(parsed.get("website", website)) or website,
        "bundesland": sanitize_special_text(parsed.get("bundesland", "")),
        "handelsketten": format_handelsketten_for_excel(
            parsed.get("handelsketten") or row.get("retail_chains_found") or ""
        ),
        "url": sanitize_special_text(parsed.get("url", row.get("url") or website)),
    }
    if claude_result["bundesland"] not in UA_OBLASTS:
        claude_result["bundesland"] = extract_bundesland(row)
    apply_row_enrichment_to_row(row, claude_result)
    if cache_key:
        claude_cache[cache_key] = claude_result
    row = apply_regex_row_contact_cleanup(row)
    return finalize_row_for_excel_tables(row)


def _contact_context_text(row: dict) -> str:
    return " ".join(
        str(row.get(k) or "")
        for k in (
            "verification_reason",
            "page_snippet",
            "retail_chains_found",
            "kategoria",
            "nazwa",
        )
    )


def _row_has_gu_signal(row: dict) -> bool:
    text = _contact_context_text(row)
    ok, _ = qualifies_as_gu_for_campaign(text)
    return ok


def _excel_status_label(row: dict) -> str:
    status = (row.get("email_status") or "").strip()
    if status:
        return status
    if (row.get("verification_reason") or "").strip() == PENDING_WWW_VERIFY_REASON:
        return "pending_www_verify"
    return ""


def _row_chain_context_text(row: dict) -> str:
    return " ".join(
        [
            _contact_context_text(row),
            str(row.get("retail_chains_found") or ""),
            str(row.get("page_snippet") or ""),
        ]
    )


def _row_passes_strict_retail_filters(row: dict) -> bool:
    """Zweryfikowany kontakt: mała firma GU + wymagana sieć handlowa."""
    if REQUIRE_SMALL_FIRM and not row.get("is_small_firm"):
        return False
    if REQUIRE_NAMED_RETAIL_CHAIN and not has_required_retail_chain_mention(
        _row_chain_context_text(row)
    ):
        return False
    if REQUIRE_GENERALUNTERNEHMER and not (
        row.get("is_gu") or _row_has_gu_signal(row)
    ):
        return False
    return True


def is_row_eligible_for_excel_export(row: dict) -> bool:
    """Firma do arkusza Kontakte — mały GU z referencją marketu (Aldi/Rewe/…)."""
    name = (row.get("company_name_clean") or row.get("nazwa") or "").strip()
    url = (row.get("url") or row.get("www") or row.get("official_website") or "").strip()
    if name.lower() == "nieznana firma" and not url:
        return False
    email = (row.get("email_target") or "").strip()
    text = _row_chain_context_text(row)
    if is_excluded_kontrahent(name=name, url=url, email=email)[0]:
        return False
    if is_non_commercial_contact(email=email, url=url, name=name):
        return False
    if is_retail_store_operator_contact(url=url, email=email, text=text):
        return False
    if (row.get("verification_reason") or "").strip() == PENDING_WWW_VERIFY_REASON:
        if not (url and name):
            return False
        return is_serper_only_pending_candidate(
            email=email, url=url, name=name, text=text
        )
    if row.get("retail_verified"):
        return _row_passes_strict_retail_filters(row)
    if email:
        return not is_blocked_non_commercial_row(row)
    if not EXPORT_PIPELINE_ROWS_WITHOUT_EMAIL:
        return False
    if not is_valid_retail_store_builder_contact(
        email="", url=url, name=name, text=text
    ):
        return False
    if REQUIRE_GENERALUNTERNEHMER and not _row_has_gu_signal(row):
        return False
    return False


def build_export_rows(rows, logger=None, cache=None):
    export_rows = []
    for row in rows:
        row = normalize_row_company_name(row)
        if not is_row_eligible_for_excel_export(row):
            continue
        email = (row.get("email_target") or "").strip()
        if not email:
            found_list = [
                x.strip()
                for x in (row.get("emails_found") or "").split(",")
                if x.strip() and "@" in x
            ]
            if found_list:
                email, _ = pick_best_email_for_inquiry(
                    found_list,
                    row.get("official_website") or row.get("www") or "",
                )
        if not is_row_llm_cleanup_enabled():
            row["adres"] = sanitize_special_text(
                row.get("full_address") or row.get("adres") or ""
            )
            row["telefon"] = sanitize_special_text(
                row.get("phones_found") or row.get("telefon") or ""
            )
            row["bundesland"] = extract_bundesland(row)
            table_cols = row_to_excel_kontakte_columns(row, email)
        else:
            table_cols = row_to_excel_kontakte_columns(row, email)
        base = {
            **table_cols,
            "WWW_geprueft": "ja" if row.get("retail_verified") else "nein",
            "Kleinunternehmen": "ja" if row.get("is_small_firm") else "nein",
            "GU": "ja" if row.get("is_gu") or _row_has_gu_signal(row) else "nein",
            "GU_Marker": (row.get("gu_marker") or "").strip(),
            "Status": _excel_status_label(row),
        }
        if cache is not None and email:
            base = merge_export_row(base, cache, email, lang="uk")
        export_rows.append(base)
    if logger is not None:
        with_mail = sum(1 for r in export_rows if (r.get("E-mail") or "").strip())
        logger.info(
            "Excel Kontakte: %s wierszy (%s z e-mailem, %s bez) z %s w pipeline",
            len(export_rows),
            with_mail,
            len(export_rows) - with_mail,
            len(rows),
        )
    return export_rows


def build_bundesland_rows(rows):
    state_rows = []
    seen = set()
    for row in rows:
        row = normalize_row_company_name(row)
        table = row_to_excel_wojewodztwa_columns(row)
        row_name = (table.get("Nazwa firmy") or "").strip()
        row_url = (table.get("URL") or "").strip()
        if row_name.lower() == "nieznana firma" and not row_url:
            continue
        row_state = (table.get("Obwód") or "").strip()
        row_address = (table.get("Adres") or "").strip()
        dedupe_key = row_url or f"{row_name}|{row_state}|{row_address}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        state_rows.append(table)
    return state_rows


def persist_progress(all_rows, cache, logger: logging.Logger, reason: str = "") -> None:
    if reason:
        console_step(f"Zwischenstand speichern: {reason}")
    else:
        console_step("Zwischenstand speichern")
    save_excel(all_rows, OUTPUT_FILE, logger, cache=cache)
    save_cache(cache, logger)


EXCEL_IMPORT_COLUMNS = {
    "Nazwa firmy": "nazwa",
    "Adres": "adres",
    "Obwód": "bundesland",
    "Oblast": "bundesland",
    "Telefon": "telefon",
    "E-mail": "email_target",
    "Strona www": "www",
    "URL": "url",
    "GU_Marker": "gu_marker",
    "Status": "email_status",
}


def row_from_excel_record(rec: dict) -> dict:
    """Mapuje polskie nagłówki z Excela na pola wewnętrzne scrapera."""
    row: dict = {}
    for col_pl, field in EXCEL_IMPORT_COLUMNS.items():
        for key in (col_pl, field):
            val = rec.get(key)
            if val is not None and str(val).strip():
                row[field] = normalize_unicode_text(val)
                break
    name = (row.get("nazwa") or "").strip()
    if name:
        row["company_name_raw"] = name
        row["company_name_clean"] = name
    if row.get("adres"):
        row["full_address"] = row["adres"]
    if row.get("telefon"):
        row["phones_found"] = row["telefon"]
    if row.get("www"):
        row["official_website"] = row["www"]
    www_checked = str(rec.get("WWW_geprueft") or "").strip().lower()
    if www_checked == "ja":
        row["retail_verified"] = True
    elif www_checked == "nein":
        row["retail_verified"] = False
        if not (row.get("email_target") or "").strip():
            row["verification_reason"] = PENDING_WWW_VERIFY_REASON
            row["email_status"] = "pending_www_verify"
    gu_col = str(rec.get("GU") or "").strip().lower()
    if gu_col == "ja":
        row["is_gu"] = True
    elif gu_col == "nein":
        row["is_gu"] = False
    small_col = str(rec.get("Kleinunternehmen") or "").strip().lower()
    if small_col == "ja":
        row["is_small_firm"] = True
    elif small_col == "nein":
        row["is_small_firm"] = False
    chains = str(rec.get("Kategorie_materialow") or "").strip()
    if chains:
        row["retail_chains_found"] = chains
    return row


def load_existing_csv(path: Path, logger: logging.Logger):
    rows = []
    seen_urls = set()
    if not path.exists():
        return rows, seen_urls
    logger.info(f"Lade CSV: {path}")
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for r in reader:
            rows.append(r)
            if "url" in r and r["url"]:
                seen_urls.add(r["url"])
    logger.info(f"CSV geladen: {len(rows)} Zeilen, URLs={len(seen_urls)}")
    return rows, seen_urls


def load_existing_output(path: Path, logger: logging.Logger):
    if path.suffix.lower() != ".xlsx":
        return load_existing_csv(path, logger)
    rows = []
    seen_urls = set()
    if not path.exists():
        return rows, seen_urls
    logger.info(f"Lade XLSX: {path}")
    try:
        import pandas as pd  # pyright: ignore[reportMissingImports]

        try:
            df = pd.read_excel(path, sheet_name="Kontakte")
        except Exception:
            df = pd.read_excel(path)
        raw_records = df.fillna("").to_dict(orient="records")
        rows = []
        for rec in raw_records:
            row = row_from_excel_record(rec)
            if not row:
                continue
            name = (row.get("nazwa") or row.get("company_name_clean") or "").strip()
            if name.lower() == "nieznana firma" and not row.get("url"):
                continue
            rows.append(row)
            url = (row.get("url") or "").strip()
            if url:
                seen_urls.add(url)
        logger.info(f"XLSX geladen: {len(rows)} Zeilen, URLs={len(seen_urls)}")
    except Exception as e:
        logger.warning(f"XLSX-Ladefehler ({e}) – starte leer.")
    return rows, seen_urls


def _empty_cache() -> dict:
    return {
        "places": {},
        "contacts": {},
        "serper": {},
        "serper_daily": {},
        "email_daily": {},
        "email_sent_targets": {},
        "email_domain_daily": {},
        "email_suppression": {},
        "claude_row_enrichment": {},
        "claude_contact_extract": {},
        "claude_disabled_models": {},
        "serper_discovery": {},
        "serper_term_stats": {},
        "serper_limit_reached": {},
        "serper_api_exhausted": {},
        "claude_discovery_terms": {},
        "claude_page_verify": {},
        "website_crawl": {},
    }


def _prepare_cache_for_json(cache: dict) -> dict:
    """Konwersja WebsiteCrawlResult → dict przed json.dump."""
    from website_full_crawl import WebsiteCrawlResult, website_crawl_result_to_dict

    payload = dict(cache)
    wc = payload.get("website_crawl")
    if isinstance(wc, dict):
        payload["website_crawl"] = {
            site: (
                website_crawl_result_to_dict(val)
                if isinstance(val, WebsiteCrawlResult)
                else val
            )
            for site, val in wc.items()
        }
    return payload


def _hydrate_website_crawl_cache(cache: dict) -> None:
    """Po json.load: dict → WebsiteCrawlResult w website_crawl."""
    from website_full_crawl import WebsiteCrawlResult, website_crawl_result_from_dict

    wc = cache.get("website_crawl")
    if not isinstance(wc, dict):
        cache["website_crawl"] = {}
        return
    for site, val in list(wc.items()):
        if isinstance(val, WebsiteCrawlResult):
            continue
        if isinstance(val, dict) and "pages" in val:
            wc[site] = website_crawl_result_from_dict(val)


def reset_pipeline_cache() -> dict:
    """Pełny reset cache JSON (Serper, kontakty, Claude, maile)."""
    return _empty_cache()


def build_discovery_seen_urls(all_rows: list[dict], cache: dict) -> set[str]:
    """URL-e już w pipeline (Excel/wiersze). Opcjonalnie + contacts z JSON."""
    seen = {str(r.get("url") or "").strip() for r in all_rows if (r.get("url") or "").strip()}
    if not DISCOVERY_IGNORE_CONTACT_CACHE:
        for u in (cache.get("contacts") or {}):
            if u:
                seen.add(str(u).strip())
    return seen


def index_all_rows_by_url(all_rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in all_rows:
        url = str(row.get("url") or "").strip()
        if url:
            out[url] = row
    return out


def index_all_rows_by_domain(all_rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in all_rows:
        dom = get_registrable_domain(
            str(row.get("url") or row.get("www") or row.get("official_website") or "")
        )
        if dom and dom not in out:
            out[dom] = row
    return out


def row_from_cache_contact(place_url: str, info: dict) -> dict | None:
    """Jeden rekord contacts JSON → wiersz pipeline (także bez e-mail)."""
    if not isinstance(info, dict):
        return None
    name = (
        info.get("company_name_clean")
        or info.get("company_name")
        or info.get("company_name_raw")
        or ""
    ).strip()
    email = (info.get("email_target") or "").strip()
    row_probe = {
        "url": place_url,
        "www": info.get("official_website") or place_url,
        "official_website": info.get("official_website") or place_url,
        "nazwa": name,
        "company_name_clean": name,
        "email_target": email,
        "emails_found": info.get("emails_found") or "",
        "retail_verified": info.get("retail_verified", False),
        "verification_reason": info.get("verification_reason") or "",
        "page_snippet": info.get("page_snippet") or "",
        "retail_chains_found": info.get("retail_chains_found") or "",
        "is_gu": info.get("is_gu", False),
        "gu_marker": info.get("gu_marker") or "",
    }
    pending_www = (
        (info.get("verification_reason") or "").strip() == PENDING_WWW_VERIFY_REASON
        and not info.get("retail_verified")
    )
    if not pending_www and not is_row_eligible_for_excel_export(row_probe):
        return None
    phone = (info.get("phones_found") or "").strip()
    if "," in phone:
        phone = phone.split(",", 1)[0].strip()
    return normalize_row_company_name(
        {
            **row_probe,
            "company_name_raw": info.get("company_name_raw") or name,
            "full_address": info.get("full_address") or "",
            "adres": info.get("full_address") or "",
            "telefon": phone,
            "phones_found": info.get("phones_found") or phone,
            "bundesland": info.get("bundesland") or "",
            "email_status": (info.get("email_status") or "").strip(),
            "contact_sources": info.get("contact_sources") or "",
            "is_small_firm": info.get("is_small_firm", True),
            "contact_quality_score": int(info.get("contact_quality_score", 0) or 0),
        }
    )


def merge_pipeline_rows(existing: list[dict], incoming: list[dict]) -> list[dict]:
    """Łączy wiersze pipeline po URL (incoming nadpisuje pola istniejących)."""
    by_url = index_all_rows_by_url(list(existing))
    merged = list(existing)
    for row in incoming:
        url = (row.get("url") or "").strip()
        if not url:
            continue
        if url in by_url:
            by_url[url].update(row)
        else:
            merged.append(row)
            by_url[url] = row
    return merged


def build_all_rows_from_cache(cache: dict) -> list[dict]:
    """Rekonstruiert Pipeline-Zeilen aus contacts (mit und ohne E-Mail)."""
    rows: list[dict] = []
    for place_url, info in (cache.get("contacts") or {}).items():
        row = row_from_cache_contact(place_url, info)
        if row:
            rows.append(row)
    return rows


def merge_cache_contacts_into_pipeline(all_rows: list[dict], cache: dict) -> int:
    """Dopisuje/aktualizuje w pipeline wszystkie contacts z JSON (także bez maila)."""
    by_url = index_all_rows_by_url(all_rows)
    added = 0
    for place_url, info in (cache.get("contacts") or {}).items():
        row = row_from_cache_contact(place_url, info)
        if not row:
            continue
        url = row.get("url") or place_url
        if url in by_url:
            by_url[url].update(row)
        else:
            all_rows.append(row)
            by_url[url] = row
            added += 1
    return added


def load_cache(logger: logging.Logger) -> dict:
    if not CACHE_FILE.exists():
        logger.info("Kein Cache JSON – neuer Start.")
        return _empty_cache()
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        for k in (
            "places",
            "contacts",
            "serper",
            "serper_daily",
            "email_daily",
            "email_sent_targets",
            "email_domain_daily",
            "email_suppression",
            "claude_row_enrichment",
            "claude_disabled_models",
            "claude_contact_extract",
            "claude_discovery_terms",
            "claude_page_verify",
            "website_crawl",
        ):
            if k not in cache:
                cache[k] = {}
        _hydrate_website_crawl_cache(cache)
        # Legacy migration (read-only fallback buckets from Gemini naming).
        if (
            not cache.get("claude_row_enrichment")
            and isinstance(cache.get("gemini_row_enrichment"), dict)
        ):
            cache["claude_row_enrichment"] = dict(cache.get("gemini_row_enrichment") or {})
        if (
            not cache.get("claude_contact_extract")
            and isinstance(cache.get("gemini_contact_extract"), dict)
        ):
            cache["claude_contact_extract"] = dict(cache.get("gemini_contact_extract") or {})
        if (
            not cache.get("claude_discovery_terms")
            and isinstance(cache.get("gemini_discovery_terms"), dict)
        ):
            cache["claude_discovery_terms"] = dict(cache.get("gemini_discovery_terms") or {})
        if (
            not cache.get("claude_page_verify")
            and isinstance(cache.get("gemini_page_verify"), dict)
        ):
            cache["claude_page_verify"] = dict(cache.get("gemini_page_verify") or {})
        logger.info(
            "Cache geladen: places=%s, contacts=%s",
            len(cache.get("places", {})),
            len(cache.get("contacts", {})),
        )
        if ENABLE_CACHE_PURGE_INSTITUTIONS:
            removed = purge_institutions_from_cache(cache, logger)
            if removed:
                save_cache(cache, logger)
        return cache
    except Exception as e:
        logger.warning(f"Cache-Ladefehler ({e}) – neuer Cache.")
        return _empty_cache()


def purge_institutions_from_cache(
    cache: dict, logger: logging.Logger | None = None
) -> int:
    """
    Usuwa z cache JSON wpisy urzędów/instytucji (contacts, serper, enrichment).
    Zwraca liczbę usuniętyych rekordów contacts.
    """
    contacts = cache.setdefault("contacts", {})
    if not isinstance(contacts, dict):
        cache["contacts"] = {}
        contacts = cache["contacts"]
    removed_urls: list[str] = []
    removed_emails: set[str] = set()
    for place_url in list(contacts.keys()):
        info = contacts.get(place_url)
        if (
            contact_info_excluded(info, place_url)
            or is_cache_contact_institution(place_url, info)
            or is_cache_contact_not_store_builder(place_url, info)
        ):
            removed_urls.append(place_url)
            if isinstance(info, dict):
                et = (info.get("email_target") or "").strip().lower()
                if et:
                    removed_emails.add(et)
                for part in (info.get("emails_found") or "").split(","):
                    p = part.strip().lower()
                    if p and "@" in p:
                        removed_emails.add(p)
            contacts.pop(place_url, None)

    serper = cache.get("serper") or {}
    if isinstance(serper, dict):
        for key in list(serper.keys()):
            if is_cache_serper_entry_institution(serper.get(key)):
                serper.pop(key, None)

    for url in removed_urls:
        for bucket in (
            "claude_row_enrichment",
            "claude_contact_extract",
            "gemini_row_enrichment",
            "gemini_contact_extract",
        ):
            sub = cache.get(bucket)
            if not isinstance(sub, dict):
                continue
            for key in list(sub.keys()):
                if url in key or key in url:
                    sub.pop(key, None)
        # Stare kopie enrichment po URL jako klucz
        row_enrich = cache.get("claude_row_enrichment") or cache.get("gemini_row_enrichment")
        if isinstance(row_enrich, dict):
            row_enrich.pop(url, None)

    suppression = cache.get("email_suppression") or {}
    if isinstance(suppression, dict):
        for email in list(suppression.keys()):
            if is_non_commercial_email(email) or email in removed_emails:
                suppression.pop(email, None)
    sent_targets = cache.get("email_sent_targets") or {}
    if isinstance(sent_targets, dict):
        for day in list(sent_targets.keys()):
            targets = sent_targets.get(day)
            if not isinstance(targets, list):
                continue
            sent_targets[day] = [
                t for t in targets if (t or "").lower() not in removed_emails
            ]

    if logger and removed_urls:
        logger.info(
            "Cache: usunięto %s wpisów (urzędy / nie budują sklepów) z contacts (pozostało %s)",
            len(removed_urls),
            len(contacts),
        )
        print(
            f"[CACHE] Usunięto {len(removed_urls)} wpisów (urzędy / nie Filialbau) z JSON "
            f"(contacts: {len(contacts)})."
        )
    return len(removed_urls)


def save_cache(cache: dict, logger: logging.Logger) -> None:
    try:
        if ENABLE_CACHE_PURGE_INSTITUTIONS:
            purge_institutions_from_cache(cache, logger)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_prepare_cache_for_json(cache), f, ensure_ascii=False, indent=2)
        logger.info(
            "Cache gespeichert: "
            f"places={len(cache.get('places', {}))}, "
            f"contacts={len(cache.get('contacts', {}))}, "
            f"serper={len(cache.get('serper', {}))}"
        )
    except Exception as e:
        logger.error(f"Cache-Schreibfehler: {e}")


def contact_validation_fields(
    info: dict | None, place_url: str = ""
) -> tuple[str, str, str, str]:
    """Spójny kontekst dla is_valid_retail_store_builder_contact (kolejka + wysyłka)."""
    if not isinstance(info, dict):
        info = {}
    email = (info.get("email_target") or "").strip()
    url = (info.get("official_website") or place_url or "").strip()
    name = (
        info.get("company_name_clean")
        or info.get("company_name")
        or info.get("company_name_raw")
        or ""
    ).strip()
    text = " ".join(
        str(info.get(k) or "")
        for k in (
            "verification_reason",
            "page_snippet",
            "retail_chains",
            "retail_chains_found",
            "serper_title",
            "serper_snippet",
        )
    )
    return email, url, name, text


def pipeline_row_to_contact_info(row: dict) -> dict:
    """Wiersz pipeline / Excel → pola contacts JSON."""
    name = (row.get("company_name_clean") or row.get("nazwa") or "").strip()
    email = (row.get("email_target") or "").strip()
    return {
        k: v
        for k, v in {
            "company_name": name,
            "company_name_clean": name,
            "company_name_raw": (row.get("company_name_raw") or name).strip(),
            "official_website": (
                row.get("official_website") or row.get("www") or row.get("url") or ""
            ).strip(),
            "email_target": email,
            "emails_found": (row.get("emails_found") or "").strip(),
            "impressum_emails_found": (row.get("impressum_emails_found") or "").strip(),
            "phones_found": (row.get("phones_found") or row.get("telefon") or "").strip(),
            "email_status": (row.get("email_status") or "").strip(),
            "retail_verified": bool(row.get("retail_verified")),
            "verification_reason": (row.get("verification_reason") or "").strip(),
            "page_snippet": (row.get("page_snippet") or "").strip(),
            "retail_chains_found": (row.get("retail_chains_found") or "").strip(),
            "is_gu": bool(row.get("is_gu")),
            "is_small_firm": bool(row.get("is_small_firm")),
            "gu_marker": (row.get("gu_marker") or "").strip(),
            "contact_quality_score": int(row.get("contact_quality_score", 0) or 0),
            "full_address": (row.get("full_address") or row.get("adres") or "").strip(),
            "bundesland": (row.get("bundesland") or "").strip(),
        }.items()
        if v not in ("", None) or k in (
            "retail_verified",
            "is_gu",
            "is_small_firm",
            "email_target",
            "email_status",
        )
    }


def sync_pipeline_rows_to_contacts_cache(all_rows: list[dict], cache: dict) -> int:
    """Scala wiersze z Excela/pipeline do cache contacts przed wysyłką."""
    contacts = cache.setdefault("contacts", {})
    synced = 0
    for row in all_rows:
        url = (row.get("url") or row.get("www") or "").strip()
        if not url:
            continue
        info = dict(contacts.get(url) or {})
        patch = pipeline_row_to_contact_info(row)
        for key, val in patch.items():
            if key == "email_target" and not val:
                continue
            if val != "" and val is not None:
                info[key] = val
            elif key in ("retail_verified", "is_gu", "is_small_firm"):
                info[key] = val
        contacts[url] = info
        synced += 1
    if synced:
        console_step(f"Pipeline → cache contacts: {synced} URL")
    return synced


def build_email_jobs_from_cache_json(
    logger: logging.Logger,
    *,
    force_resend: bool = False,
    cache: dict | None = None,
):
    console_step("E-Mail-Warteschlange aus Cache JSON")
    data = cache
    if data is None:
        if not CACHE_FILE.exists():
            logger.info("Kein Cache JSON – keine Mails.")
            return []
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f"Cache JSON Lesefehler: {e}")
            return []
    contacts = data.get("contacts", {}) if isinstance(data, dict) else {}
    jobs = []
    for place_url, info in contacts.items():
        if not isinstance(info, dict):
            continue
        email_target = (info.get("email_target") or "").strip()
        email_status = (info.get("email_status") or "").strip().lower()
        if not email_target:
            continue
        if contact_info_excluded(info, place_url):
            continue
        _em, _url, _name, _text = contact_validation_fields(info, place_url)
        pending_www = (
            (info.get("verification_reason") or "").strip() == PENDING_WWW_VERIFY_REASON
            and not info.get("retail_verified")
        )
        if pending_www and email_target and (
            info.get("is_gu") or is_generalunternehmer(_text)[0]
        ):
            pass
        elif not info.get("retail_verified") and not is_valid_retail_store_builder_contact(
            email=email_target,
            url=_url,
            name=_name,
            text=_text,
        ):
            continue
        if REQUIRE_GENERALUNTERNEHMER and not (
            info.get("is_gu") or is_generalunternehmer(_text)[0]
        ):
            continue
        if info.get("retail_verified"):
            if REQUIRE_SMALL_FIRM and not info.get("is_small_firm"):
                continue
            chain_blob = " ".join(
                [
                    _text,
                    str(info.get("retail_chains_found") or ""),
                    str(info.get("page_snippet") or ""),
                ]
            )
            if REQUIRE_NAMED_RETAIL_CHAIN and not has_required_retail_chain_mention(
                chain_blob
            ):
                continue
        if email_status == "sent" and not force_resend:
            continue
        jobs.append(
            {
                "place_url": place_url,
                "email_target": email_target,
                "company_name": info.get("company_name", "Firma"),
                "contact_quality_score": int(info.get("contact_quality_score", 0) or 0),
            }
        )
    logger.info(f"Mail-Jobs aus JSON: {len(jobs)}")
    if not jobs and contacts:
        with_email = sum(
            1 for i in contacts.values()
            if isinstance(i, dict) and (i.get("email_target") or "").strip()
        )
        verified = sum(
            1 for i in contacts.values()
            if isinstance(i, dict) and i.get("retail_verified")
        )
        sent = sum(
            1 for i in contacts.values()
            if isinstance(i, dict) and (i.get("email_status") or "").lower() == "sent"
        )
        console_step(
            f"Brak maili do wysyłki: contacts={len(contacts)}, "
            f"z emailem={with_email}, retail_verified={verified}, już sent={sent}"
        )
    return jobs


def get_remaining_daily_email_limit(cache: dict):
    today = date.today().isoformat()
    daily = cache.setdefault("email_daily", {})
    sent_today = int(daily.get(today, 0))
    remaining = max(0, DAILY_EMAIL_LIMIT - sent_today)
    console_step(
        f"E-Mail-Limit {today}: gesendet={sent_today}, rest={remaining}, max={DAILY_EMAIL_LIMIT}"
    )
    return today, sent_today, remaining


def increase_daily_email_counter(cache: dict, increment: int = 1) -> None:
    today = date.today().isoformat()
    daily = cache.setdefault("email_daily", {})
    daily[today] = int(daily.get(today, 0)) + int(increment)


def get_email_domain(email_target: str) -> str:
    if "@" not in (email_target or ""):
        return ""
    return email_target.split("@", 1)[1].strip().lower()


def get_email_local_part(email_target: str) -> str:
    if "@" not in (email_target or ""):
        return ""
    return email_target.split("@", 1)[0].strip().lower()


def is_email_role_based_or_system(email_target: str) -> bool:
    if get_email_local_part(email_target) in SUPPRESSED_EMAIL_LOCALPARTS:
        return True
    if is_non_commercial_email(email_target):
        return True
    return is_unsuitable_inquiry_email(email_target)


def is_blocked_non_commercial_row(row: dict) -> bool:
    """Nie firma budująca sklepy (GU/Filialbau) — nie do zbierania, Excela ani wysyłki."""
    email = (row.get("email_target") or row.get("emails_found") or "").split(",")[0].strip()
    url = row.get("url") or row.get("www") or row.get("official_website") or ""
    name = row.get("company_name_clean") or row.get("nazwa") or row.get("company_name") or ""
    extra = " ".join(
        str(row.get(k) or "")
        for k in ("verification_reason", "page_snippet", "handelsketten", "retail_chains")
    )
    return not is_valid_retail_store_builder_contact(
        email=email, url=url, name=name, text=extra
    )


def is_within_send_window() -> bool:
    return _schedule_within_send_window(_SEND_WINDOW_CFG)


def get_domain_remaining_daily_limit(cache: dict, domain: str):
    today = date.today().isoformat()
    domain_daily = cache.setdefault("email_domain_daily", {}).setdefault(today, {})
    sent_for_domain = int(domain_daily.get(domain, 0))
    remaining = max(0, EMAIL_PER_DOMAIN_DAILY_LIMIT - sent_for_domain)
    return today, sent_for_domain, remaining


def increase_domain_daily_counter(cache: dict, domain: str, increment: int = 1) -> None:
    if not domain:
        return
    today = date.today().isoformat()
    domain_daily = cache.setdefault("email_domain_daily", {}).setdefault(today, {})
    domain_daily[domain] = int(domain_daily.get(domain, 0)) + int(increment)


def is_suppressed_target(cache: dict, email_target: str) -> bool:
    suppression = cache.setdefault("email_suppression", {})
    return email_target.lower() in suppression


def mark_suppressed_target(cache: dict, email_target: str, reason: str) -> None:
    if not email_target:
        return
    suppression = cache.setdefault("email_suppression", {})
    suppression[email_target.lower()] = {"reason": reason, "date": date.today().isoformat()}


def is_soft_bounce_or_spam_error(error_text: str) -> bool:
    lowered = (error_text or "").lower()
    if not lowered:
        return False
    markers = [
        "5.7.1",
        "likely unsolicited",
        "unsolicited mail",
        "message blocked",
        "blocked by policy",
        "mail rejected",
        "spam",
        "temporarily deferred",
        "try again later",
    ]
    return any(marker in lowered for marker in markers)


def sleep_between_emails(logger: logging.Logger, target_email: str) -> None:
    delay = round(random.uniform(EMAIL_SEND_DELAY_MIN_SECONDS, EMAIL_SEND_DELAY_MAX_SECONDS), 1)
    console_step(f"Anti-Spam Pause vor nächster Mail ({target_email}): {delay}s")
    logger.info(f"Email jitter sleep={delay}s target={target_email}")
    time.sleep(delay)


def sanitize_generated_email(subject: str, body: str, company_name: str):
    clean_subject = (subject or "").strip()
    clean_body = (body or "").strip()
    if not clean_subject:
        clean_subject = choose_subject_variant(company_name)
    clean_subject = re.sub(r"\+?\d[\d\s()./-]{5,}\d", "", clean_subject)
    clean_subject = clean_subject.replace("!", "").replace("?", "")
    clean_subject = clean_subject[:95].strip(" -")
    lowered_subject = clean_subject.lower()
    if any(term in lowered_subject for term in EMAIL_SPAMMY_TERMS):
        clean_subject = choose_subject_variant(company_name)
    lowered_body = clean_body.lower()
    for term in EMAIL_SPAMMY_TERMS:
        if term in lowered_body:
            clean_body = re.sub(term, "", clean_body, flags=re.IGNORECASE)
    from ua_materialy_inquiry_email_uk import strip_de_campaign_branding, strip_german_phones_from_text

    clean_body = strip_german_phones_from_text(clean_body)
    clean_body = strip_de_campaign_branding(clean_body)
    clean_body = re.sub(r"\n{3,}", "\n\n", clean_body).strip()
    return clean_subject, clean_body


def sanitize_sender_name(sender_name: str) -> str:
    from ua_materialy_inquiry_email_uk import inquiry_company_name, inquiry_sender_name

    text = (sender_name or "").strip()
    default_name = inquiry_sender_name()
    default_company = inquiry_company_name()
    default = f"{default_name}, {default_company}" if default_company else default_name
    if not text:
        return default
    text = re.sub(r"\b(tel|telefon)\b.*$", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"https?://\S+|\bwww\.\S+|\S+@\S+", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\+?\d[\d\s()./-]{5,}\d", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip(" ,;-")
    if not text:
        return default
    return text


def was_email_target_sent_today(cache: dict, email_target: str) -> bool:
    if not email_target:
        return False
    today = date.today().isoformat()
    sent_targets = cache.setdefault("email_sent_targets", {}).setdefault(today, [])
    return email_target.lower() in {x.lower() for x in sent_targets}


def mark_email_target_sent_today(cache: dict, email_target: str) -> None:
    if not email_target:
        return
    today = date.today().isoformat()
    sent_targets = cache.setdefault("email_sent_targets", {}).setdefault(today, [])
    lowered = email_target.lower()
    if lowered not in {x.lower() for x in sent_targets}:
        sent_targets.append(lowered)


def get_remaining_daily_serper_limit(cache: dict):
    today = campaign_today()
    daily = cache.setdefault("serper_daily", {})
    used_today = int(daily.get(today, 0))
    if is_serper_unlimited():
        remaining = 10**9
        console_step(
            f"Serper {today}: genutzt={used_today}, unlimited (pipeline)"
        )
        return today, used_today, remaining
    remaining = max(0, SERPER_DAILY_LIMIT - used_today)
    console_step(
        f"Serper-Limit {today}: genutzt={used_today}, rest={remaining}, max={SERPER_DAILY_LIMIT}"
    )
    return today, used_today, remaining


def increase_daily_serper_counter(cache: dict, increment: int = 1) -> None:
    today = campaign_today()
    daily = cache.setdefault("serper_daily", {})
    daily[today] = int(daily.get(today, 0)) + int(increment)


def campaign_today() -> str:
    """Dzień kampanii wg SCRAPER_TIMEZONE (domyślnie Europe/Warsaw)."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(CAMPAIGN_TIMEZONE)).date().isoformat()
    except Exception:
        return date.today().isoformat()


def clear_serper_search_caches(cache: dict) -> tuple[int, int]:
    """Wyczyść serper + serper_discovery — wymusza świeże zapytania API (bez empty-TTL)."""
    n_serper = len(cache.get("serper") or {})
    n_discovery = len(cache.get("serper_discovery") or {})
    cache["serper"] = {}
    cache["serper_discovery"] = {}
    return n_serper, n_discovery


def reset_serper_daily_for_discovery(cache: dict) -> None:
    """Sobota discovery — pełny budżet Serper na dzień kampanii."""
    today = campaign_today()
    daily = cache.setdefault("serper_daily", {})
    old = int(daily.get(today, 0) or 0)
    daily[today] = 0
    flags = cache.setdefault("serper_limit_reached", {})
    flags.pop(today, None)
    exhausted = cache.setdefault("serper_api_exhausted", {})
    if exhausted.pop(today, None):
        parts_ex = [f"serper_api_exhausted wyczyszczone ({today})"]
    else:
        parts_ex = []
    n_serper, n_discovery = clear_serper_search_caches(cache)
    if old or n_serper or n_discovery or parts_ex:
        parts = []
        if old:
            parts.append(
                f"limit było {old}, start z {SERPER_DAILY_LIMIT} zapytań"
            )
        if n_serper or n_discovery:
            parts.append(
                f"cache: serper={n_serper}, serper_discovery={n_discovery}"
            )
        parts.extend(parts_ex)
        console_step(f"Serper-Reset ({today}): " + "; ".join(parts))


def ensure_serper_budget_or_fail(cache: dict) -> None:
    if is_serper_unlimited():
        return
    _, used_today, remaining = get_remaining_daily_serper_limit(cache)
    if remaining <= 0:
        raise RuntimeError(
            f"Serper Tageslimit erreicht ({campaign_today()}: "
            f"{used_today}/{SERPER_DAILY_LIMIT}). Discovery abgebrochen."
        )


def new_discovery_funnel() -> dict:
    return {
        "serper_queries": 0,
        "api_zero_terms": 0,
        "raw_hits": 0,
        "filtered_serper": 0,
        "filtered_large_serper": 0,
        "pending_saved": 0,
        "rejected_excel": 0,
        "claude_rounds": 0,
        "claude_terms": 0,
    }


def _record_serper_term_stat(
    cache: dict,
    term: str,
    label: str,
    *,
    raw_hits: int = 0,
    pending_added: int = 0,
) -> None:
    stats = cache.setdefault("serper_term_stats", {})
    key = f"{label}:{term}"
    entry = stats.setdefault(
        key, {"term": term, "source": label, "raw": 0, "pending": 0}
    )
    entry["raw"] = int(entry.get("raw", 0)) + int(raw_hits)
    entry["pending"] = int(entry.get("pending", 0)) + int(pending_added)


def log_discovery_funnel(funnel: dict, logger: logging.Logger) -> None:
    msg = (
        "[LEjek] serper_queries={serper_queries} | api_zero={api_zero_terms} | "
        "raw_hits={raw_hits} | filtered_serper={filtered_serper} | "
        "filtered_large={filtered_large_serper} | pending_saved={pending_saved} | "
        "rejected_excel={rejected_excel} | claude_rounds={claude_rounds} | "
        "claude_terms={claude_terms}"
    ).format(**funnel)
    console_step(msg)
    logger.info(msg)


def count_pending_for_bundesland(
    rows: list, cache: dict, land: str
) -> int:
    land_norm = (land or "").strip()
    if not land_norm:
        return 0
    seen: set[str] = set()
    count = 0
    for row in rows or []:
        if (row.get("verification_reason") or "").strip() != PENDING_WWW_VERIFY_REASON:
            continue
        if row.get("retail_verified"):
            continue
        tagged = (row.get("discovery_bundesland") or "").strip()
        bl = (row.get("bundesland") or extract_bundesland(row) or "").strip()
        if tagged != land_norm and bl != land_norm:
            continue
        url = (row.get("url") or row.get("www") or "").strip()
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        count += 1
    for url, info in (cache.get("contacts") or {}).items():
        if not isinstance(info, dict):
            continue
        if (info.get("verification_reason") or "").strip() != PENDING_WWW_VERIFY_REASON:
            continue
        if info.get("retail_verified"):
            continue
        tagged = (info.get("discovery_bundesland") or "").strip()
        if tagged and tagged != land_norm:
            continue
        if url in seen:
            continue
        seen.add(url)
        count += 1
    return count


def count_all_pending_contacts(rows: list, cache: dict) -> int:
    """Wszystkie kandydaty pending_www_verify (bundesweit)."""
    seen: set[str] = set()
    count = 0
    for row in rows or []:
        if (row.get("verification_reason") or "").strip() != PENDING_WWW_VERIFY_REASON:
            continue
        if row.get("retail_verified"):
            continue
        url = (row.get("url") or row.get("www") or "").strip()
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        count += 1
    for url, info in (cache.get("contacts") or {}).items():
        if not isinstance(info, dict):
            continue
        if (info.get("verification_reason") or "").strip() != PENDING_WWW_VERIFY_REASON:
            continue
        if info.get("retail_verified"):
            continue
        if url in seen:
            continue
        seen.add(url)
        count += 1
    return count


def is_serper_limit_reached_today(cache: dict) -> bool:
    if is_serper_unlimited():
        return False
    today = campaign_today()
    daily = cache.setdefault("serper_daily", {})
    used_today = int(daily.get(today, 0))
    remaining = max(0, SERPER_DAILY_LIMIT - used_today)
    flags = cache.setdefault("serper_limit_reached", {})
    if flags.get(today):
        return True
    if remaining <= SERPER_DISCOVERY_RESERVE:
        flags[today] = True
        return True
    return False


def mark_serper_limit_reached_today(cache: dict) -> None:
    today = campaign_today()
    flags = cache.setdefault("serper_limit_reached", {})
    flags[today] = True


def _serper_discovery_cache_key(query: str, *, use_places_endpoint: bool) -> str:
    prefix = "places:" if use_places_endpoint else "search:"
    return f"{prefix}{query}"


def _parse_serper_discovery_cache_entry(entry) -> tuple[list[dict] | None, bool]:
    """Zwraca (wiersze lub None, czy_traktować_jako_cache_miss)."""
    if entry is None:
        return None, True
    if isinstance(entry, list):
        return entry, False
    if not isinstance(entry, dict):
        return None, True
    if entry.get("empty"):
        ts = (entry.get("at") or "").strip()
        if ts:
            try:
                age = datetime.now() - datetime.fromisoformat(ts)
                if age < timedelta(days=SERPER_DISCOVERY_EMPTY_CACHE_DAYS):
                    return [], False
            except ValueError:
                pass
        return None, True
    rows = entry.get("rows")
    if isinstance(rows, list):
        return rows, False
    return None, True


def get_cached_serper_discovery_rows(
    cache: dict, query: str, *, use_places_endpoint: bool = False
) -> list[dict] | None:
    sd = cache.setdefault("serper_discovery", {})
    key = _serper_discovery_cache_key(query, use_places_endpoint=use_places_endpoint)
    rows, miss = _parse_serper_discovery_cache_entry(sd.get(key))
    if miss:
        return None
    return rows


def store_serper_discovery_rows(
    cache: dict,
    query: str,
    rows: list[dict],
    *,
    use_places_endpoint: bool = False,
) -> None:
    sd = cache.setdefault("serper_discovery", {})
    key = _serper_discovery_cache_key(query, use_places_endpoint=use_places_endpoint)
    if rows:
        sd[key] = {"rows": rows, "at": datetime.now().isoformat()}
    else:
        sd[key] = {"empty": True, "at": datetime.now().isoformat(), "rows": []}


def count_retail_verified_for_bundesland(rows: list, land: str) -> int:
    land_norm = (land or "").strip()
    if not land_norm:
        return 0
    count = 0
    for row in rows or []:
        if not row.get("retail_verified"):
            continue
        tagged = (row.get("discovery_bundesland") or "").strip()
        bl = (row.get("bundesland") or extract_bundesland(row) or "").strip()
        if tagged == land_norm or bl == land_norm:
            count += 1
    return count


def request_with_retry(
    method,
    url: str,
    logger: logging.Logger,
    *,
    retry_on_rate_limit: bool = True,
    waf_skip: bool = False,
    **kwargs,
):
    from http_page_guard import PageAccessBlocked, is_waf_blocked, waf_block_reason

    last_err = None
    safe_url = sanitize_log_url(url)
    for attempt in range(1, HTTP_RETRY_ATTEMPTS + 1):
        try:
            response = method(url, **kwargs)
            if waf_skip and is_waf_blocked(response=response):
                reason = waf_block_reason(response=response)
                logger.info(
                    "WAF/Cloudflare — pomijam (bez retry): %s [%s]",
                    safe_url,
                    reason,
                )
                raise PageAccessBlocked(f"{safe_url}: {reason}")
            response.raise_for_status()
            if waf_skip:
                body = getattr(response, "text", "") or ""
                if is_waf_blocked(response=response, html=body):
                    reason = waf_block_reason(response=response, html=body)
                    logger.info(
                        "WAF/Cloudflare (treść) — pomijam: %s [%s]",
                        safe_url,
                        reason,
                    )
                    raise PageAccessBlocked(f"{safe_url}: {reason}")
            return response
        except PageAccessBlocked:
            raise
        except Exception as e:
            last_err = e
            if waf_skip and is_waf_blocked(exc=e):
                reason = waf_block_reason(exc=e)
                logger.info(
                    "WAF/Cloudflare — pomijam (bez retry): %s [%s]",
                    safe_url,
                    reason,
                )
                raise PageAccessBlocked(f"{safe_url}: {reason}") from e
            console_step(f"HTTP Retry {attempt}/{HTTP_RETRY_ATTEMPTS} {safe_url}: {e}")
            if _is_rate_limit_error(e) and not retry_on_rate_limit:
                break
            if attempt < HTTP_RETRY_ATTEMPTS:
                backoff = HTTP_BACKOFF_SECONDS * attempt
                if _is_rate_limit_error(e):
                    backoff = max(backoff, 30 * attempt)
                time.sleep(backoff)
    logger.warning(f"HTTP endgültig fehlgeschlagen: {safe_url}: {last_err}")
    if last_err is not None:
        raise last_err
    raise RuntimeError("request_with_retry ohne Antwort")


def choose_subject_variant(company_name: str) -> str:
    _ = company_name
    return FIXED_EMAIL_SUBJECT_UK


def choose_prompt_variant(company_name: str) -> str:
    idx = abs(hash((company_name or "") + "_prompt")) % len(PROMPT_VARIANTS)
    return PROMPT_VARIANTS[idx]


def _domain_from_url(url: str) -> str:
    try:
        host = (urlparse(normalize_website(url)).netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def _max_employee_count_in_blob(blob: str) -> int | None:
    counts: list[int] = []
    for pat in _EMPLOYEE_COUNT_PATTERNS:
        for m in pat.finditer(blob):
            try:
                n = int(m.group(1))
            except (TypeError, ValueError):
                continue
            if 10 <= n <= 9999:
                counts.append(n)
    return max(counts) if counts else None


def _has_regional_gu_context(
    blob: str, company_name: str = "", website: str = ""
) -> bool:
    combined = f"{blob} {company_name or ''} {website or ''}".lower()
    has_gu = any(m in combined for m in _REGIONAL_GU_CONTEXT_MARKERS)
    has_regional = any(m in combined for m in _REGIONAL_GU_REGIONAL_MARKERS)
    return has_gu and has_regional


def _is_whitelisted_regional_gu_with_employees(
    blob: str, company_name: str = "", website: str = ""
) -> bool:
    """
    Faza 4: mały regionalny GU z liczbą pracowników w opisie (< 500) — nie odrzucaj.
    Nie dotyczy domen/nazw koncernów ani silnych sygnałów holdingu.
    """
    if any(m in blob for m in _STRONG_KONZERN_OVERRIDE_MARKERS):
        return False
    if not _has_regional_gu_context(blob, company_name, website):
        return False
    emp = _max_employee_count_in_blob(blob)
    if emp is None:
        return False
    return emp <= REGIONAL_GU_EMPLOYEE_WHITELIST_MAX


def is_likely_large_company(
    company_name: str = "",
    website: str = "",
    page_text: str = "",
    serper_blob: str = "",
) -> tuple[bool, str]:
    """True = duży koncern / do odrzucenia."""
    blob = " ".join(
        [company_name or "", website or "", page_text or "", serper_blob or ""]
    ).lower()
    small_hits = sum(1 for m in SMALL_COMPANY_PAGE_MARKERS if m in blob)
    if small_hits >= 1:
        return False, ""
    domain = _domain_from_url(website)
    for blocked in LARGE_COMPANY_DOMAINS:
        if blocked in domain or blocked in blob:
            return True, f"grosses_unternehmen_domain:{blocked}"
    for marker in LARGE_COMPANY_NAME_MARKERS:
        if marker not in blob:
            continue
        if marker.strip() in ("se", "gmbh & co. kg"):
            if marker.strip() == "se":
                if not re.search(r"\bse\b", blob):
                    continue
                if not any(
                    x in blob
                    for x in ("societas europaea", " societas ", " se,", " se.")
                ) and not re.search(
                    r"\b[\w&.-]+\s+se\b", blob
                ):
                    continue
            if not any(
                x in blob
                for x in ("konzern", "weltweit", "börsennotiert", "holding", "global player")
            ):
                continue
            return True, f"grosses_unternehmen_name:{marker.strip()}"
        return True, f"grosses_unternehmen_name:{marker}"
    large_page_hits = sum(1 for m in LARGE_COMPANY_PAGE_MARKERS if m in blob)
    strong_hits = sum(1 for m in _STRONG_LARGE_PAGE_MARKERS if m in blob)
    would_be_large = (large_page_hits >= 2 and strong_hits >= 1) or strong_hits >= 2
    if would_be_large and _is_whitelisted_regional_gu_with_employees(
        blob, company_name, website
    ):
        return False, ""
    if large_page_hits >= 2 and strong_hits >= 1:
        return True, "grosses_unternehmen_seite"
    if strong_hits >= 2:
        return True, "grosses_unternehmen_seite_stark"
    return False, ""


def _is_small_ladenbau_specialist(
    company_name: str,
    website: str,
    page_text: str,
) -> bool:
    """Mały GU Ladenbau/Filialbau — bez sygnałów koncernu."""
    name_domain = f"{company_name or ''} {website or ''}".lower()
    if not any(
        m in name_domain
        for m in ("ladenbau", "filialbau", "laden-und", "storebau", "filial-")
    ):
        return False
    if is_likely_large_company(company_name, website, page_text)[0]:
        return False
    blob = (page_text or "").lower()
    if REQUIRE_GENERALUNTERNEHMER:
        gu_ok, _ = qualifies_as_gu_for_campaign(
            f"{company_name or ''} {website or ''} {page_text or ''}"
        )
        if not gu_ok:
            return False
    build_markers = (
        "bau",
        "generalunternehmer",
        "neubau",
        "umbau",
        "gewerbe",
        "handwerk",
        "realis",
        "erricht",
        "ladenbau",
        "filialbau",
        "einzelhandel",
        "supermarkt",
    )
    return any(m in blob for m in build_markers)


def detect_retail_chains_in_text(text: str) -> list[str]:
    low = (text or "").lower()
    if REQUIRE_NAMED_RETAIL_CHAIN:
        return detect_required_retail_chains(low)
    return [c for c in RETAIL_CHAIN_KEYWORDS if c in low]


def resolve_is_small_firm(
    blob: str,
    *,
    large: bool = False,
    small_hint: bool | None = None,
) -> bool:
    """True tylko przy pozytywnym sygnale małej firmy; duże zawsze False."""
    if large:
        return False
    hint = (
        small_hint
        if small_hint is not None
        else any(m in (blob or "").lower() for m in SMALL_COMPANY_PAGE_MARKERS)
    )
    if REQUIRE_SMALL_FIRM:
        return bool(hint)
    return bool(hint) or not large


def page_mentions_retail_store_projects(text: str) -> tuple[bool, list[str], str]:
    """
    GU/Filialbau (Neubau/Umbau Märkte) + dowód projektów marketów na www
    (Referenzen, Portfolio, zdjęcia sklepów lub opisy projektów).
    """
    low = (text or "").lower()
    if is_retail_store_operator_contact(text=low):
        return False, [], "einzelhandel_betrieb_kein_bau"
    if REQUIRE_GENERALUNTERNEHMER:
        gu_ok, _ = qualifies_as_gu_for_campaign(low)
        if not gu_ok:
            return False, [], "kein_generalunternehmer"
    if not mentions_retail_store_build_activity_core(low):
        return False, [], "kein_gu_filialbau_kontext"
    if REQUIRE_MARKET_PROJECTS_IN_PORTFOLIO and not has_retail_references_or_portfolio(
        low
    ):
        return False, [], "kein_markt_nachweis"

    chains = detect_retail_chains_in_text(low)
    if REQUIRE_NAMED_RETAIL_CHAIN and not chains:
        return False, [], "keine_handelskette"

    has_build = any(k in low for k in RETAIL_BUILD_KEYWORDS)
    has_ref = has_retail_references_or_portfolio(low)
    has_trade = any(k in low for k in RETAIL_TRADE_ACTIVITY_KEYWORDS)
    has_gu_bau, _ = qualifies_as_gu_for_campaign(low)
    has_umbau = any(
        k in low
        for k in (
            "umbau",
            "modernisierung",
            "revitalisierung",
            "filialumbau",
            "marktumbau",
            "filialsanierung",
        )
    )

    if portfolio_negates_market_projects(low):
        return False, chains, "kein_markt_nachweis"
    if not has_ref:
        if not REQUIRE_MARKET_PROJECTS_IN_PORTFOLIO:
            return True, chains, "gu_filialbau_kontext"
        return False, chains, "keine_referenzen_portfolio"

    if chains and has_build:
        return True, chains, "kette_referenz_ladenbau"
    if chains:
        return True, chains, "kette_und_referenz"
    if has_umbau and has_trade:
        return True, chains, "referenz_filialumbau"
    if has_build and has_gu_bau:
        return True, chains, "referenz_gu_filialbau"
    if has_trade:
        return True, chains, "referenz_einzelhandel"
    if has_build:
        return True, chains, "referenz_ladenbau"
    return True, chains, "markt_referenz_nachweis"


def sort_verification_urls(urls: list[str]) -> list[str]:
    def key(u: str) -> tuple[int, str]:
        low = u.lower()
        if any(x in low for x in RETAIL_URL_PRIORITY_KEYWORDS):
            return (0, low)
        if any(
            x in low
            for x in ("karriere", "stellen", "jobs", "career", "stellenangebot")
        ):
            return (0, low)
        if any(x in low for x in ("ueber-uns", "über-uns", "unternehmen", "about")):
            return (1, low)
        if _is_impressum_url(low):
            return (1, low)
        if any(x in low for x in ("kontakt", "contact", "impressum")):
            return (2, low)
        return (3, low)

    return sorted(urls, key=key)


def _fetch_page_html(url: str, logger: logging.Logger) -> str:
    """Pobierz HTML jednej strony (requests + retry)."""
    if not (url or "").strip().lower().startswith(("http://", "https://")):
        return ""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    try:
        r = request_with_retry(
            requests.get,
            url,
            logger,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            waf_skip=True,
        )
        return r.text or ""
    except Exception as e:
        from http_page_guard import PageAccessBlocked

        if isinstance(e, PageAccessBlocked):
            logger.info("Strona pominięta (WAF/Cloudflare): %s", url)
        else:
            logger.info("Seitenabruf fehlgeschlagen %s: %s", url, e)
        return ""


def _parse_html_page_for_crawl(
    url: str, html: str, logger: logging.Logger, cache: dict | None
) -> dict:
    parsed = parse_contacts_from_html(url, html, logger=logger, cache=cache)

    def _parse_html_playwright(page_url: str, page_html: str) -> dict:
        return parse_contacts_from_html(
            page_url, page_html, logger=logger, cache=cache
        )

    parsed = apply_playwright_cookie_fallback(
        url, logger, html, parsed, _parse_html_playwright, on_step=console_step
    )
    return {
        "emails": parsed["emails"],
        "phones": parsed["phones"],
        "company_name": parsed.get("company_name") or "",
        "contact_urls": parsed["contact_urls"],
        "page_text": parsed.get("page_text", ""),
    }


def _crawl_website_for_company(
    website: str, logger: logging.Logger, cache: dict | None
):
    from website_full_crawl import (
        WebsiteCrawlResult,
        crawl_entire_website,
        format_crawl_text_for_claude,
    )

    website = normalize_website(website)
    if not website:
        return WebsiteCrawlResult(), ""

    crawl_cache = (cache or {}).setdefault("website_crawl", {})
    if website in crawl_cache:
        cached = crawl_cache[website]
        if isinstance(cached, WebsiteCrawlResult):
            console_step(
                f"Website-Crawl Cache: {website} ({len(cached.urls_visited)} Seiten)"
            )
            return cached, format_crawl_text_for_claude(cached)

    console_step(f"Website-Crawl (gesamte Domain): {website}")

    def _parse(url: str, html: str) -> dict:
        return _parse_html_page_for_crawl(url, html, logger, cache)

    result = crawl_entire_website(
        website,
        logger,
        fetch_page_html=lambda u: _fetch_page_html(u, logger),
        parse_html_page=_parse,
        normalize_website=normalize_website,
        on_step=console_step,
    )
    crawl_cache[website] = result
    console_step(
        f"Website-Crawl fertig: {len(result.urls_visited)} Seiten"
        + (" (Limit)" if result.capped else "")
    )
    return result, format_crawl_text_for_claude(result)


def _get_website_crawl_text(
    website: str, cache: dict | None, *, purpose: str = "verify"
) -> str:
    """Tekst pełnego crawla domeny (dla Claude verify / contact extract)."""
    from website_full_crawl import WebsiteCrawlResult, format_crawl_text_for_claude

    site = normalize_website(website)
    if not site:
        return ""
    crawl = ((cache or {}).get("website_crawl") or {}).get(site)
    if isinstance(crawl, WebsiteCrawlResult):
        return format_crawl_text_for_claude(crawl, purpose=purpose)
    return ""


def merge_contacts_from_crawl(crawl, website: str) -> dict:
    """Złącz e-maile/telefony ze wszystkich podstron po pełnym crawlu."""
    emails: list[str] = []
    impressum_emails: list[str] = []
    phones: list[str] = []
    company_candidates: list[str] = []
    source_urls: list[str] = []
    text_parts: list[str] = []

    for url in crawl.urls_visited:
        details = crawl.pages.get(url) or {}
        from_impressum = _is_impressum_url(url)
        for e in details.get("emails") or []:
            if from_impressum and e not in impressum_emails:
                impressum_emails.append(e)
            if e not in emails:
                emails.append(e)
        for p in details.get("phones") or []:
            if p not in phones:
                phones.append(p)
        if details.get("company_name"):
            company_candidates.append(details["company_name"])
        if details.get("page_text"):
            text_parts.append(details["page_text"])
        if url not in source_urls:
            source_urls.append(url)

    if impressum_emails:
        console_step(
            f"Impressum: {len(impressum_emails)} E-Mail(s) — "
            f"{', '.join(impressum_emails[:3])}"
        )
    page_snippet = _truncate_page_snippet(" ".join(text_parts))
    return {
        "emails": emails,
        "impressum_emails": impressum_emails,
        "phones": phones,
        "company_name": _pick_best_company_name(company_candidates, website),
        "website": website,
        "source_urls": source_urls,
        "page_snippet": page_snippet,
    }


def gather_website_text_for_verification(
    website: str, logger: logging.Logger, cache: dict | None = None
) -> tuple[str, list[str]]:
    """Pełny crawl domeny → tekst wszystkich podstron dla Claude."""
    _crawl, page_text = _crawl_website_for_company(website, logger, cache)
    return page_text, list(_crawl.urls_visited)


def _needs_claude_discovery_supplement(
    all_rows: list,
    cache: dict,
    rotation_land: str | None,
    total_new_rows: int,
    *,
    rotate_mode: bool,
    serper_only: bool,
) -> bool:
    if rotate_mode and serper_only:
        pending = count_pending_for_bundesland(all_rows, cache, rotation_land or "")
        return pending < MIN_CONTACTS_TARGET
    return not _discovery_target_reached(
        all_rows,
        total_new_rows=total_new_rows,
        rotate_mode=rotate_mode,
        serper_only=serper_only,
    )


def _run_claude_discovery_supplement(
    all_rows: list,
    cache: dict,
    logger: logging.Logger,
    rotation_land: str | None,
    serper_kw: dict,
    funnel: dict | None,
) -> tuple[int, bool]:
    from claude_discovery_terms import generate_claude_discovery_terms

    total_new_rows = int(serper_kw.get("total_new_rows") or 0)
    stop_requested = bool(serper_kw.get("stop_requested"))
    rotate_mode = bool(serper_kw.get("rotate_mode"))
    serper_only = bool(serper_kw.get("serper_only"))
    if not ENABLE_CLAUDE_DISCOVERY_TERMS:
        return total_new_rows, stop_requested

    lands = [rotation_land] if rotation_land else list(CAMPAIGN_ACTIVE_BUNDESLAENDER)
    used_terms: list[str] = []

    for round_n in range(1, CLAUDE_DISCOVERY_MAX_ROUNDS + 1):
        if request_stop_on_runtime_limit(logger, console_step_fn=console_step):
            stop_requested = True
            break
        if stop_requested:
            break
        if not _needs_claude_discovery_supplement(
            all_rows,
            cache,
            rotation_land,
            total_new_rows,
            rotate_mode=rotate_mode,
            serper_only=serper_only,
        ):
            break

        remaining = SERPER_DISCOVERY_RESERVE + CLAUDE_DISCOVERY_TERMS_PER_ROUND
        if not is_serper_unlimited():
            _, _, remaining = get_remaining_daily_serper_limit(cache)
            if remaining <= SERPER_DISCOVERY_RESERVE:
                console_step(
                    f"Claude discovery: rezerwa Serper ({remaining} <= "
                    f"{SERPER_DISCOVERY_RESERVE})"
                )
                break

        pending_before = count_pending_for_bundesland(
            all_rows, cache, rotation_land or ""
        )

        terms = generate_claude_discovery_terms(
            cache,
            logger,
            [l for l in lands if l],
            terms_requested=CLAUDE_DISCOVERY_TERMS_PER_ROUND,
            cache_days=CLAUDE_DISCOVERY_CACHE_DAYS,
            use_cache=(round_n == 1),
            exclude_terms=used_terms,
        )
        if not terms:
            console_step("Claude discovery: brak nowych fraz po walidacji")
            break

        budget = min(
            len(terms),
            CLAUDE_DISCOVERY_TERMS_PER_ROUND,
            max(0, remaining - SERPER_DISCOVERY_RESERVE),
        )
        if budget <= 0:
            break

        batch = terms[:budget]
        used_terms.extend(batch)
        if funnel is not None:
            funnel["claude_rounds"] = funnel.get("claude_rounds", 0) + 1
            funnel["claude_terms"] = funnel.get("claude_terms", 0) + len(batch)

        console_step(
            f"Claude discovery runda {round_n}: {len(batch)} fraz → Serper"
        )
        proc_kw = {
            k: v
            for k, v in serper_kw.items()
            if k not in ("total_new_rows", "stop_requested", "funnel")
        }
        total_new_rows, stop_requested = _process_serper_terms(
            batch,
            f"claude-r{round_n}",
            apply_distance_filter=False,
            funnel=funnel,
            total_new_rows=total_new_rows,
            stop_requested=stop_requested,
            **proc_kw,
        )
        serper_kw["total_new_rows"] = total_new_rows
        serper_kw["stop_requested"] = stop_requested

        pending_after = count_pending_for_bundesland(
            all_rows, cache, rotation_land or ""
        )
        gain = pending_after - pending_before
        console_step(f"Claude discovery runda {round_n}: +{gain} pending")
        if gain < CLAUDE_DISCOVERY_MIN_GAIN:
            console_step(
                f"Claude discovery: zysk +{gain} < {CLAUDE_DISCOVERY_MIN_GAIN}, stop"
            )
            break

    return total_new_rows, stop_requested


def _finalize_verification_result(result: dict, blob: str) -> dict:
    gu_ok, gu_marker = qualifies_as_gu_for_campaign(blob)
    result["is_gu"] = gu_ok
    result["gu_marker"] = gu_marker
    if result.get("verified") and REQUIRE_GENERALUNTERNEHMER and not gu_ok:
        result["verified"] = False
        result["verification_reason"] = "kein_generalunternehmer"
        result["is_gu"] = False
        result["gu_marker"] = ""
    if result.get("verified") and REQUIRE_SMALL_FIRM and not result.get("is_small_firm"):
        result["verified"] = False
        result["verification_reason"] = "kein_kleinunternehmen"
    if result.get("verified") and REQUIRE_NAMED_RETAIL_CHAIN:
        chains = result.get("retail_chains") or detect_required_retail_chains(blob)
        if not chains:
            result["verified"] = False
            result["verification_reason"] = "keine_handelskette"
        else:
            result["retail_chains"] = chains
    return result


def verify_company_on_website(
    company_name: str,
    website: str,
    logger: logging.Logger,
    cache: dict | None,
    *,
    serper_blob: str = "",
    cache_key: str = "",
) -> dict:
    """
    Wchodzi na stronę, sprawdza mała firma + sklepy dyskontowe.
    Zwraca m.in. verified, retail_chains, verification_reason, is_gu.
    """
    page_text, pages_checked = gather_website_text_for_verification(
        website, logger, cache
    )
    blob = " ".join([page_text, serper_blob])

    if ENABLE_CLAUDE_PAGE_VERIFY:
        from claude_client import is_claude_rate_limited
        from ua_claude_page_verify import claude_verify_company_page

        if get_anthropic_api_key() and not is_claude_rate_limited(cache):
            claude = claude_verify_company_page(
                company_name,
                website,
                page_text,
                logger,
                cache,
                cache_key=cache_key or website,
                serper_blob=serper_blob,
                require_generalunternehmer=REQUIRE_GENERALUNTERNEHMER,
                require_small_firm=REQUIRE_SMALL_FIRM,
            )
            if claude is not None:
                return _finalize_verification_result(
                    {
                        "verified": claude.get("verified", False),
                        "is_small_firm": claude.get("is_small_firm", False),
                        "retail_chains": claude.get("retail_chains") or [],
                        "verification_reason": claude.get(
                            "verification_reason", "claude"
                        ),
                        "verification_method": "claude_profile",
                        "pages_checked": pages_checked,
                        "page_snippet": _truncate_page_snippet(page_text),
                        "is_gu": claude.get("is_gu", False),
                        "gu_marker": claude.get("gu_marker", ""),
                    },
                    blob,
                )

    large, large_reason = is_likely_large_company(
        company_name, website, page_text, serper_blob
    )
    if large:
        return _finalize_verification_result(
            {
                "verified": False,
                "is_small_firm": False,
                "retail_chains": [],
                "verification_reason": large_reason,
                "verification_method": "rules",
                "pages_checked": pages_checked,
                "page_snippet": _truncate_page_snippet(page_text),
            },
            blob,
        )

    if _is_small_ladenbau_specialist(company_name, website, page_text):
        chains = detect_retail_chains_in_text(page_text)
        rules_ok, _, rules_reason = page_mentions_retail_store_projects(page_text)
        return _finalize_verification_result(
            {
                "verified": rules_ok and bool(chains),
                "is_small_firm": True,
                "retail_chains": chains,
                "verification_reason": rules_reason if rules_ok else "keine_handelskette",
                "verification_method": "bs4_rules",
                "pages_checked": pages_checked,
                "page_snippet": _truncate_page_snippet(page_text),
            },
            blob,
        )

    rules_ok, chains, rules_reason = page_mentions_retail_store_projects(page_text)
    is_small = resolve_is_small_firm(blob, large=large)

    if rules_ok and is_small:
        return _finalize_verification_result(
            {
                "verified": True,
                "is_small_firm": True,
                "retail_chains": chains,
                "verification_reason": rules_reason,
                "verification_method": "bs4_rules",
                "pages_checked": pages_checked,
                "page_snippet": _truncate_page_snippet(page_text),
            },
            blob,
        )

    if not rules_ok and serper_blob.strip():
        rules_ok2, chains2, rules_reason2 = page_mentions_retail_store_projects(
            serper_blob
        )
        if rules_ok2 and is_small:
            return _finalize_verification_result(
                {
                    "verified": True,
                    "is_small_firm": True,
                    "retail_chains": chains2,
                    "verification_reason": f"serper_snippet:{rules_reason2}",
                    "verification_method": "bs4_rules",
                    "pages_checked": pages_checked,
                    "page_snippet": _truncate_page_snippet(page_text),
                },
                blob,
            )
        chains = chains or chains2
        rules_reason = rules_reason2 if not rules_ok else rules_reason

    reason = rules_reason if not rules_ok else (large_reason or "nicht_klein")
    if not is_small:
        reason = large_reason or "nicht_klein"
    return _finalize_verification_result(
        {
            "verified": False,
            "is_small_firm": is_small,
            "retail_chains": chains,
            "verification_reason": reason,
            "verification_method": "bs4_rules",
            "pages_checked": pages_checked,
            "page_snippet": _truncate_page_snippet(page_text),
        },
        blob,
    )


def score_serper_candidate(link: str, title: str = "", snippet: str = "", company_name: str = "") -> int:
    text = " ".join([link or "", title or "", snippet or ""]).lower()
    score = 0
    if not link:
        return -999
    if any(bad in text for bad in SERPER_BAD_DOMAINS):
        score -= 120
    if "impressum" in text or "kontakt" in text or "contact" in text:
        score += 22
    for term in SERPER_POSITIVE_TERMS:
        if term in text:
            score += 8
    for term in SERPER_NEGATIVE_TERMS:
        if term in text:
            score -= 35
    if company_name:
        tokens = [t for t in re.split(r"\W+", company_name.lower()) if len(t) >= 4]
        score += sum(12 for t in tokens if t in text)
    for term in SMALL_COMPANY_DISCOVERY_TERMS:
        if term in text:
            score += 10
    if is_likely_large_company(company_name, link, text)[0]:
        score -= 200
    if not is_valid_retail_store_builder_contact(
        url=link, name=title or company_name, email="", text=text
    ):
        score -= 400
    if link.startswith("https://"):
        score += 5
    if "/maps/" in link:
        score -= 80
    return score


def _geo_filters_enabled() -> bool:
    """Filtry PLZ/odległości — domyślnie wyłączone (kampania bundesweit)."""
    return bool(ENABLE_REGION_PLZ_FILTER or ENABLE_DISTANCE_FROM_REGION_KM)


def is_germany_de_candidate(link: str, title: str = "", snippet: str = "") -> bool:
    """
    Faza 3: przepuszczaj .de i niemiecką PLZ; odrzucaj tylko silne obce TLD w domenie.
    Słowa typu „Schweiz” w snippetcie nie dyskwalifikują firmy z .de.
    """
    if COUNTRY_RESTRICTION != "DE":
        return True
    dom = get_registrable_domain(link or "")
    if dom in AGGREGATOR_EMAIL_DOMAINS:
        return False
    dom_low = (dom or "").lower()
    if dom_low.endswith(".de"):
        return True
    if any(dom_low.endswith(tld) for tld in _FOREIGN_TLD_SUFFIXES):
        return False
    text = " ".join([link or "", title or "", snippet or ""]).lower()
    if re.search(r"https?://[^/\s]+\.(at|ch|pl|cz|fr|it|nl|be|lu)(/|$)", text):
        return False
    if re.search(r"\b\d{5}\b", text):
        return True
    if any(x in text for x in UA_COUNTRY_HINTS):
        return True
    if ".de/" in text or text.rstrip("/").endswith(".de"):
        return True
    return True


def compute_contact_quality_score(row: dict) -> int:
    score = 0
    if row.get("email_target"):
        score += 45
        email_sc = int(row.get("email_target_score", 0) or 0)
        score += min(25, max(0, email_sc // 2))
    if row.get("phones_found"):
        score += 20
    if row.get("official_website"):
        score += 20
    if row.get("full_address") or row.get("adres"):
        score += 10
    serper_score = int(row.get("serper_source_score", 0) or 0)
    score += min(15, max(0, serper_score // 5))
    return score


def normalize_website(url: str) -> str:
    if not url:
        return ""
    u = url.strip()
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u


def derive_name_from_website(website: str) -> str:
    normalized = normalize_website(website)
    if not normalized:
        return ""
    try:
        host = (urlparse(normalized).netloc or "").lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return ""
    root = host.split(".")[0]
    root = re.sub(r"[^a-z0-9-]+", " ", root, flags=re.IGNORECASE)
    root = root.replace("-", " ")
    root = " ".join(root.split()).strip()
    if not root:
        return ""
    return " ".join(part.capitalize() for part in root.split())


_RETAIL_CHAIN_IN_NAME = (
    "edeka",
    "rewe",
    "netto",
    "aldi",
    "penny",
    "lidl",
    "kaufland",
    "marktkauf",
)
_GENERIC_DOMAIN_ROOTS = frozenset(
    {"google", "facebook", "linkedin", "xing", "wikipedia", "youtube"}
)


def website_base_url(url: str) -> str:
    """Kanoniczna domena firmy: https://nazwa.de (bez ścieżki /referenz/…)."""
    domain = _domain_from_url(url)
    return f"https://{domain}" if domain else normalize_website(url)


def _name_aligns_with_domain(name: str, website: str) -> bool:
    domain_name = derive_name_from_website(website).lower()
    if not domain_name:
        return False
    name_low = (name or "").lower()
    for token in domain_name.split():
        if len(token) >= 4 and token in name_low:
            return True
    domain_root = (_domain_from_url(website) or "").split(".")[0]
    compact_name = re.sub(r"[^a-z0-9]", "", name_low)
    compact_root = re.sub(r"[^a-z0-9]", "", domain_root.lower())
    return len(compact_root) >= 4 and compact_root in compact_name


def should_prefer_domain_company_name(raw_name: str, website: str) -> bool:
    """True = nazwa z www.firma.de zamiast tytułu artykułu / nazwy marketu."""
    raw = " ".join((raw_name or "").split()).strip()
    domain_name = derive_name_from_website(website)
    if not domain_name:
        return False
    domain_root = (_domain_from_url(website) or "").split(".")[0].lower()
    if domain_root in _GENERIC_DOMAIN_ROOTS:
        return False
    if not raw:
        return True
    if _name_aligns_with_domain(raw, website):
        return False
    low = raw.lower()
    if low.startswith(("by ", "von ")):
        return True
    if "," in raw and any(m in low for m in _RETAIL_CHAIN_IN_NAME):
        return True
    if any(m in low for m in _RETAIL_CHAIN_IN_NAME) and not any(
        m in domain_root for m in _RETAIL_CHAIN_IN_NAME
    ):
        return True
    if not _company_name_has_legal_form(raw) and len(raw.split()) >= 3:
        return True
    return False


def clean_company_name(name: str, website: str = "") -> str:
    website = website_base_url(website) if website else ""
    raw = " ".join((name or "").split()).strip(" -|–—")
    text = raw
    if text:
        text = re.split(r"\s+[|–—-]\s+", text, maxsplit=1)[0].strip()
        text = re.sub(
            r"\s+(startseite|homepage|home|wikipedia|firmenliste|hersteller)\s*$",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()
    if text and website and should_prefer_domain_company_name(text, website):
        domain_name = derive_name_from_website(website)
        if domain_name:
            return domain_name
    if not text:
        text = derive_name_from_website(website)
    return text or "Unbekanntes Unternehmen"


def normalize_row_company_name(row: dict) -> dict:
    raw_name = (row.get("nazwa") or row.get("company_name_raw") or "").strip()
    website_hint = website_base_url(
        row.get("official_website") or row.get("www") or row.get("url") or ""
    )
    clean_name = clean_company_name(raw_name, website_hint)
    row["company_name_raw"] = raw_name
    row["company_name_clean"] = clean_name
    row["nazwa"] = clean_name
    return row


def ensure_ssl_cert_env(logger=None) -> None:
    if os.getenv("SSL_CERT_FILE"):
        return
    try:
        import certifi

        cert_path = (certifi.where() or "").strip()
        if not cert_path:
            return
        os.environ["SSL_CERT_FILE"] = cert_path
        os.environ.setdefault("REQUESTS_CA_BUNDLE", cert_path)
        msg = f"SSL_CERT_FILE gesetzt (certifi): {cert_path}"
        if logger:
            logger.info(msg)
        else:
            console_step(msg)
    except Exception as e:
        if logger:
            logger.warning(f"certifi SSL nicht gesetzt: {e}")


def _normalize_href_email(raw: str) -> str:
    """mailto:-Links aus HTML — keine Regex auf Seitentext."""
    low = unquote((raw or "").strip()).lower().replace("%40", "@")
    return normalize_email_contact(low)


def _normalize_href_phone(raw: str) -> str:
    return normalize_phone_contact((raw or "").replace("tel:", "", 1))


CONTACT_DATA_TOKEN_MAX = 40
CONTACT_EMAIL_LOCAL_MIN = 1
CONTACT_EMAIL_LOCAL_MAX = 50
CONTACT_EMAIL_DOMAIN_LABEL_MAX = 50
CONTACT_EMAIL_TOKEN_MAX = CONTACT_EMAIL_LOCAL_MAX
_PAGE_EMAIL_RE = re.compile(
    rf"[a-z0-9._%+\-]{{{CONTACT_EMAIL_LOCAL_MIN},{CONTACT_EMAIL_LOCAL_MAX}}}@"
    rf"[a-z0-9.\-]{{1,{CONTACT_EMAIL_DOMAIN_LABEL_MAX}}}\."
    rf"[a-z0-9\-]{{2,{CONTACT_EMAIL_DOMAIN_LABEL_MAX}}}",
    re.IGNORECASE,
)
_PHONE_TEXT_RE = re.compile(
    rf"(?:\+49|0049|0)[\s\-/]?(?:\(?\d{{1,5}}\)?[\s\-/]?)?[\d\s\-/]{{1,{CONTACT_DATA_TOKEN_MAX}}}\d"
)


def _deobfuscate_contact_text(text: str) -> str:
    out = text or ""
    for pattern, repl in (
        (r"\s*\[at\]\s*", "@"),
        (r"\s*\(at\)\s*", "@"),
        (r"\s+at\s+", "@"),
        (r"\s*\[dot\]\s*", "."),
        (r"\s*\(punkt\)\s*", "."),
        (r"\s+punkt\s+", "."),
        (r"\s*\[punkt\]\s*", "."),
    ):
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    return out


def _email_within_contact_limits(email: str) -> bool:
    if not email or "@" not in email:
        return False
    local, _, domain = email.partition("@")
    if len(local) < CONTACT_EMAIL_LOCAL_MIN or len(local) > CONTACT_EMAIL_LOCAL_MAX:
        return False
    for label in domain.lower().split("."):
        if not label or len(label) > CONTACT_EMAIL_DOMAIN_LABEL_MAX:
            return False
    return True


def _phone_raw_within_contact_limits(raw: str) -> bool:
    return len((raw or "").strip()) <= CONTACT_DATA_TOKEN_MAX


def _find_emails_in_text_regex(text: str) -> list[str]:
    if not text:
        return []
    emails: list[str] = []
    for raw in _PAGE_EMAIL_RE.findall(_deobfuscate_contact_text(text)):
        norm = _normalize_href_email(raw)
        if norm and _email_within_contact_limits(norm) and norm not in emails:
            emails.append(norm)
    return filter_commercial_emails(emails)


def _find_phones_in_text_regex(text: str) -> list[str]:
    if not text:
        return []
    phones: list[str] = []
    for raw in _PHONE_TEXT_RE.findall(text):
        if not _phone_raw_within_contact_limits(raw):
            continue
        norm = _normalize_href_phone(raw)
        if norm and len(norm) <= CONTACT_DATA_TOKEN_MAX and norm not in phones:
            phones.append(norm)
    return phones


def _extract_mailto_tel_from_soup(soup: BeautifulSoup) -> tuple[list[str], list[str]]:
    """Strukturalne mailto:/tel: z HTML — nie regex na całym tekście strony."""
    emails: list[str] = []
    phones: list[str] = []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if href.startswith("mailto:"):
            email = _normalize_href_email(href.replace("mailto:", "", 1))
            if email and _email_within_contact_limits(email) and email not in emails:
                emails.append(email)
        elif href.startswith("tel:"):
            phone = _normalize_href_phone(href)
            if phone and phone not in phones:
                phones.append(phone)
    return emails, phones


def _merge_contact_lists(primary: list[str], extra: list[str]) -> list[str]:
    out = list(primary or [])
    for item in extra or []:
        if item and item not in out:
            out.append(item)
    return out


def _apply_regex_contact_gate(
    emails: list[str], phones: list[str]
) -> tuple[list[str], list[str]]:
    """Końcowa warstwa regex: normalizacja, e-mail local 1–50 znaków, filter_commercial_emails."""
    gated_emails = filter_commercial_emails(
        [
            norm
            for e in emails
            if (norm := _normalize_href_email(e))
            and _email_within_contact_limits(norm)
        ]
    )
    gated_phones: list[str] = []
    for raw in phones:
        norm = _normalize_href_phone(raw)
        if (
            norm
            and len(norm) <= CONTACT_DATA_TOKEN_MAX
            and norm not in gated_phones
        ):
            gated_phones.append(norm)
    return gated_emails, gated_phones


def _row_contact_text_blob(row: dict) -> str:
    return " ".join(
        str(row.get(k) or "")
        for k in (
            "adres",
            "full_address",
            "telefon",
            "phones_found",
            "emails_found",
            "email_target",
            "page_snippet",
            "company_name_clean",
            "nazwa",
            "official_website",
            "www",
        )
    )


def apply_regex_row_contact_cleanup(row: dict) -> dict:
    """
    Po Claude row cleanup: regex na polach wiersza (e-mail local 1–50 znaków, tel do 40).
    """
    blob = _row_contact_text_blob(row)
    emails: list[str] = []
    for part in (blob, row.get("emails_found") or "", row.get("email_target") or ""):
        emails = _merge_contact_lists(emails, _find_emails_in_text_regex(str(part)))
    phones: list[str] = []
    for part in (blob, row.get("phones_found") or "", row.get("telefon") or ""):
        phones = _merge_contact_lists(phones, _find_phones_in_text_regex(str(part)))
    emails, phones = _apply_regex_contact_gate(emails, phones)

    website = (row.get("official_website") or row.get("www") or "").strip()
    if emails:
        row["emails_found"] = ", ".join(emails)
        current = _normalize_href_email((row.get("email_target") or "").strip())
        if current and current in emails:
            row["email_target"] = current
        else:
            best, _ = pick_best_email_for_inquiry(emails, website)
            row["email_target"] = best or ""
    else:
        current = _normalize_href_email((row.get("email_target") or "").strip())
        if not current or not _email_within_contact_limits(current):
            row["email_target"] = ""

    if phones:
        row["phones_found"] = ", ".join(phones)
        current_p = _normalize_href_phone((row.get("telefon") or "").strip())
        row["telefon"] = (
            current_p
            if current_p and current_p in phones
            else phones[0]
        )
    else:
        current_p = _normalize_href_phone((row.get("telefon") or "").strip())
        if not current_p or len(current_p) > CONTACT_DATA_TOKEN_MAX:
            row["telefon"] = ""

    return row


def find_emails_in_text(
    text: str,
    *,
    logger: logging.Logger | None = None,
    cache: dict | None = None,
    page_url: str = "",
    website: str = "",
) -> list[str]:
    """
    E-maile z tekstu strony — wyłącznie regex (deobfuskacja at/punkt).
    mailto: osobno w parse_contacts_from_html; filter_commercial_emails na końcu.
    """
    _ = logger, cache, page_url, website
    if not text:
        return []
    return _find_emails_in_text_regex(text)


_COMPANY_LEGAL_SUFFIX = _COMPANY_LEGAL_FORM_PATTERN
def _pick_best_company_name(
    candidates: list[str], website: str = "", email: str = ""
) -> str:
    cleaned: list[str] = []
    for raw in candidates:
        name = clean_company_name(raw, website)
        if not name or name.lower() == "unbekanntes unternehmen":
            continue
        if is_rejected_company_name_for_export(name, website, email):
            continue
        if name not in cleaned:
            cleaned.append(name)
    if not cleaned:
        return ""

    def score(name: str) -> int:
        s = 0
        low = name.lower()
        if re.search(_COMPANY_LEGAL_SUFFIX, name, re.IGNORECASE):
            s += 40
        if 8 <= len(name) <= 80:
            s += 10
        if website:
            host = get_registrable_domain(website).split(".")[0]
            if host and host in low:
                s += 25
        if any(x in low for x in ("11880", "gelbeseiten", "wikipedia", "beste ", "top 10")):
            s -= 50
        return s

    cleaned.sort(key=score, reverse=True)
    return cleaned[0]


def find_company_names_in_text(
    text: str,
    *,
    logger: logging.Logger | None = None,
    cache: dict | None = None,
    page_url: str = "",
    website: str = "",
) -> list[str]:
    _ = text, logger, cache, page_url, website
    return []


def find_company_name_in_text(
    text: str,
    *,
    logger: logging.Logger | None = None,
    cache: dict | None = None,
    page_url: str = "",
    website: str = "",
) -> str:
    candidates = find_company_names_in_text(
        text,
        logger=logger,
        cache=cache,
        page_url=page_url,
        website=website,
    )
    return _pick_best_company_name(candidates, website, "")


def find_phones_in_text(
    text: str,
    *,
    logger: logging.Logger | None = None,
    cache: dict | None = None,
    page_url: str = "",
    website: str = "",
) -> list[str]:
    """Telefony z tekstu strony — wyłącznie regex."""
    _ = logger, cache, page_url, website
    if not text:
        return []
    return _find_phones_in_text_regex(text)


def _extract_company_names_from_html(soup: BeautifulSoup, base_url: str) -> list[str]:
    names: list[str] = []
    if soup.title and soup.title.string:
        names.append(soup.title.string.strip())
    for prop in ("og:site_name", "og:title"):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            names.append(tag["content"].strip())
    for h1 in soup.find_all("h1", limit=3):
        t = h1.get_text(" ", strip=True)
        if t:
            names.append(t)
    return names


def normalize_phone_for_compare(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def build_company_query_from_row(row: dict) -> str:
    name = (row.get("nazwa") or "").strip()
    if name:
        return name
    category = (row.get("kategoria") or "").strip()
    address = (row.get("full_address") or row.get("adres") or "").strip()
    query = " ".join(x for x in [category, address] if x).strip()
    if query:
        return query
    place_url = (row.get("url") or "").strip()
    if "/maps/place/" in place_url:
        try:
            slug = place_url.split("/maps/place/", 1)[1].split("/", 1)[0]
            slug = slug.replace("+", " ").replace("%20", " ").strip()
            if slug:
                return slug
        except Exception:
            pass
    return ""


def reconcile_contact_sources(row: dict, collected: dict) -> dict:
    maps_phone = (row.get("telefon") or "").strip()
    maps_website = normalize_website(row.get("www", ""))
    website = normalize_website(collected.get("website", ""))
    website_phones = collected.get("phones", []) or []
    maps_phone_norm = normalize_phone_for_compare(maps_phone)
    website_phone_norms = {normalize_phone_for_compare(p) for p in website_phones if p}
    same_phone = bool(maps_phone_norm and maps_phone_norm in website_phone_norms)
    same_website = bool(maps_website and website and maps_website == website)
    if same_phone or same_website:
        row["telefon"] = website_phones[0] if website_phones else ""
        row["www"] = website or row.get("www", "")
        row["contact_source"] = "serper_bs4"
        row["maps_contact_rejected"] = "yes"
    else:
        row["contact_source"] = "maps_or_mixed"
        row["maps_contact_rejected"] = "no"
    if not row.get("telefon") and website_phones:
        row["telefon"] = website_phones[0]
    if not row.get("www") and website:
        row["www"] = website
    website_for_name = website_base_url(
        website or row.get("official_website") or row.get("www") or ""
    )
    if website_for_name:
        row["www"] = website_for_name
        row["official_website"] = website_for_name
    current = (row.get("company_name_clean") or row.get("nazwa") or "").strip()
    if website_for_name and should_prefer_domain_company_name(current, website_for_name):
        domain_clean = derive_name_from_website(website_for_name)
        if domain_clean:
            if not row.get("company_name_raw"):
                row["company_name_raw"] = current
            row["company_name_clean"] = domain_clean
            row["nazwa"] = domain_clean
    else:
        www_company = (collected.get("company_name") or "").strip()
        if www_company:
            weak = (
                not current
                or current.lower() in ("nieznana firma", "unbekanntes unternehmen")
                or len(current) < 6
                or any(
                    x in current.lower() for x in ("http://", "https://", "pdf", "11880")
                )
            )
            if weak or (
                re.search(_COMPANY_LEGAL_SUFFIX, www_company, re.IGNORECASE)
                and not re.search(_COMPANY_LEGAL_SUFFIX, current, re.IGNORECASE)
            ):
                clean = clean_company_name(
                    www_company, website_for_name or website or row.get("www") or ""
                )
                row["company_name_clean"] = clean
                row["nazwa"] = clean
                if not row.get("company_name_raw"):
                    row["company_name_raw"] = current or www_company
    return row


def search_official_website_with_serper(company_name: str, address: str, logger: logging.Logger, cache: dict) -> str:
    query = (company_name or "").strip()
    if not query:
        console_step("Serper übersprungen: leere Anfrage")
        return ""
    serper_cache = cache.setdefault("serper", {})
    if query in serper_cache:
        console_step("Serper Cache Treffer")
        cached = serper_cache[query]
        if isinstance(cached, dict):
            return cached.get("url", "")
        return cached or ""

    api_key = get_serper_api_key()
    if not api_key:
        logger.warning("Kein SERPER_API_KEY.")
        serper_cache[query] = ""
        return ""
    if is_serper_limit_reached_today(cache):
        serper_cache[query] = ""
        return ""
    if is_serper_api_exhausted(cache):
        serper_cache[query] = ""
        return ""
    today, used_today, remaining = get_remaining_daily_serper_limit(cache)
    if remaining <= SERPER_DISCOVERY_RESERVE:
        mark_serper_limit_reached_today(cache)
        serper_cache[query] = ""
        return ""

    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {"q": query, "gl": SERPER_COUNTRY, "hl": SERPER_LANGUAGE, "num": 5}
    try:
        console_step(f"Serper Anfrage: {query}")
        increase_daily_serper_counter(cache, 1)
        resp = request_with_retry(
            requests.post,
            SERPER_API_URL,
            logger,
            headers=headers,
            json=payload,
            timeout=SERPER_TIMEOUT,
        )
        data = resp.json()
    except Exception as e:
        if handle_serper_api_failure(cache, e, logger):
            serper_cache[query] = ""
            return ""
        logger.warning(f"Serper Fehler '{query}': {e}")
        serper_cache[query] = ""
        return ""

    candidates = []
    for k in ("organic", "places"):
        for item in data.get(k, []) or []:
            link = item.get("link") or item.get("website") or ""
            if link:
                candidates.append(
                    {
                        "link": link,
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", ""),
                    }
                )
    best_score = 0
    if candidates:
        scored = [
            (
                score_serper_candidate(
                    c.get("link", ""),
                    c.get("title", ""),
                    c.get("snippet", ""),
                    company_name,
                ),
                c,
            )
            for c in candidates[:5]
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_candidate = scored[0]
        result = normalize_website(best_candidate.get("link", ""))
    else:
        result = ""
    serper_cache[query] = {"url": result, "score": best_score}
    return result


def extract_plz_from_text(text: str) -> list[str]:
    if not text:
        return []
    found = re.findall(r"\b(\d{2})[- ]?(\d{3})\b", text)
    out: list[str] = []
    for a, b in found:
        code = f"{a}{b}"
        if code not in out:
            out.append(code)
    return out


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _normalize_plz_code(plz: str) -> str:
    digits = re.sub(r"\D", "", plz or "")
    if len(digits) == 5:
        return digits
    return ""


def plz_centroid_approx(plz: str) -> tuple[float, float] | None:
    """PLZ-Schwerpunkt (Präfix) – Filter Ostdeutschland."""
    p = _normalize_plz_code(plz)
    if not p or len(p) != 5:
        return None
    prefix = p[:2]
    suffix = int(p[2:])
    bases = {
        "01": (51.050, 13.737),  # Dresden
        "02": (51.152, 14.987),  # Görlitz
        "03": (51.760, 14.334),  # Cottbus
        "04": (51.340, 12.374),  # Leipzig
        "06": (51.482, 11.969),  # Halle
        "07": (50.928, 11.589),  # Jena
        "08": (50.827, 12.921),  # Chemnitz
        "09": (50.610, 12.495),  # Zwickau
        "14": (52.391, 13.066),  # Potsdam
        "15": (52.347, 14.550),  # Frankfurt Oder
        "16": (52.756, 13.030),  # Oranienburg
        "17": (53.629, 13.047),  # Neubrandenburg (nördl. BB)
        "18": (54.088, 12.140),  # Rostock Umkreis / nördl. BB Grenze
        "19": (53.635, 11.397),  # Schwerin Umkreis
        "37": (51.050, 10.715),  # Erfurt süd
        "38": (52.131, 11.627),  # Magdeburg
        "39": (52.272, 11.854),  # Magdeburg Ost
        "98": (50.978, 11.029),  # Erfurt
        "99": (50.684, 10.927),  # Suhl / Südthüringen
    }
    if prefix in bases:
        lat, lon = bases[prefix]
        return (lat, lon)
    return None


def plz_within_region_km(plz: str, max_km: float | None = None) -> bool:
    """PLZ w BB/SN/TH – bei ENABLE_PLZ_PREFIX_REGION_MATCH ohne Leipziger Radius (Dörfer)."""
    max_km = MAX_DISTANCE_FROM_REGION_KM if max_km is None else max_km
    p = _normalize_plz_code(plz)
    if not p:
        return False
    if p[:2] not in DE_EAST_PLZ_PREFIXES:
        return False
    if ENABLE_PLZ_PREFIX_REGION_MATCH:
        return True
    c = plz_centroid_approx(plz)
    if not c:
        return False
    return (
        haversine_km(REGION_CENTER_LAT, REGION_CENTER_LON, c[0], c[1]) <= max_km
    )


def _coords_in_de_de_bbox(lat: float, lon: float) -> bool:
    return (
        DE_DE_BBOX_LAT_MIN <= lat <= DE_DE_BBOX_LAT_MAX
        and DE_DE_BBOX_LON_MIN <= lon <= DE_DE_BBOX_LON_MAX
    )


def location_within_region_km(
    text: str = "",
    lat: float | None = None,
    lon: float | None = None,
    max_km: float | None = None,
) -> bool:
    """BB/SN/TH: PLZ-Präfix, Kleinstädte/Dörfer im Text, oder Koordinaten in Ost-BBox."""
    if not ENABLE_DISTANCE_FROM_REGION_KM and not ENABLE_REGION_PLZ_FILTER:
        return True
    max_km = MAX_DISTANCE_FROM_REGION_KM if max_km is None else max_km

    blob = (text or "").strip()
    blob_low = blob.lower()
    plzs = extract_plz_from_text(blob)
    if plzs and any(plz_within_region_km(p, max_km=max_km) for p in plzs):
        return True

    far_markers = (
        "münchen",
        "muenchen",
        "hamburg",
        "köln",
        "koeln",
        "frankfurt",
        "stuttgart",
        "düsseldorf",
        "duesseldorf",
        "bremen",
        "hannover",
        "nürnberg",
        "nuernberg",
        "westfalen",
        "nrw",
        "bayern",
        "baden-württemberg",
    )
    if any(m in blob_low for m in far_markers):
        return False

    if any(m in blob_low for m in DE_OST_PLACE_MARKERS):
        return True
    if any(m in blob_low for m in DE_OST_RURAL_HINTS):
        return True
    if any(m in blob_low for m in DE_OST_REGION_KEYWORDS):
        return True

    if lat is not None and lon is not None:
        try:
            la, lo = float(lat), float(lon)
            if ENABLE_PLZ_PREFIX_REGION_MATCH and _coords_in_de_de_bbox(la, lo):
                return True
            if ENABLE_DISTANCE_FROM_REGION_KM:
                return (
                    haversine_km(
                        REGION_CENTER_LAT,
                        REGION_CENTER_LON,
                        la,
                        lo,
                    )
                    <= max_km
                )
        except (TypeError, ValueError):
            pass

    return not ENABLE_REGION_PLZ_FILTER


def row_within_region_km(row: dict) -> bool:
    blob = " ".join(
        str(row.get(k) or "")
        for k in ("full_address", "adres", "nazwa", "kategoria", "www", "url")
    )
    lat = row.get("lat_center")
    lon = row.get("lon_center")
    try:
        lat_f = float(lat) if lat not in ("", None) else None
        lon_f = float(lon) if lon not in ("", None) else None
    except (TypeError, ValueError):
        lat_f, lon_f = None, None
    return location_within_region_km(blob, lat=lat_f, lon=lon_f)


def discover_places_with_serper(
    term: str,
    logger: logging.Logger,
    cache: dict,
    *,
    apply_location_filter: bool = True,
    use_places_endpoint: bool = False,
    serper_only: bool = False,
    funnel: dict | None = None,
) -> list[dict]:
    query = term.strip()
    if not use_places_endpoint:
        query = f"{term} {SERPER_DISCOVERY_REGION_SUFFIX}".strip()
    if not query:
        return []
    cached_rows = get_cached_serper_discovery_rows(
        cache, query, use_places_endpoint=use_places_endpoint
    )
    if cached_rows is not None:
        console_step(f"Serper Discovery Cache: {query} ({len(cached_rows)})")
        return [dict(r) for r in cached_rows]

    api_key = get_serper_api_key()
    if not api_key:
        console_step("Serper Discovery: kein API-Key")
        return []
    if is_serper_limit_reached_today(cache):
        console_step("Serper Discovery: Tageslimit")
        return []
    if is_serper_api_exhausted(cache):
        console_step("Serper Discovery: API-Kontingent aufgebraucht")
        return []
    api_url = SERPER_PLACES_API_URL if use_places_endpoint else SERPER_API_URL
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {
        "q": query,
        "gl": SERPER_COUNTRY,
        "hl": SERPER_LANGUAGE,
    }
    if not use_places_endpoint:
        payload["num"] = SERPER_DISCOVERY_RESULTS_PER_TERM
    try:
        label = "Places" if use_places_endpoint else "Discovery"
        console_step(f"Serper {label}: {query}")
        increase_daily_serper_counter(cache, 1)
        if funnel is not None:
            funnel["serper_queries"] = funnel.get("serper_queries", 0) + 1
        resp = request_with_retry(
            requests.post,
            api_url,
            logger,
            headers=headers,
            json=payload,
            timeout=SERPER_TIMEOUT,
        )
        data = resp.json()
    except Exception as e:
        if handle_serper_api_failure(cache, e, logger):
            return []
        console_step(f"Serper Discovery Fehler: {e}")
        return []

    rows = []
    seen = set()
    candidate_filter = (
        is_serper_only_pending_candidate if serper_only else is_loose_serper_discovery_candidate
    )
    buckets: tuple[str, ...] = ("places",) if use_places_endpoint else ("organic", "places")
    for bucket in buckets:
        for item in data.get(bucket, []) or []:
            if funnel is not None:
                funnel["raw_hits"] = funnel.get("raw_hits", 0) + 1
            link = normalize_website(item.get("link") or item.get("website") or "")
            if not link or link in seen:
                continue
            if not is_germany_de_candidate(
                link, item.get("title", ""), item.get("snippet", "")
            ):
                if funnel is not None:
                    funnel["filtered_serper"] = funnel.get("filtered_serper", 0) + 1
                continue
            title = (item.get("title") or "").strip()
            snippet = (item.get("snippet") or item.get("address") or "").strip()
            if not candidate_filter(
                url=link,
                name=title,
                text=f"{title} {snippet}",
                search_term=term,
            ):
                if funnel is not None:
                    funnel["filtered_serper"] = funnel.get("filtered_serper", 0) + 1
                continue
            blob = " ".join([link, title, snippet])
            if apply_location_filter and (
                ENABLE_REGION_PLZ_FILTER or ENABLE_DISTANCE_FROM_REGION_KM
            ):
                if not location_within_region_km(blob):
                    if funnel is not None:
                        funnel["filtered_serper"] = funnel.get("filtered_serper", 0) + 1
                    continue
            company_clean = clean_company_name(item.get("title", ""), link)
            if is_excluded_kontrahent(name=company_clean, url=link, email="")[0]:
                if funnel is not None:
                    funnel["filtered_serper"] = funnel.get("filtered_serper", 0) + 1
                continue
            if is_likely_large_company(company_clean, link, blob)[0]:
                if funnel is not None:
                    funnel["filtered_large_serper"] = funnel.get(
                        "filtered_large_serper", 0
                    ) + 1
                continue
            seen.add(link)
            rows.append(
                {
                    "fraza": term,
                    "nazwa": company_clean,
                    "company_name_raw": (item.get("title") or "").strip(),
                    "company_name_clean": clean_company_name(item.get("title", ""), link),
                    "ocena": "",
                    "liczba_opinii": "",
                    "kategoria": term,
                    "adres": snippet,
                    "full_address": snippet,
                    "page_snippet": f"{title} {snippet}".strip(),
                    "status": "",
                    "telefon": item.get("phoneNumber") or item.get("phone") or "",
                    "www": link,
                    "url": link,
                    "lat_center": "",
                    "lon_center": "",
                }
            )
    store_serper_discovery_rows(
        cache, query, rows, use_places_endpoint=use_places_endpoint
    )
    if funnel is not None and not rows:
        funnel["api_zero_terms"] = funnel.get("api_zero_terms", 0) + 1
    console_step(f"Serper Discovery Ergebnisse '{term}': {len(rows)}")
    return rows


def _is_impressum_url(url: str) -> bool:
    low = (url or "").lower()
    return "impressum" in low or "/imprint" in low


def guess_impressum_urls(base_url: str) -> list[str]:
    """Heurystyka: typowe ścieżki Impressum na tej samej domenie (mail często tylko tam)."""
    base = normalize_website(base_url)
    if not base:
        return []
    try:
        parsed = urlparse(base)
        host = (parsed.netloc or "").lower()
        if not host:
            return []
        scheme = parsed.scheme or "https"
        root = f"{scheme}://{host}"
    except Exception:
        return []
    out: list[str] = []
    for path in IMPRESSUM_GUESS_PATHS:
        full = urljoin(root + "/", path.lstrip("/"))
        if full not in out:
            out.append(full)
    return out


def sort_contact_urls_priority_pl(urls: list[str]) -> list[str]:
    """DE: najpierw Impressum, potem Kontakt; na końcu RODO/Datenschutz."""

    def key(u: str) -> tuple[int, int, str]:
        low = u.lower()
        if any(
            x in low
            for x in (
                "rodo",
                "privacy",
                "datenschutz",
                "dsgvo",
                "ochrona-danych",
                "ochrona_danych",
                "polityka-prywatnosci",
                "polityka_prywatnosci",
                "gdpr",
                "cookies",
                "cookie-richtlinie",
                "regulamin",
            )
        ):
            return (3, len(low), low)
        if _is_impressum_url(low):
            return (0, len(low), low)
        if any(
            x in low
            for x in (
                "kontakt",
                "contact",
                "anfahrt",
                "ofert",
                "wycen",
                "sprzedaz",
                "zapytan",
            )
        ):
            return (1, len(low), low)
        return (2, len(low), low)

    return sorted(urls, key=key)


def collect_impressum_urls(website: str, discovered: list[str] | None = None) -> list[str]:
    """Wszystkie URL Impressum: zgadnięte ścieżki + linki ze strony (bez limitu kontaktów)."""
    seen: set[str] = set()
    out: list[str] = []
    for u in guess_impressum_urls(website):
        if u not in seen:
            seen.add(u)
            out.append(u)
    for u in discovered or []:
        u = (u or "").strip()
        if not u.startswith(("http://", "https://")):
            continue
        if _is_impressum_url(u) and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def merge_contact_subpage_urls(website: str, discovered: list[str]) -> list[str]:
    """Impressum (link + zgadnięte ścieżki) przed innymi podstronami."""
    seen: set[str] = set()
    merged: list[str] = []
    for u in guess_impressum_urls(website) + list(discovered or []):
        u = (u or "").strip()
        if not u.startswith(("http://", "https://")) or u in seen:
            continue
        seen.add(u)
        merged.append(u)
    impressum = [u for u in merged if _is_impressum_url(u)]
    kontakt = [
        u
        for u in merged
        if u not in impressum
        and any(x in u.lower() for x in ("kontakt", "contact"))
    ]
    rest = [u for u in merged if u not in impressum and u not in kontakt]
    ordered = sort_contact_urls_priority_pl(impressum + kontakt + rest)
    return ordered[:MAX_CONTACT_LINKS]


def collect_non_impressum_contact_urls(
    website: str, discovered: list[str] | None = None
) -> list[str]:
    """Kontakt / referenzen — bez Impressum (Impressum ma osobny przebieg)."""
    merged = merge_contact_subpage_urls(website, list(discovered or []))
    return [u for u in merged if not _is_impressum_url(u)][:MAX_CONTACT_LINKS]


def extract_html_text_with_media_hints(soup: BeautifulSoup) -> str:
    """Tekst strony + alt/title/figcaption/src obrazów (zdjęcia marketów)."""
    parts: list[str] = []
    if soup:
        parts.append(soup.get_text(" ", strip=True))
        for img in soup.find_all("img"):
            for attr in ("alt", "title"):
                val = (img.get(attr) or "").strip()
                if val:
                    parts.append(val)
            src = (img.get("src") or img.get("data-src") or "").strip()
            if src:
                parts.append(src)
        for tag in soup.find_all("figcaption"):
            cap = tag.get_text(" ", strip=True)
            if cap:
                parts.append(cap)
    return " ".join(p for p in parts if p)


def parse_contacts_from_html(
    base_url: str,
    html: str,
    *,
    logger: logging.Logger | None = None,
    cache: dict | None = None,
) -> dict:
    """
    Kontakty: 1) parse HTML→text  2) regex e-mail/tel z tekstu  3) mailto/tel z DOM
    4) filter_commercial_emails — ostatni krok (bez LLM).
    """
    soup = BeautifulSoup(html or "", "html.parser")
    page_text = extract_html_text_with_media_hints(soup)
    emails = find_emails_in_text(
        page_text,
        logger=logger,
        cache=cache,
        page_url=base_url,
        website=base_url,
    )
    phones = find_phones_in_text(
        page_text,
        logger=logger,
        cache=cache,
        page_url=base_url,
        website=base_url,
    )
    mailto_emails, tel_phones = _extract_mailto_tel_from_soup(soup)
    emails = _merge_contact_lists(emails, mailto_emails)
    phones = _merge_contact_lists(phones, tel_phones)
    emails, phones = _apply_regex_contact_gate(emails, phones)
    company_candidates = _extract_company_names_from_html(soup, base_url)
    company_candidates.extend(
        find_company_names_in_text(
            page_text,
            logger=logger,
            cache=cache,
            page_url=base_url,
            website=base_url,
        )
    )
    company_name = _pick_best_company_name(company_candidates, base_url, "")
    contact_urls = []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        label = (a.get_text(" ", strip=True) or "").lower()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        if any(k in href.lower() or k in label for k in RETAIL_CONTACT_LINK_KEYWORDS):
            full = urljoin(base_url, href)
            if full.startswith(("http://", "https://")) and full not in contact_urls:
                contact_urls.append(full)
    contact_urls = merge_contact_subpage_urls(base_url, contact_urls)
    return {
        "emails": emails,
        "phones": phones,
        "company_name": company_name,
        "contact_urls": contact_urls,
        "page_text": page_text,
    }


def parse_contacts_from_page(
    url: str, logger: logging.Logger, cache: dict | None = None
) -> dict:
    if not (url or "").strip().lower().startswith(("http://", "https://")):
        return {"emails": [], "phones": [], "contact_urls": [], "page_text": ""}
    console_step(f"Lade Seite: {url}")
    html = _fetch_page_html(url, logger)
    if not html:
        return {"emails": [], "phones": [], "contact_urls": [], "page_text": ""}
    return _parse_html_page_for_crawl(url, html, logger, cache)


def _truncate_page_snippet(text: str, max_chars: int = PAGE_SNIPPET_MAX_CHARS) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 3] + "..."


def _parse_emails_found_field(raw: str) -> list[str]:
    return [
        x.strip()
        for x in (raw or "").split(",")
        if x.strip() and "@" in x
    ]


def log_email_pick_decision(
    logger: logging.Logger,
    *,
    place_url: str = "",
    company_name: str = "",
    website: str = "",
    candidates: list[str] | None = None,
    target: str = "",
    score: int = 0,
    method: str = "none",
    note: str = "",
) -> None:
    """Jedna linia: wybrany mail, score, metoda, ranking kandydatów."""
    cand = list(candidates or [])
    ranked = rank_email_candidates(cand, website or "")
    ranked_txt = ", ".join(f"{e}({s})" for e, s in ranked[:8]) or "(brak)"
    label = (company_name or place_url or website or "?")[:72]
    site_short = (website or place_url or "")[:96]
    if target:
        msg = (
            f"E-mail pick | {label} | {site_short} | "
            f"wybrano={target} score={score} method={method} | "
            f"kandydaci: {ranked_txt}"
        )
        if note:
            msg += f" | {note}"
        logger.info(msg)
        console_step(f"E-mail: {target} (score={score}, {method})")
    else:
        best_score = ranked[0][1] if ranked else 0
        msg = (
            f"E-mail pick | {label} | {site_short} | "
            f"BRAK (min={MIN_EMAIL_SCORE_FOR_SEND}, best={best_score}) | "
            f"kandydaci: {ranked_txt}"
        )
        if note:
            msg += f" | {note}"
        logger.info(msg)


def backfill_emails_in_cache(cache: dict, logger: logging.Logger) -> dict:
    """
    Przelicza email_target z emails_found (nowe reguły Punycode / filtr śmieci).
    Czyści emails_found z fałszywych trafień regex.
    """
    contacts = cache.get("contacts") or {}
    stats = {
        "checked": 0,
        "filled": 0,
        "updated": 0,
        "cleaned_found": 0,
        "unchanged": 0,
        "still_empty": 0,
    }
    for place_url, info in contacts.items():
        if not isinstance(info, dict):
            continue
        stats["checked"] += 1
        raw_found = (info.get("emails_found") or "").strip()
        candidates = filter_commercial_emails(_parse_emails_found_field(raw_found))
        impressum_candidates = filter_commercial_emails(
            _parse_emails_found_field(info.get("impressum_emails_found") or "")
        )
        cleaned_found = ", ".join(candidates)
        if cleaned_found != raw_found:
            info["emails_found"] = cleaned_found
            stats["cleaned_found"] += 1
        website = (info.get("official_website") or place_url or "").strip()
        company = (
            info.get("company_name_clean")
            or info.get("company_name")
            or info.get("company_name_raw")
            or ""
        ).strip()
        old_target = (info.get("email_target") or "").strip().lower()
        target, score, pick_method = pick_email_with_impressum_priority(
            candidates, impressum_candidates, website
        )
        if target and is_non_commercial_email(target):
            target = ""
        if target:
            new_low = target.lower()
            if new_low != old_target:
                if old_target:
                    stats["updated"] += 1
                else:
                    stats["filled"] += 1
                info["email_target"] = target
                info["email_target_score"] = score
                info["email_pick_method"] = (
                    pick_method if pick_method != "none" else "rules_backfill"
                )
                if (info.get("email_status") or "") in (
                    "",
                    "no_suitable_email",
                ):
                    info["email_status"] = "backfilled"
                log_email_pick_decision(
                    logger,
                    place_url=place_url,
                    company_name=company,
                    website=website,
                    candidates=candidates,
                    target=target,
                    score=score,
                    method="rules_backfill",
                    note="backfill",
                )
            else:
                stats["unchanged"] += 1
                if score > int(info.get("email_target_score", 0) or 0):
                    info["email_target_score"] = score
        else:
            stats["still_empty"] += 1
            if candidates and not old_target:
                log_email_pick_decision(
                    logger,
                    place_url=place_url,
                    company_name=company,
                    website=website,
                    candidates=candidates,
                    target="",
                    score=score,
                    method="none",
                    note="backfill_bez_progu",
                )
    logger.info(
        "Backfill e-mail cache: sprawdzono=%s, uzupelniono=%s, zmieniono=%s, "
        "oczyszczono emails_found=%s, bez zmian=%s, nadal pusto=%s",
        stats["checked"],
        stats["filled"],
        stats["updated"],
        stats["cleaned_found"],
        stats["unchanged"],
        stats["still_empty"],
    )
    return stats


def collect_urls_for_www_reverify(
    cache: dict,
    all_rows: list | None = None,
    *,
    reverify_all: bool = False,
) -> list[str]:
    """URL do ponownej weryfikacji www: pending lub cały cache (+ wiersze pipeline)."""
    contacts = cache.get("contacts") or {}
    urls: list[str] = []
    seen: set[str] = set()

    def _add(url: str) -> None:
        u = (url or "").strip()
        if u and u not in seen:
            seen.add(u)
            urls.append(u)

    if reverify_all:
        for url, info in contacts.items():
            if isinstance(info, dict):
                _add(url)
        for row in all_rows or []:
            _add((row.get("url") or row.get("www") or "").strip())
        return urls

    for url, info in contacts.items():
        if not isinstance(info, dict):
            continue
        if (info.get("verification_reason") or "").strip() == PENDING_WWW_VERIFY_REASON:
            _add(url)
    for row in all_rows or []:
        url = (row.get("url") or row.get("www") or "").strip()
        if not url or url in seen:
            continue
        reason = (row.get("verification_reason") or "").strip()
        if reason == PENDING_WWW_VERIFY_REASON and not row.get("retail_verified"):
            _add(url)
    return urls


def verify_pending_contacts(
    cache: dict,
    logger: logging.Logger,
    *,
    all_rows: list | None = None,
    reverify_all: bool = False,
) -> dict:
    """WWW-verify: pending po piatkowym Serper lub ponownie cały cache (--reverify-all-contacts)."""
    contacts = cache.setdefault("contacts", {})
    pending_urls = collect_urls_for_www_reverify(
        cache, all_rows, reverify_all=reverify_all
    )

    stats = {
        "pending": len(pending_urls),
        "verified": 0,
        "rejected": 0,
        "errors": 0,
        "reverify_all": reverify_all,
    }
    if not pending_urls:
        label = "cache" if reverify_all else "pending"
        console_step(f"Verify www: brak rekordów ({label})")
        return stats

    console_step(
        f"Verify www: {len(pending_urls)} URL"
        + (" (cały cache — ponowna weryfikacja)" if reverify_all else " (pending)")
    )
    rows_by_url = index_all_rows_by_url(all_rows or [])
    for url in pending_urls:
        row = rows_by_url.get(url)
        if not row:
            info = contacts.get(url) or {}
            row = {
                "url": url,
                "www": url,
                "nazwa": info.get("company_name") or info.get("company_name_clean") or "",
                "company_name_clean": info.get("company_name_clean") or "",
                "discovery_bundesland": info.get("discovery_bundesland") or "",
            }
            if all_rows is not None:
                all_rows.append(row)
                rows_by_url[url] = row
        try:
            updated = enrich_row_with_contacts(row, cache, logger, force_refresh=True)
            rows_by_url[url] = updated
            if updated.get("retail_verified"):
                stats["verified"] += 1
            else:
                stats["rejected"] += 1
        except Exception as exc:
            stats["errors"] += 1
            logger.warning("Verify pending błąd %s: %s", url, exc)

    logger.info(
        "Verify pending: oczekujących=%s, zweryfikowano=%s, odrzucono=%s, błędy=%s",
        stats["pending"],
        stats["verified"],
        stats["rejected"],
        stats["errors"],
    )
    return stats


def pick_email_with_impressum_priority(
    all_emails: list[str],
    impressum_emails: list[str],
    website: str,
) -> tuple[str, int, str]:
    """
    Najpierw Impressum (obowiązkowe źródło w DE), potem pozostałe podstrony.
    Zwraca (email, score, metoda).
    """
    site = website or ""
    impressum = filter_commercial_emails(list(impressum_emails or []))
    if impressum:
        ws_target, ws_score = pick_best_email_from_website_scrape(impressum, site)
        if ws_target:
            return ws_target, ws_score, "impressum"
        target, score = pick_best_email_for_inquiry(impressum, site)
        if target:
            return target, score, "impressum_rules"

    candidates = filter_commercial_emails(list(all_emails or []))
    target, score = pick_best_email_for_inquiry(candidates, site)
    if target:
        return target, score, "rules"
    if candidates:
        ws_target, ws_score = pick_best_email_from_website_scrape(candidates, site)
        if ws_target:
            return ws_target, ws_score, "website_inbox"
    return "", score if candidates else 0, "none"


def resolve_inquiry_email_target(
    collected: dict,
    website: str,
    company_name: str,
    logger: logging.Logger,
    cache: dict | None,
    *,
    cache_key: str = "",
    retail_verified: bool = False,
    verification_text: str = "",
) -> tuple[str, int, str]:
    """
    Zwraca (email_target, score, metoda).
    metoda: impressum | impressum_rules | rules | website_inbox | none
    """
    candidates = filter_commercial_emails(list(collected.get("emails") or []))
    impressum_candidates = filter_commercial_emails(
        list(collected.get("impressum_emails") or [])
    )
    site = collected.get("website") or website or ""
    snippet = " ".join(
        x for x in (collected.get("page_snippet") or "", verification_text or "") if x
    ).strip()

    target, score, method = pick_email_with_impressum_priority(
        candidates, impressum_candidates, site
    )
    if (
        target
        and not retail_verified
        and not is_valid_retail_store_builder_contact(
            email=target, url=site, name=company_name, text=snippet
        )
    ):
        log_email_pick_decision(
            logger,
            place_url=cache_key,
            company_name=company_name,
            website=site,
            candidates=candidates,
            target="",
            score=score,
            method="blocked_not_store_builder",
            note=f"odrzucono={target}",
        )
        return "", score, "blocked_not_store_builder"

    log_email_pick_decision(
        logger,
        place_url=cache_key,
        company_name=company_name,
        website=site,
        candidates=candidates,
        target=target,
        score=score,
        method=method,
    )
    return target, score, method


def collect_contacts_from_website(
    website: str, logger: logging.Logger, cache: dict | None = None
) -> dict:
    website = normalize_website(website)
    if not website:
        console_step("Keine Website – Kontaktsuche übersprungen")
        return {
            "emails": [],
            "phones": [],
            "company_name": "",
            "website": "",
            "source_urls": [],
            "page_snippet": "",
        }
    console_step(f"Kontakte sammeln (nach WWW-Prüfung): {website}")
    crawl_cache = (cache or {}).get("website_crawl") or {}
    crawl = crawl_cache.get(website)
    if crawl is not None:
        return merge_contacts_from_crawl(crawl, website)

    crawl_result, _ = _crawl_website_for_company(website, logger, cache)
    return merge_contacts_from_crawl(crawl_result, website)


def _assemble_inquiry_email_body(company_name: str, opening: str = "") -> str:
    """Fallback — stały szablon UA gdy Claude niedostępny."""
    _ = company_name, opening
    return FIXED_MATERIAL_INQUIRY_UK.strip()


def generate_email_content(
    company_name: str,
    logger: logging.Logger,
    cache=None,
    *,
    contact_info: dict | None = None,
    place_url: str = "",
):
    """Spersonalizowany mail UA przez Claude (unikalny per firma)."""
    from email_custom_template import inquiry_try_custom
    from ua_claude_inquiry_email import claude_generate_inquiry_email_ua

    display_name = (
        (contact_info or {}).get("company_name_clean")
        or (contact_info or {}).get("company_name")
        or company_name
        or "Постачальник"
    )
    subject_hint = choose_subject_variant(display_name)

    custom = inquiry_try_custom(
        use_custom=USE_CUSTOM_EMAIL_TEMPLATE,
        custom_draft=CUSTOM_EMAIL_DRAFT,
        company_name=display_name,
        lang=CUSTOM_EMAIL_LANG,
        logger=logger,
        subject_hint=subject_hint,
        email_context={
            **(CUSTOM_EMAIL_CONTEXT or {}),
            "city_name": (CUSTOM_EMAIL_CONTEXT or {}).get("city_name") or CUSTOM_EMAIL_CITY,
            "delivery_address": (CUSTOM_EMAIL_CONTEXT or {}).get("delivery_address")
            or DELIVERY_ADDRESS_UA,
        },
        on_step=console_step,
    )
    if custom is not None:
        subject, body = custom
        return sanitize_generated_email(subject, body, display_name)

    if ENABLE_CLAUDE_INQUIRY_EMAIL:
        style = choose_prompt_variant(display_name)
        generated = claude_generate_inquiry_email_ua(
            display_name,
            logger,
            cache,
            contact_info=contact_info,
            cache_key=place_url or (contact_info or {}).get("url") or "",
            style_hint=style,
            on_step=console_step,
        )
        if generated:
            subject, body = generated
            console_step(f"E-mail: Claude UA (personalizowany) → {display_name}")
            return sanitize_generated_email(subject, body, display_name)

    console_step(f"E-mail: stały szablon UA (fallback) → {display_name}")
    return subject_hint, _assemble_inquiry_email_body(display_name)


def send_email_ua_materialy(
    to_email: str,
    subject: str,
    body: str,
    logger: logging.Logger,
) -> tuple[bool, str]:
    """Wysyłka kampanii UA przez yagmail (Gmail lub SMTP z .env). Bez załączników."""
    from mail_transport import merge_mail_cc_recipients, send_smtp_email
    from scraper_env import ENV_MAIL_CC, get_env_value, get_mail_password, get_mail_user

    if not (get_mail_user() and get_mail_password()):
        return False, "brak MAIL_USER / MAIL_PASSWORD"

    cc = merge_mail_cc_recipients(to_email, get_env_value(ENV_MAIL_CC))
    logger.info("UA materialy: Cc=%s | załączniki: brak", ", ".join(cc) if cc else "(brak)")
    return send_smtp_email(
        to_email,
        subject,
        body,
        logger,
        mail_type="UA materialy",
        campaign="ua_materialy",
        cc=cc,
        attachment_paths=[],
    )


def reenrich_contacts_for_mailing(
    all_rows: list[dict],
    cache: dict,
    logger: logging.Logger,
    *,
    refresh_all: bool = False,
) -> None:
    """Ponowne zbieranie e-maili ze stron www przed wysyłką."""
    contacts_cache = cache.setdefault("contacts", {})
    by_url = {str(r.get("url") or ""): r for r in all_rows if r.get("url")}
    urls = set(contacts_cache.keys()) | set(by_url.keys())
    console_step(f"Ponowne wzbogacanie kontaktów: {len(urls)} URL")
    for url in urls:
        if not url:
            continue
        cached = contacts_cache.get(url, {})
        if (
            not refresh_all
            and not DISCOVERY_IGNORE_CONTACT_CACHE
            and (cached.get("email_target") or "").strip()
        ):
            continue
        if refresh_all:
            contacts_cache.pop(url, None)
        seed = dict(by_url.get(url) or {})
        if not seed.get("url"):
            seed["url"] = url
        if not seed.get("www"):
            seed["www"] = cached.get("official_website") or url
        if not seed.get("nazwa"):
            seed["nazwa"] = cached.get("company_name") or cached.get("company_name_clean") or ""
        enriched = enrich_row_with_contacts(seed, cache, logger)
        if url in by_url:
            by_url[url].update(enriched)
        else:
            all_rows.append(enriched)
            by_url[url] = enriched


def _process_email_jobs(
    all_rows: list[dict],
    cache: dict,
    logger: logging.Logger,
    *,
    dry_run_email: bool = False,
    force_resend: bool = False,
    ignore_send_window: bool = False,
) -> None:
    persist_progress(all_rows, cache, logger, reason="vor Mailversand")
    sync_pipeline_rows_to_contacts_cache(all_rows, cache)
    email_jobs = build_email_jobs_from_cache_json(
        logger, force_resend=force_resend, cache=cache
    )
    email_jobs.sort(key=lambda x: x.get("contact_quality_score", 0), reverse=True)
    today, sent_today, remaining = get_remaining_daily_email_limit(cache)
    if remaining <= 0:
        jobs_to_send = []
        jobs_deferred = email_jobs
    else:
        jobs_to_send = email_jobs[:remaining]
        jobs_deferred = email_jobs[remaining:]
    contacts_cache = cache.get("contacts", {})
    rows_by_url = {
        (r.get("url") or "").strip(): r
        for r in all_rows
        if (r.get("url") or "").strip()
    }
    for mail in jobs_to_send:
        target = mail["email_target"]
        domain = get_email_domain(target)
        place_url = mail.get("place_url", "")
        contact_info = dict(contacts_cache.get(place_url) or {})
        row_match = rows_by_url.get(place_url)
        if row_match:
            contact_info = {**pipeline_row_to_contact_info(row_match), **contact_info}
        _em, val_url, val_name, val_text = contact_validation_fields(
            contact_info, place_url
        )
        if (
            not force_resend
            and was_email_target_sent_today(cache, target)
        ):
            status = f"duplicate_skipped_{today}"
        elif is_email_role_based_or_system(target):
            status = f"suppressed_role_based_{today}"
        elif not contact_info.get("retail_verified") and not is_valid_retail_store_builder_contact(
            email=target,
            url=val_url,
            name=val_name,
            text=val_text,
        ):
            status = f"suppressed_not_store_builder_{today}"
            mark_suppressed_target(cache, target, "not_store_builder")
        elif REQUIRE_GENERALUNTERNEHMER and not (
            contact_info.get("is_gu") or is_generalunternehmer(val_text)[0]
        ):
            status = f"suppressed_not_generalunternehmer_{today}"
            mark_suppressed_target(cache, target, "not_generalunternehmer")
        elif not force_resend and is_suppressed_target(cache, target):
            status = f"suppressed_cached_{today}"
        elif not ignore_send_window and not is_within_send_window():
            status = f"deferred_send_window_{today}"
        elif domain:
            _, _, rem_dom = get_domain_remaining_daily_limit(cache, domain)
            if rem_dom <= 0:
                status = f"deferred_domain_limit_{today}"
            else:
                status = None
        else:
            status = None
        if status:
            logger.info("E-mail übersprungen %s: %s", target, status)
            cache.setdefault("contacts", {}).setdefault(mail["place_url"], {})[
                "email_status"
            ] = status
            continue
        if force_resend:
            cache.setdefault("email_suppression", {}).pop(target.lower(), None)
        subject, body = generate_email_content(
            mail.get("company_name", "Firma"),
            logger,
            cache=cache,
            contact_info=cache.get("contacts", {}).get(mail.get("place_url"), {}),
            place_url=mail.get("place_url") or "",
        )
        if dry_run_email:
            ok, info = True, "dry_run"
            status = f"dry_run_{today}"
        else:
            ok, info = send_email_ua_materialy(target, subject, body, logger)
            status = "sent" if ok else f"error: {info}"
            if not ok and is_soft_bounce_or_spam_error(info):
                status = f"soft_fail_spam_{today}"
        if ok:
            increase_daily_email_counter(cache, 1)
            mark_email_target_sent_today(cache, target)
            increase_domain_daily_counter(cache, domain, 1)
        c = cache.setdefault("contacts", {}).setdefault(mail["place_url"], {})
        c["email_subject"] = subject
        c["email_body"] = body
        c["email_status"] = status
        if str(status).strip().lower() == "sent":
            mark_email_sent(
                c,
                subject,
                body=body,
                lang="uk",
                campaign_id="ua_materialy",
            )
        if status.startswith("error:"):
            lowered = status.lower()
            if "mailbox unavailable" in lowered or "user unknown" in lowered:
                mark_suppressed_target(cache, target, status)
        for row in all_rows:
            if row.get("url") == mail["place_url"]:
                row["email_subject"] = subject
                row["email_body"] = body
                row["email_status"] = status
                row["email_target"] = target
                break
        persist_progress(all_rows, cache, logger, reason=f"Mail {target}: {status}")
        if not dry_run_email:
            sleep_between_emails(logger, target)
    for mail in jobs_deferred:
        cache.setdefault("contacts", {}).setdefault(mail["place_url"], {})[
            "email_status"
        ] = f"deferred_{today}"
    persist_progress(all_rows, cache, logger, reason="nach Mailversand")


def enrich_row_with_contacts(
    row: dict,
    cache: dict,
    logger: logging.Logger,
    *,
    force_refresh: bool | None = None,
) -> dict:
    row = normalize_row_company_name(row)
    place_url = row.get("url", "")
    contacts_cache = cache.setdefault("contacts", {})
    refresh = (
        DISCOVERY_IGNORE_CONTACT_CACHE
        if force_refresh is None
        else force_refresh
    )
    if place_url in contacts_cache and not refresh:
        console_step(f"Kontakt-Cache: {row.get('nazwa', '')}")
        cached = contacts_cache[place_url]
        row.update(cached)
        return normalize_row_company_name(row)
    if place_url in contacts_cache and refresh:
        console_step(f"Kontakt neu laden (ignoruj cache): {row.get('nazwa', '')}")

    cached_info = contacts_cache.get(place_url) or {}
    website = normalize_website(row.get("www", "") or row.get("official_website", ""))
    if not website:
        website = normalize_website(cached_info.get("official_website") or "")
    if not website and (place_url or "").strip().lower().startswith(("http://", "https://")):
        website = normalize_website(place_url)
    serper_source_score = 0
    # Serper tylko gdy brak www w JSON/wierszu; przy reverify (force_refresh) nie odświeżamy URL z API
    need_serper = not website
    if website and FORCE_SERPER_LOOKUP and not refresh:
        need_serper = True
    if need_serper:
        serper_query = build_company_query_from_row(row)
        website = search_official_website_with_serper(
            serper_query, row.get("full_address") or row.get("adres", ""), logger, cache
        ) or website

    serper_query = build_company_query_from_row(row)
    serper_cached = cache.setdefault("serper", {}).get(serper_query, {})
    if isinstance(serper_cached, dict):
        serper_source_score = int(serper_cached.get("score", 0) or 0)

    company_for_email = row.get("company_name_clean") or row.get("nazwa") or ""
    serper_blob = " ".join(
        str(row.get(k) or "")
        for k in ("nazwa", "kategoria", "www", "url", "full_address", "adres")
    )

    verification = {
        "verified": False,
        "verification_reason": "keine_website",
        "retail_chains": [],
        "is_small_firm": False,
        "verification_method": "",
        "pages_checked": [],
        "page_snippet": "",
    }
    if website and REQUIRE_WEBSITE_RETAIL_VERIFICATION:
        verification = verify_company_on_website(
            company_for_email,
            website,
            logger,
            cache,
            serper_blob=serper_blob,
            cache_key=place_url or website,
        )
        row["retail_verified"] = verification.get("verified", False)
        row["verification_reason"] = verification.get("verification_reason", "")
        row["retail_chains_found"] = ", ".join(verification.get("retail_chains") or [])
        row["is_small_firm"] = verification.get("is_small_firm", False)
        row["is_gu"] = verification.get("is_gu", False)
        row["gu_marker"] = verification.get("gu_marker", "")
        if not verification.get("verified"):
            console_step(
                f"Odrzucono (brak Einzelhandel/Hochbau-Filialbau): "
                f"{company_for_email} — {row['verification_reason']}"
            )
            skip = {
                "emails": [],
                "phones": [],
                "website": website,
                "source_urls": verification.get("pages_checked") or [],
                "page_snippet": verification.get("page_snippet") or "",
            }
            row = reconcile_contact_sources(row, skip)
            extra = {
                "company_name": company_for_email,
                "official_website": website,
                "retail_verified": False,
                "verification_reason": row["verification_reason"],
                "retail_chains_found": row.get("retail_chains_found", ""),
                "is_small_firm": row.get("is_small_firm", False),
                "email_target": "",
                "email_status": "skipped_no_retail_proof",
            }
            row.update(extra)
            contacts_cache[place_url] = {k: row.get(k) for k in extra if k in row}
            return normalize_row_company_name(row)
    elif website:
        row["retail_verified"] = True
    else:
        row["retail_verified"] = False
        row["verification_reason"] = "keine_website"
        skip = {
            "emails": [],
            "phones": [],
            "website": "",
            "source_urls": [],
            "page_snippet": "",
        }
        row = reconcile_contact_sources(row, skip)
        row["email_status"] = "skipped_no_website"
        return normalize_row_company_name(row)

    collected = (
        collect_contacts_from_website(website, logger, cache=cache)
        if website
        else {
            "emails": [],
            "phones": [],
            "website": "",
            "source_urls": [],
            "page_snippet": "",
        }
    )
    if verification.get("page_snippet"):
        collected["page_snippet"] = verification["page_snippet"]
    row = reconcile_contact_sources(row, collected)
    subject = ""
    body = ""
    mail_status = "not_sent"
    verify_context = " ".join(
        x
        for x in (
            verification.get("page_snippet") or "",
            verification.get("verification_reason") or "",
            " ".join(verification.get("retail_chains") or []),
        )
        if x
    ).strip()
    target_email, email_score, email_pick_method = resolve_inquiry_email_target(
        collected,
        website or "",
        company_for_email,
        logger,
        cache,
        cache_key=place_url,
        retail_verified=bool(row.get("retail_verified")),
        verification_text=verify_context,
    )
    if (
        not target_email
        and ENABLE_CLAUDE_CONTACT_EXTRACT
        and website
    ):
        crawl_text = _get_website_crawl_text(
            website, cache, purpose="contact"
        ) or collected.get("page_snippet") or ""
        if crawl_text.strip():
            from claude_contact_extract import (
                claude_extract_contacts_from_pages,
                merge_claude_contacts_into_collected,
            )

            console_step(
                f"Claude Kontaktsuche (kein E-Mail per Regex): {website}"
            )
            parsed = claude_extract_contacts_from_pages(
                company_for_email,
                website,
                crawl_text,
                logger,
                cache,
                cache_key=place_url,
                on_step=console_step,
            )
            if parsed and (parsed.get("emails") or parsed.get("phones")):
                collected = merge_claude_contacts_into_collected(collected, parsed)
                row = reconcile_contact_sources(row, collected)
                target_email, email_score, email_pick_method = (
                    resolve_inquiry_email_target(
                        collected,
                        website or "",
                        company_for_email,
                        logger,
                        cache,
                        cache_key=place_url,
                        retail_verified=bool(row.get("retail_verified")),
                        verification_text=verify_context,
                    )
                )
                if target_email:
                    email_pick_method = "claude_extract"
    if target_email and is_non_commercial_email(target_email):
        target_email = ""
        email_pick_method = "blocked_institution"
    if is_blocked_non_commercial_row(
        {
            **row,
            "email_target": target_email,
            "www": website,
            "nazwa": company_for_email,
        }
    ):
        target_email = ""
        email_pick_method = "blocked_institution"
        mail_status = "skipped_institution"
    elif not target_email and collected.get("emails"):
        mail_status = "no_suitable_email"
    extra = {
        "company_name": row.get("company_name_clean") or row.get("nazwa", ""),
        "company_name_raw": row.get("company_name_raw", ""),
        "company_name_clean": row.get("company_name_clean", ""),
        "official_website": collected["website"],
        "serper_source_score": serper_source_score,
        "emails_found": ", ".join(collected["emails"]),
        "impressum_emails_found": ", ".join(collected.get("impressum_emails") or []),
        "phones_found": ", ".join(collected["phones"]),
        "contact_sources": ", ".join(collected["source_urls"]),
        "contact_source": row.get("contact_source", "serper"),
        "maps_contact_rejected": row.get("maps_contact_rejected", "no"),
        "email_target": target_email,
        "email_target_score": email_score,
        "email_pick_method": email_pick_method,
        "email_subject": subject,
        "email_body": body,
        "email_status": mail_status,
        "retail_verified": verification.get("verified", False),
        "verification_reason": verification.get("verification_reason", "ok"),
        "retail_chains_found": ", ".join(verification.get("retail_chains") or []),
        "is_small_firm": verification.get("is_small_firm", True),
        "is_gu": verification.get("is_gu", False),
        "gu_marker": verification.get("gu_marker", ""),
    }
    extra["contact_quality_score"] = compute_contact_quality_score({**row, **extra})
    row.update(extra)
    contacts_cache[place_url] = extra
    return row


def _discovery_target_reached(
    all_rows: list,
    *,
    total_new_rows: int,
    rotate_mode: bool,
    serper_only: bool = False,
) -> bool:
    # Tygodniowy pipeline: cel = nowe firmy w runie (nie łączna liczba w Excelu)
    if rotate_mode or serper_only:
        return total_new_rows >= MIN_CONTACTS_TARGET
    return len(all_rows) >= MIN_CONTACTS_TARGET


def _process_serper_terms(
    terms: list[str],
    label: str,
    *,
    all_rows: list,
    seen_global: set,
    cache: dict,
    logger: logging.Logger,
    enable_auto_email: bool,
    apply_distance_filter: bool,
    max_new_rows: int | None,
    total_new_rows: int,
    stop_requested: bool,
    rotate_mode: bool = False,
    serper_only: bool = False,
    discovery_bundesland: str | None = None,
    use_places_endpoint: bool = False,
    funnel: dict | None = None,
) -> tuple[int, bool]:
    """Zwraca (total_new_rows, stop_requested) po przetworzeniu listy fraz Serper."""
    by_url = index_all_rows_by_url(all_rows)
    by_domain = index_all_rows_by_domain(all_rows)
    contacts_cache = cache.setdefault("contacts", {})
    for term in terms:
        if request_stop_on_runtime_limit(logger, console_step_fn=console_step):
            stop_requested = True
            break
        if stop_requested or is_serper_api_exhausted(cache):
            stop_requested = True
            break
        console_step(f"Serper ({label}): {term}")
        rows = discover_places_with_serper(
            term,
            logger,
            cache,
            apply_location_filter=apply_distance_filter,
            use_places_endpoint=use_places_endpoint,
            serper_only=serper_only,
            funnel=funnel,
        )
        if is_serper_api_exhausted(cache):
            stop_requested = True
            break
        added = 0
        refreshed = 0
        for r in rows:
            raw_url = (r.get("url") or "").strip()
            if not raw_url:
                continue
            dom = get_registrable_domain(raw_url)
            base_url = website_base_url(raw_url)
            url = base_url or raw_url
            r["url"] = url
            r["www"] = url
            if discovery_bundesland:
                r["discovery_bundesland"] = discovery_bundesland
                if not (r.get("bundesland") or "").strip():
                    r["bundesland"] = discovery_bundesland
            existing = by_url.get(url) or (by_domain.get(dom) if dom else None)
            if existing and not DISCOVERY_IGNORE_CONTACT_CACHE and url in seen_global:
                continue
            if serper_only and ENABLE_CLAUDE_PAGE_VERIFY:
                r = enrich_row_with_contacts(r, cache, logger)
                if not r.get("retail_verified"):
                    reason = (r.get("verification_reason") or "claude_rejected").strip()
                    console_step(
                        f"Claude: odrzucono ({reason}): {r.get('nazwa', '')}"
                    )
                    if funnel is not None:
                        funnel["rejected_claude_verify"] = (
                            funnel.get("rejected_claude_verify", 0) + 1
                        )
                    continue
            elif serper_only:
                r["retail_verified"] = False
                r["verification_reason"] = PENDING_WWW_VERIFY_REASON
                r["email_target"] = ""
                r["email_status"] = "pending_www_verify"
            elif AUTO_ENRICH_CONTACTS:
                r = enrich_row_with_contacts(r, cache, logger)
            if (
                not serper_only
                and REQUIRE_WEBSITE_RETAIL_VERIFICATION
                and not r.get("retail_verified")
            ):
                reason = (r.get("verification_reason") or "").strip()
                console_step(
                    f"Übersprungen (www: {reason or 'kein GU/Filialbau/Referenzen'}): "
                    f"{r.get('nazwa', '')}"
                )
                continue
            if not (r.get("email_target") or "").strip():
                allow_without_email = EXPORT_PIPELINE_ROWS_WITHOUT_EMAIL and (
                    r.get("retail_verified") or serper_only
                )
                if not allow_without_email:
                    console_step(
                        f"Übersprungen (brak e-mail na www): {r.get('nazwa', '')}"
                    )
                    continue
                console_step(f"Pipeline/Excel (bez e-mail): {r.get('nazwa', '')}")
            if (r.get("email_target") or "").strip() and is_blocked_non_commercial_row(r):
                console_step(
                    f"Übersprungen (Urząd/instytucja, nie firma): {r.get('nazwa', '')}"
                )
                mark_suppressed_target(
                    cache,
                    (r.get("email_target") or "").strip(),
                    "institution",
                )
                continue
            if not is_row_eligible_for_excel_export(r):
                console_step(
                    f"Übersprungen (nie do Excela): {r.get('nazwa', '')}"
                )
                if funnel is not None:
                    funnel["rejected_excel"] = funnel.get("rejected_excel", 0) + 1
                continue
            if (
                apply_distance_filter
                and ENABLE_DISTANCE_FROM_REGION_KM
                and not row_within_region_km(r)
            ):
                continue
            if enable_auto_email and r.get("email_target"):
                r["email_status"] = "queued"
                contacts_cache.setdefault(url, {})["email_status"] = "queued"
            if serper_only and not (
                ENABLE_CLAUDE_PAGE_VERIFY and r.get("retail_verified")
            ):
                snippet_text = (
                    r.get("page_snippet")
                    or r.get("full_address")
                    or r.get("adres")
                    or ""
                ).strip()
                contacts_cache[url] = {
                    "company_name": r.get("nazwa") or "",
                    "company_name_clean": r.get("company_name_clean") or r.get("nazwa") or "",
                    "company_name_raw": r.get("company_name_raw") or "",
                    "official_website": url,
                    "full_address": r.get("full_address") or r.get("adres") or "",
                    "page_snippet": snippet_text,
                    "serper_title": r.get("company_name_raw") or r.get("nazwa") or "",
                    "serper_snippet": snippet_text,
                    "discovery_search_term": r.get("fraza") or r.get("kategoria") or "",
                    "retail_verified": False,
                    "verification_reason": PENDING_WWW_VERIFY_REASON,
                    "discovery_bundesland": discovery_bundesland or "",
                    "email_target": "",
                    "email_status": "pending_www_verify",
                }
            seen_global.add(url)
            if dom:
                seen_global.add(dom)
            if existing:
                existing.update(r)
                refreshed += 1
            else:
                all_rows.append(r)
                by_url[url] = r
                if dom:
                    by_domain[dom] = r
                added += 1
                total_new_rows += 1
                if serper_only and funnel is not None:
                    funnel["pending_saved"] = funnel.get("pending_saved", 0) + 1
            if max_new_rows is not None and total_new_rows >= max_new_rows:
                stop_requested = True
            persist_progress(all_rows, cache, logger, reason=f"serper +{total_new_rows}")
        pending_added = added if serper_only else 0
        _record_serper_term_stat(
            cache,
            term,
            label,
            raw_hits=len(rows),
            pending_added=pending_added,
        )
        suffix = f", odświeżono {refreshed}" if refreshed else ""
        print(f"{term}: +{added}{suffix}")
        persist_progress(all_rows, cache, logger, reason=f"Ende {term}")
        if _discovery_target_reached(
            all_rows,
            total_new_rows=total_new_rows,
            rotate_mode=rotate_mode,
            serper_only=serper_only,
        ):
            metric = (
                f"{total_new_rows} nowych"
                if (rotate_mode or serper_only)
                else f"{len(all_rows)} łącznie"
            )
            console_step(
                f"Cel osiągnięty: {metric} (target {MIN_CONTACTS_TARGET})"
            )
            break
    return total_new_rows, stop_requested


def run_scraper(
    jupyter_mode: bool | None = None,
    max_new_rows: int | None = None,
    enable_auto_email: bool | None = None,
    dry_run_email: bool = False,
    discovery_mode: str = "full",
    force_resend: bool = False,
    ignore_send_window: bool = False,
    rebuild_from_cache: bool = False,
    rotate_oblast: bool = False,
    **_deprecated_kwargs,
):
    if jupyter_mode is None:
        jupyter_mode = is_running_in_jupyter()
    auto_email_explicit = enable_auto_email is not None
    if enable_auto_email is None:
        enable_auto_email = ENABLE_AUTO_EMAIL
    rotate_mode = bool(rotate_oblast and discovery_mode != "emails_only")
    from ua_oblast_rotation import rotation_is_active

    if rotate_oblast and discovery_mode != "emails_only":
        rotate_mode = rotate_mode and rotation_is_active()
    serper_only = discovery_mode == "serper_only"
    if serper_only and discovery_mode != "emails_only":
        console_step(
            "Serper-only discovery: bez crawl www (weryfikacja w niedzielę "
            f"— {PENDING_WWW_VERIFY_REASON})."
        )
    if rotate_mode and enable_auto_email and not auto_email_explicit:
        enable_auto_email = False
        console_step(
            "Rotacja Bundesland: wysyłka maili wyłączona w discovery "
            "(użyj --with-auto-email aby wymusić)."
        )

    logger = setup_logging()
    deprecated = [k for k in _deprecated_kwargs if _deprecated_kwargs.get(k) is not None]
    if deprecated:
        logger.warning(
            "Ignorowane przestarzałe argumenty (moduł tylko Serper): %s",
            ", ".join(deprecated),
        )
    ensure_ssl_cert_env(logger)
    if discovery_mode != "emails_only" and not get_serper_api_key():
        raise RuntimeError("Brak SERPER_API_KEY – moduł wymaga Serper API.")

    rotation_land: str | None = None
    rotation_state: dict | None = None
    rotation_state_path = None
    if rotate_oblast and discovery_mode != "emails_only" and not rebuild_from_cache:
        from ua_oblast_rotation import (
            apply_rotation_to_module,
            commit_rotation_after_run,
            format_rotation_status,
            get_rotation_start_date,
            rotation_is_active,
        )

        if rotation_is_active():
            mod = sys.modules[__name__]
            rotation_land, rotation_state, rotation_state_path = apply_rotation_to_module(
                mod, OUTPUT_DIR
            )
            print(
                f"[ROTACJA] Discovery dla obwodu: {rotation_land} "
                f"(1 obwód / cykl, min. nowych firm={MIN_CONTACTS_TARGET})"
            )
            print(f"[ROTACJA] {format_rotation_status(OUTPUT_DIR)}")
        else:
            print(
                f"[ROTACJA] Włączenie od {get_rotation_start_date().isoformat()} — "
                f"teraz discovery dla wszystkich "
                f"{len(CAMPAIGN_ACTIVE_BUNDESLAENDER)} obwodów."
            )

    logger.info("=== START UA materiały budowlane — hurtownie / składy (Serper API) ===")
    start_scraper_runtime_clock()
    if SCRAPER_MAX_RUNTIME_SECONDS > 0:
        console_step(
            f"Twardy limit czasu: {SCRAPER_MAX_RUNTIME_SECONDS}s "
            f"({SCRAPER_MAX_RUNTIME_SECONDS // 3600}h)"
        )
    print(
        "[START] Scraper UA — hurtownie / składy materiałów budowlanych (Serper API)."
    )
    print(
        f"[MODUS] Jupyter={jupyter_mode} | Auto-Mail={enable_auto_email} | "
        f"DryRun={dry_run_email} | Discovery={discovery_mode} | "
        f"SerperOnly={serper_only} | "
        f"ForceResend={force_resend} | IgnoreWindow={ignore_send_window} | "
        f"RebuildCache={rebuild_from_cache} | "
        f"IgnoreContactCache={DISCOVERY_IGNORE_CONTACT_CACHE}"
    )
    if max_new_rows is not None:
        print(f"[LIMIT] max. nowych wierszy: {max_new_rows}")
    if rotate_mode:
        print(f"[TARGET] min. nowych firm w tym runie: {MIN_CONTACTS_TARGET}")
        print(
            f"[TARGET] min. retail_verified do rotacji landu: "
            f"{MIN_VERIFIED_CONTACTS_ROTATION}"
        )
    else:
        print(f"[TARGET] min. kontaktów: {MIN_CONTACTS_TARGET}")
        print(
            f"[BUNDESWEIT] {len(CAMPAIGN_ACTIVE_BUNDESLAENDER)} Bundesländer: "
            f"{', '.join(CAMPAIGN_ACTIVE_BUNDESLAENDER)}"
        )

    cache = load_cache(logger)
    if serper_only and discovery_mode != "emails_only" and not rebuild_from_cache:
        reset_serper_daily_for_discovery(cache)
        ensure_serper_budget_or_fail(cache)
    if rebuild_from_cache:
        cache_rows = build_all_rows_from_cache(cache)
        existing_rows, _ = load_existing_output(OUTPUT_FILE, logger)
        contacts_n = len(cache.get("contacts", {}) or {})
        if cache_rows:
            all_rows = merge_pipeline_rows(existing_rows, cache_rows)
            console_step(
                f"Excel aus Cache: {len(cache_rows)} z JSON + {len(existing_rows)} z Excel "
                f"→ {len(all_rows)} (contacts={contacts_n})"
            )
        elif existing_rows:
            all_rows = existing_rows
            console_step(
                f"Excel aus Cache: contacts=0 — zachowano {len(existing_rows)} wierszy z Excela"
            )
        else:
            all_rows = []
            console_step(
                f"Excel aus Cache neu: 0 Zeilen (contacts={contacts_n}, pusty Excel)"
            )
        seen_global = build_discovery_seen_urls(all_rows, cache)
        persist_progress(all_rows, cache, logger, reason="rebuild_from_cache")
    else:
        all_rows, _seen_from_file = load_existing_output(OUTPUT_FILE, logger)
        seen_global = build_discovery_seen_urls(all_rows, cache)
    cache_contacts_n = len(cache.get("contacts", {}) or {})
    ignore_note = (
        "ignoruj contacts JSON przy discovery"
        if DISCOVERY_IGNORE_CONTACT_CACHE
        else f"+{cache_contacts_n} URL z contacts JSON w seen"
    )
    console_step(
        f"Start: wierszy={len(all_rows)}, seen={len(seen_global)} ({ignore_note})"
    )
    merged = merge_cache_contacts_into_pipeline(all_rows, cache)
    if merged:
        console_step(
            f"Z cache JSON dopisano {merged} firm do pipeline (łącznie {len(all_rows)})"
        )
        seen_global = build_discovery_seen_urls(all_rows, cache)
    total_new_rows = 0
    stop_requested = False
    funnel = new_discovery_funnel()

    try:
        if discovery_mode == "emails_only":
            console_step("Tylko wysyłka maili z cache (bez wyszukiwania Serper)")
        else:
            serper_kw = dict(
                all_rows=all_rows,
                seen_global=seen_global,
                cache=cache,
                logger=logger,
                enable_auto_email=enable_auto_email,
                max_new_rows=max_new_rows,
                total_new_rows=total_new_rows,
                stop_requested=stop_requested,
                rotate_mode=rotate_mode,
                serper_only=serper_only,
                discovery_bundesland=rotation_land,
                funnel=funnel,
            )
            total_new_rows, stop_requested = _process_serper_terms(
                SERPER_DISCOVERY_TERMS,
                "primary",
                apply_distance_filter=_geo_filters_enabled(),
                **serper_kw,
            )
            if not stop_requested and not _discovery_target_reached(
                all_rows,
                total_new_rows=total_new_rows,
                rotate_mode=rotate_mode,
                serper_only=serper_only,
            ):
                metric = (
                    total_new_rows if (rotate_mode or serper_only) else len(all_rows)
                )
                console_step(
                    f"Za mało kontaktów ({metric}). Fallback Serper bez filtra odległości."
                )
                total_new_rows, stop_requested = _process_serper_terms(
                    SERPER_DISCOVERY_FALLBACK_TERMS,
                    "fallback",
                    apply_distance_filter=False,
                    **serper_kw,
                )
            if not stop_requested and not _discovery_target_reached(
                all_rows,
                total_new_rows=total_new_rows,
                rotate_mode=rotate_mode,
                serper_only=serper_only,
            ):
                metric = (
                    total_new_rows if (rotate_mode or serper_only) else len(all_rows)
                )
                console_step(
                    f"Za mało kontaktów ({metric}). Broad Serper — krótkie frazy."
                )
                total_new_rows, stop_requested = _process_serper_terms(
                    SERPER_DISCOVERY_BROAD_TERMS,
                    "broad",
                    apply_distance_filter=False,
                    **serper_kw,
                )
            if not stop_requested and not _discovery_target_reached(
                all_rows,
                total_new_rows=total_new_rows,
                rotate_mode=rotate_mode,
                serper_only=serper_only,
            ):
                metric = (
                    total_new_rows if (rotate_mode or serper_only) else len(all_rows)
                )
                console_step(
                    f"Za mało kontaktów ({metric}). Landkreis Serper — frazy Kreis."
                )
                total_new_rows, stop_requested = _process_serper_terms(
                    SERPER_DISCOVERY_LANDKREIS_TERMS,
                    "landkreis",
                    apply_distance_filter=False,
                    **serper_kw,
                )
            if (
                not stop_requested
                and ENABLE_SERPER_PLACES_ENDPOINT
                and not _discovery_target_reached(
                    all_rows,
                    total_new_rows=total_new_rows,
                    rotate_mode=rotate_mode,
                    serper_only=serper_only,
                )
            ):
                metric = (
                    total_new_rows if (rotate_mode or serper_only) else len(all_rows)
                )
                console_step(
                    f"Za mało kontaktów ({metric}). Serper Places API."
                )
                total_new_rows, stop_requested = _process_serper_terms(
                    SERPER_DISCOVERY_PLACES_TERMS,
                    "places",
                    apply_distance_filter=False,
                    use_places_endpoint=True,
                    **serper_kw,
                )
            if (
                not stop_requested
                and ENABLE_CLAUDE_DISCOVERY_TERMS
                and _needs_claude_discovery_supplement(
                    all_rows,
                    cache,
                    rotation_land,
                    total_new_rows,
                    rotate_mode=rotate_mode,
                    serper_only=serper_only,
                )
            ):
                console_step(
                    "Za mało wyników po szablonach — uzupełnienie Claude → Serper"
                )
                serper_kw["total_new_rows"] = total_new_rows
                serper_kw["stop_requested"] = stop_requested
                total_new_rows, stop_requested = _run_claude_discovery_supplement(
                    all_rows,
                    cache,
                    logger,
                    rotation_land,
                    serper_kw,
                    funnel,
                )
            if rotate_mode and not _discovery_target_reached(
                all_rows, total_new_rows=total_new_rows, rotate_mode=True
            ):
                console_step(
                    f"Uwaga: znaleziono tylko {total_new_rows} nowych firm "
                    f"(cel {MIN_CONTACTS_TARGET}). Land zostaje do kolejnego tygodnia."
                )
            elif rotate_mode and serper_only:
                pending_land = count_pending_for_bundesland(
                    all_rows, cache, rotation_land or ""
                )
                log_discovery_funnel(funnel, logger)
                console_step(
                    f"Serper-only: {total_new_rows} nowych, "
                    f"{pending_land} pending dla {rotation_land} "
                    f"({PENDING_WWW_VERIFY_REASON})."
                )
                if pending_land < DISCOVERY_MIN_PENDING_GHA_FAIL:
                    if is_serper_api_exhausted(cache):
                        console_step(
                            f"Serper API wyczerpane — kontynuuj z {pending_land} pending "
                            f"(poniżej progu {DISCOVERY_MIN_PENDING_GHA_FAIL})."
                        )
                    elif is_scraper_runtime_limit_reached():
                        console_step(
                            f"Limit czasu — kontynuuj z {pending_land} pending "
                            f"(poniżej progu {DISCOVERY_MIN_PENDING_GHA_FAIL})."
                        )
                    else:
                        raise RuntimeError(
                            f"Za mało kandydatów pending ({pending_land} < "
                            f"{DISCOVERY_MIN_PENDING_GHA_FAIL}) dla {rotation_land}. "
                            "Sprawdź [LEjek] w logu."
                        )
            elif serper_only:
                pending_all = count_all_pending_contacts(all_rows, cache)
                log_discovery_funnel(funnel, logger)
                console_step(
                    f"Serper-only bundesweit: {total_new_rows} nowych, "
                    f"{pending_all} pending ({PENDING_WWW_VERIFY_REASON})."
                )
                if pending_all < DISCOVERY_MIN_PENDING_GHA_FAIL:
                    if is_serper_api_exhausted(cache):
                        console_step(
                            f"Serper API wyczerpane — kontynuuj z {pending_all} pending "
                            f"(poniżej progu {DISCOVERY_MIN_PENDING_GHA_FAIL})."
                        )
                    elif is_scraper_runtime_limit_reached():
                        console_step(
                            f"Limit czasu — kontynuuj z {pending_all} pending "
                            f"(poniżej progu {DISCOVERY_MIN_PENDING_GHA_FAIL})."
                        )
                    else:
                        raise RuntimeError(
                            f"Za mało kandydatów pending ({pending_all} < "
                            f"{DISCOVERY_MIN_PENDING_GHA_FAIL}) w całych Niemczech. "
                            "Sprawdź [LEjek] w logu."
                        )

        if enable_auto_email:
            rows_with_email = sum(
                1 for r in all_rows if (r.get("email_target") or "").strip()
            )
            if discovery_mode == "emails_only" and rows_with_email:
                console_step(
                    f"Wysylka z Excela/cache: pomijam ponowny crawl www "
                    f"({rows_with_email} wierszy z e-mailem)"
                )
            else:
                reenrich_contacts_for_mailing(
                    all_rows,
                    cache,
                    logger,
                    refresh_all=force_resend,
                )
            _process_email_jobs(
                all_rows,
                cache,
                logger,
                dry_run_email=dry_run_email,
                force_resend=force_resend,
                ignore_send_window=ignore_send_window,
            )
    finally:
        if serper_only and discovery_mode != "emails_only" and not rebuild_from_cache:
            from discovery_run_state import record_discovery_run_state

            record_discovery_run_state(
                cache,
                all_rows=all_rows,
                total_new_rows=total_new_rows,
                serper_only=True,
                rotate_mode=rotate_mode,
                campaign_today=campaign_today(),
                serper_daily_limit=SERPER_DAILY_LIMIT,
                serper_discovery_reserve=SERPER_DISCOVERY_RESERVE,
                is_serper_unlimited=is_serper_unlimited(),
                is_serper_limit_reached_today_fn=is_serper_limit_reached_today,
                is_serper_api_exhausted_fn=is_serper_api_exhausted,
                discovery_target_reached_fn=_discovery_target_reached,
            )
        persist_progress(all_rows, cache, logger, reason="Ende Lauf")

    if (
        rotation_land
        and rotation_state is not None
        and rotation_state_path is not None
        and discovery_mode != "emails_only"
        and not serper_only
        and rotation_is_active()
    ):
        from ua_oblast_rotation import commit_rotation_after_run

        verified_n = count_retail_verified_for_bundesland(all_rows, rotation_land)
        if verified_n >= MIN_VERIFIED_CONTACTS_ROTATION:
            nxt = commit_rotation_after_run(
                rotation_state_path, rotation_state, rotation_land
            )
            print(
                f"[ROTACJA] {verified_n} retail_verified dla {rotation_land} "
                f"(≥{MIN_VERIFIED_CONTACTS_ROTATION}). Następny cykl: {nxt}"
            )
        else:
            print(
                f"[ROTACJA] Tylko {verified_n}/{MIN_VERIFIED_CONTACTS_ROTATION} "
                f"retail_verified dla {rotation_land} — land bez przesunięcia."
            )
    elif (
        rotation_land
        and rotation_state is not None
        and serper_only
    ):
        print(
            f"[ROTACJA] Serper-only ({rotation_land}): rotacja bez przesunięcia "
            f"(weryfikacja www w niedzielę, cel {MIN_VERIFIED_CONTACTS_ROTATION} verified)."
        )

    logger.info(f"Fertig. {len(all_rows)} Zeilen -> {OUTPUT_FILE}")
    print(f"\nFertig. {len(all_rows)} Zeilen -> {OUTPUT_FILE}")


def run_in_jupyter(
    enable_auto_email: bool | None = None,
    max_new_rows: int | None = None,
    dry_run_email: bool = True,
    **_deprecated_kwargs,
):
    """Wejście dla Jupyter Lab (tylko Serper API)."""
    if enable_auto_email is None:
        enable_auto_email = ENABLE_AUTO_EMAIL
    console_step(
        f"Jupyter: auto_mail={enable_auto_email}, dry_run={dry_run_email}, discovery=serper_only"
    )
    run_scraper(
        jupyter_mode=True,
        max_new_rows=max_new_rows,
        enable_auto_email=enable_auto_email,
        dry_run_email=dry_run_email,
        discovery_mode="serper_only",
        **_deprecated_kwargs,
    )


def _run_smoke_tests() -> None:
    assert normalize_website("example.de") == "https://example.de"
    assert normalize_website("") == ""
    assert clean_company_name("  GU Ladenbau XY  | Start", "https://bau.de") == "Bau"
    assert (
        clean_company_name(
            "Edeka Fellenzer, Puderbach",
            "https://heger-store.de/referenz/edeka-fellenzer-puderbach/",
        )
        == "Heger Store"
    )
    assert (
        clean_company_name(
            "by bioPress Verlag KG",
            "https://www.biopress.de/de/inhalte/details/10651/",
        )
        == "by bioPress Verlag KG"
    )
    assert website_base_url("https://heger-store.de/referenz/x") == "https://heger-store.de"
    assert extract_bundesland({"bundesland": "Sachsen"}) == "Sachsen"
    assert extract_bundesland({"full_address": "04109 Leipzig"}) == "Sachsen"
    assert haversine_km(REGION_CENTER_LAT, REGION_CENTER_LON, REGION_CENTER_LAT, REGION_CENTER_LON) < 0.01
    assert location_within_region_km("Generalunternehmer Ladenbau Leipzig")
    assert location_within_region_km("Generalunternehmer München")
    assert location_within_region_km("GU Filialbau Köln Nordrhein-Westfalen")
    assert ENABLE_PLZ_PREFIX_REGION_MATCH is False
    assert ENABLE_REGION_PLZ_FILTER is False
    assert "Україна" in INQUIRY_REGION_UA
    assert "цемент" in MATERIAL_CATEGORIES_UA
    assert "будівельних матеріалів" in FIXED_MATERIAL_INQUIRY_UK
    assert "цемент" in FIXED_MATERIAL_INQUIRY_UK or "пісок" in FIXED_MATERIAL_INQUIRY_UK
    assert "будівельних матеріалів" in FIXED_EMAIL_SUBJECT_UK
    assert "MFG" not in FIXED_EMAIL_SUBJECT_UK
    from ua_materialy_inquiry_email_uk import (
        DEFAULT_INQUIRY_PHONE_UK,
        DEFAULT_INQUIRY_SENDER_NAME_UK,
        build_inquiry_signature_uk,
        inquiry_phone,
        inquiry_sender_name,
    )

    assert DEFAULT_INQUIRY_SENDER_NAME_UK == "Свінчак Максим"
    assert DEFAULT_INQUIRY_PHONE_UK == "+380977091141"
    assert inquiry_sender_name() in FIXED_MATERIAL_INQUIRY_UK
    assert inquiry_phone() in build_inquiry_signature_uk()
    assert FIXED_EMAIL_SUBJECT_UK.startswith("Запит")
    assert choose_subject_variant("Test ТОВ") == FIXED_EMAIL_SUBJECT_UK
    assert get_email_attachments_ua_materialy() == []
    assert ENABLE_EMAIL_ATTACHMENT is False
    assert UA_EMAIL_ALLOW_ATTACHMENTS is False
    assert callable(send_email_ua_materialy)
    assert ENABLE_CLAUDE_INQUIRY_EMAIL is True
    body = _assemble_inquiry_email_body("Test ТОВ", "Короткий тест.")
    assert body == FIXED_MATERIAL_INQUIRY_UK.strip()
    from ua_claude_prompts import build_personalized_inquiry_email_prompt_uk

    prompt = build_personalized_inquiry_email_prompt_uk(
        company_name="Будматеріали Київ ТОВ",
        website="https://budmat.ua",
        oblast="Kyiv",
        materials="цемент, пісок",
        page_snippet="Оптовий склад будматеріалів у Києві",
    )
    assert "українською" in prompt.lower() or "українська" in prompt.lower()
    assert "Будматеріали Київ ТОВ" in prompt
    cleaned = sanitize_email_body(FIXED_MATERIAL_INQUIRY_UK)
    assert "\n\n" in cleaned
    assert "Шановні" in cleaned
    assert "З повагою" in cleaned
    assert "Короткий тест" not in body
    assert is_germany_de_candidate("https://firma.ua/kontakt", "Будматеріали Київ", "")
    from contact_extract_utils import parse_contact_extract_response

    parsed_contacts = parse_contact_extract_response(
        '{"company_name":"Muster Bau GmbH","emails":["info@example.de"],'
        '"phones":["+49 341 1234567"],"reason":"ok"}'
    )
    assert parsed_contacts["emails"] == ["info@example.de"]
    assert parsed_contacts["phones"]
    assert "GmbH" in parsed_contacts["company_name"]
    assert ENABLE_CLAUDE_PAGE_VERIFY is True
    assert ENABLE_CLAUDE_CONTACT_EXTRACT is True
    assert CLAUDE_UNLIMITED is True
    assert ENABLE_CLAUDE_ROW_CLEANUP is True
    assert CONTACT_DATA_TOKEN_MAX == 40
    assert CONTACT_EMAIL_LOCAL_MIN == 1
    assert CONTACT_EMAIL_LOCAL_MAX == 50
    assert CONTACT_EMAIL_TOKEN_MAX == 50
    assert ENABLE_CLAUDE_DISCOVERY_TERMS is False
    assert ENABLE_REGION_PLZ_FILTER is False
    assert len(SERPER_DISCOVERY_TERMS) >= 20
    from ua_oblast_rotation import (
        BUNDESLAND_ROTATION_ORDER,
        peek_next_bundesland,
    )

    assert len(BUNDESLAND_ROTATION_ORDER) == 25
    assert peek_next_bundesland() in BUNDESLAND_ROTATION_ORDER
    from mail_transport import merge_mail_cc_recipients

    assert merge_mail_cc_recipients("kontakt@firma.de", "") == []
    assert is_rejected_company_name_for_export(
        "[PDF] X öffentlich nichtöffentlich", "", "shop@pdf-xchange.de"
    )
    assert is_rejected_company_name_for_export("Erfurt", "", "")
    assert is_rejected_company_name_for_export(
        "Max Wiessner Baugeschäft GmbH", "https://maxwiessner.de", "office@maxwiessner.de"
    )
    assert is_excluded_kontrahent(
        name="NEULA GmbH", url="https://neula.de", email="info@neula.de"
    )[0]
    assert _company_name_has_legal_form("Kultbau GmbH")
    assert _company_name_has_legal_form("Müller Filialbau e.K.")
    assert _company_name_has_legal_form("Weber Bau GbR")
    assert not _company_name_has_legal_form("Schmidt e.Kfm.")
    assert not is_rejected_company_name_for_export(
        "Müller Filialbau e.K.", "https://mueller-filialbau.de", "info@mueller-filialbau.de"
    )
    assert not is_rejected_company_name_for_export(
        "Schmidt & Partner GbR", "https://schmidt-bau.de", "kontakt@schmidt-bau.de"
    )
    assert is_non_commercial_email("info@leipzig.de")
    assert is_non_commercial_email("service@thueringen-entdecken.de")
    assert not is_non_commercial_email("office@maxwiessner.de")
    assert is_non_commercial_contact(name="Stadt Leipzig, Dezernat Wirtschaft")
    assert not is_valid_commercial_company_contact(
        email="info@tgzp.de",
        name="Potsdamer Technologie- und Gründerzentren",
    )
    assert not is_valid_commercial_company_contact(
        email="info@ibau.de", name="Generalunternehmer"
    )
    assert is_valid_commercial_company_contact(
        email="info@sus-bau.de",
        url="https://sus-bau.de",
        name="Baufirma SuS Bau",
    )
    assert is_valid_retail_store_builder_contact(
        email="info@budmat.ua",
        url="https://www.budmat.ua/",
        name="Будматеріали Київ ТОВ",
        text="Оптовий склад будматеріалів цемент пісок щебінь каталог ціни доставка",
    )
    assert not is_valid_retail_store_builder_contact(
        email="info@design.ua",
        url="https://design.ua",
        name="Дизайн інтер'єру",
        text="Ремонт квартир під ключ дизайн інтер'єру",
    )
    assert is_valid_retail_store_builder_contact(
        name="Склад будматеріалів",
        url="https://budmat.ua",
        email="info@budmat.ua",
        text="Продаж цементу та піску оптом. Каталог товарів.",
    )
    assert not is_valid_retail_store_builder_contact(
        url="https://www.olx.ua/ogloszenie",
        name="OLX оголошення",
        text="Продам б/у цеглу",
    )
    assert is_media_publisher_contact(
        url="https://www.news.ua/budivnytstvo",
        name="news.ua",
        email="redakcja@news.ua",
    )
    assert not is_loose_serper_discovery_candidate(
        url="https://www.news.ua/budivnytstvo",
        name="news.ua",
        text="Новини будівництва",
    )
    from ua_oblast_keywords import (
        SERPER_DISCOVERY_BROAD_TERMS,
        SERPER_DISCOVERY_LANDKREIS_TERMS,
        SERPER_DISCOVERY_PLACES_TERMS,
        build_region_suffix,
    )

    assert build_region_suffix(["Kyiv"]) == "Україна"
    assert len(SERPER_DISCOVERY_BROAD_TERMS) >= 10
    assert len(SERPER_DISCOVERY_LANDKREIS_TERMS) >= 5
    assert len(SERPER_DISCOVERY_PLACES_TERMS) >= 5
    assert REQUIRE_GENERALUNTERNEHMER is True
    assert PENDING_WWW_VERIFY_REASON == "pending_www_verify"
    assert MIN_VERIFIED_CONTACTS_ROTATION == 20
    assert DISCOVERY_MIN_PENDING_GHA_FAIL == 5
    assert MAX_PAGES_FOR_RETAIL_VERIFICATION >= 8
    from ua_materialy_supplier_filter import is_serper_only_pending_candidate

    assert is_serper_only_pending_candidate(
        name="Склад будматеріалів Львів",
        url="https://budmat-lviv.ua",
        text="будматеріали опт цемент пісок",
    )
    assert not is_serper_only_pending_candidate(
        name="Дизайн студія", url="https://design.ua", text="дизайн інтер'єру"
    )
    assert is_unsuitable_inquiry_email("privacy@firma.ua")
    best, sc = pick_best_email_for_inquiry(
        ["datenschutz@shop.ua", "info@budmat.ua"],
        "https://www.budmat.ua/",
    )
    assert best == "info@budmat.ua" and sc >= MIN_EMAIL_SCORE_FOR_SEND
    assert is_row_eligible_for_excel_export(
        {
            "nazwa": "Будматеріали Київ ТОВ",
            "url": "https://budmat.ua",
            "email_target": "",
            "retail_verified": True,
            "is_gu": True,
            "gu_marker": "будматеріали",
            "verification_reason": "claude_material_supplier",
            "page_snippet": "Оптовий склад будматеріалів цемент пісок",
            "retail_chains_found": "цемент",
        }
    )
    assert not is_row_eligible_for_excel_export(
        {
            "nazwa": "Дизайн інтер'єру",
            "url": "https://design.ua",
            "email_target": "",
            "retail_verified": True,
            "page_snippet": "Ремонт квартир",
        }
    )
    assert len(SERPER_DISCOVERY_TERMS) >= 100
    assert "новини" in SERPER_NEGATIVE_TERMS
    assert SERPER_COUNTRY == "ua"
    assert COUNTRY_RESTRICTION == "UA"
    from http_page_guard import is_waf_blocked

    assert is_waf_blocked(exc=Exception("522 ServerError for url"))
    assert not is_waf_blocked(html="<html><body>Будматеріали ТОВ Київ</body></html>")
    print("_run_smoke_tests: OK")


def main(run_config_path: str | Path | None = None):
    import sys as _sys
    from pathlib import Path as _Path

    launch_kw: dict = {}
    if run_config_path:
        from scraper_run_config import apply_run_config_file, run_scraper_launch_kwargs

        mod = _sys.modules[__name__]
        apply_run_config_file(mod, _Path(run_config_path), _Path(__file__).resolve().parent)
        launch_kw = run_scraper_launch_kwargs(mod)
    run_scraper(
        jupyter_mode=is_running_in_jupyter(),
        **launch_kw,
    )


if __name__ == "__main__":
    import sys

    if "--test" in sys.argv:
        _run_smoke_tests()
    else:
        rc_path = None
        if "--run-config" in sys.argv:
            i = sys.argv.index("--run-config")
            if i + 1 < len(sys.argv):
                rc_path = sys.argv[i + 1]
        extra_kw: dict = {}
        if "--send-emails-only" in sys.argv:
            extra_kw.update(
                {
                    "discovery_mode": "emails_only",
                    "enable_auto_email": True,
                    "dry_run_email": False,
                }
            )
            if SEND_WINDOW_DISABLED:
                extra_kw["ignore_send_window"] = True
            print("[TRYB] Tylko wysyłka maili z cache (bez nowego wyszukiwania).")
        if "--backfill-emails-from-cache" in sys.argv:
            logger = setup_logging()
            cache = load_cache(logger)
            stats = backfill_emails_in_cache(cache, logger)
            save_cache(cache, logger)
            cache_rows = build_all_rows_from_cache(cache)
            existing_rows, _ = load_existing_output(OUTPUT_FILE, logger)
            all_rows = merge_pipeline_rows(existing_rows, cache_rows)
            save_excel(all_rows, OUTPUT_FILE, logger, cache=cache)
            print(
                f"[BACKFILL] cache zapisany → {CACHE_FILE}\n"
                f"  sprawdzono={stats['checked']}, uzupelniono={stats['filled']}, "
                f"zmieniono={stats['updated']}, oczyszczono emails_found={stats['cleaned_found']}, "
                f"nadal bez maila={stats['still_empty']}\n"
                f"  Excel → {OUTPUT_FILE} ({len(all_rows)} wierszy pipeline)"
            )
            raise SystemExit(0)
        if "--verify-pending-contacts" in sys.argv:
            logger = setup_logging()
            cache = load_cache(logger)
            all_rows, _seen_from_file = load_existing_output(OUTPUT_FILE, logger)
            reverify_all = "--reverify-all-contacts" in sys.argv
            if reverify_all:
                print(
                    "[TRYB] Ponowna weryfikacja www wszystkich firm z cache "
                    "(nowe filtry GU / sieci / Impressum)."
                )
            stats = verify_pending_contacts(
                cache,
                logger,
                all_rows=all_rows,
                reverify_all=reverify_all,
            )
            persist_progress(all_rows, cache, logger, reason="verify_pending_contacts")
            from ua_oblast_rotation import (
                commit_rotation_after_run,
                load_rotation_state,
                peek_next_bundesland,
                rotation_is_active,
                rotation_state_path,
            )

            rot_path = rotation_state_path(OUTPUT_DIR)
            rot_state = load_rotation_state(rot_path)
            current_land = peek_next_bundesland(rot_state)
            verified_n = count_retail_verified_for_bundesland(all_rows, current_land)
            pending_n = count_pending_for_bundesland(all_rows, cache, current_land)
            rot_msg = (
                f"[ROTACJA] verified={verified_n}, pending={pending_n} "
                f"(cel {MIN_VERIFIED_CONTACTS_ROTATION}) dla {current_land}"
            )
            if rotation_is_active() and (
                verified_n >= MIN_VERIFIED_CONTACTS_ROTATION
                or pending_n >= MIN_VERIFIED_CONTACTS_ROTATION
            ):
                nxt = commit_rotation_after_run(rot_path, rot_state, current_land)
                rot_msg += f" — przesunięto rotację, następny land: {nxt}"
            else:
                if not rotation_is_active():
                    rot_msg += " — rotacja jeszcze nieaktywna (przed datą startu)"
                else:
                    rot_msg += " — land bez przesunięcia"
            print(
                f"[VERIFY] urls={stats['pending']}, verified={stats['verified']}, "
                f"rejected={stats['rejected']}, errors={stats['errors']}, "
                f"reverify_all={stats.get('reverify_all', False)}\n"
                f"  Excel → {OUTPUT_FILE} ({len(all_rows)} wierszy)\n"
                f"  {rot_msg}"
            )
            raise SystemExit(0)
        if "--rebuild-from-cache" in sys.argv:
            extra_kw["rebuild_from_cache"] = True
            if "discovery_mode" not in extra_kw:
                extra_kw["discovery_mode"] = "emails_only"
            print("[TRYB] Excel i wiersze pipeline z cache JSON (tylko rekordy z E-Mail).")
        if "--purge-institutions" in sys.argv:
            logger = setup_logging()
            cache = load_cache(logger)
            print(
                f"[CACHE] JSON oczyszczony: contacts={len(cache.get('contacts', {}))} "
                f"→ {CACHE_FILE}"
            )
            raise SystemExit(0)
        if "--force-resend" in sys.argv:
            extra_kw["force_resend"] = True
            print("[TRYB] Ponowna wysyłka także do adresów ze statusem sent.")
        if "--ignore-send-window" in sys.argv:
            extra_kw["ignore_send_window"] = True
            print("[TRYB] Wysyłka poza oknem 8–18.")
        if "--dry-run-email" in sys.argv:
            extra_kw["dry_run_email"] = True
            print("[TRYB] Dry-run: treść maili bez faktycznej wysyłki.")
        if "--respect-cache" in sys.argv:
            globals()["DISCOVERY_IGNORE_CONTACT_CACHE"] = False
            print(
                "[TRYB] Discovery respektuje contacts JSON (pomija znane URL, "
                "bez ponownego www)."
            )
        if "--oblast" in sys.argv or "--bundesland" in sys.argv:
            i = sys.argv.index("--oblast") if "--oblast" in sys.argv else sys.argv.index("--bundesland")
            if i + 1 < len(sys.argv):
                bl = sys.argv[i + 1].split(",")
                configure_campaign_bundeslaender(sys.modules[__name__], bl)
                print(f"[TRYB] Aktywne obwody: {', '.join(CAMPAIGN_ACTIVE_BUNDESLAENDER)}")
        if "--rotation-status" in sys.argv:
            from ua_oblast_rotation import format_rotation_status

            print(format_rotation_status(OUTPUT_DIR))
            raise SystemExit(0)
        rotate_bl = "--rotate-oblast" in sys.argv
        if rotate_bl:
            extra_kw["rotate_oblast"] = True
            if "--with-auto-email" in sys.argv:
                extra_kw["enable_auto_email"] = True
            print("[TRYB] Rotacja Bundesland: 1 land na cykl discovery.")
        if "--no-auto-email" in sys.argv:
            extra_kw["enable_auto_email"] = False
            print("[TRYB] Wysyłka maili wyłączona w tym uruchomieniu.")
        if "--serper-only-discovery" in sys.argv:
            extra_kw["discovery_mode"] = "serper_only"
            print(
                "[TRYB] Serper-only: zapis kandydatów bez crawl www "
                f"({PENDING_WWW_VERIFY_REASON})."
            )
        if rc_path:
            from scraper_run_config import apply_run_config_file, run_scraper_launch_kwargs

            mod = sys.modules[__name__]
            apply_run_config_file(mod, Path(rc_path), Path(__file__).resolve().parent)
            try:
                with open(Path(rc_path), encoding="utf-8") as _rcf:
                    apply_ua_run_config_extras(mod, json.load(_rcf))
            except Exception:
                pass
            launch_kw = run_scraper_launch_kwargs(mod)
            launch_kw.update(extra_kw)
            run_scraper(jupyter_mode=is_running_in_jupyter(), **launch_kw)
        else:
            run_scraper(jupyter_mode=is_running_in_jupyter(), **extra_kw)

