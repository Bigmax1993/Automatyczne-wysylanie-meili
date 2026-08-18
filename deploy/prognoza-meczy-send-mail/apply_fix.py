#!/usr/bin/env python3
"""Wgraj poprawkę wysyłki Gmail do repo prognoza-meczy."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

COPY_MAP = {
    ROOT / "scripts/fetch_predykcje_artifact.py": "scripts/fetch_predykcje_artifact.py",
    ROOT / ".github/workflows/send-mail.yml": ".github/workflows/send-mail.yml",
    ROOT / "tests/test_fetch_predykcje_artifact.py": "tests/test_fetch_predykcje_artifact.py",
}


def apply_fix(target_repo: Path) -> list[str]:
    if not target_repo.is_dir():
        raise SystemExit(f"Brak katalogu docelowego: {target_repo}")
    changed: list[str] = []
    for src, rel in COPY_MAP.items():
        if not src.is_file():
            raise SystemExit(f"Brakuje pliku źródłowego: {src}")
        dest = target_repo / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        changed.append(rel)
    return changed


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        raise SystemExit(f"Użycie: {Path(__file__).name} <katalog-prognoza-meczy>")
    target = Path(args[0]).resolve()
    changed = apply_fix(target)
    print("Zaktualizowano:")
    for path in changed:
        print(f"  - {path}")


if __name__ == "__main__":
    main()
