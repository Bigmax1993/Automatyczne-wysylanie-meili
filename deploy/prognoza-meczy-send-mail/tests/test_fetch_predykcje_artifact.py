"""Testy pobierania artifactu pipeline do wysyłki maila."""

from __future__ import annotations

import io
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import fetch_predykcje_artifact as fetcher


def _run_payload(*, run_id: int = 99, run_number: int = 3, hours_ago: int = 2) -> dict:
    created = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return {
        "id": run_id,
        "run_number": run_number,
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "html_url": f"https://github.com/o/r/actions/runs/{run_id}",
    }


def _artifact_zip(xlsx_name: str = "predykcje_2026.xlsx", content: bytes = b"xlsx") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(xlsx_name, content)
    return buf.getvalue()


def test_find_latest_successful_run_rejects_stale_runs():
    with patch.object(
        fetcher,
        "_api_json",
        return_value={"workflow_runs": [_run_payload(hours_ago=24 * 10)]},
    ):
        with pytest.raises(RuntimeError, match="starszy niż"):
            fetcher.find_latest_successful_run(
                repo="o/r",
                token="tok",
                workflow="pipeline.yml",
                branch="main",
                max_age_days=8,
            )


def test_find_latest_successful_run_picks_recent():
    run = _run_payload()
    with patch.object(
        fetcher,
        "_api_json",
        return_value={"workflow_runs": [run]},
    ):
        picked = fetcher.find_latest_successful_run(
            repo="o/r",
            token="tok",
            workflow="pipeline.yml",
            branch="main",
            max_age_days=8,
        )
    assert picked["id"] == 99


def test_fetch_predykcje_xlsx_writes_file(tmp_path: Path):
    dest = tmp_path / "predykcje_2026.xlsx"

    def fake_api_json(url: str, token: str):
        if "/workflows/" in url:
            return {"workflow_runs": [_run_payload()]}
        if "/artifacts?per_page=100" in url:
            return {
                "artifacts": [
                    {"id": 501, "name": "predykcje-xlsx", "expired": False},
                ]
            }
        raise AssertionError(f"unexpected url: {url}")

    with (
        patch.object(fetcher, "_api_json", side_effect=fake_api_json),
        patch.object(
            fetcher,
            "download_artifact_zip",
            return_value=_artifact_zip(content=b"fresh"),
        ),
    ):
        info = fetcher.fetch_predykcje_xlsx(
            repo="o/r",
            token="tok",
            dest=dest,
        )

    assert dest.read_bytes() == b"fresh"
    assert info["artifact_id"] == 501
    assert info["run_number"] == 3


def test_main_uses_fallback_when_artifact_missing(tmp_path: Path, capsys):
    fallback = tmp_path / "fallback.xlsx"
    fallback.write_bytes(b"repo-copy")
    dest = tmp_path / "predykcje_2026.xlsx"

    with patch.object(
        fetcher,
        "fetch_predykcje_xlsx",
        side_effect=RuntimeError("brak artifactu"),
    ):
        code = fetcher.main(
            [
                "--repo",
                "o/r",
                "--token",
                "tok",
                "--dest",
                str(dest),
                "--fallback",
                str(fallback),
            ]
        )

    assert code == 0
    assert dest.read_bytes() == b"repo-copy"
    err = capsys.readouterr().err
    assert "fallback" in err.lower()


def test_main_fails_without_fallback_on_missing_artifact(capsys):
    with patch.object(
        fetcher,
        "fetch_predykcje_xlsx",
        side_effect=RuntimeError("Brak udanego runu"),
    ):
        code = fetcher.main(["--repo", "o/r", "--token", "tok"])

    assert code == 1
    assert "Brak udanego runu" in capsys.readouterr().err
