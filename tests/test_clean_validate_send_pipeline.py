"""Testy clean_validate_send_pipeline (JSON z OpenAI, walidacja, wysyłka z CSV)."""

from __future__ import annotations

import json
import logging
import os
import sys

import pandas as pd
import pytest

import clean_validate_send_pipeline as pipe
import contact_mailer as cm


def test_extract_json_object_parses_embedded_json() -> None:
    text = 'Wynik:\n{"Firma":"ABC","E-mail rekrutacyjny":"a@b.com"}\nDziekuje'
    parsed = pipe._extract_json_object(text)
    assert parsed["Firma"] == "ABC"
    assert parsed["E-mail rekrutacyjny"] == "a@b.com"


def test_extract_json_object_raises_for_missing_json() -> None:
    with pytest.raises(ValueError, match="JSON"):
        pipe._extract_json_object("brak danych")


def test_validate_row_detects_required_issues() -> None:
    row = {
        cm.COL_COMPANY: "",
        cm.COL_ROLE: "",
        cm.COL_EMAIL: "zly-email",
    }
    status, notes = pipe._validate_row(row)
    assert status == "Błąd"
    assert "Brak firmy" in notes
    assert "Brak stanowiska/roli" in notes
    assert "Niepoprawny e-mail" in notes


def test_validate_row_ok() -> None:
    row = {
        cm.COL_COMPANY: "Firma X",
        cm.COL_ROLE: "Data Analyst",
        cm.COL_EMAIL: "hr@firmax.pl",
    }
    status, notes = pipe._validate_row(row)
    assert status == "OK"
    assert notes == ""


def test_build_raw_row_payload_skips_empty_values() -> None:
    row = pd.Series(
        {
            "Firma": "Firma Y",
            "Puste": " ",
            "Brak": pd.NA,
        }
    )
    payload = pipe._build_raw_row_payload(row)
    assert payload == {"Firma": "Firma Y"}


def test_send_from_cleaned_csv_respects_daily_limit(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cm, "MAX_EMAILS_PER_DAY", 1)
    monkeypatch.setattr(cm, "CAMPAIGN_LOG_ENABLED", False)
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat")
    monkeypatch.setattr(cm, "_generate_mail_with_retry", lambda **_k: "Tresc")
    monkeypatch.setattr(pipe, "_save_csv", lambda _df, _path: None)

    df = pd.DataFrame(
        [
            {
                cm.COL_EMAIL: "already@example.com",
                cm.COL_COMPANY: "Old",
                cm.COL_ROLE: "DA",
                cm.COL_CITY: "Wroclaw",
                "Walidacja": "OK",
                cm.STATUS_COL: "Tak",
                cm.DATE_COL: cm._now_for_excel(),
            },
            {
                cm.COL_EMAIL: "new@example.com",
                cm.COL_COMPANY: "New",
                cm.COL_ROLE: "DA",
                cm.COL_CITY: "Poznan",
                "Walidacja": "OK",
                cm.STATUS_COL: pd.NA,
                cm.DATE_COL: pd.NaT,
            },
        ]
    )

    stats = pipe._send_from_cleaned_csv(
        df=df,
        csv_path=str(tmp_path / "out.csv"),
        dry_run=True,
        cv_path="cv.pdf",
    )
    assert stats["sent"] == 0
    assert stats["daily_limit_reached"] == 1


def test_send_from_cleaned_csv_passes_contract_preference(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cm, "MAX_EMAILS_PER_DAY", 10)
    monkeypatch.setattr(cm, "CAMPAIGN_LOG_ENABLED", False)
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)
    monkeypatch.setattr(pipe, "_save_csv", lambda _df, _path: None)

    captured = {}

    def _subject(**kwargs):
        captured.update(kwargs)
        return "Temat"

    monkeypatch.setattr(cm, "_generate_subject_with_retry", _subject)
    monkeypatch.setattr(cm, "_generate_mail_with_retry", lambda **_k: "Tresc")

    df = pd.DataFrame(
        [
            {
                cm.COL_EMAIL: "new@example.com",
                cm.COL_COMPANY: "New",
                cm.COL_ROLE: "DA",
                cm.COL_CITY: "Poznan",
                cm.COL_MODE: "UOP / B2B",
                cm.COL_NOTES: "ogloszenie UOP i B2B",
                "Walidacja": "OK",
                cm.STATUS_COL: pd.NA,
                cm.DATE_COL: pd.NaT,
            },
        ]
    )

    stats = pipe._send_from_cleaned_csv(
        df=df,
        csv_path=str(tmp_path / "out.csv"),
        dry_run=True,
        cv_path="cv.pdf",
    )
    assert stats["sent"] == 1
    assert captured["contract_preference"] == "UOP"
    assert captured["offer_b2b"] is False


