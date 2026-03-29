from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

import sent_mail_registry as sm


@pytest.fixture
def reg_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "registry_enabled", lambda: True)
    monkeypatch.setattr(sm, "registry_dir", lambda: str(tmp_path))
    return tmp_path


def test_append_and_candidates(reg_dir, monkeypatch):
    monkeypatch.setattr(sm, "close_prior_pending_same_email", lambda *a, **k: None)
    old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    path = sm.jsonl_path_for_batch("Kontakty_serpapi.xlsx")
    rec = {
        "record_id": "a",
        "sent_at": old,
        "email": "x@firma.pl",
        "company": "Firma",
        "role": "Rola",
        "city": "Miasto",
        "industry": "IT",
        "website": "https://w.pl",
        "phone": "",
        "mode": "",
        "source": "",
        "notes": "",
        "subject": "T",
        "locale": "pl",
        "batch_file": "Kontakty_serpapi.xlsx",
        "output_csv": "out.csv",
        "kind": "initial",
        "reply_received": False,
        "follow_up_sent_at": None,
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    cand = sm.follow_up_candidates(7, registry_directory=str(reg_dir))
    assert len(cand) == 1
    assert cand[0]["email"] == "x@firma.pl"


def test_candidates_too_young(reg_dir):
    path = sm.jsonl_path_for_batch("b.xlsx")
    recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    rec = {
        "record_id": "b",
        "sent_at": recent,
        "email": "y@z.pl",
        "company": "Y",
        "role": "",
        "city": "",
        "industry": "",
        "website": "",
        "phone": "",
        "mode": "",
        "source": "",
        "notes": "",
        "subject": "",
        "locale": "pl",
        "batch_file": "b.xlsx",
        "output_csv": "o.csv",
        "kind": "initial",
        "reply_received": False,
        "follow_up_sent_at": None,
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    assert sm.follow_up_candidates(7, registry_directory=str(reg_dir)) == []


def test_mark_reply_received(reg_dir):
    path = sm.jsonl_path_for_batch("c.xlsx")
    rec = {
        "record_id": "c",
        "sent_at": "2020-01-01T00:00:00+00:00",
        "email": "reply@test.pl",
        "company": "C",
        "role": "",
        "city": "",
        "industry": "",
        "website": "",
        "phone": "",
        "mode": "",
        "source": "",
        "notes": "",
        "subject": "",
        "locale": "pl",
        "batch_file": "c.xlsx",
        "output_csv": "o.csv",
        "kind": "initial",
        "reply_received": False,
        "follow_up_sent_at": None,
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    n = sm.mark_reply_received("reply@test.pl", registry_directory=str(reg_dir))
    assert n == 1
    rows = sm._load_jsonl_file(path)
    assert rows[0]["reply_received"] is True


def test_append_sent_record_closes_prior(reg_dir):
    sm.append_sent_record(
        batch_path="main.xlsx",
        output_csv_path="o.csv",
        email="u@u.pl",
        company="U",
        role="r",
        city="c",
        industry="i",
        website="w",
        phone="p",
        mode="m",
        source="s",
        notes="n",
        subject="sub",
        locale="pl",
        dry_run=False,
    )
    path = sm.jsonl_path_for_batch("main.xlsx")
    first = sm._load_jsonl_file(path)
    assert len(first) == 1

    sm.append_sent_record(
        batch_path="followup.xlsx",
        output_csv_path="o2.csv",
        email="u@u.pl",
        company="U",
        role="r",
        city="c",
        industry="i",
        website="w",
        phone="p",
        mode="m",
        source="s",
        notes="n",
        subject="sub2",
        locale="pl",
        dry_run=False,
    )
    first_again = sm._load_jsonl_file(path)
    assert len(first_again) == 1
    assert first_again[0]["follow_up_sent_at"] is not None

    second_path = sm.jsonl_path_for_batch("followup.xlsx")
    second = sm._load_jsonl_file(second_path)
    assert len(second) == 1
    assert second[0]["kind"] == "follow_up"


def test_registry_disabled_under_pytest(monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "x")
    assert sm.registry_enabled() is False


def test_cleanup_removes_stale_by_sent_at(reg_dir, monkeypatch):
    monkeypatch.setattr(sm, "registry_retention_days", lambda: 14)
    path = reg_dir / "stale.jsonl"
    old = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
    path.write_text(
        json.dumps({"sent_at": old, "email": "a@b.c", "record_id": "1"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    assert sm.cleanup_stale_registry_files(registry_directory=str(reg_dir)) == 1
    assert not path.is_file()


def test_cleanup_keeps_recent_jsonl(reg_dir, monkeypatch):
    monkeypatch.setattr(sm, "registry_retention_days", lambda: 14)
    path = reg_dir / "fresh.jsonl"
    recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    path.write_text(
        json.dumps({"sent_at": recent, "email": "a@b.c", "record_id": "1"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    assert sm.cleanup_stale_registry_files(registry_directory=str(reg_dir)) == 0
    assert path.is_file()


def test_cleanup_disabled_when_retention_zero(reg_dir, monkeypatch):
    monkeypatch.setattr(sm, "registry_retention_days", lambda: 0)
    path = reg_dir / "old.jsonl"
    old = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    path.write_text(
        json.dumps({"sent_at": old, "email": "a@b.c", "record_id": "1"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    assert sm.cleanup_stale_registry_files(registry_directory=str(reg_dir)) == 0
    assert path.is_file()


def test_append_skips_when_disabled(reg_dir, monkeypatch):
    monkeypatch.setattr(sm, "registry_enabled", lambda: False)
    sm.append_sent_record(
        batch_path="z.xlsx",
        output_csv_path="z.csv",
        email="a@b.c",
        company="A",
        role="",
        city="",
        industry="",
        website="",
        phone="",
        mode="",
        source="",
        notes="",
        subject="",
        locale="pl",
        dry_run=False,
    )
    assert not list(reg_dir.iterdir())
