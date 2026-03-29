"""Testy domain_blocklist (parsowanie pliku, wildcard, cache)."""

from __future__ import annotations

import pytest

import domain_blocklist as bl


def test_parse_strips_at_and_comments(tmp_path, monkeypatch) -> None:
    p = tmp_path / "block.txt"
    p.write_text(
        "# komentarz\n"
        "@spam.pl\n"
        "  evil.test  # tail\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(bl, "BLOCKLIST_PATH", str(p))
    bl.clear_blocklist_cache()
    assert bl.recipient_domain_is_blocked("x@spam.pl") is True
    assert bl.recipient_domain_is_blocked("x@evil.test") is True


def test_email_without_at_not_blocked() -> None:
    assert bl.recipient_domain_is_blocked("not-an-email") is False
    assert bl.recipient_domain_is_blocked("") is False


def test_wildcard_subdomain_blocked_not_root(tmp_path, monkeypatch) -> None:
    p = tmp_path / "w.txt"
    p.write_text("*.apps.example\n", encoding="utf-8")
    monkeypatch.setattr(bl, "BLOCKLIST_PATH", str(p))
    bl.clear_blocklist_cache()
    assert bl.recipient_domain_is_blocked("u@hr.apps.example") is True
    assert bl.recipient_domain_is_blocked("u@apps.example") is False


def test_exact_domain_match(tmp_path, monkeypatch) -> None:
    p = tmp_path / "e.txt"
    p.write_text("only.pl\n", encoding="utf-8")
    monkeypatch.setattr(bl, "BLOCKLIST_PATH", str(p))
    bl.clear_blocklist_cache()
    assert bl.recipient_domain_is_blocked("a@only.pl") is True
    assert bl.recipient_domain_is_blocked("a@sub.only.pl") is False


def test_clear_blocklist_cache_forces_reload(tmp_path, monkeypatch) -> None:
    p = tmp_path / "mut.txt"
    p.write_text("a.pl\n", encoding="utf-8")
    monkeypatch.setattr(bl, "BLOCKLIST_PATH", str(p))
    bl.clear_blocklist_cache()
    assert bl.recipient_domain_is_blocked("x@a.pl") is True
    p.write_text("b.pl\n", encoding="utf-8")
    bl.clear_blocklist_cache()
    assert bl.recipient_domain_is_blocked("x@a.pl") is False
    assert bl.recipient_domain_is_blocked("x@b.pl") is True


def test_reload_after_reload_sec_reads_new_file(monkeypatch, tmp_path) -> None:
    p = tmp_path / "c.txt"
    p.write_text("z.pl\n", encoding="utf-8")
    monkeypatch.setattr(bl, "BLOCKLIST_PATH", str(p))
    monkeypatch.setattr(bl, "_RELOAD_SEC", 30.0)
    bl.clear_blocklist_cache()
    ticks = [0.0]
    monkeypatch.setattr(bl.time, "time", lambda: ticks[0])
    assert bl.recipient_domain_is_blocked("x@z.pl") is True
    p.write_text("y.pl\n", encoding="utf-8")
    ticks[0] = 100.0
    assert bl.recipient_domain_is_blocked("x@z.pl") is False
    assert bl.recipient_domain_is_blocked("x@y.pl") is True


def test_missing_file_returns_empty_blocklist(monkeypatch) -> None:
    monkeypatch.setattr(bl, "BLOCKLIST_PATH", str("/nonexistent/path/block.txt"))
    bl.clear_blocklist_cache()
    assert bl.load_blocked_domains() == frozenset()
    assert bl.recipient_domain_is_blocked("any@where.pl") is False
