"""Testy build_contacts_serpapi: zapytania, zbieranie grup, enrichment, limity dzienne."""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta

import pytest

import build_contacts_serpapi as serp

_SERP_API_KEY_ENVS = ("SERPAPI_API_KEY", "SERP_API_KEY", "SERPAPI_KEY")


def _clear_serp_api_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() czyta kilka nazw zmiennych — w testach wyczyść wszystkie (unikaj przypadkowego klucza z PATH)."""
    for k in _SERP_API_KEY_ENVS:
        monkeypatch.delenv(k, raising=False)


@pytest.fixture(autouse=True)
def _isolate_serpapi_weekly_state_and_reset_gate(monkeypatch, tmp_path) -> None:
    """Izolacja pliku tygodniowego limitu + reset globali między testami (deterministyczny CI)."""
    p = tmp_path / "weekly_isolated.json"
    monkeypatch.setenv("SERPAPI_WEEKLY_STATE_PATH", str(p))
    p.write_text("{}", encoding="utf-8")
    serp._serp_week_gate_week = ""
    serp._serp_week_gate_closed = False
    serp._serp_weekly_cap_warning_logged = False


class _Resp:
    def __init__(self, text: str, status_code: int) -> None:
        self.text = text
        self.status_code = status_code


def test_normalize_url_adds_https() -> None:
    assert serp._normalize_url("example.com") == "https://example.com"
    assert serp._normalize_url("https://example.com") == "https://example.com"


def test_extract_email_from_html_prefers_mailto() -> None:
    html = """
    <html><body>
      <a href="mailto:hr@example.com?subject=hi">Kontakt</a>
      <p>sales@example.com</p>
    </body></html>
    """
    assert serp._extract_email_from_html(html) == "hr@example.com"


def test_looks_like_captcha_or_block_detection() -> None:
    assert serp._looks_like_captcha_or_block(429, "")
    assert serp._looks_like_captcha_or_block(200, "<html>verify you are human</html>")
    assert not serp._looks_like_captcha_or_block(200, "<html>kontakt hr@example.com</html>")


def test_record_key_uses_domain_or_name() -> None:
    assert serp._record_key("Firma X", "https://www.example.com/a") == "example.com"
    assert serp._record_key("Firma   X", "") == "firma x"


def test_is_job_portal_domain_detects_portals() -> None:
    assert serp._is_job_portal_domain("https://pracuj.pl/oferta/123")
    assert serp._is_job_portal_domain("justjoin.it")
    assert not serp._is_job_portal_domain("example.com")


def test_extract_organic_clears_portal_website() -> None:
    row = serp._extract_organic(
        {"title": "Firma Z - oferta pracy", "link": "https://pracuj.pl/oferta/abc"},
        category="Software house data BI",
        query="test",
        city="Wroclaw",
    )
    assert row["Firma"] == "Firma Z"
    assert row["Strona WWW"] == ""


def test_collect_group_deduplicates_results(monkeypatch) -> None:
    monkeypatch.setattr(serp.time, "sleep", lambda _x: None)

    def _fake_query(_api_key: str, _query: str, _start: int, num: int) -> dict:
        assert num == 10
        return {
            "local_results": [
                {"title": "Firma A", "website": "https://a.example.com", "phone": "123"}
            ],
            "organic_results": [
                {"title": "Firma A - jobs", "link": "https://a.example.com/jobs"},
                {"title": "Firma B - careers", "link": "https://b.example.com"},
            ],
        }

    monkeypatch.setattr(serp, "_query_serpapi", _fake_query)
    rows = serp.collect_group(
        api_key="x",
        group_name="test",
        keywords=["Data analytics consulting"],
        cities=["Wroclaw"],
        target_count=10,
        max_requests=1,
        request_sleep_s=0.0,
        pages_per_query=1,
        num_per_request=10,
    )

    websites = {r["Strona WWW"] for r in rows}
    assert len(rows) == 2
    assert "https://a.example.com" in websites
    assert "https://b.example.com" in websites


def test_collect_group_handles_local_results_dict_places(monkeypatch) -> None:
    monkeypatch.setattr(serp.time, "sleep", lambda _x: None)

    def _fake_query(_api_key: str, _query: str, _start: int, num: int) -> dict:
        assert num == 10
        return {
            "local_results": {
                "places": [
                    {"title": "Firma C", "website": "https://c.example.com", "phone": "123"}
                ]
            },
            "organic_results": [],
        }

    monkeypatch.setattr(serp, "_query_serpapi", _fake_query)
    rows = serp.collect_group(
        api_key="x",
        group_name="test",
        keywords=["Data analytics consulting"],
        cities=["Wroclaw"],
        target_count=1,
        max_requests=1,
        request_sleep_s=0.0,
        pages_per_query=1,
        num_per_request=10,
    )
    assert len(rows) == 1
    assert rows[0]["Firma"] == "Firma C"


def test_collect_group_serpapi_error_does_not_crash(monkeypatch, capsys) -> None:
    monkeypatch.setattr(serp.time, "sleep", lambda _x: None)

    def _fake_query(_api_key: str, _query: str, _start: int, num: int) -> dict:
        return {"error": "SerpAPI quota exceeded"}

    monkeypatch.setattr(serp, "_query_serpapi", _fake_query)
    rows = serp.collect_group(
        api_key="x",
        group_name="errtest",
        keywords=["Data analytics consulting"],
        cities=["Wroclaw"],
        target_count=5,
        max_requests=2,
        request_sleep_s=0.0,
        pages_per_query=1,
        num_per_request=10,
    )
    assert rows == []
    out = capsys.readouterr().out
    assert "SerpAPI error" in out
    assert "quota exceeded" in out


def test_collect_group_empty_api_payload_collects_nothing(monkeypatch) -> None:
    monkeypatch.setattr(serp.time, "sleep", lambda _x: None)

    def _empty(_api_key: str, _query: str, _start: int, num: int) -> dict:
        return {}

    monkeypatch.setattr(serp, "_query_serpapi", _empty)
    rows = serp.collect_group(
        api_key="x",
        group_name="empty",
        keywords=["Data analytics consulting"],
        cities=["Wroclaw"],
        target_count=5,
        max_requests=3,
        request_sleep_s=0.0,
        pages_per_query=1,
        num_per_request=10,
    )
    assert rows == []


def test_collect_group_serpapi_error_then_success_still_collects(monkeypatch) -> None:
    monkeypatch.setattr(serp.time, "sleep", lambda _x: None)
    calls = {"n": 0}

    def _fake_query(_api_key: str, _query: str, _start: int, num: int) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            return {"error": "temporary"}
        return {
            "organic_results": [
                {"title": "Po bledzie Sp z oo", "link": "https://po-bledzie.example.com"},
            ]
        }

    monkeypatch.setattr(serp, "_query_serpapi", _fake_query)
    rows = serp.collect_group(
        api_key="x",
        group_name="mix",
        keywords=["Data analytics consulting"],
        cities=["Wroclaw"],
        target_count=5,
        max_requests=10,
        request_sleep_s=0.0,
        pages_per_query=1,
        num_per_request=10,
    )
    assert len(rows) >= 1
    assert any("po-bledzie.example.com" in r.get("Strona WWW", "") for r in rows)


def test_find_company_website_uses_non_portal_result(monkeypatch) -> None:
    def _fake_query(_api_key: str, _query: str, start: int, num: int) -> dict:
        assert start == 0
        assert num == 10
        return {
            "organic_results": [
                {"link": "https://pracuj.pl/oferta/1"},
                {"link": "https://firmax.pl"},
            ]
        }

    monkeypatch.setattr(serp, "_query_serpapi", _fake_query)
    website = serp._find_company_website("k", "Firma X", "Wroclaw")
    assert website == "https://firmax.pl"


def test_find_public_contact_page_uses_non_portal_result(monkeypatch) -> None:
    def _fake_query(_api_key: str, _query: str, start: int, num: int) -> dict:
        assert start == 0
        assert num == 10
        return {
            "organic_results": [
                {"link": "https://justjoin.it/job/abc"},
                {"link": "https://firmax.pl/kontakt"},
            ]
        }

    monkeypatch.setattr(serp, "_query_serpapi", _fake_query)
    page = serp._find_public_contact_page("k", "Firma X", "Wroclaw")
    assert page == "https://firmax.pl/kontakt"


def test_extract_recruit_email_from_site_returns_empty_when_all_requests_fail(monkeypatch) -> None:
    def _fake_get(_url, timeout, headers):
        return _Resp("", 503)

    monkeypatch.setattr(serp.requests, "get", _fake_get)
    assert serp._extract_recruit_email_from_site("https://firma.example.com") == ""


def test_extract_recruit_email_from_site_tries_multiple_urls_on_http_errors(monkeypatch) -> None:
    calls = {"n": 0}

    def _fake_get(_url, timeout, headers):
        calls["n"] += 1
        return _Resp("<html>err</html>", 500)

    monkeypatch.setattr(serp.requests, "get", _fake_get)
    assert serp._extract_recruit_email_from_site("https://firma.example.com") == ""
    assert calls["n"] >= 5


def test_extract_recruit_email_from_site_skips_captcha_page(monkeypatch) -> None:
    responses = [
        _Resp("<html>verify you are human</html>", 200),
        _Resp("<html><a href='mailto:hr@firma.pl'>mail</a></html>", 200),
    ]
    state = {"i": 0}

    def _fake_get(url, timeout, headers):
        idx = state["i"]
        state["i"] += 1
        return responses[min(idx, len(responses) - 1)]

    monkeypatch.setattr(serp.requests, "get", _fake_get)
    email = serp._extract_recruit_email_from_site("https://firma.pl")
    assert email == "hr@firma.pl"


def test_extract_local_clears_job_portal_website() -> None:
    row = serp._extract_local(
        {
            "title": "Firma Portal",
            "website": "https://pracuj.pl/oferta/1",
            "phone": "+48 111 222 333",
            "address": "ul. Test 1, Wroclaw",
        },
        category="Agencja outsourcingowa IT",
        query="test",
        city="Wroclaw",
    )
    assert row["Strona WWW"] == ""


def test_main_daily_limit_exits_2(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SERPAPI_DAILY_LIMIT_ENABLED", "1")
    monkeypatch.setenv("SERPAPI_RUN_STATE_PATH", str(tmp_path / "st"))
    (tmp_path / "st").write_text(datetime.now().date().isoformat(), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_contacts_serpapi.py",
            "--firm-target",
            "1",
            "--output",
            str(tmp_path / "out.xlsx"),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        serp.main()
    assert exc.value.code == 2


def test_main_missing_api_key_exits_2(monkeypatch, tmp_path) -> None:
    _clear_serp_api_key_env(monkeypatch)
    monkeypatch.setenv("SERPAPI_DAILY_LIMIT_ENABLED", "0")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_contacts_serpapi.py",
            "--firm-target",
            "1",
            "--output",
            str(tmp_path / "out.xlsx"),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        serp.main()
    assert exc.value.code == 2


def test_main_missing_serp_package_exits_2(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SERPAPI_API_KEY", "x")
    monkeypatch.setenv("SERPAPI_DAILY_LIMIT_ENABLED", "0")
    monkeypatch.setattr(serp, "GoogleSearch", None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_contacts_serpapi.py",
            "--firm-target",
            "1",
            "--output",
            str(tmp_path / "out.xlsx"),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        serp.main()
    assert exc.value.code == 2


def test_serp_daily_limit_enabled_reads_env(monkeypatch) -> None:
    monkeypatch.delenv("SERPAPI_DAILY_LIMIT_ENABLED", raising=False)
    assert serp._serp_daily_limit_enabled() is False
    for v in ("1", "true", "yes", "on"):
        monkeypatch.setenv("SERPAPI_DAILY_LIMIT_ENABLED", v)
        assert serp._serp_daily_limit_enabled() is True
    monkeypatch.setenv("SERPAPI_DAILY_LIMIT_ENABLED", "0")
    assert serp._serp_daily_limit_enabled() is False


def test_serp_run_state_path_env_override(monkeypatch, tmp_path) -> None:
    custom = str(tmp_path / "custom_state")
    monkeypatch.setenv("SERPAPI_RUN_STATE_PATH", custom)
    assert serp._serp_run_state_path() == custom


def test_should_skip_serp_today_matches_state_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SERPAPI_DAILY_LIMIT_ENABLED", "1")
    p = tmp_path / "state"
    monkeypatch.setenv("SERPAPI_RUN_STATE_PATH", str(p))
    y = (datetime.now().date() - timedelta(days=1)).isoformat()
    p.write_text(y + "\n", encoding="utf-8")
    assert serp._should_skip_serp_today() is False
    p.write_text(datetime.now().date().isoformat(), encoding="utf-8")
    assert serp._should_skip_serp_today() is True


def _argv_serp_minimal(out: str) -> list[str]:
    return [
        "build_contacts_serpapi.py",
        "--firm-target",
        "0",
        "--agency-target",
        "0",
        "--ecommerce-target",
        "0",
        "--cities",
        "Wroclaw",
        "--no-discover-websites",
        "--output",
        out,
    ]


def test_main_zero_targets_writes_state_when_daily_limit_on(monkeypatch, tmp_path) -> None:
    """Bez wywołań SerpAPI (target 0); po sukcesie zapis daty przy włączonym limicie dziennym."""
    monkeypatch.setenv("SERPAPI_DAILY_LIMIT_ENABLED", "1")
    monkeypatch.setenv("SERPAPI_API_KEY", "unused-when-zero-targets")
    state_path = tmp_path / "nested" / "serp_state"
    monkeypatch.setenv("SERPAPI_RUN_STATE_PATH", str(state_path))
    out = tmp_path / "empty_leads.xlsx"
    monkeypatch.setattr(serp.time, "sleep", lambda _x: None)
    monkeypatch.setattr(sys, "argv", _argv_serp_minimal(str(out)))
    serp.main()
    assert state_path.is_file()
    assert serp._read_serp_last_run_date(str(state_path)) == datetime.now().date().isoformat()
    assert out.is_file()


def test_main_zero_targets_does_not_write_state_when_daily_limit_off(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.delenv("SERPAPI_DAILY_LIMIT_ENABLED", raising=False)
    monkeypatch.setenv("SERPAPI_API_KEY", "unused-when-zero-targets")
    state_path = tmp_path / "should_not_exist"
    monkeypatch.setenv("SERPAPI_RUN_STATE_PATH", str(state_path))
    out = tmp_path / "empty_leads.xlsx"
    monkeypatch.setattr(serp.time, "sleep", lambda _x: None)
    monkeypatch.setattr(sys, "argv", _argv_serp_minimal(str(out)))
    serp.main()
    assert not state_path.exists()
    assert out.is_file()


def test_write_serp_last_run_date_creates_parent_dir(tmp_path) -> None:
    path = tmp_path / "a" / "b" / "state.txt"
    serp._write_serp_last_run_date(str(path), date(2030, 1, 15))
    assert path.read_text(encoding="utf-8").strip() == "2030-01-15"
