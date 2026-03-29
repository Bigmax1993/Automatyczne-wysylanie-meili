"""Scenariusze brzegowe: SMTP bez wysyłki, pusty katalog kontaktów, mieszane pliki dodatkowe."""

from __future__ import annotations

import smtplib
import sys
from email.message import EmailMessage

import pandas as pd

import clean_validate_send_pipeline as pipe
import contact_mailer as cm


def _row_sent_ok() -> dict:
    return {
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
        cm.STATUS_COL: "Tak",
        cm.DATE_COL: "",
        "Walidacja": "OK",
        "Uwagi walidacji": "",
    }


def test_send_from_cleaned_csv_all_already_sent_never_calls_send_message(
    tmp_path, monkeypatch
) -> None:
    """Gdy każdy wiersz ma status wysłany, SMTP loguje się, ale send_message nie jest wołane."""
    df = pd.DataFrame([_row_sent_ok()])
    csv_path = tmp_path / "k.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF")

    class TrackSMTP:
        def __init__(self) -> None:
            self.login_ok = False

        def login(self, _u: str, _p: str) -> None:
            self.login_ok = True

        def send_message(self, _msg: EmailMessage) -> None:
            raise AssertionError("send_message nie powinno byc wywolane")

        def quit(self) -> None:
            pass

    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda *_a, **_k: TrackSMTP())
    monkeypatch.setattr(cm, "password", "fake-app-password")
    monkeypatch.setattr(cm, "CAMPAIGN_LOG_ENABLED", False)

    def _no_openai(**_kwargs):
        raise AssertionError("OpenAI nie powinno byc wywolane")

    monkeypatch.setattr(cm, "_generate_subject_with_retry", _no_openai)
    monkeypatch.setattr(cm, "_generate_mail_with_retry", _no_openai)

    stats = pipe._send_from_cleaned_csv(
        df=pd.read_csv(csv_path, encoding="utf-8-sig"),
        csv_path=str(csv_path),
        dry_run=False,
        cv_path=str(cv),
    )

    assert stats["sent"] == 0
    assert stats["skipped"] >= 1


def test_main_extra_contacts_dir_empty_logs_message(tmp_path, monkeypatch, capsys) -> None:
    main_input = tmp_path / "main.xlsx"
    extra_dir = tmp_path / "pusty_kontakty"
    extra_dir.mkdir()
    out_csv = tmp_path / "out.csv"
    pd.DataFrame([{"Firma": "A", "E-mail rekrutacyjny": "a@x.pl"}]).to_excel(main_input, index=False)

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(pipe, "OpenAI", lambda api_key: object())
    monkeypatch.setattr(cm, "_resolve_cv_path", lambda: str(tmp_path / "cv.pdf"))
    (tmp_path / "cv.pdf").write_bytes(b"%PDF")
    monkeypatch.setattr(
        pipe,
        "_process_source",
        lambda *a, **k: {
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
            str(extra_dir),
            "--dry-run",
        ],
    )
    pipe.main()
    captured = capsys.readouterr().out
    assert "Brak dodatkowych plików kontaktów" in captured


def test_main_skip_clean_processes_mixed_csv_and_xlsx_extras(tmp_path, monkeypatch) -> None:
    main_csv = tmp_path / "glowny.csv"
    kd = tmp_path / "kontakty"
    kd.mkdir()
    base = _row_sent_ok()
    base[cm.STATUS_COL] = ""
    pd.DataFrame([{**base, cm.COL_EMAIL: "a@x.pl"}]).to_csv(main_csv, index=False, encoding="utf-8-sig")
    pd.DataFrame([{"Firma": "X", "E-mail rekrutacyjny": "x@x.pl"}]).to_excel(kd / "extra.xlsx", index=False)
    pd.DataFrame([{"Firma": "Y", "E-mail rekrutacyjny": "y@x.pl"}]).to_csv(kd / "extra.csv", index=False)

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(cm, "_resolve_cv_path", lambda: str(tmp_path / "cv.pdf"))
    (tmp_path / "cv.pdf").write_bytes(b"%PDF")

    inputs: list[tuple[str, bool]] = []

    def _ps(source_path, output_csv, client, model, cv_path, dry_run, skip_clean=False):
        inputs.append((source_path, skip_clean))
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
            str(main_csv),
            "--skip-clean",
            "--dry-run",
            "--extra-contacts-dir",
            str(kd),
        ],
    )
    pipe.main()

    assert len(inputs) == 3
    assert all(sc for _, sc in inputs)
