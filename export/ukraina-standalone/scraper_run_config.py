# -*- coding: utf-8 -*-
"""
Ładowanie plików run_config/*.json (--run-config) dla scraperów kampanii.

apply_run_config_file — ustawia atrybuty modułu scrapera z JSON.
run_scraper_launch_kwargs — zwraca argumenty dla run_scraper().

Pola active_bundeslaender i min_contacts_target obsługuje apply_gu_run_config_extras
w de_gu_bauunternehmen_scraper.py (wywoływane po apply_run_config_file).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_MODULE_STRING_ATTRS = {
    "lang": ("CUSTOM_EMAIL_LANG", "SERPER_LANGUAGE"),
    "city_name": ("CUSTOM_EMAIL_CITY",),
    "delivery_address": ("INQUIRY_REGION_DE",),
}

_MODULE_BOOL_ATTRS = {
    "enable_auto_email": "ENABLE_AUTO_EMAIL",
}

_LAUNCH_KW_KEYS = (
    "enable_auto_email",
    "dry_run_email",
    "discovery_mode",
    "max_new_rows",
    "force_resend",
    "ignore_send_window",
    "rebuild_from_cache",
)


def _resolve_config_path(path: Path | str, base_dir: Path | str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = Path(base_dir) / p
    return p.resolve()


def load_run_config_file(path: Path | str, base_dir: Path | str) -> dict[str, Any]:
    cfg_path = _resolve_config_path(path, base_dir)
    with open(cfg_path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"run_config must be a JSON object: {cfg_path}")
    return data


def apply_run_config_file(module, path: Path | str, base_dir: Path | str) -> dict[str, Any]:
    """Wczytaj JSON i zastosuj znane pola na module scrapera."""
    data = load_run_config_file(path, base_dir)
    module._RUN_CONFIG_DATA = data

    config_type = data.get("config_type")
    if config_type is not None:
        module._RUN_CONFIG_TYPE = str(config_type)

    for json_key, attr_names in _MODULE_STRING_ATTRS.items():
        if json_key not in data:
            continue
        value = str(data[json_key]).strip()
        if not value:
            continue
        for attr in attr_names:
            if hasattr(module, attr):
                setattr(module, attr, value)

    for json_key, attr_name in _MODULE_BOOL_ATTRS.items():
        if json_key in data and hasattr(module, attr_name):
            setattr(module, attr_name, bool(data[json_key]))

    if "min_contacts_target" in data and hasattr(module, "MIN_CONTACTS_TARGET"):
        try:
            module.MIN_CONTACTS_TARGET = int(data["min_contacts_target"])
        except (TypeError, ValueError):
            pass

    return data


def run_scraper_launch_kwargs(module) -> dict[str, Any]:
    """Zbuduj kwargs dla run_scraper() z zapisanego run_config i stanu modułu."""
    data: dict[str, Any] = getattr(module, "_RUN_CONFIG_DATA", None) or {}
    kw: dict[str, Any] = {}

    for key in _LAUNCH_KW_KEYS:
        if key not in data or data[key] is None:
            continue
        value = data[key]
        if key == "discovery_mode":
            kw[key] = str(value)
        elif key == "max_new_rows":
            try:
                kw[key] = int(value)
            except (TypeError, ValueError):
                pass
        elif key in ("enable_auto_email", "dry_run_email", "force_resend", "ignore_send_window", "rebuild_from_cache"):
            kw[key] = bool(value)
        else:
            kw[key] = value

    if "enable_auto_email" not in kw and hasattr(module, "ENABLE_AUTO_EMAIL"):
        kw["enable_auto_email"] = bool(module.ENABLE_AUTO_EMAIL)

    return kw
