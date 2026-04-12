"""
Warstwa wysyłki wiadomości: personalizacja treści, SMTP Gmail i rejestr wysyłek.

Moduł odpowiada za przygotowanie e-maili na podstawie danych kontaktowych,
kontrolę limitów wysyłki oraz oznaczanie statusów w plikach wejściowych.
"""

import logging
import os
import re
import smtplib
import unicodedata
import time
import json
import csv
import random
from email.message import EmailMessage
from glob import glob
from typing import Dict, Mapping, Optional
from urllib.parse import urlparse

import pandas as pd

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency at import time
    OpenAI = None  # type: ignore[assignment]

from domain_blocklist import recipient_domain_is_blocked
from pipeline_logging import setup_logging

logger = logging.getLogger(__name__)
setup_logging("contact_mailer")

# --- Konfiguracja ---
DEFAULT_GMAIL_SENDER_EMAIL = "svinchak1993@gmail.com"


def resolve_sender_email(environ: Optional[Mapping[str, str]] = None) -> str:
    """Adres Gmail do SMTP i pola From: GMAIL_SENDER_EMAIL, potem SENDER_EMAIL, potem domyślny."""
    env = os.environ if environ is None else environ
    raw = env.get("GMAIL_SENDER_EMAIL") or env.get("SENDER_EMAIL")
    if raw is None or not str(raw).strip():
        return DEFAULT_GMAIL_SENDER_EMAIL.strip()
    return str(raw).strip()


SENDER_EMAIL = resolve_sender_email()
SEARCH_DIR = r"C:\Users\svinc\Documents"
PATTERN = "Kontakty*.xlsx"

COL_COMPANY = "Firma"
COL_CITY = "Miasto"
COL_INDUSTRY = "Branża"
COL_ROLE = "Stanowisko / Rola"
COL_WEBSITE = "Strona WWW"
COL_EMAIL = "E-mail rekrutacyjny"
COL_PHONE = "Tel / Kontakt"
COL_MODE = "Tryb pracy"
COL_SOURCE = "Źródło / Portal"
COL_NOTES = "Uwagi"

STATUS_COL = "Email wysłany"
DATE_COL = "Data wysłania"

MAIL_SIGNATORY_NAME = (os.environ.get("MAIL_SIGNATORY_NAME") or "Maksym Swinczak").strip()

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
DRY_RUN = os.environ.get("DRY_RUN", "0").lower() in {"1", "true", "yes"}
OPENAI_MAX_RETRIES = int(os.environ.get("OPENAI_MAX_RETRIES", "3"))
# Treść maila: poniżej progu ponowna próba z ostrzejszą instrukcją (0 = wyłączone).
MAIL_BODY_MIN_CHARS = int(os.environ.get("MAIL_BODY_MIN_CHARS", "400"))
MAIL_BODY_MIN_SENTENCES = int(os.environ.get("MAIL_BODY_MIN_SENTENCES", "4"))
MAIL_BODY_TEMPERATURE = float(os.environ.get("MAIL_BODY_TEMPERATURE", "0.55"))
SMTP_MAX_RETRIES = int(os.environ.get("SMTP_MAX_RETRIES", "3"))
MAX_EMAILS_PER_DAY = int(os.environ.get("MAX_EMAILS_PER_DAY", "40"))
MIN_DELAY_SECONDS = float(os.environ.get("MIN_DELAY_SECONDS", "20"))
MAX_DELAY_SECONDS = float(os.environ.get("MAX_DELAY_SECONDS", "90"))
FETCH_EMAIL_FROM_WEBSITE = os.environ.get("FETCH_EMAIL_FROM_WEBSITE", "0").lower() in {
    "1",
    "true",
    "yes",
}
FETCH_EMAIL_TIMEOUT = float(os.environ.get("FETCH_EMAIL_TIMEOUT", "8"))
ALERT_ON_ERROR_COUNT = int(os.environ.get("ALERT_ON_ERROR_COUNT", "999"))
ALERT_LOG_PATH = os.environ.get("ALERT_LOG_PATH", "").strip()
MAIL_PROMPT_VERSION = os.environ.get("MAIL_PROMPT_VERSION", "").strip()
CAMPAIGN_LOG_ENABLED = os.environ.get("CAMPAIGN_LOG_ENABLED", "1").lower() in {
    "1",
    "true",
    "yes",
}
CAMPAIGN_LOG_PATH = os.environ.get(
    "CAMPAIGN_LOG_PATH",
    os.path.join(
        SEARCH_DIR,
        f"campaign_log_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
    ),
)

SYSTEM_PROMPT = """Jesteś asystentem do pisania profesjonalnych, treściwych maili aplikacyjnych po polsku (kilka logicznych zdań w akapitach — nie jednowierszowe ogólniki).
Cała treść wiadomości musi być w całości po polsku: bez zdań, zwrotów ani pojedynczych słów w języku angielskim lub innym (wyjątek: nazwy własne firm, produktów lub adresy URL dokładnie jak w danych wejściowych).
Bezwzględne reguły (żadnych wyjątków):
- Zakaz halucynacji: nie dopowiadaj faktów o kandydacie, firmie, ofercie, terminach, projektach ani doświadczeniu. Używaj wyłącznie informacji, które wprost wynikają z wiadomości użytkownika (firma, rola, miasto, branża, strona WWW, tryb pracy, uwagi). Jeśli czegoś nie ma w danych — milcz na ten temat.
- W treści maila nie wstawiaj żadnych numerów telefonów ani innych numerów kontaktu (żadnych ciągów cyfr telefonu, „zadzwonię”, „pod numerem”, „kontakt telefoniczny”) — nawet gdyby pojawiły się w surowych danych pomocniczych, ignoruj je w treści.
- Nie wspominaj w treści maila o narzędziach lub usługach zbierania leadów (np. SerpAPI) ani o technicznych metodach znalezienia oferty. Jeśli w danych nie ma konkretnego portalu lub źródła ogłoszenia, nie poruszaj tematu skąd znalazłeś ofertę.
Pisz naturalnie w ramach powyższych ograniczeń.
Podpis: najpierw linia z „Pozdrawiam,” lub „Pozdrawiam”, od następnej linii wyłącznie imię i nazwisko podane w instrukcji użytkownika — bez placeholderów w nawiasach.
Zwróć samą treść maila (bez tematu w środku)."""
SUBJECT_SYSTEM_PROMPT = """Tworzysz krótki temat e-maila aplikacyjnego po polsku.
Cały temat musi być w całości po polsku (bez angielskich słów ani mieszanych języków; nazwy własne firm mogą zostać w oryginale z danych).
Temat ma być konkretny, profesjonalny i spersonalizowany pod firmę/rolę.
Nie używaj w temacie nazw narzędzi zbierania danych (np. SerpAPI). Nie umieszczaj numerów telefonów ani żadnych ciągów cyfr jak numer.
Zwróć tylko temat (jedna linia, bez cudzysłowów)."""

