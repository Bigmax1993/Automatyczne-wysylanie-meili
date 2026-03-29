"""Testy kopii zapasowych DataFrame do JSON (json_data_backup)."""

from __future__ import annotations

import json
import os
import time

import pandas as pd

import json_data_backup as jb


def test_backup_disabled_while_pytest_active() -> None:
    assert jb._under_pytest()
    assert jb.backup_enabled() is False


def test_backup_enabled_when_pytest_flag_bypassed(monkeypatch) -> None:
    monkeypatch.setattr(jb, "_under_pytest", lambda: False)
    monkeypatch.setenv("PIPELINE_JSON_BACKUP", "1")
    assert jb.backup_enabled() is True
    monkeypatch.setenv("PIPELINE_JSON_BACKUP", "0")
    assert jb.backup_enabled() is False


def test_maybe_backup_writes_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(jb, "_under_pytest", lambda: False)
    monkeypatch.setenv("PIPELINE_JSON_BACKUP", "1")
    monkeypatch.setenv("PIPELINE_JSON_BACKUP_DIR", str(tmp_path))
    df = pd.DataFrame([{"Firma": "X", "E-mail rekrutacyjny": "a@b.pl"}])
    target = str(tmp_path / "Kontakty_cleaned.csv")
    jb.maybe_backup_dataframe(df, target, reason="csv_save")

    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["backup_format"] == 1
    assert payload["row_count"] == 1
    assert payload["reason"] == "csv_save"
    assert os.path.abspath(target) == payload["target_path"]
    assert payload["columns"] == ["Firma", "E-mail rekrutacyjny"]
    assert len(payload["data"]) == 1
    assert payload["data"][0]["Firma"] == "X"


def test_maybe_backup_skips_when_disabled(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(jb, "_under_pytest", lambda: False)
    monkeypatch.setenv("PIPELINE_JSON_BACKUP", "0")
    monkeypatch.setenv("PIPELINE_JSON_BACKUP_DIR", str(tmp_path))
    jb.maybe_backup_dataframe(pd.DataFrame([{"a": 1}]), str(tmp_path / "x.csv"))
    assert list(tmp_path.glob("*.json")) == []


def test_maybe_backup_no_op_for_none_df(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(jb, "_under_pytest", lambda: False)
    monkeypatch.setenv("PIPELINE_JSON_BACKUP", "1")
    monkeypatch.setenv("PIPELINE_JSON_BACKUP_DIR", str(tmp_path))
    jb.maybe_backup_dataframe(None, str(tmp_path / "x.csv"))  # type: ignore[arg-type]
    assert list(tmp_path.glob("*.json")) == []


def test_prune_removes_oldest_when_over_max(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(jb, "_under_pytest", lambda: False)
    monkeypatch.setenv("PIPELINE_JSON_BACKUP", "1")
    monkeypatch.setenv("PIPELINE_JSON_BACKUP_DIR", str(tmp_path))
    monkeypatch.setenv("PIPELINE_JSON_BACKUP_MAX_FILES", "3")

    for i in range(3):
        p = tmp_path / f"old_{i}.json"
        p.write_text("{}", encoding="utf-8")
        time.sleep(0.02)

    df = pd.DataFrame([{"k": 1}])
    jb.maybe_backup_dataframe(df, str(tmp_path / "sheet.csv"), reason="r")
    remaining = sorted(tmp_path.glob("*.json"), key=lambda x: x.stat().st_mtime)
    assert len(remaining) == 3


def test_sanitize_token_in_filename(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(jb, "_under_pytest", lambda: False)
    monkeypatch.setenv("PIPELINE_JSON_BACKUP", "1")
    monkeypatch.setenv("PIPELINE_JSON_BACKUP_DIR", str(tmp_path))
    jb.maybe_backup_dataframe(
        pd.DataFrame([{"a": 1}]),
        str(tmp_path / "data.csv"),
        reason="weird !@# reason",
    )
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    assert "weird" in files[0].name
