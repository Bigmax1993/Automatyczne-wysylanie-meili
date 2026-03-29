"""Rozwiązywanie e-maila ze strony WWW (try_resolve_email_from_website)."""

from __future__ import annotations

import build_contacts_serpapi as serp
import contact_mailer as cm


def test_try_resolve_disabled_keeps_empty(monkeypatch) -> None:
    monkeypatch.setattr(cm, "FETCH_EMAIL_FROM_WEBSITE", False)
    e, filled = cm.try_resolve_email_from_website("", "https://firma.pl")
    assert e == "" and filled is False


def test_try_resolve_keeps_valid_email(monkeypatch) -> None:
    monkeypatch.setattr(cm, "FETCH_EMAIL_FROM_WEBSITE", True)

    def _boom(_u: str, timeout: float = 8.0) -> str:
        raise AssertionError("nie wołaj sieci")

    monkeypatch.setattr(serp, "_extract_recruit_email_from_site", _boom)
    e, filled = cm.try_resolve_email_from_website("jan@a.pl", "https://x.pl")
    assert e == "jan@a.pl" and filled is False


def test_try_resolve_fills_from_site(monkeypatch) -> None:
    monkeypatch.setattr(cm, "FETCH_EMAIL_FROM_WEBSITE", True)

    def _fake(url: str, timeout: float = 8.0) -> str:
        assert "firma" in url
        return "hr@firma.pl"

    monkeypatch.setattr(serp, "_extract_recruit_email_from_site", _fake)
    e, filled = cm.try_resolve_email_from_website("", "https://firma.example.com")
    assert e == "hr@firma.pl" and filled is True


def test_try_resolve_replaces_invalid_with_valid_from_site(monkeypatch) -> None:
    monkeypatch.setattr(cm, "FETCH_EMAIL_FROM_WEBSITE", True)
    monkeypatch.setattr(
        serp,
        "_extract_recruit_email_from_site",
        lambda _u, timeout=8.0: "ok@firma.pl",
    )
    e, filled = cm.try_resolve_email_from_website("zly-adres", "firma.pl")
    assert e == "ok@firma.pl" and filled is True