SYSTEM_PROMPT_DE = """Du formulierst professionelle, inhaltlich substanzielle deutsche Bewerbungs-E-Mails (mehrere Sätze in Absätzen — keine Einzeiler mit Allgemeinplätzen).
Der gesamte Nachrichtentext muss durchgehend auf Deutsch sein: keine englischen oder polnischen Sätze oder Einzelwörter (Ausnahme: Eigennamen von Firmen oder Produkten sowie URLs genau wie in den Eingabedaten).
Strikte Regeln (ohne Ausnahme):
- Keine Halluzinationen: keine erfundenen Fakten über den Bewerber, das Unternehmen, die Stelle, Fristen oder Projekte. Nutze ausschließlich Informationen, die sich ausdrücklich aus den Nutzerdaten ergeben (Firma, Rolle, Stadt, Branche, Website, Arbeitsmodell, Hinweise). Fehlt eine Information — nicht erwähnen.
- Im Fließtext der E-Mail keine Telefonnummern und keine anderen Kontaktnummern (keine Ziffernfolgen wie Rufnummern, kein „ich rufe an unter …“, kein „telefonisch unter“) — auch wenn solche Angaben in Hilfsdaten vorkämen, im Text ignorieren.
- Erwähne im Fließtext keine Lead-Tools oder technischen Erfassungsdienste (z. B. SerpAPI). Fehlt ein konkretes Portal oder eine echte Quelle der Stellenausschreibung in den Daten, sprich das Thema „woher die Stelle“ gar nicht an.
Formuliere natürlich innerhalb dieser Grenzen.
Signatur: zuerst die Grußformel „Mit freundlichen Grüßen," oder „Mit freundlichen Grüßen", in der nächsten Zeile ausschließlich der vollständige Name aus der Nutzeranweisung — keine Platzhalter in eckigen Klammern.
Gib nur den E-Mail-Text zurück (ohne Betreff im Text)."""

SUBJECT_SYSTEM_PROMPT_DE = """Du erstellst eine kurze deutsche Betreffzeile für eine Bewerbungs-E-Mail.
Der gesamte Betreff muss auf Deutsch sein (ohne englische Wörter; Firmennamen aus den Daten dürfen original bleiben).
Betreff: konkret, professionell, personalisiert auf Firma/Rolle.
Keine Namen von Datenerfassungs-Tools (z. B. SerpAPI) im Betreff. Keine Telefonnummern und keine ziffernartigen Nummernfolgen im Betreff.
Gib nur eine Zeile Betreff zurück (ohne Anführungszeichen)."""

_GERMAN_HOST_SUFFIXES = (".de", ".at")

FIELD_ALIASES = {
    "company": [COL_COMPANY],
    "city": [COL_CITY],
    "industry": [COL_INDUSTRY, "Branza"],
    "role": [COL_ROLE, "Stanowisko/Rola", "Stanowisko"],
    "website": [COL_WEBSITE, "WWW", "Strona"],
    "email": [COL_EMAIL, "Email", "E-mail"],
    "phone": [COL_PHONE, "Tel/Kontakt", "Telefon", "Tel. kontaktowy", "Tel kontaktowy"],
    "mode": [COL_MODE],
    "source": [COL_SOURCE, "Źródło/Portal", "Zrodlo / Portal"],
    "notes": [COL_NOTES],
}


def _source_column_names_for_context() -> frozenset[str]:
    names = {COL_SOURCE}
    names.update(FIELD_ALIASES.get("source", []))
    return frozenset(names)


def _phone_column_names_for_context() -> frozenset[str]:
    names = {COL_PHONE}
    names.update(FIELD_ALIASES.get("phone", []))
    return frozenset(names)


def _public_source_for_mail_prompt(source: str) -> Optional[str]:
    """
    Tekst „prawdziwego” źródła ogłoszenia do promptów (treść maila, temat, JSON kontekstu).
    None = nie podawaj modelowi źródła (SerpAPI, placeholder, pusto) — bez wzmianki w mailu.
    """
    s = _clean_text(source, "").strip()
    if not s:
        return None
    low = s.lower()
    if low.startswith("(brak"):
        return None
    stripped_paren = low.strip("()")
    if stripped_paren in ("brak źródła", "brak zrodla", "brak"):
        return None
    if low == "serpapi" or low.startswith("serpapi/") or low.startswith("serpapi "):
        return None
    return s


def _redact_source_in_row_context_json(context_json: str) -> str:
    """Usuwa lub zastępuje pole źródła w JSON, żeby model nie widział SerpAPI w kontekście wiersza."""
    try:
        d = json.loads(context_json)
    except (json.JSONDecodeError, TypeError):
        return context_json
    if not isinstance(d, dict):
        return context_json
    changed = False
    for k in list(d.keys()):
        if k in _source_column_names_for_context():
            raw = str(d.get(k, ""))
            pub = _public_source_for_mail_prompt(raw)
            if pub is None:
                if k in d:
                    del d[k]
                    changed = True
            elif pub != raw:
                d[k] = pub
                changed = True
    if not changed:
        return context_json
    return json.dumps(d, ensure_ascii=False, indent=2)


def _redact_phone_in_row_context_json(context_json: str) -> str:
    """Usuwa z JSON kontekstu pola telefonu — model nie ma podawać numerów w treści maila."""
    try:
        d = json.loads(context_json)
    except (json.JSONDecodeError, TypeError):
        return context_json
    if not isinstance(d, dict):
        return context_json
    changed = False
    for k in list(d.keys()):
        if k in _phone_column_names_for_context():
            if k in d:
                del d[k]
                changed = True
    if not changed:
        return context_json
    return json.dumps(d, ensure_ascii=False, indent=2)


def znajdz_excel(search_dir: str, pattern: str) -> str:
    matches = glob(os.path.join(search_dir, pattern))
    if not matches:
        raise FileNotFoundError(f"Nie znaleziono pliku: {pattern} w {search_dir}")
    return max(matches, key=os.path.getmtime)


def normalize_gmail_app_password(raw: Optional[str]) -> str:
    """
    Hasło aplikacji Gmail z panelu Google bywa wyświetlane ze spacjami (4×4 znaki).
    SMTP przyjmuje zwykle 16 znaków bez spacji; usuwamy też białe znaki z brzegów.
    """
    if not raw:
        return ""
    return "".join(str(raw).strip().split())


