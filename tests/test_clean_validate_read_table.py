"""Testy _read_table w clean_validate_send_pipeline (CSV / XLSX)."""

from __future__ import annotations

import pandas as pd

import clean_validate_send_pipeline as pipe


def test_read_table_csv(tmp_path) -> None:
    p = tmp_path / "a.csv"
    df_in = pd.DataFrame([{"a": 1, "b": 2}])
    df_in.to_csv(p, index=False, encoding="utf-8-sig")
    out = pipe._read_table(str(p))
    assert len(out) == 1
    assert int(out.loc[0, "a"]) == 1


def test_read_table_xlsx(tmp_path) -> None:
    p = tmp_path / "b.xlsx"
    df_in = pd.DataFrame([{"Firma": "F", "E-mail rekrutacyjny": "e@f.pl"}])
    df_in.to_excel(p, index=False)
    out = pipe._read_table(str(p))
    assert len(out) >= 1
