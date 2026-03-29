"""_process_source, main() CLI, czyszczenie, limity przy prawdziwym dry_run=False (mock SMTP), sortowanie plików."""

from __future__ import annotations

import os
import smtplib
import sys
from email.message import EmailMessage

import pandas as pd
import pytest

import clean_validate_send_pipeline as pipe
import contact_mailer as cm


def _valid_send_row(email: str) -> dict:
    return {
        cm.COL_COMPANY: "C",
        cm.COL_CITY: "Wroclaw",
        cm.COL_INDUSTRY: "IT",
        cm.COL_ROLE: "Analityk",
        cm.COL_WEBSITE: "https://x.pl",
        cm.COL_EMAIL: email,
        cm.COL_PHONE: "",
        cm.COL_MODE: "UOP",
        cm.COL_SOURCE: "t",
        cm.COL_NOTES: "",
        cm.STATUS_COL: "",
        cm.DATE_COL: "",
        "Walidacja": "OK",
        "Uwagi walidacji": "",
    }


def test_process_source_requires_openai_client_when_cleaning(tmp_path) -> None:
    inp = tmp_path / "in.xlsx"
    pd.DataFrame([{"Firma": "A"}]).to_excel(inp, index=False)
    with pytest.raises(RuntimeError, match="klienta OpenAI"):
        pipe._process_source(
            source_path=str(inp),
            output_csv=str(tmp_path / "out.csv"),
            client=None,
            model="gpt",
            cv_path="cv.pdf",
            dry_run=True,
            skip_clean=False,
        )


def test_process_source_clean_then_send_order(tmp_path, monkeypatch) -> None:
    inp = tmp_path / "in.xlsx"
    out_csv = tmp_path / "cleaned.csv"
    pd.DataFrame([{"Firma": "A", "E-mail rekrutacyjny": "a@a.pl"}]).to_excel(inp, index=False)

    cleaned = pd.DataFrame([_valid_send_row("a@a.pl")])

    calls: list[str] = []

    def _clean(df, client, model):
        calls.append("clean")
        assert len(df) == 1
        return cleaned

    def _send(**kwargs):
        calls.append("send")
        assert kwargs["dry_run"] is True
        assert len(kwargs["df"]) == 1
        return {
            "sent": 0,
            "skipped": 0,
            "openai_errors": 0,
            "smtp_errors": 0,
            "daily_limit_reached": 0,
        }

    monkeypatch.setattr(pipe, "_clean_and_validate", _clean)
    monkeypatch.setattr(pipe, "_send_from_cleaned_csv", _send)

    pipe._process_source(
        source_path=str(inp),
        output_csv=str(out_csv),
        client=object(),
        model="m",
        cv_path="cv.pdf",
        dry_run=True,
        skip_clean=False,
    )

    assert calls == ["clean", "send"]
    assert out_csv.is_file()


def test_clean_and_validate_propagates_row_cleaning_error(monkeypatch) -> None:
    raw_df = pd.DataFrame([{"Firma": "X"}])

    def _boom(*_a, **_k):
        raise RuntimeError("OpenAI timeout")

    monkeypatch.setattr(pipe, "_clean_row_with_openai", _boom)

    with pytest.raises(RuntimeError, match="OpenAI timeout"):
        pipe._clean_and_validate(raw_df, client=object(), model="m")


def test_clean_and_validate_empty_input() -> None:
    raw_df = pd.DataFrame()
    out = pipe._clean_and_validate(raw_df, client=object(), model="m")
    assert len(out) == 0
    for col in pipe.OUTPUT_COLUMNS:
        assert col in out.columns


def test_send_from_cleaned_csv_dry_run_prints_dry_run_line(capsys, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cm, "CAMPAIGN_LOG_ENABLED", False)
    monkeypatch.setattr(cm, "_attach_cv", lambda _m, _p: None)  # dry_run też buduje załącznik
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "T")
    monkeypatch.setattr(cm, "_generate_mail_with_retry", lambda **_k: "B")
    monkeypatch.setattr(pipe, "_save_csv", lambda _df, _path: None)

    df = pd.DataFrame([_valid_send_row("hr@example.com")])
    pipe._send_from_cleaned_csv(
        df=df,
        csv_path=str(tmp_path / "o.csv"),
        dry_run=True,
        cv_path=str(tmp_path / "cv.pdf"),
    )
    out = capsys.readouterr().out
    assert "[DRY_RUN]" in out
    assert "hr@example.com" in out


