#!/usr/bin/env python3
"""Kopiuje poprawkę „rozegrane mecze → arkusz Матчі_2026” do checkoutu prognoza-meczy."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = ROOT / "files"

TARGETS = [
    "upcoming.py",
    "predykcje.py",
    "tests/test_upcoming.py",
    "tests/test_predykcje.py",
]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"Uzycie: {sys.argv[0]} <katalog-prognoza-meczy>")
    dest_root = Path(sys.argv[1]).resolve()
    if not dest_root.is_dir():
        raise SystemExit(f"Brak katalogu: {dest_root}")

    for rel in TARGETS:
        src = FILES / rel
        dst = dest_root / rel
        if not src.is_file():
            raise SystemExit(f"Brak pliku w bundle: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"OK {rel}")


if __name__ == "__main__":
    main()
