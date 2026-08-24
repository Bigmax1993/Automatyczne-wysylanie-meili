# -*- coding: utf-8 -*-
"""Nadchodzące mecze lig Aleksa z FootyStats (bez wyniku).

Nie nadpisuje aleks_ligi_stats.xlsx — tylko cache + DataFrame do predykcji.

Uruchomienie:
  python upcoming.py
  python upcoming.py --days 5 --refresh
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from bs4 import BeautifulSoup

import export_aleks_stats as aleks
import scrape_footystats as sf
from team_names import TEAM_ALIASES, canonical_name, known_teams_by_league, map_team_to_known

ROOT = Path(__file__).resolve().parent
CACHE_PATH = ROOT / "cache" / "upcoming_fixtures.json"
CACHE_TTL_HOURS = 6
URL_EN = "https://footystats.org/"
BBC_FIXTURES = "https://www.bbc.com/sport/football/scores-fixtures/{iso}"
BBC_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
VERSUS_RE = re.compile(r"^(.+?)\s+versus\s+(.+?)\s+kick off\s+", re.I)
FT_RE = re.compile(r"^(.+?)\s+(\d+)\s*,\s*(.+?)\s+(\d+)\s+at\s+Full time$", re.I)

BBC_LEAGUE_MAP = {
    "Premier League": "Premier League",
    "Spanish La Liga": "La Liga",
    "Italian Serie A": "Serie A",
    "German Bundesliga": "Bundesliga",
    "German 2. Bundesliga": "Bundesliga 2",
    "Dutch Eredivisie": "Eredivisie",
    "Swedish Allsvenskan": "Allsvenskan",
    "Norwegian Eliteserien": "Eliteserien",
    "Swiss Super League": "Super League",
}

logger = logging.getLogger("upcoming")

COL_LIGA = "ліга"
COL_DATA = "дата"
COL_HOME = "господар"
COL_AWAY = "гість"
COL_RESULT = "результат"

STAT_EMPTY = {
    "фоли_господар": "",
    "фоли_гість": "",
    "фоли": "",
    "кутові_господар": "",
    "кутові_гість": "",
    "кутові": "",
    "жовті_картки_господар": "",
    "жовті_картки_гість": "",
    "жовті_картки": "",
    "удари_господар": "",
    "удари_гість": "",
    "удари": "",
    "удари_в_площину_господар": "",
    "удари_в_площину_гість": "",
    "удари_в_площину": "",
    "оз": "",
}


def _safe_print(text: str) -> None:
    try:
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(errors="replace")
            except Exception:
                pass
        print(text)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"))


def urls_for_date(day: date) -> list[str]:
    """Kandydaci URL FootyStats na dany dzień (EN, potem RU)."""
    iso = day.strftime("%Y-%m-%d")
    dmy = day.strftime("%d-%m-%Y")
    month = day.strftime("%B").lower()
    return [
        f"{URL_EN}?date={iso}",
        f"{URL_EN}{day.day}-{month}-{day.year}",
        f"{sf.URL}?date={iso}",
        f"{sf.URL}?date={dmy}",
        URL_EN if day == date.today() else "",
        sf.URL if day == date.today() else "",
    ]


def complete_match_date(dd_mm: str, *, year: int | None = None, fallback: date | None = None) -> str:
    """Zamienia 18/08 na 18/08/2026."""
    fb = fallback or date.today()
    y = year or fb.year
    text = (dd_mm or "").strip()
    m = re.match(r"^(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?$", text)
    if not m:
        return fb.strftime("%d/%m/%Y")
    d, mo, yr = int(m.group(1)), int(m.group(2)), m.group(3)
    if yr:
        y = int(yr)
        if y < 100:
            y += 2000
    try:
        return date(y, mo, d).strftime("%d/%m/%Y")
    except ValueError:
        return fb.strftime("%d/%m/%Y")


def _versus_count(el) -> int:
    n = 0
    for span in el.select("span.visually-hidden"):
        if VERSUS_RE.match(span.get_text(" ", strip=True)):
            n += 1
    return n


def _league_block(h2):
    p = h2
    for _ in range(8):
        p = getattr(p, "parent", None)
        if p is None:
            return None
        n_h2 = len(p.select("h2[class*=GroupHeader]"))
        if _versus_count(p) > 0 and n_h2 == 1:
            return p
    return None


def _bbc_section_spans(h2) -> list[str]:
    """Teksty span.visually-hidden w sekcji ligi (od h2 do następnego h2)."""
    texts: list[str] = []
    for sib in h2.find_all_next():
        if sib.name == "h2" and "GroupHeader" in " ".join(sib.get("class", [])):
            break
        if sib.name == "span" and "visually-hidden" in " ".join(sib.get("class", [])):
            texts.append(sib.get_text(" ", strip=True))
    return texts


def parse_bbc_results(html: str, match_day: date) -> list[dict]:
    """Parsuje rozegrane mecze lig Aleksa (wynik FT) ze strony BBC Sport."""
    soup = BeautifulSoup(html or "", "lxml")
    rows: list[dict] = []
    for h2 in soup.select("h2[class*=GroupHeader]"):
        title = h2.get_text(" ", strip=True)
        liga = BBC_LEAGUE_MAP.get(title)
        if not liga:
            continue
        for text in _bbc_section_spans(h2):
            m = FT_RE.match(text)
            if not m:
                continue
            hg, ag = int(m.group(2)), int(m.group(4))
            rows.append(
                {
                    "Kraj": "",
                    "Liga": liga,
                    "_aleks_liga": liga,
                    "Gospodarz": m.group(1).strip(),
                    "Gość": m.group(3).strip(),
                    "Data": match_day.strftime("%d/%m/%Y"),
                    "Wynik": f"{hg}:{ag}",
                    "HG": hg,
                    "AG": ag,
                }
            )
    return rows


def parse_bbc_fixtures(html: str, match_day: date) -> list[dict]:
    """Parsuje nadchodzące mecze lig Aleksa ze strony BBC Sport."""
    soup = BeautifulSoup(html or "", "lxml")
    rows: list[dict] = []
    for h2 in soup.select("h2[class*=GroupHeader]"):
        title = h2.get_text(" ", strip=True)
        liga = BBC_LEAGUE_MAP.get(title)
        if not liga:
            continue
        box = _league_block(h2)
        if box is None:
            continue
        for span in box.select("span.visually-hidden"):
            m = VERSUS_RE.match(span.get_text(" ", strip=True))
            if not m:
                continue
            rows.append(
                {
                    "Kraj": "",
                    "Liga": liga,
                    "_aleks_liga": liga,
                    "Gospodarz": m.group(1).strip(),
                    "Gość": m.group(2).strip(),
                    "Data": match_day.strftime("%d/%m/%Y"),
                }
            )
    return rows


def fetch_bbc_html(day: date) -> str:
    url = BBC_FIXTURES.format(iso=day.strftime("%Y-%m-%d"))
    try:
        r = requests.get(url, timeout=45, headers={"User-Agent": BBC_UA})
        if r.status_code != 200 or len(r.content) < 500:
            logger.warning("BBC %s: HTTP %s", day, r.status_code)
            return ""
        return r.content.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("BBC %s fail: %s", day, exc)
        return ""


def fetch_bbc_day(day: date) -> list[dict]:
    html = fetch_bbc_html(day)
    if not html:
        return []
    rows = parse_bbc_fixtures(html, day)
    logger.info("BBC %s: %s meczow lig Aleksa", day, len(rows))
    return rows


def fetch_bbc_results_day(day: date) -> list[dict]:
    html = fetch_bbc_html(day)
    if not html:
        return []
    rows = parse_bbc_results(html, day)
    logger.info("BBC wyniki %s: %s meczow lig Aleksa", day, len(rows))
    return rows


def rows_to_aleks_fixtures(
    rows: list[dict],
    *,
    match_day: date,
    known: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    """Filtr lig Aleksa → wiersze bez wyniku (nadchodzące)."""
    known = known or {}
    ready = [r for r in rows if r.get("_aleks_liga")]
    rest = [r for r in rows if not r.get("_aleks_liga")]
    aleks_rows = list(ready) + (aleks.filter_aleks_matches(rest) if rest else [])
    out: list[dict[str, Any]] = []
    date_str = match_day.strftime("%d/%m/%Y")
    for m in aleks_rows:
        liga = str(m.get("_aleks_liga") or "")
        home = map_team_to_known(str(m.get("Gospodarz") or ""), liga, known)
        away = map_team_to_known(str(m.get("Gość") or ""), liga, known)
        if not home or not away:
            continue
        out.append(
            {
                COL_LIGA: liga,
                COL_DATA: date_str,
                COL_HOME: home,
                COL_AWAY: away,
                COL_RESULT: "",
                **STAT_EMPTY,
            }
        )
    if not out:
        return pd.DataFrame(columns=[COL_LIGA, COL_DATA, COL_HOME, COL_AWAY, COL_RESULT])
    return pd.DataFrame(out).drop_duplicates(subset=[COL_LIGA, COL_DATA, COL_HOME, COL_AWAY])


def rows_to_aleks_results(
    rows: list[dict],
    *,
    match_day: date,
    known: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    """Filtr lig Aleksa → wiersze z wynikiem FT (BBC)."""
    known = known or {}
    ready = [r for r in rows if r.get("_aleks_liga")]
    rest = [r for r in rows if not r.get("_aleks_liga")]
    aleks_rows = list(ready) + (aleks.filter_aleks_matches(rest) if rest else [])
    out: list[dict[str, Any]] = []
    date_str = match_day.strftime("%d/%m/%Y")
    for m in aleks_rows:
        liga = str(m.get("_aleks_liga") or "")
        home = map_team_to_known(str(m.get("Gospodarz") or ""), liga, known)
        away = map_team_to_known(str(m.get("Gość") or ""), liga, known)
        score = str(m.get("Wynik") or "").strip()
        if not home or not away or not re.match(r"^\d+:\d+$", score):
            continue
        hg, ag = (int(x) for x in score.split(":", 1))
        out.append(
            {
                COL_LIGA: liga,
                COL_DATA: date_str,
                COL_HOME: home,
                COL_AWAY: away,
                COL_RESULT: score,
                **STAT_EMPTY,
                "оз": "так" if hg > 0 and ag > 0 else "ні",
            }
        )
    if not out:
        return pd.DataFrame(columns=[COL_LIGA, COL_DATA, COL_HOME, COL_AWAY, COL_RESULT])
    return pd.DataFrame(out).drop_duplicates(subset=[COL_LIGA, COL_DATA, COL_HOME, COL_AWAY])


def _has_ft_score(value: object) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(re.match(r"^\d+:\d+$", str(value).strip()))


def _match_keys(df: pd.DataFrame) -> list[tuple[str, str, str, str]]:
    d = pd.to_datetime(df[COL_DATA], dayfirst=True, errors="coerce")
    return list(
        zip(
            df[COL_LIGA].astype(str),
            d.dt.strftime("%Y-%m-%d"),
            df[COL_HOME].map(lambda x: canonical_name(str(x))),
            df[COL_AWAY].map(lambda x: canonical_name(str(x))),
        )
    )


def merge_recent_results(
    existing: pd.DataFrame,
    recent: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Dopisuje/uzupełnia wyniki FT z BBC (bez nadpisywania istniejących wyników)."""
    stats = {"added": 0, "updated": 0}
    if recent is None or recent.empty:
        return existing, stats
    if existing is None or existing.empty:
        return recent.copy(), {"added": len(recent), "updated": 0}

    out = existing.copy().reset_index(drop=True)
    key_to_idx = {k: i for i, k in enumerate(_match_keys(out))}
    for _, row in recent.iterrows():
        score = row.get(COL_RESULT)
        if not _has_ft_score(score):
            continue
        key = _match_keys(pd.DataFrame([row]))[0]
        if key in key_to_idx:
            idx = key_to_idx[key]
            if not _has_ft_score(out.iloc[idx][COL_RESULT]):
                out.at[idx, COL_RESULT] = score
                if "оз" in row.index and pd.notna(row.get("оз")):
                    out.at[idx, "оз"] = row["оз"]
                stats["updated"] += 1
            continue
        add = row.copy()
        for col in out.columns:
            if col not in add.index:
                add[col] = pd.NA
        out = pd.concat([out, pd.DataFrame([add[list(out.columns)]])], ignore_index=True)
        key_to_idx[key] = len(out) - 1
        stats["added"] += 1
    return out, stats