def test_clean_and_validate_builds_required_output_columns(monkeypatch) -> None:
    raw_df = pd.DataFrame([{"Firma": "A", "E-mail rekrutacyjny": "hr@a.pl"}])

    monkeypatch.setattr(
        pipe,
        "_clean_row_with_openai",
        lambda client, row_payload, model: {
            cm.COL_COMPANY: "A",
            cm.COL_CITY: "Wroclaw",
            cm.COL_INDUSTRY: "IT",
            cm.COL_ROLE: "Data Analyst",
            cm.COL_WEBSITE: "",
            cm.COL_EMAIL: "hr@a.pl",
            cm.COL_PHONE: "",
            cm.COL_MODE: "UOP",
            cm.COL_SOURCE: "pracuj.pl",
            cm.COL_NOTES: "",
        },
    )

    out = pipe._clean_and_validate(raw_df, client=object(), model="x")
    for col in pipe.OUTPUT_COLUMNS:
        assert col in out.columns
    assert out.loc[0, "Walidacja"] == "OK"


def test_pipeline_progress_every_n_invalid_env_defaults(monkeypatch) -> None:
    monkeypatch.setenv("PIPELINE_PROGRESS_EVERY_N", "not-a-number")
    assert pipe._pipeline_progress_every_n() == 50


def test_pipeline_progress_every_n_zero_disables(monkeypatch) -> None:
    monkeypatch.setenv("PIPELINE_PROGRESS_EVERY_N", "0")
    assert pipe._pipeline_progress_every_n() == 0


def test_clean_and_validate_logs_progress_every_n(monkeypatch, caplog) -> None:
    monkeypatch.setenv("PIPELINE_PROGRESS_EVERY_N", "2")
    raw_df = pd.DataFrame(
        [{"Firma": f"F{i}", "E-mail rekrutacyjny": f"a{i}@b.pl"} for i in range(5)]
    )

    def _fake_row(client, row_payload, model):
        return {
            cm.COL_COMPANY: row_payload.get("Firma", ""),
            cm.COL_CITY: "Wroclaw",
            cm.COL_INDUSTRY: "IT",
            cm.COL_ROLE: "Data Analyst",
            cm.COL_WEBSITE: "",
            cm.COL_EMAIL: row_payload.get("E-mail rekrutacyjny", ""),
            cm.COL_PHONE: "",
            cm.COL_MODE: "UOP",
            cm.COL_SOURCE: "x",
            cm.COL_NOTES: "",
        }

    monkeypatch.setattr(pipe, "_clean_row_with_openai", _fake_row)

    with caplog.at_level(logging.INFO):
        pipe._clean_and_validate(raw_df, client=object(), model="x")

    progress_msgs = [r.message for r in caplog.records if "Czyszczenie OpenAI" in r.message]
    assert any("2/5" in m for m in progress_msgs)
    assert any("4/5" in m for m in progress_msgs)


def test_list_extra_contacts_files_excludes_main(tmp_path) -> None:
    main_p = tmp_path / "main.xlsx"
    a = tmp_path / "a.xlsx"
    b = tmp_path / "b.xlsx"
    main_p.write_bytes(b"x")
    a.write_bytes(b"x")
    b.write_bytes(b"x")
    os.utime(a, (1000000000, 1000000000))
    os.utime(b, (1000000200, 1000000200))
    listed = pipe._list_extra_contacts_files(str(tmp_path), {str(main_p)})
    assert len(listed) == 2
    assert os.path.basename(listed[0]) == "a.xlsx"
    assert os.path.basename(listed[1]) == "b.xlsx"


def test_find_latest_contacts_file_prefers_newest(tmp_path) -> None:
    older = tmp_path / "a.xlsx"
    newer = tmp_path / "b.xlsx"
    older.write_text("x", encoding="utf-8")
    newer.write_text("y", encoding="utf-8")
    os.utime(older, (1000000000, 1000000000))
    os.utime(newer, (1000000100, 1000000100))

    latest = pipe._find_latest_contacts_file(str(tmp_path))
    assert latest.endswith("b.xlsx")


