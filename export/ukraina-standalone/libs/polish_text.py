# -*- coding: utf-8 -*-
"""
UTF-8 i polskie znaki (ąćęłńóśźż) — konfiguracja środowiska, naprawa kodowania, logi, subprocess.
"""
from __future__ import annotations

import io
import logging
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import unquote

_CONFIGURED = False

_MOJIBAKE_MARKERS = (
    "Ä…",
    "Ä™",
    "Ä‡",
    "Å‚",
    "Å„",
    "Ã³",
    "Å›",
    "Åº",
    "Å¼",
    "Ä",
    "Å",
    "Ã",
    "â€",
    "Ä‡",
    "Å›",
    "Ä…",
)

_POLISH_CHARS_RE = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")


def configure_utf8_environment() -> None:
    """Ustawia UTF-8 dla konsoli, subprocess i domyślnego I/O (Windows + Linux)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    if sys.platform == "win32":
        try:
            os.system("chcp 65001 >nul 2>&1")
        except Exception:
            pass

    for stream_name in ("stdout", "stderr", "stdin"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            try:
                buf = getattr(stream, "buffer", None)
                if buf is not None:
                    wrapper = io.TextIOWrapper(
                        buf,
                        encoding="utf-8",
                        errors="replace",
                        line_buffering=stream_name != "stdin",
                    )
                    setattr(sys, stream_name, wrapper)
            except Exception:
                pass


def fix_polish_mojibake(text: str) -> str:
    """Naprawia typowe błędy kodowania (np. WojewÃ³dztwo → Województwo)."""
    if not text:
        return ""
    s = str(text)
    if _POLISH_CHARS_RE.search(s) and not any(m in s for m in ("Ã", "Ä", "Å")):
        return s
    if not any(m in s for m in _MOJIBAKE_MARKERS):
        return s
    try:
        fixed = s.encode("latin-1").decode("utf-8")
        if fixed and fixed != s:
            return fixed
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    try:
        fixed = s.encode("cp1252").decode("utf-8")
        if fixed and fixed != s:
            return fixed
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return s


def normalize_unicode_text(value: Any) -> str:
    if value is None:
        return ""
    text = fix_polish_mojibake(str(value))
    text = unquote(text)
    return unicodedata.normalize("NFC", text)


def sanitize_special_text(value: Any) -> str:
    """Czyści tekst z kontrolnych znaków; zachowuje polskie litery."""
    text = normalize_unicode_text(value)
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", " ", text)
    text = " ".join(text.split())
    return text.strip(" -|")


def sanitize_email_body(value: Any) -> str:
    """Czyści treść maila — zachowuje akapity (\\n), w przeciwieństwie do sanitize_special_text."""
    text = normalize_unicode_text(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return "\n".join(lines).strip()


def email_plain_to_html(plain: str) -> str:
    """Plain text z pustymi liniami → HTML z akapitami (webmail home.pl / Outlook)."""
    import html as html_module

    blocks: list[str] = []
    for block in re.split(r"\n\s*\n", (plain or "").strip()):
        block = block.strip()
        if not block:
            continue
        inner = html_module.escape(block).replace("\n", "<br>\n")
        blocks.append(
            '<p style="margin:0 0 12px 0;line-height:1.45;">' f"{inner}</p>"
        )
    if not blocks:
        return "<div></div>"
    return (
        '<div style="font-family:Calibri,Arial,Helvetica,sans-serif;'
        'font-size:11pt;color:#000000;">'
        + "".join(blocks)
        + "</div>"
    )


def normalize_row_dict(row: dict) -> dict:
    out: dict = {}
    for key, val in row.items():
        k = normalize_unicode_text(key) if isinstance(key, str) else key
        if isinstance(val, str):
            out[k] = normalize_unicode_text(val)
        else:
            out[k] = val
    return out


def utf8_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def create_stream_handler() -> logging.StreamHandler:
    configure_utf8_environment()
    return logging.StreamHandler(sys.stdout)


def setup_script_logging(name: str, log_file: Path | str | None = None) -> logging.Logger:
    """Logger ze skryptów scraperów (konsola UTF-8 + plik UTF-8)."""
    configure_utf8_environment()
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    ch = create_stream_handler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(str(log_path), encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger


def setup_module_logging(name: str) -> logging.Logger:
    """Prosty logger dla sync_*.py / send_email_reminders.py."""
    configure_utf8_environment()
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        h = create_stream_handler()
        h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(h)
    return logger