password = normalize_gmail_app_password(os.environ.get("GMAIL_APP_PASSWORD"))
_client: Optional["OpenAI"] = None

# RFC 5321 (praktyczne limity); domena z co najmniej jedną kropką (TLD) — typowe dla SMTP rekrutacyjnego.
MAX_EMAIL_ADDRESS_LEN = 254
MAX_EMAIL_LOCAL_LEN = 64
MAX_EMAIL_DOMAIN_LEN = 253
# Część lokalna: litera/cyfra lub …środek z ._%+-… i końcowa litera/cyfra (min. 1 znak).
_LOCAL_PART_RE = re.compile(
    r"\A(?:[a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9._%+\-]{0,62}[a-zA-Z0-9])\Z",
    re.IGNORECASE,
)
_DOMAIN_LABEL = r"[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
_DOMAIN_FULL_RE = re.compile(
    rf"\A(?:{_DOMAIN_LABEL})(?:\.(?:{_DOMAIN_LABEL}))+\Z",
    re.IGNORECASE,
)

MAX_STATUS_LEN = 240


def _get_openai_client() -> "OpenAI":
    global _client
    if _client is not None:
        return _client
    if OpenAI is None:
        raise RuntimeError("Brak biblioteki openai. Zainstaluj: pip install openai")

    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Brak OPENAI_API_KEY w zmiennych środowiskowych.")

    _client = OpenAI(api_key=api_key)
    return _client


def _clean_text(value, fallback: str = "") -> str:
    if pd.isna(value):
        return fallback
    text = str(value).strip()
    if text.lower() in {"nan", "none", ""}:
        return fallback
    return text


def _safe_status(text: str) -> str:
    clean = _clean_text(text)
    if len(clean) <= MAX_STATUS_LEN:
        return clean
    return clean[: MAX_STATUS_LEN - 3] + "..."


def _already_sent(value) -> bool:
    if pd.isna(value):
        return False
    return _clean_text(value).lower() in {"tak", "yes", "true", "1"}


def normalize_recipient_email(raw: str) -> str:
    """
    Obcina białe znaki, normalizuje Unicode (NFKC), wyciąga adres z formy
    „Jan Kowalski <jan@firma.pl>”.
    """
    s = _clean_text(raw, "")
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    m = re.search(r"<([^<>\s]+@[^<>\s]+)>", s)
    if m:
        s = m.group(1).strip()
    return s.strip()


def _is_valid_email(email: str) -> bool:
    s = normalize_recipient_email(email)
    if not s or len(s) > MAX_EMAIL_ADDRESS_LEN:
        return False
    if s.count("@") != 1:
        return False
    local, domain = s.split("@", 1)
    if not local or not domain:
        return False
    if len(local) > MAX_EMAIL_LOCAL_LEN or len(domain) > MAX_EMAIL_DOMAIN_LEN:
        return False
    if "." not in domain:
        return False
    if not _LOCAL_PART_RE.match(local):
        return False
    if not _DOMAIN_FULL_RE.match(domain):
        return False
    return True


def try_resolve_email_from_website(current_email: str, website: str) -> tuple[str, bool]:
    """
    Gdy brak poprawnego e-maila, a jest strona WWW — próba pobrania adresu z witryny
    (mailto + tekst strony, kilka typowych ścieżek). Wymaga FETCH_EMAIL_FROM_WEBSITE=1.

    Zwraca (email, True) jeśli uzupełniono ze strony, w przeciwnym razie (wartość wejściowa lub "", False).
    """
    cur = _clean_text(current_email, "")
    if cur and _is_valid_email(cur):
        return normalize_recipient_email(cur), False
    if not FETCH_EMAIL_FROM_WEBSITE:
        return cur, False
    w = _clean_text(website, "")
    if not w or w.lower().startswith("(brak"):
        return cur, False
    try:
        import build_contacts_serpapi as serp
    except Exception:
        return cur, False
    found = _clean_text(serp._extract_recruit_email_from_site(w, timeout=FETCH_EMAIL_TIMEOUT), "")
    if found and _is_valid_email(found):
        return normalize_recipient_email(found), True
    return cur, False


def maybe_error_alert(stats: Dict[str, int], prefix: str = "") -> None:
    """Gdy openai_errors+smtp_errors >= ALERT_ON_ERROR_COUNT — komunikat + opcjonalnie zapis do pliku."""
    if ALERT_ON_ERROR_COUNT <= 0:
        return
    err = stats.get("openai_errors", 0) + stats.get("smtp_errors", 0)
    if err < ALERT_ON_ERROR_COUNT:
        return
    msg = f"{prefix}UWAGA: OpenAI+SMTP błędy={err} (próg alertu={ALERT_ON_ERROR_COUNT})"
    logger.warning("%s", msg)
    if ALERT_LOG_PATH:
        try:
            with open(ALERT_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"{pd.Timestamp.now().isoformat()} {msg}\n")
        except OSError:
            pass


def _count_probable_sentences(text: str) -> int:
    """Szacuje liczbę zdań (PL/DE); filtruje bardzo krótkie fragmenty po podziale na . ! ?"""
    if not (text or "").strip():
        return 0
    parts = re.split(r"[.!?]+", text)
    return sum(1 for p in parts if len(p.strip()) >= 20)


def _mail_body_too_short(body: str) -> bool:
    if MAIL_BODY_MIN_CHARS <= 0 and MAIL_BODY_MIN_SENTENCES <= 0:
        return False
    t = (body or "").strip()
    if MAIL_BODY_MIN_CHARS > 0 and len(t) < MAIL_BODY_MIN_CHARS:
        return True
    if MAIL_BODY_MIN_SENTENCES > 0 and _count_probable_sentences(t) < MAIL_BODY_MIN_SENTENCES:
        return True
    return False


_MAIL_LENGTH_RETRY_HINT_PL = (
    "Poprzednia wersja była zbyt krótka lub zbyt ogólnikowa. Przepisz cały mail od zera:\n"
    "- minimum 5 pełnych zdań w 2–3 akapitach,\n"
    "- co najmniej ok. 450 znaków z treścią merytoryczną (nie licząc samego podpisu),\n"
    "- odnieś się konkretnie do firmy lub roli z danych; unikaj jednego zdania bez treści.\n"
    "- bez numerów telefonu w treści; bez wymyślonych faktów — tylko dane z instrukcji."
)

