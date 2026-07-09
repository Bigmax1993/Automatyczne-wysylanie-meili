# -*- coding: utf-8 -*-
"""Wspólna konfiguracja pytest — ścieżka projektu i libs."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIBS = ROOT / "libs"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(LIBS) not in sys.path:
    sys.path.insert(0, str(LIBS))

os.environ.setdefault("KANBUD_PROJECT_ROOT", str(LIBS))
os.environ.setdefault("PYTHONUTF8", "1")
