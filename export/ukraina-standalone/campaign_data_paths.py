# -*- coding: utf-8 -*-
"""
Ścieżki wyników kampanii: cache JSON, Excel, log, wyslane/ (.eml).

Domyślny cel chmury (Google Drive):
  https://drive.google.com/drive/folders/1tP8oUi72t4EHDbE9GnHFdvfNtNsJe4xf

Ustaw lokalnie zsynchronizowany folder:
  KANBUD_GOOGLE_DRIVE_GU_PATH=C:\\ścieżka\\do\\folderu\\w\\My Drive
  lub KANBUD_DATA_DIR=ta_sama_ścieżka
"""
from __future__ import annotations

import os
from pathlib import Path

GOOGLE_DRIVE_GU_FOLDER_ID = "1tP8oUi72t4EHDbE9GnHFdvfNtNsJe4xf"
GOOGLE_DRIVE_GU_FOLDER_URL = (
    f"https://drive.google.com/drive/folders/{GOOGLE_DRIVE_GU_FOLDER_ID}?usp=drive_link"
)
GOOGLE_DRIVE_PL_FOLDER_ID = "1O15CdN0TH8rx74sPP5C1GuYSweX81IGw"
GOOGLE_DRIVE_PL_FOLDER_URL = (
    f"https://drive.google.com/drive/folders/{GOOGLE_DRIVE_PL_FOLDER_ID}?usp=drive_link"
)

# Nazwy podfolderów szukane pod „Google Drive” / „Dyski współdzielone”
_DRIVE_FOLDER_NAMES_GU = (
    "GU Bauunternehmen Wyniki",
    "Kanbud GU Wyniki",
    "de_gu_wyniki",
)
_DRIVE_FOLDER_NAMES_UA = (
    "UA Materialy Budowlane Wyniki",
    "Kanbud UA Materialy Wyniki",
    "ua_materialy_wyniki",
)
_DRIVE_FOLDER_NAMES_PL = (
    "PL Materialy Budowlane Wyniki",
    "Kanbud PL Materialy Wyniki",
    "pl_materialy_wyniki",
)
_DRIVE_FOLDER_NAMES = _DRIVE_FOLDER_NAMES_GU


def _google_drive_bases() -> list[Path]:
    home = Path.home()
    bases: list[Path] = []
    for p in (
        os.environ.get("GDRIVE_MIRROR_PATH", "").strip(),
        os.environ.get("KANBUD_GOOGLE_DRIVE_GU_PATH", "").strip(),
        r"G:\My Drive",
        r"G:\Dyski współdzielone",
        r"H:\My Drive",
        str(home / "Google Drive" / "My Drive"),
        str(home / "Google Drive"),
        str(home / "Dyski współdzielone"),
    ):
        if p:
            bases.append(Path(p))
    return bases


def resolve_data_root(campaign_dir: Path, *, campaign: str = "gu") -> Path:
    """
    Katalog danych kampanii: Wyniki/, wyslane/.
    campaign: gu | ua | pl
    """
    if campaign == "ua":
        folder_names = _DRIVE_FOLDER_NAMES_UA
    elif campaign == "pl":
        folder_names = _DRIVE_FOLDER_NAMES_PL
    else:
        folder_names = _DRIVE_FOLDER_NAMES_GU
    for key in ("KANBUD_DATA_DIR", "KANBUD_GOOGLE_DRIVE_GU_PATH", "KANBUD_GOOGLE_DRIVE_PATH"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            p = Path(raw).expanduser().resolve()
            if p.is_dir():
                return p

    for base in _google_drive_bases():
        if not base.is_dir():
            continue
        for name in folder_names:
            candidate = (base / name).resolve()
            if candidate.is_dir():
                return candidate

    return Path(campaign_dir).resolve()


def wyniki_dir(data_root: Path) -> Path:
    return data_root / "Wyniki"


def wyslane_dir(data_root: Path) -> Path:
    return data_root / "wyslane"


def ensure_data_dirs(data_root: Path) -> None:
    wyniki_dir(data_root).mkdir(parents=True, exist_ok=True)
    wyslane_dir(data_root).mkdir(parents=True, exist_ok=True)


def apply_data_root_to_env(data_root: Path) -> Path:
    """Ustawia KANBUD_DATA_DIR (mail_transport.get_wyslane_dir) i tworzy podfoldery."""
    root = data_root.resolve()
    os.environ["KANBUD_DATA_DIR"] = str(root)
    ensure_data_dirs(root)
    return root


def campaign_output_paths(campaign_dir: Path, basename: str) -> dict[str, Path]:
    """
    basename np. de_gu_bauunternehmen lub ua_materialy → pliki w Wyniki/.
    """
    campaign = (
        "pl" if basename.startswith("pl_")
        else "ua" if basename.startswith("ua_")
        else "gu"
    )
    root = apply_data_root_to_env(resolve_data_root(campaign_dir, campaign=campaign))
    out = wyniki_dir(root)
    return {
        "data_root": root,
        "output_dir": out,
        "output_file": out / f"{basename}_kontakte.xlsx",
        "cache_file": out / f"{basename}_cache.json",
        "log_file": out / f"{basename}_scraper.log",
        "wyslane_dir": wyslane_dir(root),
    }