_MAIL_LENGTH_RETRY_HINT_DE = (
    "Die vorherige Version war zu kurz oder zu allgemein. Schreiben Sie die gesamte E-Mail neu:\n"
    "- mindestens 5 vollständige Sätze in 2–3 Absätzen,\n"
    "- mindestens ca. 450 Zeichen inhaltlicher Text (ohne bloße Grußzeile),\n"
    "- konkreter Bezug zu Firma/Rolle aus den Daten; keine Ein-Satz-Floskeln.\n"
    "- keine Telefonnummern im Text; keine erfundenen Fakten — nur die Nutzerdaten."
)


def _website_hostname(website: str) -> str:
    u = _clean_text(website, "")
    if not u or u == "(brak strony www)":
        return ""
    low = u.lower()
    if not low.startswith(("http://", "https://")):
        u = "https://" + u
    try:
        host = urlparse(u).hostname or ""
    except Exception:
        return ""
    return host.lower()


def _mail_locale(website: str, email: str = "") -> str:
    """'de' dla domeny strony lub adresu e-mail koncowego na .de / .at; inaczej 'pl'."""
    host = _website_hostname(website)
    for suf in _GERMAN_HOST_SUFFIXES:
        if host.endswith(suf):
            return "de"
    em = _clean_text(email, "").lower()
    if "@" in em:
        dom = em.split("@", 1)[1]
        for suf in _GERMAN_HOST_SUFFIXES:
            if dom.endswith(suf):
                return "de"
    return "pl"


def _resolve_excel_path() -> str:
    return znajdz_excel(SEARCH_DIR, PATTERN)


def _resolve_cv_path() -> str:
    cv_patterns = (
        "CV*.pdf",
        "cv*.pdf",
        "*CV*.pdf",
        "*cv*.pdf",
        "*resume*.pdf",
        "*Resume*.pdf",
    )
    cv_env = os.environ.get("CV_PATH", "").strip()
    if cv_env:
        if os.path.isfile(cv_env):
            return cv_env
        if os.path.isfile(cv_env + ".pdf"):
            return cv_env + ".pdf"
        if os.path.isdir(cv_env):
            env_candidates = []
            for pattern in cv_patterns:
                env_candidates.extend(glob(os.path.join(cv_env, pattern)))
            if env_candidates:
                return max(env_candidates, key=os.path.getmtime)

    candidates = []
    for pattern in cv_patterns:
        candidates.extend(glob(os.path.join(SEARCH_DIR, pattern)))

    # CV często leży w Documents\CV (nie w korzeniu Documents)
    for sub in ("CV", "cv", "Curriculum", "Resume", "resumes"):
        subdir = os.path.join(SEARCH_DIR, sub)
        if os.path.isdir(subdir):
            for pattern in cv_patterns:
                candidates.extend(glob(os.path.join(subdir, pattern)))

    if not candidates:
        env_hint = f" CV_PATH='{cv_env}'." if cv_env else ""
        raise FileNotFoundError(
            "Nie znaleziono CV. Ustaw zmienną środowiskową CV_PATH na plik PDF."
            + env_hint
        )
    return max(candidates, key=os.path.getmtime)


def _now_for_excel() -> pd.Timestamp:
    # Sekundy zapewniaja zgodnosc z kolumnami datetime64[s] i [ns].
    return pd.Timestamp.now().floor("s")


def _first_existing_column(df: pd.DataFrame, aliases: list[str]) -> Optional[str]:
    for col in aliases:
        if col in df.columns:
            return col
    return None


def _resolve_column_map(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    col_map: Dict[str, Optional[str]] = {}
    for field, aliases in FIELD_ALIASES.items():
        col_map[field] = _first_existing_column(df, aliases)
    return col_map


def _row_value(row: pd.Series, column_name: Optional[str], fallback: str = "") -> str:
    if not column_name:
        return fallback
    return _clean_text(row.get(column_name), fallback)


def _attach_cv(msg: EmailMessage, cv_path: str) -> None:
    with open(cv_path, "rb") as f:
        data = f.read()
    msg.add_attachment(
        data,
        maintype="application",
        subtype="pdf",
        filename=os.path.basename(cv_path),
    )


def _build_row_context(row: pd.Series) -> str:
    context: Dict[str, str] = {}
    for col in row.index:
        val = _clean_text(row.get(col), "")
        if val:
            context[str(col)] = val
    return json.dumps(context, ensure_ascii=False, indent=2)


def _build_row_context_for_generation(row: pd.Series, website: str) -> str:
    """Kontekst wiersza; opcjonalnie skrót publicznej strony WWW (ENABLE_WEB_PAGE_CONTEXT=1)."""
    base = _redact_phone_in_row_context_json(
        _redact_source_in_row_context_json(_build_row_context(row))
    )
    try:
        from web_page_context import append_page_excerpt_to_context_json
    except ImportError:
        return base
    return append_page_excerpt_to_context_json(base, website)


def _should_offer_b2b(industry: str, source: str, notes: str) -> bool:
    hay = f"{industry} {source} {notes}".lower()
    tokens = (
        "sklep internetowy",
        "e-commerce",
        "ecommerce",
        "shopify",
        "woocommerce",
        "magento",
    )
    return any(t in hay for t in tokens)


def _detect_contract_preference(mode: str, source: str, notes: str) -> str:
    hay = f"{mode} {source} {notes}".lower()
    uop_tokens = ("uop", "umowa o pracę", "umowa o prace")
    b2b_tokens = ("b2b", "kontrakt", "działalność", "dzialalnosc")
    has_uop = any(t in hay for t in uop_tokens)
    has_b2b = any(t in hay for t in b2b_tokens)

    if has_uop and has_b2b:
        return "UOP"
    if has_b2b:
        return "B2B"
    if has_uop:
        return "UOP"
    return "AUTO"


def _count_sent_today(df: pd.DataFrame) -> int:
    if STATUS_COL not in df.columns or DATE_COL not in df.columns:
        return 0
    today = pd.Timestamp.now().date()
    sent_count = 0
    for _, row in df.iterrows():
        if not _already_sent(row.get(STATUS_COL)):
            continue
        date_value = row.get(DATE_COL)
        try:
            ts = pd.to_datetime(date_value)
            if pd.notna(ts) and ts.date() == today:
                sent_count += 1
        except Exception:
            continue
    return sent_count


def _append_campaign_log(
    log_path: str,
    email: str,
    company: str,
    subject: str,
    status: str,
    reason: str = "",
) -> None:
    if not CAMPAIGN_LOG_ENABLED:
        return
    directory = os.path.dirname(log_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    write_header = not os.path.exists(log_path)
    with open(log_path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp",
                "email",
                "firma",
                "subject",
                "status",
                "reason",
            ],
        )
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": pd.Timestamp.now().isoformat(),
                "email": email,
                "firma": company,
                "subject": subject,
                "status": status,
                "reason": reason,
            }
        )


