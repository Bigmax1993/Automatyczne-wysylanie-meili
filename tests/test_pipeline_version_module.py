"""Testy modulu pipeline_version (spojnosc z plikiem VERSION)."""

from __future__ import annotations

from pathlib import Path

import pipeline_version as pv


def test_pipeline_version_matches_version_file() -> None:
    root = Path(__file__).resolve().parent.parent
    vf = root / "VERSION"
    assert vf.is_file()
    assert pv.PIPELINE_VERSION == vf.read_text(encoding="utf-8").strip()


def test_pipeline_version_non_empty_semver_like() -> None:
    assert len(pv.PIPELINE_VERSION) >= 3
    assert any(c.isdigit() for c in pv.PIPELINE_VERSION)
