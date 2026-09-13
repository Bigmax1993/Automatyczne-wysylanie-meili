"""
Wyszukiwanie konkretnej osoby w publicznej bazie IPN Straty
(https://straty.pl/szukaj-osoby.php).

To jest klient formularza publicznego (ten sam POST co w przeglądarce).
Służy do kwerendy genealogicznej / historycznej — NIE jest źródłem leadów
i nie jest podłączony do pipeline'u wysyłki maili.

Limity: wymagane nazwisko, odstęp HTTP per host, twardy limit szczegółów.
Nie obchodzi logowania, CAPTCHA ani innych zabezpieczeń.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence
import requests
from bs4 import BeautifulSoup

import pipeline_version as pv
from fetch_throttle import throttle_hostname_before_http
from pipeline_logging import setup_logging

logger = logging.getLogger(__name__)

SEARCH_URL = os.environ.get(
    "STRATY_SEARCH_URL", "https://straty.pl/szukaj-osoby.php"
).strip() or "https://straty.pl/szukaj-osoby.php"
DEFAULT_TIMEOUT_SEC = float(os.environ.get("STRATY_HTTP_TIMEOUT", "20"))
DEFAULT_MAX_DETAILS = 10
HARD_MAX_DETAILS = 25
USER_AGENT = os.environ.get(
    "STRATY_USER_AGENT",
    "StratyOsobyLookup/1.0 (genealogical lookup of IPN Straty public form)",
)

LIST_FIELD_ORDER = (
    "lp",
    "nazwisko",
    "imie",
    "panienskie",
    "data_urodzenia",
    "miejsce_urodzenia",
    "imie_ojca",
    "imie_matki",
    "data_smierci",
)
RECORD_ID_RE = re.compile(r"^id(\d+)$", re.I)
BLOCK_HINTS = (
    "captcha",
    "recaptcha",
    "verify you are human",
    "access denied",
    "just a moment",
    "cloudflare",
)


class StratySearchError(RuntimeError):
    """Błąd kwerendy (walidacja, HTTP, blokada)."""


@dataclass
class SearchQuery:
    nazwisko: str = ""
    imie: str = ""
    panienskie: str = ""
    imie_o: str = ""
    imie_m: str = ""
    ur_miejsce: str = ""
    ur_dzien: str = ""
    ur_miesiac: str = ""
    ur_rok: str = ""
    zam_miejsce: str = ""
    zawod: str = ""
    sm_dzien: str = ""
    sm_miesiac: str = ""
    sm_rok: str = ""

    def normalized(self) -> "SearchQuery":
        data = {k: _clean_text(v) for k, v in asdict(self).items()}
        return replace(self, **data)

    def as_form(self, submit: str = "szukaj") -> Dict[str, str]:
        q = self.normalized()
        payload = {k: v for k, v in asdict(q).items()}
        if submit == "szukaj":
            payload["szukaj"] = "Szukaj"
        return payload

    def identifying_fields(self) -> Dict[str, str]:
        q = self.normalized()
        return {k: v for k, v in asdict(q).items() if v}


@dataclass
class PersonMatch:
    record_id: str
    lp: str = ""
    nazwisko: str = ""
    imie: str = ""
    panienskie: str = ""
    data_urodzenia: str = ""
    miejsce_urodzenia: str = ""
    imie_ojca: str = ""
    imie_matki: str = ""
    data_smierci: str = ""

    def as_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass
class PersecutionRecord:
    zrodlo: str = ""
    zrodlo_url: str = ""
    zrodlo_sygnatura: str = ""
    pola: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "zrodlo": self.zrodlo,
            "zrodlo_url": self.zrodlo_url,
            "zrodlo_sygnatura": self.zrodlo_sygnatura,
            "pola": dict(self.pola),
        }


@dataclass
class PersonDetail:
    record_id: str
    dane_osobowe: Dict[str, str] = field(default_factory=dict)
    przesladowania: List[PersecutionRecord] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "dane_osobowe": dict(self.dane_osobowe),
            "przesladowania": [p.as_dict() for p in self.przesladowania],
        }


@dataclass
class SearchResult:
    kind: str
    message: str = ""
    query: Optional[SearchQuery] = None
    matches: List[PersonMatch] = field(default_factory=list)
    details: List[PersonDetail] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "message": self.message,
            "query": asdict(self.query) if self.query else {},
            "matches": [m.as_dict() for m in self.matches],
            "details": [d.as_dict() for d in self.details],
            "source": SEARCH_URL,
        }


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _looks_like_block(status_code: int, html: str) -> bool:
    if status_code in {401, 403, 429, 503}:
        return True
    low = (html or "").lower()
    return any(h in low for h in BLOCK_HINTS)


def validate_query(query: SearchQuery) -> SearchQuery:
    q = query.normalized()
    if len(q.nazwisko) < 2:
        raise StratySearchError(
            "Podaj --nazwisko (min. 2 znaki). Baza IPN wymaga zawężenia kwerendy."
        )
    for label, raw in (("ur_dzien", q.ur_dzien), ("sm_dzien", q.sm_dzien)):
        if raw and (not raw.isdigit() or not 1 <= int(raw) <= 31):
            raise StratySearchError(f"Nieprawidłowy {label}: {raw}")
    for label, raw in (("ur_miesiac", q.ur_miesiac), ("sm_miesiac", q.sm_miesiac)):
        if raw and (not raw.isdigit() or not 1 <= int(raw) <= 12):
            raise StratySearchError(f"Nieprawidłowy {label}: {raw}")
    if q.ur_rok and (not q.ur_rok.isdigit() or not 1800 <= int(q.ur_rok) <= 1945):
        raise StratySearchError(
            f"Nieprawidłowy ur_rok: {q.ur_rok} (oczekiwany rok 1800–1945)"
        )
    if q.sm_rok and (not q.sm_rok.isdigit() or not 1800 <= int(q.sm_rok) <= 2100):
        raise StratySearchError(f"Nieprawidłowy sm_rok: {q.sm_rok}")
    return q


def parse_search_html(html: str) -> SearchResult:
    soup = BeautifulSoup(html or "", "html.parser")
    heading = _clean_text(
        " ".join(h.get_text(" ", strip=True) for h in soup.select("h3.heading-3"))
    )
    low_heading = heading.lower()

    if soup.select_one("div.daneosobowe"):
        detail = parse_detail_html(html, record_id="")
        return SearchResult(kind="detail", message="Karta osoby", details=[detail])

    if "brak kryteri" in low_heading:
        return SearchResult(kind="no_criteria", message=heading or "Brak kryteriów wyszukiwania.")
    if "za dużo" in low_heading or "za duzo" in low_heading or "uściślij" in low_heading or "uscislij" in low_heading:
        return SearchResult(
            kind="too_many",
            message=heading or "Za dużo wyników — uściślij kryteria.",
        )
    if "nie ma danych" in low_heading:
        return SearchResult(
            kind="no_matches",
            message=heading or "Nie ma danych spełniających kryteria.",
        )

    matches = _parse_match_grid(soup)
    if matches:
        return SearchResult(
            kind="results",
            message=f"Znaleziono {len(matches)} rekord(ów).",
            matches=matches,
        )

    if soup.find("input", {"name": "nazwisko", "id": "nazwisko"}):
        return SearchResult(kind="form", message="Formularz wyszukiwania (brak wyników).")

    return SearchResult(kind="unknown", message=heading or "Nie rozpoznano odpowiedzi straty.pl.")


def _parse_match_grid(soup: BeautifulSoup) -> List[PersonMatch]:
    grouped: Dict[str, List[str]] = {}
    order: List[str] = []
    for inp in soup.find_all("input"):
        name = (inp.get("name") or "").strip()
        m = RECORD_ID_RE.match(name)
        if not m:
            continue
        rec_id = m.group(1)
        if rec_id not in grouped:
            grouped[rec_id] = []
            order.append(rec_id)
        grouped[rec_id].append(_clean_text(inp.get("value")))

    matches: List[PersonMatch] = []
    for rec_id in order:
        values = grouped[rec_id]
        padded = (values + [""] * len(LIST_FIELD_ORDER))[: len(LIST_FIELD_ORDER)]
        fields = dict(zip(LIST_FIELD_ORDER, padded))
        matches.append(PersonMatch(record_id=rec_id, **fields))
    return matches


def parse_detail_html(html: str, record_id: str = "") -> PersonDetail:
    soup = BeautifulSoup(html or "", "html.parser")
    osobowe = soup.select_one("div.daneosobowe")
    dane = _label_value_pairs(osobowe)

    records: List[PersecutionRecord] = []
    current: Optional[PersecutionRecord] = None
    root = osobowe.parent if osobowe and osobowe.parent else soup
    for child in root.find_all("div"):
        classes = child.get("class") or []
        if "zrodlo" in classes:
            if current:
                records.append(current)
            current = _parse_zrodlo_block(child)
        elif "danerepresji" in classes:
            if current is None:
                current = PersecutionRecord()
            current.pola.update(_label_value_pairs(child))
            records.append(current)
            current = None
    if current:
        records.append(current)

    return PersonDetail(record_id=record_id, dane_osobowe=dane, przesladowania=records)


def _parse_zrodlo_block(block: Any) -> PersecutionRecord:
    link = block.select_one("a.link_zrodlo") if getattr(block, "select_one", None) else None
    sygnatura = ""
    for div in block.find_all("div"):
        if div.find("a"):
            continue
        text = _clean_text(div.get_text(" ", strip=True))
        if not text:
            continue
        low = text.lower()
        if low.startswith("źródło") or low.startswith("zrodlo"):
            continue
        if div.find("div"):
            continue
        sygnatura = text
    return PersecutionRecord(
        zrodlo=_clean_text(link.get_text(" ", strip=True) if link else ""),
        zrodlo_url=_clean_text(link.get("href") if link else ""),
        zrodlo_sygnatura=sygnatura,
    )


def _label_value_pairs(container: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if container is None:
        return out
    pending_label: Optional[str] = None
    for child in getattr(container, "children", []):
        classes = child.get("class", []) if getattr(child, "get", None) else []
        text = _clean_text(child.get_text(" ", strip=True) if getattr(child, "get_text", None) else "")
        if "trzylabel" in classes:
            pending_label = text
        elif "trzydane" in classes and pending_label:
            out[pending_label] = text
            pending_label = None
    return out


def _new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pl,en;q=0.8",
        }
    )
    return session


def post_form(
    payload: Mapping[str, str],
    *,
    session: Optional[requests.Session] = None,
    timeout: float = DEFAULT_TIMEOUT_SEC,
    url: str = SEARCH_URL,
) -> str:
    sess = session or _new_session()
    throttle_hostname_before_http(url)
    try:
        resp = sess.post(url, data=dict(payload), timeout=timeout)
    except requests.RequestException as exc:
        raise StratySearchError(f"Błąd HTTP przy zapytaniu do straty.pl: {exc}") from exc
    html = resp.text or ""
    if _looks_like_block(resp.status_code, html):
        raise StratySearchError(
            f"Serwer straty.pl odrzucił żądanie (HTTP {resp.status_code}). "
            "Nie obchodzę blokad — spróbuj później w przeglądarce."
        )
    if resp.status_code >= 400:
        raise StratySearchError(f"straty.pl zwrócił HTTP {resp.status_code}")
    return html


def search_person(
    query: SearchQuery,
    *,
    session: Optional[requests.Session] = None,
    timeout: float = DEFAULT_TIMEOUT_SEC,
    fetch_details: bool = False,
    max_details: int = DEFAULT_MAX_DETAILS,
    url: str = SEARCH_URL,
) -> SearchResult:
    q = validate_query(query)
    sess = session or _new_session()
    html = post_form(q.as_form("szukaj"), session=sess, timeout=timeout, url=url)
    result = parse_search_html(html)
    result.query = q

    if result.kind != "results" or not fetch_details:
        return result

    cap = min(max(0, int(max_details)), HARD_MAX_DETAILS)
    if cap <= 0:
        return result
    if len(result.matches) > cap:
        logger.info(
            "Szczegóły tylko dla pierwszych %s z %s rekordów (limit --max-details).",
            cap,
            len(result.matches),
        )
    details: List[PersonDetail] = []
    for match in result.matches[:cap]:
        details.append(
            fetch_person_detail(
                q,
                match,
                session=sess,
                timeout=timeout,
                url=url,
            )
        )
    result.details = details
    return result


def fetch_person_detail(
    query: SearchQuery,
    match: PersonMatch,
    *,
    session: Optional[requests.Session] = None,
    timeout: float = DEFAULT_TIMEOUT_SEC,
    url: str = SEARCH_URL,
) -> PersonDetail:
    q = query.normalized()
    payload = q.as_form(submit="")
    payload.pop("szukaj", None)
    payload[f"id{match.record_id}"] = match.lp or "1"
    html = post_form(payload, session=session, timeout=timeout, url=url)
    parsed = parse_search_html(html)
    if parsed.kind == "detail" and parsed.details:
        detail = parsed.details[0]
        detail.record_id = match.record_id
        return detail
    return PersonDetail(
        record_id=match.record_id,
        dane_osobowe={
            "nazwisko": match.nazwisko,
            "imię": match.imie,
            "uwaga": parsed.message or "Nie udało się odczytać karty osoby.",
        },
    )


def result_to_json(result: SearchResult) -> str:
    return json.dumps(result.as_dict(), ensure_ascii=False, indent=2)


def write_output(result: SearchResult, path: str) -> None:
    lower = path.lower()
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    if lower.endswith(".json"):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(result_to_json(result))
            fh.write("\n")
        return
    rows = _flatten_for_table(result)
    fieldnames = _table_fieldnames(rows)
    if lower.endswith(".csv"):
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return
    if lower.endswith(".xlsx") or lower.endswith(".xls"):
        import pandas as pd

        df = pd.DataFrame(rows, columns=fieldnames)
        df.to_excel(path, index=False)
        return
    raise StratySearchError("Nieobsługiwane rozszerzenie --output (użyj .json, .csv lub .xlsx).")


def _flatten_for_table(result: SearchResult) -> List[Dict[str, str]]:
    details_by_id = {d.record_id: d for d in result.details}
    rows: List[Dict[str, str]] = []
    source_rows: List[PersonMatch] = list(result.matches)
    if not source_rows and result.details:
        source_rows = [PersonMatch(record_id=d.record_id) for d in result.details]
    for match in source_rows:
        row = match.as_dict()
        row["status"] = result.kind
        row["komunikat"] = result.message
        detail = details_by_id.get(match.record_id)
        if detail:
            for key, val in detail.dane_osobowe.items():
                row[f"karta_{key}"] = val
            row["zrodla"] = " | ".join(
                f"{p.zrodlo} {p.zrodlo_sygnatura}".strip() for p in detail.przesladowania
            )
            row["represje"] = " | ".join(
                ", ".join(f"{k}: {v}" for k, v in p.pola.items())
                for p in detail.przesladowania
            )
        rows.append(row)
    if not rows:
        rows.append(
            {
                "status": result.kind,
                "komunikat": result.message,
            }
        )
    return rows


def _table_fieldnames(rows: Sequence[Mapping[str, str]]) -> List[str]:
    keys: List[str] = []
    seen = set()
    preferred = [
        "status",
        "komunikat",
        "record_id",
        *LIST_FIELD_ORDER,
        "zrodla",
        "represje",
    ]
    for key in preferred:
        if any(key in row for row in rows) and key not in seen:
            keys.append(key)
            seen.add(key)
    for row in rows:
        for key in row:
            if key not in seen:
                keys.append(key)
                seen.add(key)
    return keys


def format_table(result: SearchResult) -> str:
    lines = [f"Status: {result.kind}", f"Źródło: {SEARCH_URL}"]
    if result.message:
        lines.append(result.message)
    if result.query:
        used = result.query.identifying_fields()
        if used:
            lines.append("Kryteria: " + ", ".join(f"{k}={v}" for k, v in used.items()))
    if result.matches:
        headers = ["lp", "nazwisko", "imie", "data_urodzenia", "miejsce_urodzenia", "imie_ojca", "record_id"]
        widths = {h: len(h) for h in headers}
        dicts = [m.as_dict() for m in result.matches]
        for row in dicts:
            for h in headers:
                widths[h] = max(widths[h], len(row.get(h, "")))
        fmt = "  ".join(f"{{:{widths[h]}}}" for h in headers)
        lines.append(fmt.format(*headers))
        lines.append(fmt.format(*("-" * widths[h] for h in headers)))
        for row in dicts:
            lines.append(fmt.format(*(row.get(h, "") for h in headers)))
    for detail in result.details:
        lines.append("")
        lines.append(f"--- Karta id{detail.record_id} ---")
        for key, val in detail.dane_osobowe.items():
            lines.append(f"  {key}: {val}")
        for i, rec in enumerate(detail.przesladowania, start=1):
            lines.append(f"  Źródło {i}: {rec.zrodlo} ({rec.zrodlo_sygnatura}) {rec.zrodlo_url}".strip())
            for key, val in rec.pola.items():
                lines.append(f"    {key}: {val}")
    if result.kind == "too_many":
        lines.append("Podaj imię, rok urodzenia, imię ojca lub miejsce — publiczna baza nie zwraca zbyt szerokich list.")
    return "\n".join(lines) + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Wyszukaj osobę w publicznej bazie IPN Straty (straty.pl). "
            "Kwerenda genealogiczna / historyczna — nie do mailingu."
        )
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"search_straty_osoby {pv.PIPELINE_VERSION}",
    )
    parser.add_argument("--nazwisko", required=True, help="Nazwisko (wymagane)")
    parser.add_argument("--imie", default="", help="Imię")
    parser.add_argument("--panienskie", default="", help="Nazwisko panieńskie")
    parser.add_argument("--imie-ojca", dest="imie_o", default="", help="Imię ojca")
    parser.add_argument("--imie-matki", dest="imie_m", default="", help="Imię matki")
    parser.add_argument("--ur-miejsce", dest="ur_miejsce", default="", help="Miejsce urodzenia")
    parser.add_argument("--ur-dzien", dest="ur_dzien", default="", help="Dzień urodzenia (1–31)")
    parser.add_argument("--ur-miesiac", dest="ur_miesiac", default="", help="Miesiąc urodzenia (1–12)")
    parser.add_argument("--ur-rok", dest="ur_rok", default="", help="Rok urodzenia")
    parser.add_argument(
        "--zam-miejsce",
        dest="zam_miejsce",
        default="",
        help="Miejsce zamieszkania przed wojną",
    )
    parser.add_argument("--zawod", default="", help="Zawód")
    parser.add_argument("--sm-dzien", dest="sm_dzien", default="", help="Dzień śmierci (1–31)")
    parser.add_argument("--sm-miesiac", dest="sm_miesiac", default="", help="Miesiąc śmierci (1–12)")
    parser.add_argument("--sm-rok", dest="sm_rok", default="", help="Rok śmierci")
    parser.add_argument(
        "--details",
        action="store_true",
        help="Pobierz kartę osoby (represje, źródło) dla znalezionych rekordów",
    )
    parser.add_argument(
        "--max-details",
        type=int,
        default=DEFAULT_MAX_DETAILS,
        help=f"Maks. liczba kart do pobrania (domyślnie {DEFAULT_MAX_DETAILS}, twardy limit {HARD_MAX_DETAILS})",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Plik wynikowy: .json / .csv / .xlsx",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Wypisz JSON na stdout (zamiast tabeli)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SEC,
        help="Timeout HTTP w sekundach",
    )
    return parser


def query_from_args(args: argparse.Namespace) -> SearchQuery:
    return SearchQuery(
        nazwisko=args.nazwisko,
        imie=args.imie,
        panienskie=args.panienskie,
        imie_o=args.imie_o,
        imie_m=args.imie_m,
        ur_miejsce=args.ur_miejsce,
        ur_dzien=args.ur_dzien,
        ur_miesiac=args.ur_miesiac,
        ur_rok=args.ur_rok,
        zam_miejsce=args.zam_miejsce,
        zawod=args.zawod,
        sm_dzien=args.sm_dzien,
        sm_miesiac=args.sm_miesiac,
        sm_rok=args.sm_rok,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    setup_logging("search_straty_osoby")
    prev_propagate = logger.propagate
    extra_handler: Optional[logging.Handler] = None
    if args.json:
        logger.propagate = False
        extra_handler = logging.StreamHandler(sys.stderr)
        extra_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger.addHandler(extra_handler)
    try:
        return _run_cli(args)
    finally:
        logger.propagate = prev_propagate
        if extra_handler is not None:
            logger.removeHandler(extra_handler)
            extra_handler.close()


def _run_cli(args: argparse.Namespace) -> int:
    try:
        query = query_from_args(args)
        result = search_person(
            query,
            timeout=args.timeout,
            fetch_details=bool(args.details),
            max_details=args.max_details,
        )
    except StratySearchError as exc:
        logger.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return 2

    if args.output:
        try:
            write_output(result, args.output)
            logger.info("Zapisano: %s", args.output)
        except StratySearchError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.json:
        print(result_to_json(result))
    else:
        print(format_table(result), end="")

    if result.kind in {"too_many", "no_criteria"}:
        return 3
    if result.kind == "no_matches":
        return 1
    if result.kind == "unknown":
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