def sync_played_from_bbc(
    df_2026: pd.DataFrame,
    df_history: pd.DataFrame,
    *,
    from_date: date,
    days_back: int = 21,
    persist_aleks: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """Pobiera wyniki FT z BBC i dopisuje rozegrane mecze do DataFrame + aleks."""
    recent = fetch_recent_results(
        days_back=days_back,
        from_date=from_date,
        history=df_history,
    )
    stats: dict[str, int] = {"fetched": len(recent), "added": 0, "updated": 0, "saved": 0}
    if recent.empty:
        return df_2026, df_history, stats
    df_2026, merge_stats = merge_recent_results(df_2026, recent)
    df_history, _ = merge_recent_results(df_history, recent)
    stats["added"] = merge_stats["added"]
    stats["updated"] = merge_stats["updated"]
    if persist_aleks:
        saved = sync_recent_to_aleks(recent)
        stats["saved"] = int(saved.get("saved") or 0)
    return df_2026, df_history, stats


def fetch_recent_results(
    *,
    days_back: int = 21,
    from_date: date | None = None,
    until: date | None = None,
    history: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Pobiera rozegrane mecze z ostatnich dni (BBC Sport, wynik FT)."""
    until = until or date.today()
    start = until - timedelta(days=max(1, days_back))
    if from_date is not None and start < from_date:
        start = from_date
    known = known_teams_by_league(history) if history is not None else {}
    frames: list[pd.DataFrame] = []
    day = start
    while day < until:
        try:
            rows = fetch_bbc_results_day(day)
        except Exception:
            logger.exception("Nie udalo sie pobrac wynikow %s", day)
            rows = []
        df = rows_to_aleks_results(rows, match_day=day, known=known)
        if not df.empty:
            frames.append(df)
        day += timedelta(days=1)
    if not frames:
        return pd.DataFrame(columns=[COL_LIGA, COL_DATA, COL_HOME, COL_AWAY, COL_RESULT])
    return pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=[COL_LIGA, COL_DATA, COL_HOME, COL_AWAY]
    )


def sync_recent_to_aleks(recent: pd.DataFrame) -> dict[str, int]:
    """Zapisuje nowe/uzupełnione wyniki BBC do aleks_ligi_stats.xlsx."""
    from preview_pandas import read_aleks_table, resolve_aleks_path, save_aleks_table

    if recent is None or recent.empty:
        return {"added": 0, "updated": 0, "saved": 0}
    path = resolve_aleks_path()
    if path is None:
        return {"added": 0, "updated": 0, "saved": 0}
    full = read_aleks_table(path)
    full_merged, stats = merge_recent_results(full, recent)
    if stats["added"] + stats["updated"] == 0:
        return {**stats, "saved": 0}
    save_aleks_table(full_merged, path)
    return {**stats, "saved": stats["added"] + stats["updated"]}


def fetch_day_html(day: date) -> tuple[str, str] | None:
    """Pobiera HTML dnia; pierwsza URL z meczami wygrywa."""
    for url in urls_for_date(day):
        if not url:
            continue
        try:
            html, source = sf.fetch_html(url)
        except SystemExit:
            continue
        except Exception as exc:
            logger.warning("Fetch fail %s: %s", url, exc)
            continue
        if html and not sf._is_cloudflare_block(html, sf._extract_title(html)):
            _, rows = sf.parse_matches(html)
            if rows:
                logger.info("Dzien %s: %s meczow z %s (%s)", day, len(rows), url, source)
                return html, source
            logger.info("Dzien %s: HTML OK ale 0 meczow (%s)", day, url)
    return None


def fetch_day_rows(day: date) -> list[dict]:
    """BBC Sport — dni bez lig Aleksa zwracają [] (to normalne, nie fallback do CF)."""
    return fetch_bbc_day(day)


def load_upcoming_cache(*, ttl_hours: int = CACHE_TTL_HOURS) -> dict | None:
    try:
        if not CACHE_PATH.exists():
            return None
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        cached_at = payload.get("cached_at")
        if not cached_at:
            return None
        ts = datetime.fromisoformat(cached_at)
        if datetime.now() - ts > timedelta(hours=ttl_hours):
            return None
        return payload
    except Exception:
        return None


def save_upcoming_cache(by_day: dict[str, list[dict]]) -> Path:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cached_at": datetime.now().isoformat(timespec="seconds"),
        "days": by_day,
    }
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return CACHE_PATH


def fetch_upcoming_fixtures(
    *,
    days: int = 7,
    start: date | None = None,
    refresh: bool = False,
    history: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Pobiera nadchodzące mecze na `days` dni od `start` (domyślnie dziś)."""
    start = start or date.today()
    known = known_teams_by_league(history) if history is not None else {}
    wanted = [(start + timedelta(days=i)) for i in range(max(1, days))]
    wanted_keys = [d.strftime("%Y-%m-%d") for d in wanted]

    by_day: dict[str, list[dict]] = {}
    if not refresh:
        cached = load_upcoming_cache()
        if cached and isinstance(cached.get("days"), dict):
            by_day = {k: v for k, v in cached["days"].items() if k in wanted_keys}

    missing = [d for d, k in zip(wanted, wanted_keys) if k not in by_day]
    if missing:
        for day in missing:
            try:
                rows = fetch_day_rows(day)
            except Exception:
                logger.exception("Nie udalo sie pobrac %s", day)
                rows = []
            by_day[day.strftime("%Y-%m-%d")] = rows
        save_upcoming_cache(by_day)

    frames: list[pd.DataFrame] = []
    for day in wanted:
        rows = by_day.get(day.strftime("%Y-%m-%d")) or []
        df = rows_to_aleks_fixtures(rows, match_day=day, known=known)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=[COL_LIGA, COL_DATA, COL_HOME, COL_AWAY, COL_RESULT])
    return pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=[COL_LIGA, COL_DATA, COL_HOME, COL_AWAY]
    )


