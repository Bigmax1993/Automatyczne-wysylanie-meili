"""Regresje znanych błędów w contact_mailer (statusy, długość treści)."""

from __future__ import annotations

import pandas as pd
import pytest

import contact_mailer as cm


@pytest.mark.regression
def test_process_rows_accepts_datetime64_seconds_column(monkeypatch) -> None:
    """Regresja: zapis daty nie moze wywalac sie dla datetime64[s]."""
    monkeypatch.setattr(cm, "DRY_RUN", True)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "zapisz_excel", lambda _df, _path: None)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_CHARS", 0)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_SENTENCES", 0)
    monkeypatch.setattr(cm, "wygeneruj_tresc_maila", lambda *_a, **_k: "tresc")
    monkeypatch.setattr(cm, "_now_for_excel", lambda: pd.Timestamp("2026-01-01 10:00:00"))
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat")

    df = pd.DataFrame(
        [
            {
                cm.COL_EMAIL: "regresja@example.com",
                cm.COL_COMPANY: "Firma R",
                cm.COL_ROLE: "Data Analyst",
                cm.COL_CITY: "Wroclaw",
                cm.COL_PHONE: "123123123",
                cm.STATUS_COL: pd.NA,
            }
        ]
    )
    df[cm.DATE_COL] = pd.Series([pd.NaT], dtype="datetime64[s]")

    stats = cm._process_rows(df, excel_path="dummy.xlsx", smtp=None, cv_path="cv.pdf")

    assert stats["sent"] == 1
    assert df.at[0, cm.STATUS_COL] == "Tak"
    assert str(df[cm.DATE_COL].dtype) == "datetime64[s]"
    assert str(df.at[0, cm.DATE_COL]) == "2026-01-01 10:00:00"


@pytest.mark.regression
def test_safe_status_for_long_openai_error_is_truncated(monkeypatch) -> None:
    """Regresja: bardzo dlugi blad OpenAI musi sie miescic w komorce Excela."""
    monkeypatch.setattr(cm, "DRY_RUN", True)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "zapisz_excel", lambda _df, _path: None)
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat")

    def _raise_long_error(*_args, **_kwargs):
        raise RuntimeError("x" * 500)

    monkeypatch.setattr(cm, "wygeneruj_tresc_maila", _raise_long_error)

    df = pd.DataFrame(
        [
            {
                cm.COL_EMAIL: "regresja2@example.com",
                cm.COL_COMPANY: "Firma RX",
                cm.COL_ROLE: "BI Analyst",
                cm.COL_CITY: "Poznan",
                cm.COL_PHONE: "555111222",
                cm.STATUS_COL: pd.NA,
                cm.DATE_COL: pd.NaT,
            }
        ]
    )

    stats = cm._process_rows(df, excel_path="dummy.xlsx", smtp=None, cv_path="cv.pdf")

    assert stats["openai_errors"] == 1
    status = str(df.at[0, cm.STATUS_COL])
    assert status.startswith("Błąd OpenAI:")
    assert len(status) <= cm.MAX_STATUS_LEN


@pytest.mark.regression
def test_uop_preference_overrides_b2b_for_ecommerce(monkeypatch) -> None:
    """Regresja: przy UOP/B2B ma wybrac UOP (bez oferty B2B)."""
    monkeypatch.setattr(cm, "DRY_RUN", True)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "zapisz_excel", lambda _df, _path: None)
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat")

    captured = {}

    def _capture_generate(**kwargs):
        captured.update(kwargs)
        return "Tresc"

    monkeypatch.setattr(cm, "_generate_mail_with_retry", _capture_generate)

    df = pd.DataFrame(
        [
            {
                cm.COL_EMAIL: "uop@example.com",
                cm.COL_COMPANY: "Eshop",
                cm.COL_ROLE: "Data Analyst",
                cm.COL_CITY: "Poznan",
                cm.COL_INDUSTRY: "Sklep internetowy / e-commerce",
                cm.COL_MODE: "UOP / B2B",
                cm.COL_NOTES: "Oferta współpracy B2B",
                cm.STATUS_COL: pd.NA,
                cm.DATE_COL: pd.NaT,
            }
        ]
    )

    stats = cm._process_rows(df, excel_path="dummy.xlsx", smtp=None, cv_path="cv.pdf")
    assert stats["sent"] == 1
    assert captured["contract_preference"] == "UOP"
    assert captured["offer_b2b"] is False


@pytest.mark.regression
def test_non_ecommerce_does_not_force_b2b() -> None:
    assert not cm._should_offer_b2b(
        industry="IT consulting",
        source="pracuj.pl",
        notes="rekrutacja analityk danych",
    )