def test_find_latest_contacts_file_prefers_newest_among_csv_xls(tmp_path) -> None:
    xlsx_f = tmp_path / "old.xlsx"
    csv_f = tmp_path / "newest.csv"
    xls_f = tmp_path / "mid.xls"
    for p in (xlsx_f, csv_f, xls_f):
        p.write_text("x", encoding="utf-8")
    os.utime(xlsx_f, (1000000000, 1000000000))
    os.utime(xls_f, (1000000000, 1000000050))
    os.utime(csv_f, (1000000000, 1000000200))

    latest = pipe._find_latest_contacts_file(str(tmp_path))
    assert os.path.basename(latest) == "newest.csv"


def test_find_latest_contacts_file_raises_when_no_contact_files(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="Brak pliku kontaktów"):
        pipe._find_latest_contacts_file(str(tmp_path))


def test_find_latest_contacts_file_raises_when_directory_missing(tmp_path) -> None:
    missing = tmp_path / "nie_ma_takiego"
    with pytest.raises(FileNotFoundError):
        pipe._find_latest_contacts_file(str(missing))


def test_main_processes_extra_contacts_file(tmp_path, monkeypatch) -> None:
    main_input = tmp_path / "main.xlsx"
    extra_dir = tmp_path / "kontakty"
    extra_dir.mkdir()
    extra_input = extra_dir / "extra.xlsx"
    out_csv = tmp_path / "out.csv"

    pd.DataFrame([{"Firma": "A", "E-mail rekrutacyjny": "a@x.pl"}]).to_excel(main_input, index=False)
    pd.DataFrame([{"Firma": "B", "E-mail rekrutacyjny": "b@x.pl"}]).to_excel(extra_input, index=False)

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(pipe, "OpenAI", lambda api_key: object())
    monkeypatch.setattr(cm, "_resolve_cv_path", lambda: "cv.pdf")
    calls = {"n": 0}

    def _ps(source_path, output_csv, client, model, cv_path, dry_run, skip_clean=False):
        calls["n"] += 1
        return {
            "sent": 1,
            "skipped": 0,
            "openai_errors": 0,
            "smtp_errors": 0,
            "daily_limit_reached": 0,
        }

    monkeypatch.setattr(pipe, "_process_source", _ps)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "clean_validate_send_pipeline.py",
            "--input",
            str(main_input),
            "--output-csv",
            str(out_csv),
            "--extra-contacts-dir",
            str(extra_dir),
            "--dry-run",
        ],
    )
    pipe.main()
    assert calls["n"] == 2


def test_main_processes_multiple_extra_contacts_files(tmp_path, monkeypatch) -> None:
    main_input = tmp_path / "main.xlsx"
    extra_dir = tmp_path / "kontakty"
    extra_dir.mkdir()
    pd.DataFrame([{"Firma": "A", "E-mail rekrutacyjny": "a@x.pl"}]).to_excel(main_input, index=False)
    pd.DataFrame([{"Firma": "B", "E-mail rekrutacyjny": "b@x.pl"}]).to_excel(
        extra_dir / "jeden.xlsx", index=False
    )
    pd.DataFrame([{"Firma": "C", "E-mail rekrutacyjny": "c@x.pl"}]).to_excel(
        extra_dir / "dwa.xlsx", index=False
    )
    out_csv = tmp_path / "out.csv"

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(pipe, "OpenAI", lambda api_key: object())
    monkeypatch.setattr(cm, "_resolve_cv_path", lambda: "cv.pdf")
    calls = {"n": 0}

    def _ps(source_path, output_csv, client, model, cv_path, dry_run, skip_clean=False):
        calls["n"] += 1
        return {
            "sent": 0,
            "skipped": 0,
            "openai_errors": 0,
            "smtp_errors": 0,
            "daily_limit_reached": 0,
        }

    monkeypatch.setattr(pipe, "_process_source", _ps)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "clean_validate_send_pipeline.py",
            "--input",
            str(main_input),
            "--output-csv",
            str(out_csv),
            "--extra-contacts-dir",
            str(extra_dir),
            "--dry-run",
        ],
    )
    pipe.main()
    assert calls["n"] == 3


def test_main_skips_extra_when_same_file(tmp_path, monkeypatch) -> None:
    main_input = tmp_path / "same.xlsx"
    out_csv = tmp_path / "out.csv"
    pd.DataFrame([{"Firma": "A", "E-mail rekrutacyjny": "a@x.pl"}]).to_excel(main_input, index=False)

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(pipe, "OpenAI", lambda api_key: object())
    monkeypatch.setattr(cm, "_resolve_cv_path", lambda: "cv.pdf")

    calls = {"n": 0}

    def _process_source(source_path, output_csv, client, model, cv_path, dry_run, skip_clean=False):
        calls["n"] += 1
        return {"sent": 0, "skipped": 0, "openai_errors": 0, "smtp_errors": 0, "daily_limit_reached": 0}

    monkeypatch.setattr(pipe, "_process_source", _process_source)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "clean_validate_send_pipeline.py",
            "--input",
            str(main_input),
            "--output-csv",
            str(out_csv),
            "--extra-contacts-dir",
            str(tmp_path),
            "--dry-run",
        ],
    )
    pipe.main()
    assert calls["n"] == 1


