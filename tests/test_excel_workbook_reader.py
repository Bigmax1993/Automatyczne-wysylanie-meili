"""Wczytywanie skoroszytów wieloarkuszowych (nagłówki, pomijane arkusze)."""

from __future__ import annotations

import pandas as pd

import excel_workbook_reader as ewr


def test_read_excel_workbook_logs_path(tmp_path, capsys) -> None:
    path = tmp_path / "log_me.xlsx"
    pd.DataFrame([{"Firma": "A", "E-mail rekrutacyjny": "a@b.pl"}]).to_excel(path, index=False)
    df = ewr.read_excel_workbook(str(path))
    assert len(df) >= 1
    assert "Wczytywanie skoroszytu" in capsys.readouterr().out


def test_read_excel_detects_header_after_title_rows(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("EXCEL_FORCE_HEADER_ROW", raising=False)
    path = tmp_path / "raport.xlsx"
    rows = [
        ["400 FIRM — tytuł", None],
        [None, None],
        ["Lp.", "Firma", "Miasto", "E-mail rekrutacyjny", "Stanowisko / Rola"],
        [1, "ACME", "Wrocław", "hr@acme.pl", "Data Analyst"],
    ]
    pd.DataFrame(rows).to_excel(path, header=False, index=False)
    df = ewr.read_excel_workbook(str(path))
    assert len(df) == 1
    assert df.iloc[0]["Firma"] == "ACME"
    assert df.iloc[0]["E-mail rekrutacyjny"] == "hr@acme.pl"


def test_read_excel_skips_summary_sheet(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("EXCEL_FORCE_HEADER_ROW", raising=False)
    path = tmp_path / "multi.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        pd.DataFrame([["tylko", "podsumowanie"]]).to_excel(
            w, sheet_name="Podsumowanie", header=False, index=False
        )
        pd.DataFrame(
            [
                ["Lp.", "Firma", "E-mail rekrutacyjny"],
                [1, "X", "x@x.pl"],
            ]
        ).to_excel(w, sheet_name="400 Firm", header=False, index=False)
    df = ewr.read_excel_workbook(str(path))
    assert len(df) == 1
    assert df.iloc[0]["Firma"] == "X"


def test_read_excel_concat_sheets(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("EXCEL_FORCE_HEADER_ROW", raising=False)
    path = tmp_path / "two.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        pd.DataFrame(
            [["Lp.", "Firma", "E-mail rekrutacyjny"], [1, "A", "a@a.pl"]]
        ).to_excel(w, sheet_name="Ark1", header=False, index=False)
        pd.DataFrame(
            [["Lp.", "Firma", "E-mail rekrutacyjny"], [1, "B", "b@b.pl"]]
        ).to_excel(w, sheet_name="Ark2", header=False, index=False)
    df = ewr.read_excel_workbook(str(path))
    assert len(df) == 2
    assert set(df["Firma"].tolist()) == {"A", "B"}


def test_read_excel_skips_sheet_from_EXCEL_SKIP_SHEET_NAMES(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("EXCEL_FORCE_HEADER_ROW", raising=False)
    monkeypatch.setenv("EXCEL_SKIP_SHEET_NAMES", "draft,scratch")
    path = tmp_path / "skip_env.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        pd.DataFrame(
            [["Lp.", "Firma", "E-mail rekrutacyjny"], [1, "Ignored", "i@i.pl"]]
        ).to_excel(w, sheet_name="Draft", header=False, index=False)
        pd.DataFrame(
            [["Lp.", "Firma", "E-mail rekrutacyjny"], [1, "Kept", "k@k.pl"]]
        ).to_excel(w, sheet_name="Data", header=False, index=False)
    df = ewr.read_excel_workbook(str(path))
    assert len(df) == 1
    assert df.iloc[0]["Firma"] == "Kept"


def test_read_excel_force_header_row_index(tmp_path, monkeypatch) -> None:
    """_FORCE_HEADER jest wczytywane przy imporcie modułu; symulujemy EXCEL_FORCE_HEADER_ROW=2."""
    monkeypatch.setattr(ewr, "_FORCE_HEADER", "2")
    path = tmp_path / "forced.xlsx"
    rows = [
        ["noise", None],
        [None, None],
        ["Firma", "E-mail rekrutacyjny"],
        ["ForcedCo", "f@f.pl"],
    ]
    pd.DataFrame(rows).to_excel(path, header=False, index=False)
    df = ewr.read_excel_workbook(str(path))
    assert len(df) == 1
    assert df.iloc[0]["Firma"] == "ForcedCo"
