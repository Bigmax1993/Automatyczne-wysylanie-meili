"""E2E: clean_validate_send_pipeline z mockiem OpenAI (dry-run)."""

from __future__ import annotations

import json
import sys

import pandas as pd
import pytest

import clean_validate_send_pipeline as pipe
import contact_mailer as cm


class _FakeOpenAIResponse:
    def __init__(self, content: str) -> None:
        self.choices = [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]


class _FakeCompletions:
    def __init__(self, payloads: list[dict[str, str]]) -> None:
        self.payloads = payloads
        self.idx = 0

    def create(self, **_kwargs):
        payload = self.payloads[self.idx]
        self.idx += 1
        return _FakeOpenAIResponse(json.dumps(payload, ensure_ascii=False))


class _FakeChat:
    def __init__(self, payloads: list[dict[str, str]]) -> None:
        self.completions = _FakeCompletions(payloads)


class _FakeOpenAIClient:
    def __init__(self, payloads: list[dict[str, str]]) -> None:
        self.chat = _FakeChat(payloads)


@pytest.mark.e2e
def test_pipeline_e2e_dry_run(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "input.xlsx"
    output_path = tmp_path / "cleaned.csv"
    cv_path = tmp_path / "CV_Test.pdf"
    cv_path.write_bytes(b"%PDF-1.4\n%e2e\n")

    raw_df = pd.DataFrame(
        [
            {"Firma": "Firma A", "Miasto": "Wroclaw", "Stanowisko / Rola": "Data Analyst", "E-mail rekrutacyjny": "hr@a.pl"},
            {"Firma": "Firma B", "Miasto": "Poznan", "Stanowisko / Rola": "BI Analyst", "E-mail rekrutacyjny": ""},
        ]
    )
    raw_df.to_excel(input_path, index=False)

    cleaned_payloads = [
        {
            cm.COL_COMPANY: "Firma A",
            cm.COL_CITY: "Wroclaw",
            cm.COL_INDUSTRY: "IT",
            cm.COL_ROLE: "Data Analyst",
            cm.COL_WEBSITE: "https://a.pl",
            cm.COL_EMAIL: "hr@a.pl",
            cm.COL_PHONE: "",
            cm.COL_MODE: "UOP",
            cm.COL_SOURCE: "pracuj.pl",
            cm.COL_NOTES: "",
        },
        {
            cm.COL_COMPANY: "Firma B",
            cm.COL_CITY: "Poznan",
            cm.COL_INDUSTRY: "IT",
            cm.COL_ROLE: "BI Analyst",
            cm.COL_WEBSITE: "https://b.pl",
            cm.COL_EMAIL: "",
            cm.COL_PHONE: "",
            cm.COL_MODE: "B2B",
            cm.COL_SOURCE: "justjoin.it",
            cm.COL_NOTES: "",
        },
    ]

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(pipe, "OpenAI", lambda api_key: _FakeOpenAIClient(cleaned_payloads))
    monkeypatch.setattr(cm, "_resolve_cv_path", lambda: str(cv_path))
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat E2E")
    monkeypatch.setattr(cm, "_generate_mail_with_retry", lambda **_k: "Tresc E2E")
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)
    monkeypatch.setattr(cm, "_apply_send_delay", lambda: None)
    monkeypatch.setattr(cm, "CAMPAIGN_LOG_ENABLED", False)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "clean_validate_send_pipeline.py",
            "--input",
            str(input_path),
            "--output-csv",
            str(output_path),
            "--dry-run",
            "--skip-extra-contacts",
        ],
    )

    pipe.main()

    out = pd.read_csv(output_path)
    assert len(out) == 2
    assert out.loc[0, "Walidacja"] == "OK"
    assert out.loc[0, cm.STATUS_COL] == "Tak"
    assert out.loc[1, "Walidacja"] == "Błąd"
    assert "Brak e-maila" in str(out.loc[1, "Uwagi walidacji"])
    assert out.loc[0, cm.COL_COMPANY] == "Firma A"
