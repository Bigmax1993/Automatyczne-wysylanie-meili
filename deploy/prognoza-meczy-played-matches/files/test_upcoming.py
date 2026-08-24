"""Testy upcoming.py (bez sieci)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

import upcoming as up


def test_complete_match_date():
    assert up.complete_match_date("18/08", year=2026) == "18/08/2026"
    assert up.complete_match_date("18/08/2026") == "18/08/2026"


def test_map_team_to_known():
    known = {
        "Premier League": ["Arsenal", "Man City", "Chelsea", "Nott'm Forest"],
        "Super League": ["Zurich", "Basel"],
        "Allsvenskan": ["Goteborg", "Elfsborg"],
        "La Liga": ["Ath Bilbao", "Sevilla"],
    }
    assert up.map_team_to_known("Arsenal", "Premier League", known) == "Arsenal"
    assert up.map_team_to_known("Arsenal FC", "Premier League", known) == "Arsenal"
    assert up.map_team_to_known("Manchester City", "Premier League", known) == "Man City"
    assert up.map_team_to_known("Nottingham Forest", "Premier League", known) == "Nott'm Forest"
    assert up.map_team_to_known("ZÃ¼rich", "Super League", known) == "Zurich"
    assert up.map_team_to_known("IFK Gbg", "Allsvenskan", known) == "Goteborg"
    assert up.map_team_to_known("Athletic Club", "La Liga", known) == "Ath Bilbao"


def test_rows_to_aleks_fixtures_filters_leagues():
    rows = [
        {
            "Kraj": "England",
            "Liga": "Premier League",
            "Gospodarz": "Arsenal",
            "Gość": "Chelsea",
            "Data": "18/08",
        },
        {
            "Kraj": "England",
            "Liga": "National League",
            "Gospodarz": "Barnet",
            "Gość": "York",
            "Data": "18/08",
        },
    ]
    known = {"Premier League": ["Arsenal", "Chelsea"]}
    df = up.rows_to_aleks_fixtures(rows, match_day=date(2026, 8, 18), known=known)
    assert len(df) == 1
    assert df.iloc[0]["ліга"] == "Premier League"
    assert df.iloc[0]["дата"] == "18/08/2026"
    assert df.iloc[0]["результат"] == ""


def test_rows_to_aleks_keeps_premapped_la_liga():
    rows = [
        {
            "Kraj": "",
            "Liga": "La Liga",
            "_aleks_liga": "La Liga",
            "Gospodarz": "Real Madrid",
            "Gość": "Osasuna",
            "Data": "19/08/2026",
        }
    ]
    df = up.rows_to_aleks_fixtures(rows, match_day=date(2026, 8, 19), known={})
    assert len(df) == 1
    assert df.iloc[0]["ліга"] == "La Liga"


def test_parse_bbc_fixtures():
    html = """
    <html><body>
      <div class="ssrcss-1ox7t1a-Container">
        <h2 class="ssrcss-m22vfq-GroupHeader">Premier League</h2>
        <span class="visually-hidden">Arsenal versus Chelsea kick off 15:00</span>
        <span class="visually-hidden">Everton versus Crystal Palace kick off 17:30</span>
      </div>
      <div class="ssrcss-1ox7t1a-Container">
        <h2 class="ssrcss-m22vfq-GroupHeader">Brazilian Serie A</h2>
        <span class="visually-hidden">Flamengo versus Palmeiras kick off 20:00</span>
      </div>
    </body></html>
    """
    rows = up.parse_bbc_fixtures(html, date(2026, 8, 22))
    assert len(rows) == 2
    assert {r["Liga"] for r in rows} == {"Premier League"}
    assert rows[0]["Gospodarz"] == "Arsenal"
    assert rows[0]["Gość"] == "Chelsea"


def test_merge_upcoming_skips_duplicates():
    existing = pd.DataFrame(
        [
            {
                "ліга": "Premier League",
                "дата": pd.Timestamp("2026-08-18"),
                "господар": "Arsenal",
                "гість": "Chelsea",
                "результат": "1:0",
            }
        ]
    )
    upcoming = pd.DataFrame(
        [
            {
                "ліга": "Premier League",
                "дата": "18/08/2026",
                "господар": "Arsenal",
                "гість": "Chelsea",
                "результат": "",
            },
            {
                "ліга": "La Liga",
                "дата": "18/08/2026",
                "господар": "Real Madrid",
                "гість": "Osasuna",
                "результат": "",
            },
        ]
    )
    out = up.merge_upcoming(existing, upcoming)
    assert len(out) == 2
    assert "Osasuna" in set(out["гість"].astype(str))


def test_parse_bbc_results():
    html = """
    <html><body>
      <h2 class="ssrcss-m22vfq-GroupHeader">Premier League</h2>
      <span class="visually-hidden">Hull City 2 , Manchester United 0 at Full time</span>
      <span class="visually-hidden">Everton 2 , Crystal Palace 0 at Full time</span>
      <h2 class="ssrcss-m22vfq-GroupHeader">Brazilian Serie A</h2>
      <span class="visually-hidden">Flamengo 1 , Palmeiras 0 at Full time</span>
    </body></html>
    """
    rows = up.parse_bbc_results(html, date(2026, 8, 22))
    assert len(rows) == 2
    assert rows[0]["Wynik"] == "2:0"
    assert rows[0]["Gospodarz"] == "Hull City"
    assert rows[1]["Gość"] == "Crystal Palace"


def test_rows_to_aleks_results_sets_btts():
    rows = [
        {
            "_aleks_liga": "Premier League",
            "Gospodarz": "Everton",
            "Gość": "Crystal Palace",
            "Wynik": "2:0",
        }
    ]
    known = {"Premier League": ["Everton", "Crystal Palace"]}
    df = up.rows_to_aleks_results(rows, match_day=date(2026, 8, 22), known=known)
    assert len(df) == 1
    assert df.iloc[0]["результат"] == "2:0"
    assert df.iloc[0]["оз"] == "ні"


def test_merge_recent_results_adds_and_updates():
    existing = pd.DataFrame(
        [
            {
                "ліга": "Premier League",
                "дата": "22/08/2026",
                "господар": "Everton",
                "гість": "Crystal Palace",
                "результат": "",
                "оз": "",
            }
        ]
    )
    recent = pd.DataFrame(
        [
            {
                "ліга": "Premier League",
                "дата": "22/08/2026",
                "господар": "Everton",
                "гість": "Crystal Palace",
                "результат": "2:0",
                "оз": "ні",
            },
            {
                "ліга": "Premier League",
                "дата": "22/08/2026",
                "господар": "Hull",
                "гість": "Man United",
                "результат": "2:0",
                "оз": "ні",
            },
        ]
    )
    out, stats = up.merge_recent_results(existing, recent)
    assert stats == {"added": 1, "updated": 1}
    assert len(out) == 2
    everton = out[out["господар"] == "Everton"].iloc[0]
    assert everton["результат"] == "2:0"
    assert "Man United" in set(out["гість"].astype(str))


def test_sync_played_from_bbc_merges(monkeypatch):
    recent = pd.DataFrame(
        [
            {
                "ліга": "Premier League",
                "дата": "22/08/2026",
                "господар": "Hull",
                "гість": "Man United",
                "результат": "2:0",
                "оз": "ні",
            }
        ]
    )
    monkeypatch.setattr(up, "fetch_recent_results", lambda **kwargs: recent)
    monkeypatch.setattr(up, "sync_recent_to_aleks", lambda recent: {"saved": 0})

    df = pd.DataFrame(columns=[up.COL_LIGA, up.COL_DATA, up.COL_HOME, up.COL_AWAY, up.COL_RESULT])
    hist = df.copy()
    out, hist_out, stats = up.sync_played_from_bbc(
        df,
        hist,
        from_date=date(2026, 8, 13),
        persist_aleks=True,
    )
    assert stats["added"] == 1
    assert len(out) == 1
    assert out.iloc[0]["результат"] == "2:0"
    assert len(hist_out) == 1
