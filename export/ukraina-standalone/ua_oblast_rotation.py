# -*- coding: utf-8 -*-
"""
Rotacja obwodów UA — jeden obwód na cykl discovery (np. piątek).

Stan: Wyniki/ua_materialy_oblast_rotation.json
Start rotacji: domyślnie 2026-07-13 (env UA_OBLAST_ROTATION_START).
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from ua_oblast_keywords import OBLAST_CONFIG, configure_campaign_oblasts

DEFAULT_ROTATION_START = date(2026, 7, 13)

# Duże rynki → mniejsze obwody
OBLAST_ROTATION_ORDER: tuple[str, ...] = (
    "Kyiv",
    "Lvivska",
    "Odeska",
    "Kharkivska",
    "Dnipropetrovska",
    "Zaporizka",
    "Vinnytska",
    "Poltavska",
    "Cherkaska",
    "Zhytomyrska",
    "Rivnenska",
    "Volyn",
    "Ternopilska",
    "Ivano-Frankivska",
    "Chernivetska",
    "Zakarpatska",
    "Khmelnytska",
    "Kyivska",
    "Chernihivska",
    "Sumska",
    "Mykolaivska",
    "Kirovohradska",
    "Khersonska",
    "Donetska",
    "Luhanska",
)
BUNDESLAND_ROTATION_ORDER = OBLAST_ROTATION_ORDER

STATE_FILENAME = "ua_materialy_oblast_rotation.json"
DEFAULT_MIN_CONTACTS_SINGLE_OBLAST = 20


def get_rotation_start_date() -> date:
    raw = (os.environ.get("UA_OBLAST_ROTATION_START") or "").strip()
    if not raw:
        return DEFAULT_ROTATION_START
    return date.fromisoformat(raw)


def rotation_is_active(as_of: date | None = None) -> bool:
    """False przed startem rotacji — discovery może iść po całej UA."""
    return (as_of or date.today()) >= get_rotation_start_date()


def rotation_state_path(wyniki_dir: Path) -> Path:
    return wyniki_dir / STATE_FILENAME


def _empty_state() -> dict[str, Any]:
    return {"version": 1, "next_index": 0, "history": []}


def load_rotation_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_state()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _empty_state()
        data.setdefault("version", 1)
        data.setdefault("next_index", 0)
        data.setdefault("history", [])
        return data
    except (OSError, json.JSONDecodeError):
        return _empty_state()


def save_rotation_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def peek_next_oblast(state: dict[str, Any] | None = None) -> str:
    st = state if state is not None else _empty_state()
    idx = int(st.get("next_index", 0)) % len(OBLAST_ROTATION_ORDER)
    return OBLAST_ROTATION_ORDER[idx]


peek_next_bundesland = peek_next_oblast


def apply_rotation_to_module(
    module,
    wyniki_dir: Path,
    *,
    min_contacts: int = DEFAULT_MIN_CONTACTS_SINGLE_OBLAST,
    max_discovery_terms: int = 120,
) -> tuple[str, dict[str, Any], Path]:
    state_path = rotation_state_path(wyniki_dir)
    state = load_rotation_state(state_path)
    oblast = peek_next_oblast(state)
    configure_campaign_oblasts(module, [oblast], max_discovery_terms=max_discovery_terms)
    if hasattr(module, "MIN_CONTACTS_TARGET"):
        module.MIN_CONTACTS_TARGET = min_contacts
    return oblast, state, state_path


def commit_rotation_after_run(
    state_path: Path,
    state: dict[str, Any],
    oblast: str,
    *,
    run_date: date | None = None,
) -> str:
    idx = int(state.get("next_index", 0)) % len(OBLAST_ROTATION_ORDER)
    if OBLAST_ROTATION_ORDER[idx] != oblast:
        oblast = OBLAST_ROTATION_ORDER[idx]
    history = list(state.get("history") or [])
    history.append(
        {
            "oblast": oblast,
            "index": idx,
            "at": (run_date or date.today()).isoformat(),
        }
    )
    state["history"] = history[-32:]
    state["next_index"] = (idx + 1) % len(OBLAST_ROTATION_ORDER)
    save_rotation_state(state_path, state)
    return peek_next_oblast(state)


def format_rotation_status(wyniki_dir: Path) -> str:
    state_path = rotation_state_path(wyniki_dir)
    state = load_rotation_state(state_path)
    start = get_rotation_start_date()
    if not rotation_is_active():
        return (
            f"Rotacja obwodów od {start.isoformat()} — "
            f"teraz tryb cała Ukraina (bez rotacji). "
            f"Następny obwód po starcie: {OBLAST_ROTATION_ORDER[0]}"
        )
    current = peek_next_oblast(state)
    nxt_idx = int(state.get("next_index", 0))
    nxt = OBLAST_ROTATION_ORDER[(nxt_idx + 1) % len(OBLAST_ROTATION_ORDER)]
    return (
        f"Bieżący obwód (ten tydzień): {current} | "
        f"następny po zakończeniu: {nxt} | "
        f"indeks={nxt_idx}/{len(OBLAST_ROTATION_ORDER)}"
    )