def _apply_send_delay() -> None:
    low = max(0.0, min(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS))
    high = max(0.0, max(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS))
    delay = random.uniform(low, high)
    time.sleep(delay)


def _send_message_with_retry(smtp: smtplib.SMTP_SSL, msg: EmailMessage) -> None:
    last_error: Optional[Exception] = None
    retries = max(1, SMTP_MAX_RETRIES)
    for attempt in range(1, retries + 1):
        try:
            smtp.send_message(msg)
            return
        except Exception as e:
            last_error = e
            if attempt < retries:
                time.sleep(0.7)

    assert last_error is not None
    raise RuntimeError(f"SMTP nie wysłał wiadomości po {retries} próbach: {last_error}")


def _smtp_quit_safe(smtp: Optional[smtplib.SMTP_SSL]) -> None:
    """Zamknij sesję SMTP bez wyjątku, gdy serwer już rozłączył (np. przed quit())."""
    if smtp is None:
        return
    try:
        smtp.quit()
    except (smtplib.SMTPServerDisconnected, OSError, smtplib.SMTPException, EOFError):
        try:
            smtp.close()
        except Exception:
            pass


def _resolved_cv_download_url() -> str:
    """
    Link do CV w promptach generowania treści (OpenAI).
    Gdy zmienna CV_DOWNLOAD_URL nie jest ustawiona w środowisku — domyślny publiczny link.
    Gdy CV_DOWNLOAD_URL jest ustawione na pusty string — bez linku w instrukcjach (tylko załącznik).
    """
    raw = os.environ.get("CV_DOWNLOAD_URL")
    if raw is not None:
        return str(raw).strip()
    return (
        "https://drive.google.com/file/d/15V22fA-VOlprVRW4fYyYFv_daHbolgyt/"
        "view?usp=drive_link"
    )


def wygeneruj_tresc_maila(
    company: str,
    role: str,
    city: str,
    industry: str,
    website: str,
    phone: str,
    mode: str,
    source: str,
    notes: str,
    row_context: str,
    offer_b2b: bool,
    contract_preference: str,
    locale: str = "pl",
    extra_user_instruction: str = "",
) -> str:
    loc = "de" if locale == "de" else "pl"
    cv_url = _resolved_cv_download_url()

    src_pub = _public_source_for_mail_prompt(source)
    source_line_de = (
        f"- Quelle/Portal der Stellenausschreibung (nur wenn relevant, nicht erfinden): {src_pub}\n"
        if src_pub
        else "- Keine konkrete Jobbörse/Quelle in den Daten — erwähnen Sie keine technischen Suchwerkzeuge und keine erfundene Quelle.\n"
    )

    if loc == "de":
        b2b_instruction = (
            "- schlagen Sie konkret eine B2B-Zusammenarbeit in Datenanalyse/E-Commerce vor"
            if offer_b2b
            else "- Fokus auf Bewerbung (Festanstellung/Projekt) ohne kommerzielles Angebot"
        )
        contract_instruction = (
            "- bevorzugen Sie in der Ansprache ein Angestelltenverhältnis (UOP), wenn die Ausschreibung UOP und B2B anbietet"
            if contract_preference == "UOP"
            else "- bevorzugen Sie B2B, weil die Ausschreibung nur B2B nennt"
            if contract_preference == "B2B"
            else "- keine feste Vertragsform, wenn sich das aus den Daten nicht eindeutig ergibt"
        )
        cv_goal_de = (
            "- Sie bewerben sich auf die Stelle und signalisieren Interesse an einem Vorstellungsgespräch\n"
            f"- Sie teilen mit, dass Sie den Lebenslauf im Anhang senden und auf diesen Download-Link verweisen; "
            f"übernehmen Sie die URL exakt so in den Fließtext (Zeichen für Zeichen, nicht kürzen): {cv_url}"
            if cv_url
            else "- Sie bewerben sich auf die Stelle und signalisieren Interesse an einem Vorstellungsgespräch\n"
            "- Sie teilen mit, dass Sie den Lebenslauf im Anhang senden"
        )
        user_prompt = f"""Schreiben Sie eine ausführliche, personalisierte Bewerbungs-E-Mail auf Deutsch (mindestens 4–7 inhaltliche Sätze in 2–3 Absätzen, keine Einzeiler).

Ziel:
{cv_goal_de}

Daten Firma/Stelle (ausschließlich diese Angaben für den Fließtext verwenden, nichts dazuerfinden):
- Firma: {company}
- Rolle: {role}
- Stadt: {city}
- Branche: {industry}
- Website: {website}
- Arbeitsmodell: {mode}
{source_line_de}- Hinweise: {notes}

Vollständige Zeilendaten (JSON):
{row_context}

Anforderungen:
- gesamter E-Mail-Text ausschließlich auf Deutsch (keine englischen oder polnischen Einblendungen)
- professioneller, höflicher Ton
- keine Telefonnummern und keine ziffernartigen Rufnummern im Text; keine Einladung zum Zuruf auf eine Nummer
- keine erfundenen Fakten über mich, die Stelle oder das Unternehmen — nur das, was oben oder im JSON ausdrücklich steht
- erfinden Sie keine Fakten über meine Berufserfahrung
- wenn im JSON ein Feld „fragment_publicznej_strony_www“ vorkommt, nutzen Sie es nur als ergänzende öffentliche Information; erfinden Sie keine Details jenseits dieses Fragments; Telefonnummern aus dem Fragment nicht übernehmen
- {b2b_instruction}
- {contract_instruction}
- Abschluss mit „Mit freundlichen Grüßen," oder „Mit freundlichen Grüßen", danach eine neue Zeile und **nur** der Name: {MAIL_SIGNATORY_NAME} (genau so, ohne Klammern oder Platzhalter)."""
        if extra_user_instruction.strip():
            user_prompt += (
                "\n\nZusätzliche redaktionelle Anweisung:\n" + extra_user_instruction.strip()
            )
        system_content = SYSTEM_PROMPT_DE
    else:
        source_line_pl = (
            f"- źródło ogłoszenia (portal/strona — tylko jeśli podane, nie dopowiadaj): {src_pub}\n"
            if src_pub
            else "- brak konkretnego portalu/źródła w danych — nie wspominaj narzędzi zbierania leadów ani nie wymyślaj skąd znalazłeś ofertę.\n"
        )
        b2b_instruction = (
            "- zaproponuj konkretnie współpracę B2B przy analityce danych/e-commerce"
            if offer_b2b
            else "- skup się na kandydaturze etatowej/projektowej bez oferty handlowej"
        )
        contract_instruction = (
            "- w komunikacji preferuj UOP (jeśli ogłoszenie dopuszcza UOP i B2B, wybierz UOP)"
            if contract_preference == "UOP"
            else "- w komunikacji preferuj B2B (ogłoszenie wskazuje wyłącznie B2B)"
            if contract_preference == "B2B"
            else "- nie deklaruj formy współpracy, jeśli nie wynika jasno z danych"
        )
        cv_goal_pl = (
            "- aplikuję na stanowisko i wyrażam zainteresowanie rozmową rekrutacyjną\n"
            f"- informuję, że w załączniku przesyłam CV oraz podaję link do pobrania; w treści maila umieść dokładnie ten adres URL "
            f"(znak w znak, bez skracania): {cv_url}"
            if cv_url
            else "- aplikuję na stanowisko i wyrażam zainteresowanie rozmową rekrutacyjną\n"
            "- informuję, że w załączniku przesyłam CV"
        )
        user_prompt = f"""Napisz treściwy, spersonalizowany e-mail aplikacyjny po polsku (co najmniej 4–7 pełnych zdań w 2–3 akapitach; same pozdrowienia bez treści merytorycznej są niedopuszczalne).

Mój cel:
{cv_goal_pl}

Dane firmy i oferty (tylko te pola do treści maila — niczego nie dopowiadaj):
- firma: {company}
- stanowisko/rola: {role}
- miasto: {city}
- branża: {industry}
- strona WWW: {website}
- tryb pracy: {mode}
{source_line_pl}- uwagi: {notes}

Pełne dane z wiersza (JSON z Excela):
{row_context}

Wymagania:
- cała treść maila wyłącznie po polsku (zero angielskich zwrotów typu „Best regards”, „Looking forward” itp.)
- ton profesjonalny i uprzejmy
- zakaz numerów telefonów w treści: nie wstawiaj żadnego numeru, żadnej frazy typu „zadzwonię pod …” — ignoruj numery także w fragmencie strony
- tylko twarde fakty z listy powyżej i z JSON — zero domysłów o mnie, firmie, ofercie lub terminach
- nie wymyślaj faktów o moim doświadczeniu
- jeśli w JSON jest pole „fragment_publicznej_strony_www”, traktuj je wyłącznie jako uzupełnienie publicznych informacji z witryny; nie wymyślaj szczegółów spoza tego fragmentu i pozostałych pól; nie kopiuj z fragmentu numerów telefonów
- {b2b_instruction}
- {contract_instruction}
- zakończ linią „Pozdrawiam,” lub „Pozdrawiam”, a **zaraz pod spodem w nowej linii wyłącznie** podpis: {MAIL_SIGNATORY_NAME} (dokładnie ten zapis, bez nawiasów kwadratowych i bez tekstu typu [Twoje imię])."""
        if extra_user_instruction.strip():
            user_prompt += (
                "\n\nDodatkowa instrukcja redakcyjna:\n" + extra_user_instruction.strip()
            )
        system_content = SYSTEM_PROMPT

    client = _get_openai_client()
    r = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_prompt},
        ],
        temperature=MAIL_BODY_TEMPERATURE,
    )

    content = r.choices[0].message.content
    if not content:
        raise ValueError("OpenAI zwrócił pustą treść maila.")
    return content.strip()