def test_main_handles_missing_extra_contacts_dir(tmp_path, monkeypatch) -> None:
    main_input = tmp_path / "main.xlsx"
    out_csv = tmp_path / "out.csv"
    pd.DataFrame([{"Firma": "A", "E-mail rekrutacyjny": "a@x.pl"}]).to_excel(main_input, index=False)

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(pipe, "OpenAI", lambda api_key: object())
    monkeypatch.setattr(cm, "_resolve_cv_path", lambda: "cv.pdf")
    monkeypatch.setattr(
        pipe,
        "_process_source",
        lambda source_path, output_csv, client, model, cv_path, dry_run, skip_clean=False: {
            "sent": 0,
            "skipped": 0,
            "openai_errors": 0,
            "smtp_errors": 0,
            "daily_limit_reached": 0,
        },
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "clean_validate_send_pipeline.py",
            "--input",
            str(main_input),
            "--output-csv",
            str(out_csv),
            "--extra-contacts-dir",
            str(tmp_path / "missing_dir"),
            "--dry-run",
        ],
    )
    pipe.main()


def test_ensure_cleaned_frame_fills_missing_columns() -> None:
    df = pd.DataFrame([{cm.COL_COMPANY: "X", "Walidacja": "OK"}])
    out = pipe._ensure_cleaned_frame(df)
    assert cm.COL_EMAIL in out.columns
    assert out.loc[0, cm.COL_COMPANY] == "X"


def test_skip_clean_requires_input(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["clean_validate_send_pipeline.py", "--skip-clean", "--skip-extra-contacts", "--dry-run"],
    )
    with pytest.raises(RuntimeError, match="--skip-clean"):
        pipe.main()


def test_skip_clean_dry_run_without_openai(tmp_path, monkeypatch) -> None:
    csv_path = tmp_path / "cleaned.csv"
    row = {
        cm.COL_COMPANY: "Firma",
        cm.COL_CITY: "Wroclaw",
        cm.COL_INDUSTRY: "IT",
        cm.COL_ROLE: "Analityk",
        cm.COL_WEBSITE: "https://x.pl",
        cm.COL_EMAIL: "hr@x.pl",
        cm.COL_PHONE: "",
        cm.COL_MODE: "UOP",
        cm.COL_SOURCE: "test",
        cm.COL_NOTES: "",
        cm.STATUS_COL: "",
        cm.DATE_COL: "",
        "Walidacja": "OK",
        "Uwagi walidacji": "",
    }
    pd.DataFrame([row]).to_csv(csv_path, index=False, encoding="utf-8-sig")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(cm, "_resolve_cv_path", lambda: str(tmp_path / "cv.pdf"))
    (tmp_path / "cv.pdf").write_bytes(b"%PDF")
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "T")
    monkeypatch.setattr(cm, "_generate_mail_with_retry", lambda **_k: "B")
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)
    monkeypatch.setattr(cm, "_apply_send_delay", lambda: None)
    monkeypatch.setattr(cm, "CAMPAIGN_LOG_ENABLED", False)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "clean_validate_send_pipeline.py",
            "--input",
            str(csv_path),
            "--skip-clean",
            "--dry-run",
            "--skip-extra-contacts",
        ],
    )
    pipe.main()
    out = pd.read_csv(csv_path, encoding="utf-8-sig")
    assert out.loc[0, cm.STATUS_COL] == "Tak"


def test_main_dry_run_allows_missing_cv(tmp_path, monkeypatch) -> None:
    input_csv = tmp_path / "in.csv"
    out_csv = tmp_path / "out.csv"
    pd.DataFrame([{"Firma": "A", "E-mail rekrutacyjny": "a@x.pl", "Walidacja": "OK"}]).to_csv(
        input_csv, index=False, encoding="utf-8-sig"
    )

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(pipe, "OpenAI", lambda api_key: object())
    monkeypatch.setattr(cm, "_resolve_cv_path", lambda: (_ for _ in ()).throw(FileNotFoundError("no cv")))
    monkeypatch.setattr(
        pipe,
        "_process_source",
        lambda source_path, output_csv, client, model, cv_path, dry_run, skip_clean=False: {
            "sent": 0,
            "skipped": 0,
            "openai_errors": 0,
            "smtp_errors": 0,
            "daily_limit_reached": 0,
            "email_from_web": 0,
            "skip_validation_failed": 0,
            "skip_already_sent": 0,
            "skip_invalid_or_missing_email": 0,
            "skip_blocked_domain": 0,
            "skip_daily_limit": 0,
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "clean_validate_send_pipeline.py",
            "--input",
            str(input_csv),
            "--output-csv",
            str(out_csv),
            "--dry-run",
            "--skip-extra-contacts",
        ],
    )
    pipe.main()


