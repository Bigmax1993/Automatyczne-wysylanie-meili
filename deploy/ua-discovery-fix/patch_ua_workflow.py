#!/usr/bin/env python3
"""Patch ua_materialy_pi.yml to apply discovery fix before scraper run."""
from __future__ import annotations

import sys
from pathlib import Path

PATCH_URL = (
    "https://raw.githubusercontent.com/Bigmax1993/"
    "Automatyczne-wysylanie-meili/main/deploy/ua-discovery-fix/apply_fix.py"
)

NEEDLE = (
    "      - name: Discovery (serper-only, pon-pt)\n"
    "        run: |\n"
    "          ARGS="
)
INSERT = (
    "      - name: Discovery (serper-only, pon-pt)\n"
    "        run: |\n"
    f'          curl -fsSL "{PATCH_URL}" -o /tmp/apply_discovery_fix.py\n'
    "          python3 /tmp/apply_discovery_fix.py ua_materialy_scraper.py\n"
    "          ARGS="
)


def patch(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "apply_discovery_fix.py" in text:
        print(f"Already patched: {path}")
        return
    if NEEDLE not in text:
        raise SystemExit(f"Discovery step not found in {path}")
    path.write_text(text.replace(NEEDLE, INSERT, 1), encoding="utf-8")
    print(f"Patched: {path}")


if __name__ == "__main__":
    target = Path(
        sys.argv[1]
        if len(sys.argv) > 1
        else "ua-repo/.github/workflows/ua_materialy_pi.yml"
    )
    patch(target)