def _generate_mail_with_retry(**kwargs) -> str:
    last_error: Optional[Exception] = None
    retries = max(1, OPENAI_MAX_RETRIES)
    length_hint = ""
    base_extra = (kwargs.get("extra_user_instruction") or "").strip()
    for attempt in range(1, retries + 1):
        try:
            loc = kwargs.get("locale", "pl")
            hint = _MAIL_LENGTH_RETRY_HINT_DE if loc == "de" else _MAIL_LENGTH_RETRY_HINT_PL
            merged_extra = base_extra
            if length_hint:
                merged_extra = (
                    f"{base_extra}\n\n{hint}" if base_extra else hint
                ).strip()
            call_kw = {**kwargs, "extra_user_instruction": merged_extra}
            text = wygeneruj_tresc_maila(**call_kw)
            if _mail_body_too_short(text):
                length_hint = hint
                raise ValueError("Treść maila poniżej minimalnej długości.")
            return text
        except Exception as e:
            last_error = e
            if attempt < retries:
                time.sleep(0.8)

    assert last_error is not None
    raise RuntimeError(
        f"OpenAI nie wygenerował treści po {retries} próbach: {last_error}"
    )


def wygeneruj_temat(company: str, role: str, city: str) -> str:
    return f"Aplikacja - {role} - {company} ({city})"


