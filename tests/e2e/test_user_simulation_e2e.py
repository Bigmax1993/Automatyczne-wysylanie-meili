"""E2E: symulacja użytkownika (build + pipeline + mock OpenAI)."""

from __future__ import annotations

import json
import sys

import pandas as pd
import pytest

import build_contacts_serpapi as build
import clean_validate_send_pipeline as pipe
import contact_mailer as cm


class _FakeResp:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code


class _FakeOpenAIResponse:
    def __init__(self, content: str) -> None:
        self.choices = [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]


class _FakeCompletions:
    def create(self, **kwargs):
        user_content = kwargs["messages"][-1]["content"]
        start = user_content.find("{")
        end = user_content.rfind("}")
        raw = {}
        if start != -1 and end != -1 and end > start:
            raw = json.loads(user_content[start : end + 1])

        payload = {
            cm.COL_COMPANY: str(raw.get(cm.COL_COMPANY, "Firma Test")).strip(),
            cm.COL_CITY: str(raw.get(cm.COL_CITY, "Wroclaw")).strip(),
            cm.COL_INDUSTRY: str(raw.get(cm.COL_INDUSTRY, "IT")).strip(),
            cm.COL_ROLE: str(raw.get(cm.COL_ROLE, "Data Analyst")).strip(),
            cm.COL_WEBSITE: str(raw.get(cm.COL_WEBSITE, "")).strip(),
            cm.COL_EMAIL: str(raw.get(cm.COL_EMAIL, "")).strip(),
            cm.COL_PHONE: str(raw.get(cm.COL_PHONE, "")).strip(),
            cm.COL_MODE: str(raw.get(cm.COL_MODE, "UOP")).strip(),
            cm.COL_SOURCE: str(raw.get(cm.COL_SOURCE, "SerpAPI")).strip(),
            cm.COL_NOTES: str(raw.get(cm.COL_NOTES, "")).strip(),
        }
        return _FakeOpenAIResponse(json.dumps(payload, ensure_ascii=False))


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.chat = _FakeChat()


@pytest.mark.e2e
def test_user_simulation_full_flow(tmp_path, monkeypatch) -> None:
    leads_xlsx = tmp_path / "Kontakty_user.xlsx"
    cleaned_csv = tmp_path / "Kontakty_cleaned.csv"
    cv_path = tmp_path / "CV_Test.pdf"
    cv_path.write_bytes(b"%PDF-1.4\n%user-sim\n")

    monkeypatch.setenv("SERPAPI_API_KEY", "serp-test")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "gmail-test")
    monkeypatch.setattr(build.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "_apply_send_delay", lambda: None)
    monkeypatch.setattr(cm, "CAMPAIGN_LOG_ENABLED", False)

    def _fake_query(_api_key: str, query: str, _start: int, num: int) -> dict:
        assert num > 0
        city = "Wroclaw"
        if "Poznan" in query:
            city = "Poznan"
        elif "Zielona Gora" in query:
            city = "Zielona Gora"
        domain = city.lower().replace(" ", "") + ".example.com"
        return {
            "local_results": [
                {
                    "title": f"Firma {city}",
                    "website": f"https://{domain}",
                    "phone": "+48 111 222 333",
                    "address": f"ul. Test 1, {city}",
                }
            ],
            "organic_results": [],
        }

    monkeypatch.setattr(build, "_query_serpapi", _fake_query)
    monkeypatch.setattr(
        build.requests,
        "get",
        lambda url, timeout, headers: _FakeResp(
            f"<html><body>Kontakt: hr@{build._domain(url)}</body></html>", 200
        ),
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_contacts_serpapi.py",
            "--firm-target",
            "1",
            "--agency-target",
            "1",
            "--ecommerce-target",
            "1",
            "--cities",
            "Wroclaw,Zielona Gora,Poznan",
            "--enrich-email",
            "--output",
            str(leads_xlsx),
        ],
    )
    build.main()
    assert leads_xlsx.exists()

    monkeypatch.setattr(pipe, "OpenAI", lambda api_key: _FakeOpenAIClient())
    monkeypatch.setattr(cm, "_resolve_cv_path", lambda: str(cv_path))
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat User Sim")
    monkeypatch.setattr(cm, "_generate_mail_with_retry", lambda **_k: "Tresc User Sim")
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "clean_validate_send_pipeline.py",
            "--input",
            str(leads_xlsx),
            "--output-csv",
            str(cleaned_csv),
            "--dry-run",
            "--skip-extra-contacts",
        ],
    )
    pipe.main()

    out = pd.read_csv(cleaned_csv)
    assert len(out) >= 3
    assert (out["Walidacja"] == "OK").all()
    assert (out[cm.STATUS_COL] == "Tak").sum() >= 3
    assert out[cm.COL_WEBSITE].fillna("").str.contains("example.com").any()
