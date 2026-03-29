"""Kopie zapasowe zawartości DataFrame do JSON po zapisie CSV/XLSX."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pandas as pd

logger = logging.getLogger(__name__)


def _under_pytest() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def backup_enabled() -> bool:
    if _under_pytest():
        return False
    v = (os.environ.get("PIPELINE_JSON_BACKUP") or "1").strip().lower()
    return v in ("1", "true", "yes", "on")


def _backup_root() -> Path:
    raw = (os.environ.get("PIPELINE_JSON_BACKUP_DIR") or "").strip()
    if raw:
        return Path(os.path.expanduser(raw)).resolve()
    return Path.home() / "Documents" / "pipeline_json_backups"


def _sanitize_token(s: str) -> str:
    t = re.sub(r"[^\w\-.]+", "_", (s or "").strip(), flags=re.UNICODE)
    return (t or "save")[:64]


def _prune_old_backups(directory: Path, max_files: int) -> None:
    if max_files <= 0:
        return
    files = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime)
    while len(files) > max_files:
        oldest = files.pop(0)
        try:
            oldest.unlink()
            logger.debug("Usunięto stary backup JSON: %s", oldest)
        except OSError:
            break


def maybe_backup_dataframe(
    df: pd.DataFrame,
    target_path: str,
    reason: str = "save",
) -> None:
    if not backup_enabled():
        return
    if df is None:
        return

    try:
        root = _backup_root()
        root.mkdir(parents=True, exist_ok=True)
        stem = Path(target_path).stem
        safe_stem = re.sub(r"[^\w\-.]+", "_", stem, flags=re.UNICODE)[:80] or "data"
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        fname = f"{safe_stem}_{ts}_{_sanitize_token(reason)}.json"
        out_path = root / fname

        records = json.loads(
            df.to_json(orient="records", date_format="iso", date_unit="s", force_ascii=False)
        )
        payload: Dict[str, Any] = {
            "backup_format": 1,
            "saved_at_utc": datetime.now(timezone.utc).isoformat(),
            "target_path": os.path.abspath(target_path),
            "reason": reason,
            "row_count": len(df),
            "columns": list(df.columns.astype(str)),
            "data": records,
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        logger.info("Backup JSON: %s wierszy -> %s", len(df), out_path)
        max_keep = int(os.environ.get("PIPELINE_JSON_BACKUP_MAX_FILES", "200"))
        _prune_old_backups(root, max_keep)
    except Exception:
        logger.exception("Nie udało się zapisać kopii JSON (kontynuacja bez backupu)")
