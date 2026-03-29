"""
Wczytywanie skoroszytów typu „raport”: tytuł w pierwszych wierszach, nagłówki tabeli niżej,
wiele arkuszy (firmy / agencje / …). Łączy arkusze danych, pomija m.in. „Podsumowanie”.
"""

from __future__ import annotations

import logging
import os
import re
from typing import List, Set

import pandas as pd

from pipeline_logging import setup_logging

logger = logging.getLogger(__name__)
setup_logging("excel_workbook_reader")

DEFAULT_SKIP_SHEETS_LOWER: Set[str] = frozenset(
    {"podsumowanie", "summary", "spis tresci", "readme"}
)
HEADER_SCAN_ROWS = int(os.environ.get("EXCEL_HEADER_SCAN_ROWS", "35"))
_FORCE_HEADER = os.environ.get("EXCEL_FORCE_HEADER_ROW", "").strip()


def _skip_sheet_names() -> Set[str]:
    out = set(DEFAULT_SKIP_SHEETS_LOWER)
    extra = os.environ.get("EXCEL_SKIP_SHEET_NAMES", "")
    for part in extra.split(","):
        p = part.strip().lower()
        if p:
            out.add(p)
    return out


def _cell_lower(v) -> str:
    if pd.isna(v):
        return ""
    return str(v).strip().lower()


def _row_looks_like_contact_header(values) -> bool:
    cells = [_cell_lower(x) for x in values if _cell_lower(x)]
    joined = " ".join(cells)
    if "firma" not in joined:
        return False
    if "rekrutacy" in joined or "e-mail" in joined or " e mail" in joined.replace(
        "-", " "
    ):
        return True
    if "strona" in joined and "www" in joined:
        return True
    return False


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    new_cols = []
    used: dict[str, int] = {}
    for i, c in enumerate(out.columns):
        base = re.sub(r"\s+", " ", str(c).strip()) if pd.notna(c) else ""
        if not base or base.lower().startswith("unnamed"):
            base = f"_col_{i}"
        if base in used:
            used[base] += 1
            base = f"{base}_{used[base]}"
        else:
            used[base] = 0
        new_cols.append(base)
    out.columns = new_cols
    return out


def _read_one_sheet(path: str, sheet: str) -> pd.DataFrame | None:
    force_row: int | None = None
    if _FORCE_HEADER.isdigit():
        force_row = int(_FORCE_HEADER)

    if force_row is not None:
        df = pd.read_excel(path, sheet_name=sheet, header=force_row)
        df = _normalize_columns(df)
        df = df.dropna(how="all")
        return df if len(df) else None

    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    if raw.shape[0] == 0:
        return None

    h = 0
    limit = min(HEADER_SCAN_ROWS, len(raw))
    for i in range(limit):
        if _row_looks_like_contact_header(raw.iloc[i].values):
            h = i
            break

    header_vals = raw.iloc[h].tolist()
    body = raw.iloc[h + 1 :].copy()
    body.columns = [
        re.sub(r"\s+", " ", str(c).strip()) if pd.notna(c) and str(c).strip() else f"_col_{j}"
        for j, c in enumerate(header_vals)
    ]
    body = _normalize_columns(body)
    body = body.dropna(how="all")
    if len(body) == 0:
        return None
    return body


def read_excel_workbook(path: str) -> pd.DataFrame:
    """
    Wszystkie arkusze poza listą pomijanych; nagłówek wykrywany w pierwszych wierszach
    albo EXCEL_FORCE_HEADER_ROW (0 = pierwszy wiersz Excela).
    """
    logger.info("Wczytywanie skoroszytu: %s", path)
    skip = _skip_sheet_names()
    xl = pd.ExcelFile(path)
    parts: List[pd.DataFrame] = []
    for sheet in xl.sheet_names:
        if sheet.strip().lower() in skip:
            continue
        try:
            chunk = _read_one_sheet(path, sheet)
        except Exception as e:
            logger.warning("Pominięto arkusz %r w %s: %s", sheet, path, e)
            continue
        if chunk is not None and len(chunk):
            parts.append(chunk)
    if not parts:
        logger.warning("Brak danych kontaktowych w skoroszycie (wszystkie arkusze puste lub pominięte): %s", path)
        return pd.DataFrame()
    logger.debug("Połączono %s arkuszy, %s wierszy", len(parts), sum(len(p) for p in parts))
    return pd.concat(parts, ignore_index=True)
