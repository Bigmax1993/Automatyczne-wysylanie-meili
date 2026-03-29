"""Pojedyncza wersja calego zestawu skryptow (lead -> clean -> wysylka)."""

from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parent / "VERSION"

PIPELINE_VERSION = _VERSION_FILE.read_text(encoding="utf-8").strip()
