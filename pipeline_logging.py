"""Centralna konfiguracja logowania (stdlib logging) dla skryptów potoku."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_configured = False


class _StdoutProxy:
    """Zawsze zapisuje na bieżący sys.stdout (działa z pytest capsys)."""

    __slots__ = ()

    def write(self, s: str) -> int:
        return sys.stdout.write(s)

    def flush(self) -> None:
        sys.stdout.flush()

    def isatty(self) -> bool:
        io = sys.stdout
        fn = getattr(io, "isatty", None)
        return bool(fn()) if callable(fn) else False


def reset_logging_state_for_tests() -> None:
    """Wyłącznie testy: czyści handlery root loggera i pozwala ponownie wywołać setup_logging."""
    global _configured
    _configured = False
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass


def setup_logging(component: str = "pipeline") -> None:
    """
    Konfiguruje root logger (stdout przez proxy + opcjonalnie plik).
    Wywołaj raz na początku main() każdego skryptu CLI.
    """
    global _configured
    if _configured:
        return
    _configured = True

    level_name = (os.environ.get("PIPELINE_LOG_LEVEL") or "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Proxy → bieżący stdout (pytest capsys podmienia sys.stdout po imporcie modułów)
    sh = logging.StreamHandler(_StdoutProxy())
    sh.setLevel(level)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    log_file = (os.environ.get("PIPELINE_LOG_FILE") or "").strip()
    to_file = (os.environ.get("PIPELINE_LOG_TO_FILE") or "0").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if to_file and not log_file:
        log_file = str(Path.home() / "Documents" / "pipeline_logs" / "python_pipeline.log")
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            path,
            maxBytes=int(os.environ.get("PIPELINE_LOG_MAX_BYTES", "10485760")),
            backupCount=int(os.environ.get("PIPELINE_LOG_BACKUP_COUNT", "5")),
            encoding="utf-8",
        )
        fh.setLevel(level)
        fh.setFormatter(fmt)
        root.addHandler(fh)

    logging.getLogger(__name__).debug(
        "setup_logging component=%s level=%s file=%s",
        component,
        level_name,
        log_file or "-",
    )