def wygeneruj_temat_spersonalizowany(
    company: str,
    role: str,
    city: str,
    industry: str,
    mode: str,
    source: str,
    offer_b2b: bool,
    contract_preference: str,
    locale: str = "pl",
) -> str:
    loc = "de" if locale == "de" else "pl"
    src_pub = _public_source_for_mail_prompt(source)
    source_line_de = f"- Quelle/Portal (öffentliche Stellenausschreibung): {src_pub}\n" if src_pub else ""
    source_hint_de = (
        ""
        if src_pub
        else "- Im Betreff keine technischen Suchwerkzeuge und keine erfundene Quelle nennen.\n"
    )
    source_line_pl = f"- źródło ogłoszenia (portal/strona): {src_pub}\n" if src_pub else ""
    source_hint_pl = (
        ""
        if src_pub
        else "- W temacie nie wspominaj narzędzi zbierania leadów ani nie wymyślaj źródła oferty.\n"
    )

    if loc == "de":
        b2b_hint = "Der Betreff soll eine B2B-Kooperation andeuten." if offer_b2b else ""
        contract_hint = (
            "Wenn die Stelle UOP und B2B anbietet, soll der Betreff Festanstellung/UOP bevorzugen."
            if contract_preference == "UOP"
            else "Der Betreff soll B2B betonen, da die Ausschreibung nur B2B nennt."
            if contract_preference == "B2B"
            else ""
        )
        de_tail = [source_hint_de.rstrip("\n")] if source_hint_de else []
        if b2b_hint:
            de_tail.append(f"- {b2b_hint}")
        if contract_hint:
            de_tail.append(f"- {contract_hint}")
        de_tail_block = ("\n".join(line for line in de_tail if line) + "\n") if de_tail else ""
        user_prompt = f"""Erstellen Sie den Betreff einer Bewerbungs-E-Mail.

Daten:
- Firma: {company}
- Rolle: {role}
- Stadt: {city}
- Branche: {industry}
- Modell: {mode}
{source_line_de}
Anforderungen:
- gesamter Betreff auf Deutsch (ohne englische Wörter),
- max. 90 Zeichen,
- keine Emojis,
- keine Telefonnummern und keine Ziffernfolgen wie eine Nummer,
- konkret und professionell,
{de_tail_block}"""
        subject_system = SUBJECT_SYSTEM_PROMPT_DE
    else:
        b2b_hint = "Temat ma sugerować propozycję współpracy B2B." if offer_b2b else ""
        contract_hint = (
            "Jeśli ogłoszenie ma UOP i B2B, temat ma sugerować preferencję UOP."
            if contract_preference == "UOP"
            else "Temat ma sugerować B2B, bo ogłoszenie wskazuje tylko B2B."
            if contract_preference == "B2B"
            else ""
        )
        pl_tail = [source_hint_pl.rstrip("\n")] if source_hint_pl else []
        if b2b_hint:
            pl_tail.append(f"- {b2b_hint}")
        if contract_hint:
            pl_tail.append(f"- {contract_hint}")
        pl_tail_block = ("\n".join(line for line in pl_tail if line) + "\n") if pl_tail else ""
        user_prompt = f"""Utwórz temat e-maila aplikacyjnego.

Dane:
- firma: {company}
- rola: {role}
- miasto: {city}
- branża: {industry}
- tryb pracy: {mode}
{source_line_pl}
Wymagania:
- cały temat wyłącznie po polsku (bez angielskich słów),
- max 90 znaków,
- bez emoji,
- bez numerów telefonu i bez ciągów cyfr jak numer,
- konkret i profesjonalny ton,
{pl_tail_block}"""
        subject_system = SUBJECT_SYSTEM_PROMPT

    client = _get_openai_client()
    r = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": subject_system},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )
    content = (r.choices[0].message.content or "").strip()
    if not content:
        raise ValueError("OpenAI zwrócił pusty temat.")
    return content.replace("\n", " ").strip()[:90]


def _generate_subject_with_retry(
    company: str,
    role: str,
    city: str,
    industry: str,
    mode: str,
    source: str,
    offer_b2b: bool = False,
    contract_preference: str = "AUTO",
    locale: str = "pl",
) -> str:
    last_error: Optional[Exception] = None
    retries = max(1, OPENAI_MAX_RETRIES)
    for attempt in range(1, retries + 1):
        try:
            return wygeneruj_temat_spersonalizowany(
                company=company,
                role=role,
                city=city,
                industry=industry,
                mode=mode,
                source=source,
                offer_b2b=offer_b2b,
                contract_preference=contract_preference,
                locale=locale,
            )
        except Exception as e:
            last_error = e
            if attempt < retries:
                time.sleep(0.4)

    assert last_error is not None
    raise RuntimeError(
        f"OpenAI nie wygenerował tematu po {retries} próbach: {last_error}"
    )


def zapisz_excel(df: pd.DataFrame, sciezka: str) -> None:
    df.to_excel(sciezka, index=False)
    try:
        from json_data_backup import maybe_backup_dataframe

        maybe_backup_dataframe(df, sciezka, reason="excel_save")
    except Exception:
        logger.exception("Kopia JSON po zapisie Excel nie powiodła się")


def main() -> None:
    try:
        from sent_mail_registry import cleanup_stale_registry_files

        n_del = cleanup_stale_registry_files()
        if n_del:
            logger.info("Rejestr wysyłek JSON: usunięto %s przeterminowanych plików .jsonl", n_del)
    except Exception:
        logger.exception("Czyszczenie przeterminowanych plików rejestru .jsonl nie powiodło się")

    excel_path = _resolve_excel_path()
    cv_path = _resolve_cv_path()
    from excel_workbook_reader import read_excel_workbook

    df = read_excel_workbook(excel_path)
    col_map = _resolve_column_map(df)

    for required in ("email", "company", "role"):
        if not col_map.get(required):
            raise ValueError(f"Brak wymaganej kolumny dla pola: {required}")

    if STATUS_COL not in df.columns:
        df[STATUS_COL] = pd.NA
    if DATE_COL not in df.columns:
        df[DATE_COL] = pd.NaT

    if DRY_RUN:
        stats = _process_rows(df, excel_path=excel_path, smtp=None, cv_path=cv_path, col_map=col_map)
    else:
        if not password:
            raise RuntimeError("Brak GMAIL_APP_PASSWORD w zmiennych środowiskowych.")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(SENDER_EMAIL, password)
            stats = _process_rows(df, excel_path=excel_path, smtp=smtp, cv_path=cv_path, col_map=col_map)

    line = (
        "Podsumowanie: "
        f"wyslano={stats['sent']}, "
        f"pominieto={stats['skipped']}, "
        f"limit_dzienny={stats['daily_limit_reached']}, "
        f"bledy_openai={stats['openai_errors']}, "
        f"bledy_smtp={stats['smtp_errors']}, "
        f"bledne_maile={stats['invalid_email']}, "
        f"email_ze_strony={stats['email_from_web']}"
    )
    if MAIL_PROMPT_VERSION:
        line += f", prompt_wersja={MAIL_PROMPT_VERSION}"
    logger.info("%s", line)
    logger.info(
        "Szczegoly_pominiec: juz_wyslane=%s, brak_maila=%s, domena_zablokowana=%s, limit_dzienny_wiersze=%s",
        stats["skip_already_sent"],
        stats["skip_missing_email"],
        stats["skip_blocked_domain"],
        stats["skip_daily_limit"],
    )
    maybe_error_alert(stats, prefix="mailer: ")


