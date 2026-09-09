# -*- coding: utf-8 -*-
"""Ścieżki projektu — bez twardych ścieżek użytkownika Windows (GitHub / inne maszyny)."""
from __future__ import annotations

from pathlib import Path

from scraper_env import ENV_KANBUD_DATA_DIR, get_env_value

PROJECT_ROOT = Path(__file__).resolve().parent


def get_app_root() -> Path:
    """
    Katalog z app.py i scraperami.
    Dla EXE desktop: ustawiane przez desktop_app (KANBUD_APP_ROOT).
    """
    import os
    import sys

    raw = os.environ.get("KANBUD_APP_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PROJECT_ROOT


def resolve_python_executable() -> str:
    """Python do subprocessów (scrapery). Przy pakiecie desktop: runtime/."""
    import sys

    root = get_app_root()
    for rel in (
        Path("runtime") / "Scripts" / "python.exe",
        Path("runtime") / "python.exe",
    ):
        p = root / rel
        if p.is_file():
            return str(p)
    return sys.executable


def get_data_root() -> Path:
    """
    Katalog danych operacyjnych (cache, Excel, logi).
    Domyślnie = folder projektu; nadpisz: KANBUD_DATA_DIR w .env / zmiennych Windows.
    """
    raw = get_env_value(ENV_KANBUD_DATA_DIR, "")
    if raw:
        return Path(raw).expanduser().resolve()
    return get_app_root()


def results_dir(folder_name: str) -> Path:
    """Np. results_dir('Wyniki_Transport_PL')."""
    return get_data_root() / folder_name


def gui_data_dir() -> Path:
    return get_app_root() / "gui_data"


def has_local_campaign_data() -> bool:
    """Czy na dysku są foldery Wyniki_* (kampanie PL/DE)."""
    root = get_data_root()
    markers = (
        "Wyniki_Gdansk",
        "Wyniki_Warszawa",
        "Wyniki_Saalfeld",
        "Wyniki_Transport_PL",
    )
    return any((root / name).is_dir() for name in markers)


def is_cloud_deployment() -> bool:
    """Streamlit Cloud / hosting bez lokalnych Wyniki_*."""
    import os

    if os.environ.get("KANBUD_FORCE_LOCAL", "").strip() in ("1", "true", "yes"):
        return False
    if os.environ.get("KANBUD_CLOUD_HOST", "").strip() in ("1", "true", "yes"):
        return True
    return not has_local_campaign_data()


def switzerland_wyniki_dir() -> Path:
    """
    Folder wyników kampanii CH (cache, Excel).
    Szuka w KANBUD_DATA_DIR/Szwajcaria/Wyniki, potem w PROJECT_ROOT/Szwajcaria/Wyniki.
    """
    primary = get_data_root() / "Szwajcaria" / "Wyniki"
    legacy = PROJECT_ROOT / "Szwajcaria" / "Wyniki"
    if primary.exists() or not legacy.exists():
        return primary
    return legacy