def test_safe_stem_for_output_sanitizes() -> None:
    stem_sp = pipe._safe_stem_for_output("plik ze spacja.xlsx")
    assert " " not in stem_sp
    assert "_" in stem_sp
    stem = pipe._safe_stem_for_output("Raport #1 (2024).xlsx")
    assert "#" not in stem
    assert "(" not in stem
    assert len(stem) <= 80
    assert pipe._safe_stem_for_output(".xlsx") == "kontakty"


def test_list_extra_contacts_files_includes_csv(tmp_path) -> None:
    (tmp_path / "a.csv").write_text("x", encoding="utf-8")
    (tmp_path / "b.xlsx").write_bytes(b"x")
    listed = pipe._list_extra_contacts_files(str(tmp_path), set())
    names = {os.path.basename(p) for p in listed}
    assert "a.csv" in names
    assert "b.xlsx" in names


def test_main_skip_clean_runs_on_all_extra_csv_files(tmp_path, monkeypatch) -> None:
    row_ok = {
        cm.COL_COMPANY: "A",
        cm.COL_CITY: "Wroclaw",
        cm.COL_INDUSTRY: "IT",
        cm.COL_ROLE: "R",
        cm.COL_WEBSITE: "https://x.pl",
        cm.COL_EMAIL: "a@x.pl",
        cm.COL_PHONE: "",
        cm.COL_MODE: "UOP",
        cm.COL_SOURCE: "t",
        cm.COL_NOTES: "",
        cm.STATUS_COL: "",
        cm.DATE_COL: "",
        "Walidacja": "OK",
        "Uwagi walidacji": "",
    }
    main_csv = tmp_path / "glowny.csv"
    kd = tmp_path / "kontakty"
    kd.mkdir()
    pd.DataFrame([row_ok]).to_csv(main_csv, index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [{**row_ok, cm.COL_EMAIL: "b@x.pl", cm.COL_COMPANY: "B"}]
    ).to_csv(kd / "d1.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [{**row_ok, cm.COL_EMAIL: "c@x.pl", cm.COL_COMPANY: "C"}]
    ).to_csv(kd / "d2.csv", index=False, encoding="utf-8-sig")

    calls = {"n": 0, "skip_flags": []}

    def _ps(source_path, output_csv, client, model, cv_path, dry_run, skip_clean=False):
        calls["n"] += 1
        calls["skip_flags"].append(skip_clean)
        return {
            "sent": 0,
            "skipped": 0,
            "openai_errors": 0,
            "smtp_errors": 0,
            "daily_limit_reached": 0,
        }

    monkeypatch.setattr(pipe, "_process_source", _ps)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(cm, "_resolve_cv_path", lambda: str(tmp_path / "cv.pdf"))
    (tmp_path / "cv.pdf").write_bytes(b"%PDF")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "clean_validate_send_pipeline.py",
            "--input",
            str(main_csv),
            "--skip-clean",
            "--dry-run",
            "--extra-contacts-dir",
            str(kd),
        ],
    )
    pipe.main()
    assert calls["n"] == 3
    assert all(calls["skip_flags"])


def test_save_csv_writes_json_backup_when_enabled(tmp_path, monkeypatch) -> None:
    import json_data_backup as jb

    monkeypatch.setattr(jb, "_under_pytest", lambda: False)
    monkeypatch.setenv("PIPELINE_JSON_BACKUP", "1")
    bdir = tmp_path / "json_bkp"
    monkeypatch.setenv("PIPELINE_JSON_BACKUP_DIR", str(bdir))
    out_csv = tmp_path / "cleaned_rows.csv"
    df = pd.DataFrame([{cm.COL_COMPANY: "X", cm.COL_EMAIL: "m@x.pl"}])
    pipe._save_csv(df, str(out_csv))
    assert out_csv.is_file()
    backups = list(bdir.glob("*.json"))
    assert len(backups) == 1
    payload = json.loads(backups[0].read_text(encoding="utf-8"))
    assert payload["reason"] == "csv_save"
    assert payload["row_count"] == 1