def _process_rows(
    df: pd.DataFrame,
    excel_path: str,
    smtp: Optional[smtplib.SMTP_SSL],
    cv_path: str,
    col_map: Optional[Dict[str, Optional[str]]] = None,
) -> Dict[str, int]:
    if col_map is None:
        col_map = _resolve_column_map(df)

    stats: Dict[str, int] = {
        "sent": 0,
        "skipped": 0,
        "openai_errors": 0,
        "smtp_errors": 0,
        "invalid_email": 0,
        "daily_limit_reached": 0,
        "email_from_web": 0,
        "skip_already_sent": 0,
        "skip_missing_email": 0,
        "skip_blocked_domain": 0,
        "skip_daily_limit": 0,
    }
    sent_today = _count_sent_today(df)
    daily_limit = max(1, MAX_EMAILS_PER_DAY)

    for idx, row in df.iterrows():
        company_for_log = _row_value(row, col_map.get("company"), "(brak firmy)")
        if _already_sent(row.get(STATUS_COL)):
            stats["skipped"] += 1
            stats["skip_already_sent"] += 1
            _append_campaign_log(
                CAMPAIGN_LOG_PATH,
                email=_row_value(row, col_map.get("email")),
                company=company_for_log,
                subject="",
                status="skipped",
                reason="already_sent",
            )
            continue

        email_col = col_map.get("email")
        website_for_fetch = _row_value(row, col_map.get("website"), "")
        email, filled_web = try_resolve_email_from_website(
            _row_value(row, email_col), website_for_fetch
        )
        if filled_web and email_col:
            df.at[idx, email_col] = email
            zapisz_excel(df, excel_path)
            stats["email_from_web"] += 1
        if not email:
            stats["skipped"] += 1
            stats["skip_missing_email"] += 1
            _append_campaign_log(
                CAMPAIGN_LOG_PATH,
                email="",
                company=company_for_log,
                subject="",
                status="skipped",
                reason="missing_email",
            )
            continue
        if not _is_valid_email(email):
            stats["invalid_email"] += 1
            df.at[idx, STATUS_COL] = "Błąd: niepoprawny e-mail"
            zapisz_excel(df, excel_path)
            _append_campaign_log(
                CAMPAIGN_LOG_PATH,
                email=normalize_recipient_email(email) or email,
                company=company_for_log,
                subject="",
                status="invalid_email",
                reason="invalid_email",
            )
            continue

        email = normalize_recipient_email(email)

        if recipient_domain_is_blocked(email):
            stats["skipped"] += 1
            stats["skip_blocked_domain"] += 1
            df.at[idx, STATUS_COL] = "Pominięto: domena zablokowana"
            zapisz_excel(df, excel_path)
            _append_campaign_log(
                CAMPAIGN_LOG_PATH,
                email=email,
                company=company_for_log,
                subject="",
                status="skipped",
                reason="blocked_domain",
            )
            continue

        if sent_today >= daily_limit:
            stats["skipped"] += 1
            stats["daily_limit_reached"] += 1
            stats["skip_daily_limit"] += 1
            df.at[idx, STATUS_COL] = "Pominięto: limit dzienny"
            zapisz_excel(df, excel_path)
            _append_campaign_log(
                CAMPAIGN_LOG_PATH,
                email=email,
                company=company_for_log,
                subject="",
                status="skipped",
                reason="daily_limit_reached",
            )
            continue

        company = _row_value(row, col_map.get("company"), "(brak firmy)")
        role = _row_value(row, col_map.get("role"), "(brak stanowiska)")
        city = _row_value(row, col_map.get("city"), "(brak miasta)")
        industry = _row_value(row, col_map.get("industry"), "(brak branży)")
        website = _row_value(row, col_map.get("website"), "(brak strony WWW)")
        phone = _row_value(row, col_map.get("phone"), "(nie podano)")
        mode = _row_value(row, col_map.get("mode"), "(brak informacji)")
        source = _row_value(row, col_map.get("source"), "(brak źródła)")
        notes = _row_value(row, col_map.get("notes"), "(brak uwag)")
        contract_preference = _detect_contract_preference(
            mode=mode, source=source, notes=notes
        )
        offer_b2b = _should_offer_b2b(industry=industry, source=source, notes=notes)
        if contract_preference == "UOP":
            offer_b2b = False
        elif contract_preference == "B2B":
            offer_b2b = True
        row_context = _build_row_context_for_generation(row, website)
        mail_locale = _mail_locale(website, email)

        try:
            temat = _generate_subject_with_retry(
                company=company,
                role=role,
                city=city,
                industry=industry,
                mode=mode,
                source=source,
                offer_b2b=offer_b2b,
                contract_preference=contract_preference,
                locale=mail_locale,
            )
            tresc = _generate_mail_with_retry(
                company=company,
                role=role,
                city=city,
                industry=industry,
                website=website,
                phone=phone,
                mode=mode,
                source=source,
                notes=notes,
                row_context=row_context,
                offer_b2b=offer_b2b,
                contract_preference=contract_preference,
                locale=mail_locale,
            )
        except Exception as e:
            stats["openai_errors"] += 1
            df.at[idx, STATUS_COL] = _safe_status(f"Błąd OpenAI: {e}")
            zapisz_excel(df, excel_path)
            _append_campaign_log(
                CAMPAIGN_LOG_PATH,
                email=email,
                company=company,
                subject="",
                status="openai_error",
                reason=str(e),
            )
            continue

        msg = EmailMessage()
        msg["Subject"] = temat
        msg["From"] = SENDER_EMAIL
        msg["To"] = email
        msg.set_content(tresc)
        _attach_cv(msg, cv_path)

        try:
            if DRY_RUN:
                logger.info("[DRY_RUN] %s | %s", email, temat)
            else:
                assert smtp is not None
                _send_message_with_retry(smtp, msg)
        except Exception as e:
            stats["smtp_errors"] += 1
            df.at[idx, STATUS_COL] = _safe_status(f"Błąd SMTP: {e}")
            zapisz_excel(df, excel_path)
            _append_campaign_log(
                CAMPAIGN_LOG_PATH,
                email=email,
                company=company,
                subject=temat,
                status="smtp_error",
                reason=str(e),
            )
            continue

        stats["sent"] += 1
        sent_today += 1
        df.at[idx, STATUS_COL] = "Tak"
        df.at[idx, DATE_COL] = _now_for_excel()
        zapisz_excel(df, excel_path)
        _append_campaign_log(
            CAMPAIGN_LOG_PATH,
            email=email,
            company=company,
            subject=temat,
            status="sent",
            reason="",
        )
        try:
            from sent_mail_registry import append_sent_record

            append_sent_record(
                batch_path=excel_path,
                output_csv_path=excel_path,
                email=email,
                company=company,
                role=role,
                city=city,
                industry=industry,
                website=website,
                phone=phone,
                mode=mode,
                source=source,
                notes=notes,
                subject=temat,
                locale=mail_locale,
                dry_run=DRY_RUN,
            )
        except Exception:
            logger.exception("Zapis rejestru JSON wysłanych maili nie powiódł się")
        logger.info("Wysłano: %s | %s", email, temat)

        if not DRY_RUN:
            _apply_send_delay()

    return stats


if __name__ == "__main__":
    main()
