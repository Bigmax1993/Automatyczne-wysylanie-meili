# -*- coding: utf-8 -*-
"""Repo GU â€” sys.path: korzeĹ„ repo + libs/."""
from __future__ import annotations
import os, sys
from pathlib import Path
_REPO = Path(__file__).resolve().parent
_LIBS = _REPO / "libs"

def ensure_import_paths(campaign_dir: Path | None = None) -> Path:
    campaign_dir = (campaign_dir or Path.cwd()).resolve()
    for folder in (campaign_dir, _REPO, _LIBS):
        s = str(folder.resolve())
        if s not in sys.path:
            sys.path.insert(0, s)
    if (_LIBS / "polish_text.py").is_file():
        libs_s = str(_LIBS.resolve())
        os.environ.setdefault("KANBUD_PROJECT_ROOT", libs_s)
        if libs_s not in sys.path:
            sys.path.append(libs_s)
        return _LIBS
    raise ImportError("Brak libs/polish_text.py w repozytorium GU.")
