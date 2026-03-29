"""Integracja contact_mailer z mockiem SMTP i generatorami OpenAI."""

from __future__ import annotations

import pandas as pd

import contact_mailer as cm


class FakeSMTP:
    instances = []

    def __init__(self, _host: str, _port: int) -> None:
        self.logged_in = None
        self.sent_messages = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def login(self, email: str, password: str) -> None:
        self.logged_in = (email, password)

    def send_message(self, msg) -> None:
        self.sent_messages.append(msg)


def _write_contacts_file(tmp_path, rows: list[dict]) -> str:
    path = tmp_path / "Kontakty_test.xlsx"
    pd.DataFrame(rows).to_excel(path, index=False)
    return str(path)


def _write_cv_file(tmp_path) -> str:
    path = tmp_path / "CV_Test.pdf"
    path.write_bytes(b"%PDF-1.4\n%test-cv\n")
    return str(path)


def test_main_dry_run_updates_excel(tmp_path, monkeypatch) -> None:
    cv_path = _write_cv_file(tmp_path)
    excel_path = _write_contacts_file(
        tmp_path,
        [
            {
                cm.COL_EMAIL: "jan@example.com",
                cm.COL_COMPANY: "Firma A",
                cm.COL_ROLE: "Data Analyst",
                cm.COL_CITY: "Wroclaw",
                cm.COL_PHONE: "123456789",
            }
        ],
    )

    monkeypatch.setattr(cm, "SEARCH_DIR", str(tmp_path))
    monkeypatch.setattr(cm, "PATTERN", "Kontakty*.xlsx")
    monkeypatch.setattr(cm, "DRY_RUN", True)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_CHARS", 0)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_SENTENCES", 0)
    monkeypatch.setattr(cm, "wygeneruj_tresc_maila", lambda *_a, **_k: "Tresc testowa")
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat testowy")
    monkeypatch.setattr(cm, "_resolve_cv_path", lambda: cv_path)

    cm.main()

    out = pd.read_excel(excel_path)
    assert out.loc[0, cm.STATUS_COL] == "Tak"
    assert pd.notna(out.loc[0, cm.DATE_COL])


def test_main_smtp_mode_sends_and_marks_invalid_email(tmp_path, monkeypatch) -> None:
    FakeSMTP.instances = []
    cv_path = _write_cv_file(tmp_path)
    excel_path = _write_contacts_file(
        tmp_path,
        [
            {
                cm.COL_EMAIL: "anna@example.com",
                cm.COL_COMPANY: "Firma B",
                cm.COL_ROLE: "BI Analyst",
                cm.COL_CITY: "Poznan",
                cm.COL_PHONE: "222333444",
            },
            {
                cm.COL_EMAIL: "bledny-email",
                cm.COL_COMPANY: "Firma C",
                cm.COL_ROLE: "Data Engineer",
                cm.COL_CITY: "Zielona Gora",
                cm.COL_PHONE: "999888777",
            },
        ],
    )

    monkeypatch.setattr(cm, "SEARCH_DIR", str(tmp_path))
    monkeypatch.setattr(cm, "PATTERN", "Kontakty*.xlsx")
    monkeypatch.setattr(cm, "DRY_RUN", False)
    monkeypatch.setattr(cm, "password", "app-password-test")
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_CHARS", 0)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_SENTENCES", 0)
    monkeypatch.setattr(cm, "wygeneruj_tresc_maila", lambda *_a, **_k: "Tresc testowa")
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat testowy")
    monkeypatch.setattr(cm.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(cm, "_resolve_cv_path", lambda: cv_path)

    cm.main()

    assert len(FakeSMTP.instances) == 1
    smtp = FakeSMTP.instances[0]
    assert smtp.logged_in == (cm.SENDER_EMAIL, "app-password-test")
    assert len(smtp.sent_messages) == 1
    attachment_names = [
        part.get_filename()
        for part in smtp.sent_messages[0].iter_attachments()
        if part.get_filename()
    ]
    assert "CV_Test.pdf" in attachment_names

    out = pd.read_excel(excel_path)
    assert out.loc[0, cm.STATUS_COL] == "Tak"
    assert out.loc[1, cm.STATUS_COL] == "Błąd: niepoprawny e-mail"


def test_main_respects_daily_limit_integration(tmp_path, monkeypatch) -> None:
    FakeSMTP.instances = []
    cv_path = _write_cv_file(tmp_path)
    excel_path = _write_contacts_file(
        tmp_path,
        [
            {
                cm.COL_EMAIL: "one@example.com",
                cm.COL_COMPANY: "Firma A",
                cm.COL_ROLE: "Data Analyst",
                cm.COL_CITY: "Wroclaw",
            },
            {
                cm.COL_EMAIL: "two@example.com",
                cm.COL_COMPANY: "Firma B",
                cm.COL_ROLE: "BI Analyst",
                cm.COL_CITY: "Poznan",
            },
        ],
    )

    monkeypatch.setattr(cm, "SEARCH_DIR", str(tmp_path))
    monkeypatch.setattr(cm, "PATTERN", "Kontakty*.xlsx")
    monkeypatch.setattr(cm, "DRY_RUN", False)
    monkeypatch.setattr(cm, "MAX_EMAILS_PER_DAY", 1)
    monkeypatch.setattr(cm, "password", "app-password-test")
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "_apply_send_delay", lambda: None)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_CHARS", 0)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_SENTENCES", 0)
    monkeypatch.setattr(cm, "wygeneruj_tresc_maila", lambda *_a, **_k: "Tresc testowa")
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat testowy")
    monkeypatch.setattr(cm.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(cm, "_resolve_cv_path", lambda: cv_path)
    monkeypatch.setattr(cm, "CAMPAIGN_LOG_ENABLED", False)

    cm.main()

    smtp = FakeSMTP.instances[0]
    assert len(smtp.sent_messages) == 1
    out = pd.read_excel(excel_path)
    assert out.loc[0, cm.STATUS_COL] == "Tak"
    assert "limit dzienny" in str(out.loc[1, cm.STATUS_COL]).lower()


def test_main_prefers_uop_over_b2b_in_generation(tmp_path, monkeypatch) -> None:
    cv_path = _write_cv_file(tmp_path)
    excel_path = _write_contacts_file(
        tmp_path,
        [
            {
                cm.COL_EMAIL: "uop@example.com",
                cm.COL_COMPANY: "Firma UOP",
                cm.COL_ROLE: "Data Analyst",
                cm.COL_CITY: "Wroclaw",
                cm.COL_MODE: "UOP / B2B",
                cm.COL_INDUSTRY: "Sklep internetowy / e-commerce",
                cm.COL_NOTES: "oferta b2b i uop",
            }
        ],
    )

    captured = {}

    def _capture_subject(**kwargs):
        captured.update(kwargs)
        return "Temat"

    monkeypatch.setattr(cm, "SEARCH_DIR", str(tmp_path))
    monkeypatch.setattr(cm, "PATTERN", "Kontakty*.xlsx")
    monkeypatch.setattr(cm, "DRY_RUN", True)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "_generate_subject_with_retry", _capture_subject)
    monkeypatch.setattr(cm, "_generate_mail_with_retry", lambda **_k: "Tresc")
    monkeypatch.setattr(cm, "_resolve_cv_path", lambda: cv_path)
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)
    monkeypatch.setattr(cm, "CAMPAIGN_LOG_ENABLED", False)

    cm.main()

    out = pd.read_excel(excel_path)
    assert out.loc[0, cm.STATUS_COL] == "Tak"
    assert captured["contract_preference"] == "UOP"
    assert captured["offer_b2b"] is False
