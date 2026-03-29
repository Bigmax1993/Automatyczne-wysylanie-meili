"""Kontrola wysyłki: limity, dry-run, log kampanii, statystyki dostarczenia."""

from __future__ import annotations

import pandas as pd
import pytest

import contact_mailer as cm


class FlakySMTP:
    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0
        self.sent_messages = []

    def send_message(self, msg) -> None:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("temporary smtp error")
        self.sent_messages.append(msg)


def _base_valid_row(email: str, company: str = "Firma A") -> dict:
    return {
        cm.COL_EMAIL: email,
        cm.COL_COMPANY: company,
        cm.COL_ROLE: "Data Analyst",
        cm.COL_CITY: "Wroclaw",
        cm.STATUS_COL: pd.NA,
        cm.DATE_COL: pd.NaT,
    }


def test_smtp_retry_succeeds_on_third_attempt(monkeypatch) -> None:
    monkeypatch.setattr(cm, "DRY_RUN", False)
    monkeypatch.setattr(cm, "SMTP_MAX_RETRIES", 3)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "_apply_send_delay", lambda: None)
    monkeypatch.setattr(cm, "zapisz_excel", lambda _df, _path: None)
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat")
    monkeypatch.setattr(cm, "_generate_mail_with_retry", lambda **_k: "Tresc")
    monkeypatch.setattr(cm, "CAMPAIGN_LOG_ENABLED", False)

    df = pd.DataFrame([_base_valid_row("hr@example.com")])
    smtp = FlakySMTP(fail_times=2)

    stats = cm._process_rows(df, excel_path="dummy.xlsx", smtp=smtp, cv_path="cv.pdf")

    assert stats["sent"] == 1
    assert smtp.calls == 3
    assert len(smtp.sent_messages) == 1


def test_daily_limit_counts_already_sent_today(monkeypatch) -> None:
    monkeypatch.setattr(cm, "DRY_RUN", True)
    monkeypatch.setattr(cm, "MAX_EMAILS_PER_DAY", 2)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "zapisz_excel", lambda _df, _path: None)
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat")
    monkeypatch.setattr(cm, "_generate_mail_with_retry", lambda **_k: "Tresc")
    monkeypatch.setattr(cm, "CAMPAIGN_LOG_ENABLED", False)

    df = pd.DataFrame(
        [
            {
                cm.COL_EMAIL: "done@example.com",
                cm.COL_COMPANY: "Done",
                cm.COL_ROLE: "Data Analyst",
                cm.COL_CITY: "Wroclaw",
                cm.STATUS_COL: "Tak",
                cm.DATE_COL: cm._now_for_excel(),
            },
            _base_valid_row("one@example.com", "One"),
            _base_valid_row("two@example.com", "Two"),
        ]
    )

    stats = cm._process_rows(df, excel_path="dummy.xlsx", smtp=None, cv_path="cv.pdf")

    assert stats["sent"] == 1
    assert stats["daily_limit_reached"] == 1
    assert "limit dzienny" in str(df.at[2, cm.STATUS_COL]).lower()


def test_campaign_log_integrity_for_mixed_rows(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cm, "DRY_RUN", True)
    monkeypatch.setattr(cm, "MAX_EMAILS_PER_DAY", 50)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "zapisz_excel", lambda _df, _path: None)
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat test")
    monkeypatch.setattr(cm, "_generate_mail_with_retry", lambda **_k: "Tresc")
    monkeypatch.setattr(cm, "CAMPAIGN_LOG_ENABLED", True)
    monkeypatch.setattr(cm, "CAMPAIGN_LOG_PATH", str(tmp_path / "campaign_log.csv"))

    df = pd.DataFrame(
        [
            {
                cm.COL_EMAIL: "sent@example.com",
                cm.COL_COMPANY: "A",
                cm.COL_ROLE: "R",
                cm.COL_CITY: "Wroclaw",
                cm.STATUS_COL: "Tak",
                cm.DATE_COL: cm._now_for_excel(),
            },
            _base_valid_row("bad-email", "B"),
            _base_valid_row("new@example.com", "C"),
        ]
    )

    stats = cm._process_rows(df, excel_path="dummy.xlsx", smtp=None, cv_path="cv.pdf")
    assert stats["sent"] == 1

    log_df = pd.read_csv(cm.CAMPAIGN_LOG_PATH)
    statuses = set(log_df["status"].tolist())
    reasons = set(log_df["reason"].fillna("").tolist())

    assert {"skipped", "invalid_email", "sent"}.issubset(statuses)
    assert "already_sent" in reasons
    sent_row = log_df[log_df["status"] == "sent"].iloc[0]
    assert sent_row["subject"] == "Temat test"


def test_send_message_with_retry_raises_after_max_attempts(monkeypatch) -> None:
    monkeypatch.setattr(cm, "SMTP_MAX_RETRIES", 2)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    smtp = FlakySMTP(fail_times=5)

    with pytest.raises(RuntimeError, match="SMTP nie wysłał wiadomości po 2 próbach"):
        cm._send_message_with_retry(smtp, cm.EmailMessage())


def test_send_message_with_retry_stops_after_first_success(monkeypatch) -> None:
    monkeypatch.setattr(cm, "SMTP_MAX_RETRIES", 5)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    smtp = FlakySMTP(fail_times=0)
    msg = cm.EmailMessage()
    cm._send_message_with_retry(smtp, msg)
    assert smtp.calls == 1
    assert len(smtp.sent_messages) == 1
