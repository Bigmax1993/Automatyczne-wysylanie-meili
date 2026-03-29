"""Testy brzegowe contact_mailer (kolumny, limity, log kampanii, zapis Excel, znajdz_excel)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import pytest
from email.message import EmailMessage

import contact_mailer as cm


def test_znajdz_excel_returns_newest_match(tmp_path) -> None:
    d = tmp_path / "docs"
    d.mkdir()
    old = d / "Kontakty_old.xlsx"
    new = d / "Kontakty_new.xlsx"
    pd.DataFrame([{"a": 1}]).to_excel(old, index=False)
    time.sleep(0.05)
    pd.DataFrame([{"a": 2}]).to_excel(new, index=False)
    found = cm.znajdz_excel(str(d), "Kontakty*.xlsx")
    assert Path(found).resolve() == new.resolve()


def test_znajdz_excel_raises_when_no_match(tmp_path) -> None:
    empty = tmp_path / "e"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match="Nie znaleziono pliku"):
        cm.znajdz_excel(str(empty), "Brak*.xlsx")


def test_resolve_column_map_supports_aliases() -> None:
    df = pd.DataFrame(
        [
            {
                "Email": "a@b.com",
                "Firma": "Firma A",
                "Stanowisko": "Data Analyst",
                "Miasto": "Wroclaw",
                "Telefon": "123456789",
                "Branza": "IT",
                "WWW": "example.com",
                "Zrodlo / Portal": "pracuj.pl",
            }
        ]
    )

    col_map = cm._resolve_column_map(df)

    assert col_map["email"] == "Email"
    assert col_map["role"] == "Stanowisko"
    assert col_map["phone"] == "Telefon"
    assert col_map["industry"] == "Branza"
    assert col_map["website"] == "WWW"
    assert col_map["source"] == "Zrodlo / Portal"


def test_main_raises_for_missing_required_columns(monkeypatch) -> None:
    import excel_workbook_reader

    df = pd.DataFrame([{cm.COL_COMPANY: "Firma A", cm.COL_CITY: "Wroclaw"}])
    monkeypatch.setattr(cm, "_resolve_excel_path", lambda: "dummy.xlsx")
    monkeypatch.setattr(cm, "_resolve_cv_path", lambda: "cv.pdf")
    monkeypatch.setattr(excel_workbook_reader, "read_excel_workbook", lambda _p: df)

    with pytest.raises(ValueError, match="Brak wymaganej kolumny"):
        cm.main()


def test_resolve_cv_path_raises_when_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cm, "SEARCH_DIR", str(tmp_path))
    monkeypatch.delenv("CV_PATH", raising=False)

    with pytest.raises(FileNotFoundError, match="Nie znaleziono CV"):
        cm._resolve_cv_path()


def test_resolve_cv_path_finds_pdf_in_documents_cv_subfolder(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cm, "SEARCH_DIR", str(tmp_path))
    monkeypatch.delenv("CV_PATH", raising=False)
    cv_dir = tmp_path / "CV"
    cv_dir.mkdir()
    cv_path = cv_dir / "Maksym Swinczak CV.pdf"
    cv_path.write_bytes(b"%PDF-1.4 test\n")

    resolved = cm._resolve_cv_path()
    assert resolved == str(cv_path)


def test_resolve_cv_path_prefers_env_path(tmp_path, monkeypatch) -> None:
    cv_path = tmp_path / "MojeCV.pdf"
    cv_path.write_bytes(b"%PDF-1.4 test\n")
    monkeypatch.setenv("CV_PATH", str(cv_path))

    resolved = cm._resolve_cv_path()
    assert resolved == str(cv_path)


def test_resolve_cv_path_accepts_env_without_pdf_extension(tmp_path, monkeypatch) -> None:
    cv_path = tmp_path / "MojeCV.pdf"
    cv_path.write_bytes(b"%PDF-1.4 test\n")
    monkeypatch.setenv("CV_PATH", str(tmp_path / "MojeCV"))

    resolved = cm._resolve_cv_path()
    assert resolved == str(cv_path)


def test_resolve_cv_path_accepts_env_directory(tmp_path, monkeypatch) -> None:
    cv_dir = tmp_path / "cv_folder"
    cv_dir.mkdir()
    cv_path = cv_dir / "CV_Kandydat.pdf"
    cv_path.write_bytes(b"%PDF-1.4 test\n")
    monkeypatch.setenv("CV_PATH", str(cv_dir))

    resolved = cm._resolve_cv_path()
    assert resolved == str(cv_path)


def test_resolve_cv_path_accepts_env_directory_file_with_cv_inside_name(
    tmp_path, monkeypatch
) -> None:
    cv_dir = tmp_path / "cv_folder_2"
    cv_dir.mkdir()
    cv_path = cv_dir / "Maksym Swinczak CV.pdf"
    cv_path.write_bytes(b"%PDF-1.4 test\n")
    monkeypatch.setenv("CV_PATH", str(cv_dir))

    resolved = cm._resolve_cv_path()
    assert resolved == str(cv_path)


def test_process_rows_counts_skipped_and_sent(monkeypatch) -> None:
    monkeypatch.setattr(cm, "DRY_RUN", True)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "zapisz_excel", lambda _df, _path: None)
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)
    monkeypatch.setattr(cm, "_generate_mail_with_retry", lambda **_kwargs: "tresc")
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat")

    df = pd.DataFrame(
        [
            {
                cm.COL_EMAIL: "sent@example.com",
                cm.COL_COMPANY: "A",
                cm.COL_ROLE: "R",
                cm.COL_CITY: "C",
                cm.STATUS_COL: "Tak",
                cm.DATE_COL: pd.NaT,
            },
            {
                cm.COL_EMAIL: "",
                cm.COL_COMPANY: "B",
                cm.COL_ROLE: "R2",
                cm.COL_CITY: "C2",
                cm.STATUS_COL: pd.NA,
                cm.DATE_COL: pd.NaT,
            },
            {
                cm.COL_EMAIL: "new@example.com",
                cm.COL_COMPANY: "C",
                cm.COL_ROLE: "R3",
                cm.COL_CITY: "C3",
                cm.STATUS_COL: pd.NA,
                cm.DATE_COL: pd.NaT,
            },
        ]
    )

    stats = cm._process_rows(df, excel_path="dummy.xlsx", smtp=None, cv_path="cv.pdf")

    assert stats["skipped"] == 2
    assert stats["sent"] == 1
    assert df.at[2, cm.STATUS_COL] == "Tak"


def test_process_rows_uses_default_fallback_when_optional_columns_missing(monkeypatch) -> None:
    monkeypatch.setattr(cm, "DRY_RUN", True)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "zapisz_excel", lambda _df, _path: None)
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat")

    captured = {}

    def _capture_generate(**kwargs):
        captured.update(kwargs)
        return "tresc"

    monkeypatch.setattr(cm, "_generate_mail_with_retry", _capture_generate)

    df = pd.DataFrame(
        [
            {
                cm.COL_EMAIL: "new2@example.com",
                cm.COL_COMPANY: "Firma D",
                cm.COL_ROLE: "Data Engineer",
                cm.COL_CITY: "Poznan",
                cm.STATUS_COL: pd.NA,
                cm.DATE_COL: pd.NaT,
            }
        ]
    )

    stats = cm._process_rows(df, excel_path="dummy.xlsx", smtp=None, cv_path="cv.pdf")

    assert stats["sent"] == 1
    assert captured["industry"] == "(brak branży)"
    assert captured["website"] == "(brak strony WWW)"
    assert captured["source"] == "(brak źródła)"


def test_process_rows_respects_daily_limit(monkeypatch) -> None:
    monkeypatch.setattr(cm, "DRY_RUN", True)
    monkeypatch.setattr(cm, "MAX_EMAILS_PER_DAY", 1)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "zapisz_excel", lambda _df, _path: None)
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat")
    monkeypatch.setattr(cm, "_generate_mail_with_retry", lambda **_kwargs: "tresc")
    monkeypatch.setattr(cm, "CAMPAIGN_LOG_ENABLED", False)

    df = pd.DataFrame(
        [
            {
                cm.COL_EMAIL: "one@example.com",
                cm.COL_COMPANY: "A",
                cm.COL_ROLE: "R",
                cm.COL_CITY: "C",
                cm.STATUS_COL: pd.NA,
                cm.DATE_COL: pd.NaT,
            },
            {
                cm.COL_EMAIL: "two@example.com",
                cm.COL_COMPANY: "B",
                cm.COL_ROLE: "R2",
                cm.COL_CITY: "C2",
                cm.STATUS_COL: pd.NA,
                cm.DATE_COL: pd.NaT,
            },
        ]
    )

    stats = cm._process_rows(df, excel_path="dummy.xlsx", smtp=None, cv_path="cv.pdf")
    assert stats["sent"] == 1
    assert stats["daily_limit_reached"] == 1
    assert "limit dzienny" in str(df.at[1, cm.STATUS_COL]).lower()


def test_append_campaign_log_writes_csv(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cm, "CAMPAIGN_LOG_ENABLED", True)
    log_path = str(tmp_path / "campaign_log.csv")

    cm._append_campaign_log(
        log_path=log_path,
        email="hr@example.com",
        company="Firma Log",
        subject="Temat",
        status="sent",
        reason="",
    )

    out = pd.read_csv(log_path)
    assert len(out) == 1
    assert out.loc[0, "email"] == "hr@example.com"
    assert out.loc[0, "status"] == "sent"


def test_attach_cv_raises_for_missing_file(tmp_path) -> None:
    msg = EmailMessage()
    missing = tmp_path / "brak_cv.pdf"
    with pytest.raises(FileNotFoundError):
        cm._attach_cv(msg, str(missing))


def test_resolve_column_map_prefers_primary_names_over_aliases() -> None:
    df = pd.DataFrame(
        [
            {
                cm.COL_EMAIL: "primary@example.com",
                "Email": "alias@example.com",
                cm.COL_ROLE: "Data Analyst",
                "Stanowisko": "Alias Role",
                cm.COL_COMPANY: "Firma Pri",
            }
        ]
    )
    col_map = cm._resolve_column_map(df)
    assert col_map["email"] == cm.COL_EMAIL
    assert col_map["role"] == cm.COL_ROLE


def test_zapisz_excel_writes_json_backup_when_enabled(tmp_path, monkeypatch) -> None:
    import json_data_backup as jb

    monkeypatch.setattr(jb, "_under_pytest", lambda: False)
    monkeypatch.setenv("PIPELINE_JSON_BACKUP", "1")
    bdir = tmp_path / "json_bkp"
    monkeypatch.setenv("PIPELINE_JSON_BACKUP_DIR", str(bdir))

    out_xlsx = tmp_path / "Kontakty_test.xlsx"
    df = pd.DataFrame([{cm.COL_COMPANY: "C1", cm.COL_EMAIL: "e@x.pl"}])
    cm.zapisz_excel(df, str(out_xlsx))

    assert out_xlsx.is_file()
    backups = list(bdir.glob("*.json"))
    assert len(backups) == 1
    payload = json.loads(backups[0].read_text(encoding="utf-8"))
    assert payload["row_count"] == 1
    assert payload["reason"] == "excel_save"
    assert Path(payload["target_path"]) == out_xlsx.resolve()