def merge_upcoming(existing: pd.DataFrame, upcoming: pd.DataFrame) -> pd.DataFrame:
    """Dokleja nadchodzące, pomijając mecze już obecne (liga+data+drużyny)."""
    if upcoming is None or upcoming.empty:
        return existing
    if existing.empty:
        return upcoming.copy()

    def keys(df: pd.DataFrame) -> list[tuple[str, str, str, str]]:
        d = pd.to_datetime(df[COL_DATA], dayfirst=True, errors="coerce")
        return list(
            zip(
                df[COL_LIGA].astype(str),
                d.dt.strftime("%Y-%m-%d"),
                df[COL_HOME].map(lambda x: canonical_name(str(x))),
                df[COL_AWAY].map(lambda x: canonical_name(str(x))),
            )
        )

    have = set(keys(existing))
    mask = [k not in have for k in keys(upcoming)]
    add = upcoming.loc[mask].copy()
    if add.empty:
        return existing
    for col in existing.columns:
        if col not in add.columns:
            add[col] = pd.NA
    return pd.concat([existing, add[list(existing.columns)]], ignore_index=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Nadchodzace mecze FootyStats")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from preview_pandas import read_aleks_table, resolve_aleks_path

    hist = pd.DataFrame()
    src = resolve_aleks_path()
    if src is not None:
        hist = read_aleks_table(src)
    df = fetch_upcoming_fixtures(days=args.days, refresh=args.refresh, history=hist)
    _safe_print(f"Nadchodzace (ligi Aleksa): {len(df)}")
    if not df.empty:
        _safe_print(df.groupby(COL_LIGA).size().to_string())
        _safe_print(df[[COL_DATA, COL_LIGA, COL_HOME, COL_AWAY]].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