def test_send_from_cleaned_csv_non_dry_daily_limit_stops_second_recipient(
    tmp_path, monkeypatch
) -> None:
    """Przy limicie 1 drugi poprawny wiersz dostaje status limitu (bez OpenAI dla drugiego)."""
    monkeypatch.setattr(cm, "MAX_EMAILS_PER_DAY", 1)
    monkeypatch.setattr(cm, "CAMPAIGN_LOG_ENABLED", False)
    monkeypatch.setattr(cm, "_attach_cv", lambda _m, _p: None)
    (tmp_path / "cv.pdf").write_bytes(b"%PDF")
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat")
    monkeypatch.setattr(cm, "_generate_mail_with_retry", lambda **_k: "Treść")
    monkeypatch.setattr(cm, "_apply_send_delay", lambda: None)
    monkeypatch.setattr(cm, "password", "fake")

    class TrackSMTP:
        def __init__(self) -> None:
            self.send_calls = 0

        def login(self, *_a, **_k) -> None:
            pass

        def send_message(self, _msg: EmailMessage) -> None:
            self.send_calls += 1

        def quit(self) -> None:
            pass

    instance = TrackSMTP()
    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda *_a, **_k: instance)

    csv_path = tmp_path / "out.csv"
    df = pd.DataFrame(
        [_valid_send_row("first@example.com"), _valid_send_row("second@example.com")]
    )

    stats = pipe._send_from_cleaned_csv(
        df=df,
        csv_path=str(csv_path),
        dry_run=False,
        cv_path=str(tmp_path / "cv.pdf"),
    )

    assert stats["sent"] == 1
    assert stats["daily_limit_reached"] == 1
    assert instance.send_calls == 1
    assert "limit" in str(df.iloc[1][cm.STATUS_COL]).lower()


def test_main_raises_without_openai_when_cleaning(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "clean_validate_send_pipeline.py",
            "--input",
            "dummy.xlsx",
            "--skip-extra-contacts",
            "--dry-run",
        ],
    )
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        pipe.main()


def test_main_skip_clean_missing_input_file(monkeypatch, tmp_path) -> None:
    missing = tmp_path / "nie_ma.csv"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "clean_validate_send_pipeline.py",
            "--skip-clean",
            "--input",
            str(missing),
            "--skip-extra-contacts",
            "--dry-run",
        ],
    )
    with pytest.raises(FileNotFoundError, match="Brak pliku"):
        pipe.main()


def test_list_extra_contacts_files_tiebreak_by_path_when_same_mtime(tmp_path) -> None:
    a = tmp_path / "m_plik.xlsx"
    b = tmp_path / "a_plik.xlsx"
    a.write_bytes(b"x")
    b.write_bytes(b"y")
    t = 1_700_000_000
    os.utime(a, (t, t))
    os.utime(b, (t, t))
    listed = pipe._list_extra_contacts_files(str(tmp_path), set())
    basenames = [os.path.basename(p) for p in listed]
    assert basenames == sorted(basenames)


def test_safe_stem_truncates_to_eighty_chars() -> None:
    long_stem = "x" * 120
    path = f"{long_stem}.xlsx"
    stem = pipe._safe_stem_for_output(path)
    assert len(stem) == 80
    assert stem == "x" * 80


def test_send_from_cleaned_csv_campaign_log_validation_failed(tmp_path, monkeypatch) -> None:
    log_p = tmp_path / "campaign.csv"
    monkeypatch.setattr(cm, "CAMPAIGN_LOG_ENABLED", True)
    monkeypatch.setattr(cm, "CAMPAIGN_LOG_PATH", str(log_p))
    monkeypatch.setattr(cm, "_attach_cv", lambda _m, _p: None)

    df = pd.DataFrame([{**_valid_send_row("x@x.pl"), "Walidacja": "Błąd"}])
    stats = pipe._send_from_cleaned_csv(
        df=df,
        csv_path=str(tmp_path / "o.csv"),
        dry_run=True,
        cv_path=str(tmp_path / "cv.pdf"),
    )
    assert stats["skipped"] == 1
    log_df = pd.read_csv(log_p)
    assert log_df.loc[0, "status"] == "skipped"
    assert log_df.loc[0, "reason"] == "validation_failed"
