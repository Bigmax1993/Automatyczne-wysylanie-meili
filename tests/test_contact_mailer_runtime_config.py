"""Konfiguracja środowiskowa contact_mailer (CV_PATH, podpowiedzi błędów)."""

from __future__ import annotations

import pytest

import contact_mailer as cm


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", ""),
        (None, ""),
        ("  ", ""),
        ("abcd efgh ijkl mnop", "abcdefghijklmnop"),
        (" abcd efgh ijkl mnop \n", "abcdefghijklmnop"),
    ],
)
def test_normalize_gmail_app_password(raw: str | None, expected: str) -> None:
    assert cm.normalize_gmail_app_password(raw) == expected


def test_resolve_sender_email_default() -> None:
    assert cm.resolve_sender_email({}) == cm.DEFAULT_GMAIL_SENDER_EMAIL


def test_resolve_sender_email_from_gmail_env() -> None:
    assert cm.resolve_sender_email({"GMAIL_SENDER_EMAIL": " a@b.com "}) == "a@b.com"


def test_resolve_sender_email_sender_alias() -> None:
    assert cm.resolve_sender_email({"SENDER_EMAIL": "x@y.pl"}) == "x@y.pl"


def test_resolve_sender_email_gmail_wins_over_sender() -> None:
    assert (
        cm.resolve_sender_email({"GMAIL_SENDER_EMAIL": "g@gmail.com", "SENDER_EMAIL": "s@gmail.com"})
        == "g@gmail.com"
    )


def test_resolve_sender_email_whitespace_falls_back_to_default() -> None:
    assert cm.resolve_sender_email({"GMAIL_SENDER_EMAIL": "  \t"}) == cm.DEFAULT_GMAIL_SENDER_EMAIL


def test_resolve_cv_path_error_contains_env_hint(tmp_path, monkeypatch) -> None:
    missing = tmp_path / "NieistniejaceCV"
    monkeypatch.setattr(cm, "SEARCH_DIR", str(tmp_path))
    monkeypatch.setenv("CV_PATH", str(missing))

    with pytest.raises(FileNotFoundError) as exc:
        cm._resolve_cv_path()

    assert "CV_PATH" in str(exc.value)
    assert str(missing) in str(exc.value)


def test_apply_send_delay_respects_bounds(monkeypatch) -> None:
    monkeypatch.setattr(cm, "MIN_DELAY_SECONDS", 1.0)
    monkeypatch.setattr(cm, "MAX_DELAY_SECONDS", 3.0)
    captured = {"delay": None}

    monkeypatch.setattr(cm.random, "uniform", lambda low, high: 2.5)
    monkeypatch.setattr(cm.time, "sleep", lambda value: captured.update({"delay": value}))
    cm._apply_send_delay()

    assert captured["delay"] == 2.5
