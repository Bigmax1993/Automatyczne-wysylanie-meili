"""Operacje pomocnicze: blocklista domen, raport validate-only, alerty błędów."""

from __future__ import annotations

import sys

import pandas as pd

import clean_validate_send_pipeline as pipe
import contact_mailer as cm
import domain_blocklist as bl


def test_recipient_domain_is_blocked_exact(tmp_path, monkeypatch) -> None:
    p = tmp_path / "b.txt"
    p.write_text("blocked.pl\n", encoding="utf-8")
    monkeypatch.setattr(bl, "BLOCKLIST_PATH", str(p))
    bl.clear_blocklist_cache()
    assert bl.recipient_domain_is_blocked("x@blocked.pl") is True
    assert bl.recipient_domain_is_blocked("x@other.pl") is False


def test_recipient_domain_is_blocked_wildcard(tmp_path, monkeypatch) -> None:
    p = tmp_path / "b.txt"
    p.write_text("*.mail.example.org\n", encoding="utf-8")
    monkeypatch.setattr(bl, "BLOCKLIST_PATH", str(p))
    bl.clear_blocklist_cache()
    assert bl.recipient_domain_is_blocked("a@hr.mail.example.org") is True
    assert bl.recipient_domain_is_blocked("a@mail.example.org") is False


def test_validate_only_report_counts(tmp_path, monkeypatch, capsys) -> None:
    csv_path = tmp_path / "r.csv"
    pd.DataFrame(
        [
            {
                cm.COL_COMPANY: "A",
                cm.COL_ROLE: "R",
                cm.COL_CITY: "W",
                cm.COL_EMAIL: "ok@firma.pl",
                "Walidacja": "OK",
                cm.STATUS_COL: "",
            },
            {
                cm.COL_COMPANY: "B",
                cm.COL_ROLE: "R",
                cm.COL_CITY: "W",
                cm.COL_EMAIL: "",
                "Walidacja": "OK",
                cm.STATUS_COL: "",
            },
            {
                cm.COL_COMPANY: "C",
                cm.COL_ROLE: "R",
                cm.COL_CITY: "W",
                cm.COL_EMAIL: "c@c.pl",
                "Walidacja": "Błąd",
                cm.STATUS_COL: "",
            },
        ]
    ).to_csv(csv_path, index=False, encoding="utf-8-sig")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "clean_validate_send_pipeline.py",
            "--validate-only",
            "--input",
            str(csv_path),
        ],
    )
    pipe.main()
    out = capsys.readouterr().out
    assert "nadaje_sie_do_wysylki=1" in out
    assert "brak_lub_zly_email=1" in out
    assert "walidacja_nie_ok=1" in out


def test_process_rows_skips_blocked_domain(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cm, "DRY_RUN", True)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "zapisz_excel", lambda _df, _path: None)
    monkeypatch.setattr(cm, "_attach_cv", lambda _m, _p: None)
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "T")
    monkeypatch.setattr(cm, "_generate_mail_with_retry", lambda **_k: "x" * 500)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_CHARS", 0)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_SENTENCES", 0)
    monkeypatch.setattr(cm, "recipient_domain_is_blocked", lambda _e: True)

    df = pd.DataFrame(
        [
            {
                cm.COL_EMAIL: "a@zablokowana.pl",
                cm.COL_COMPANY: "Z",
                cm.COL_ROLE: "R",
                cm.COL_CITY: "W",
                cm.STATUS_COL: pd.NA,
                cm.DATE_COL: pd.NaT,
            }
        ]
    )
    stats = cm._process_rows(df, excel_path=str(tmp_path / "x.xlsx"), smtp=None, cv_path="c.pdf")
    assert stats["skip_blocked_domain"] == 1
    assert stats["skipped"] == 1


def test_maybe_error_alert_prints_when_threshold(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cm, "ALERT_ON_ERROR_COUNT", 1)
    monkeypatch.setattr(cm, "ALERT_LOG_PATH", "")
    cm.maybe_error_alert({"openai_errors": 1, "smtp_errors": 0}, prefix="t: ")
    assert "UWAGA" in capsys.readouterr().out
