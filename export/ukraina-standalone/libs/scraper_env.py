# -*- coding: utf-8 -*-
"""
Wspólne nazwy zmiennych środowiskowych (identyczne jak w PowerShell User/Machine).

Ustawienie na stałe (PowerShell):
  [System.Environment]::SetEnvironmentVariable("SERPER_API_KEY", "...", "User")
  [System.Environment]::SetEnvironmentVariable("MAIL_USER", "twoj@domena.pl", "User")
  [System.Environment]::SetEnvironmentVariable("MAIL_PASSWORD", "...", "User")
  [System.Environment]::SetEnvironmentVariable("SMTP_HOST", "serwer.home.pl", "User")
  [System.Environment]::SetEnvironmentVariable("IMAP_HOST", "serwer.home.pl", "User")
  # Opcjonalnie (stare nazwy nadal działają): GMAIL_USER, GMAIL_APP_PASSWORD, GMAIL_SENDER_NAME
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

_DOTENV_LOADED = False


def _load_dotenv_file() -> None:
    """Ładuje .env z katalogu projektu (nie commituj .env z kluczami)."""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.is_file():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except OSError:
        pass


_load_dotenv_file()

# --- Nazwy 1:1 z PowerShell ([Environment]::SetEnvironmentVariable(..., "User")) ---
ENV_SERPER_API_KEY = "SERPER_API_KEY"
ENV_MAIL_USER = "MAIL_USER"
ENV_MAIL_PASSWORD = "MAIL_PASSWORD"
ENV_MAIL_SENDER_NAME = "MAIL_SENDER_NAME"
ENV_SMTP_HOST = "SMTP_HOST"
ENV_SMTP_PORT = "SMTP_PORT"
ENV_SMTP_SSL = "SMTP_SSL"
ENV_IMAP_HOST = "IMAP_HOST"
ENV_IMAP_PORT = "IMAP_PORT"
ENV_IMAP_SSL = "IMAP_SSL"
ENV_MAIL_BCC = "MAIL_BCC"
ENV_MAIL_CC = "MAIL_CC"
ENV_MAIL_ARCHIVE_IMAP = "MAIL_ARCHIVE_IMAP"
# Kompatybilność wsteczna (Gmail lub stare instalacje)
ENV_GMAIL_USER = "GMAIL_USER"
ENV_GMAIL_APP_PASSWORD = "GMAIL_APP_PASSWORD"
ENV_GMAIL_SENDER_NAME = "GMAIL_SENDER_NAME"
ENV_ANTHROPIC_API_KEY = "ANTHROPIC_API_KEY"
ENV_CLAUDE_MODEL = "CLAUDE_MODEL"
ENV_CLAUDE_MODEL_VERIFY = "CLAUDE_MODEL_VERIFY"
ENV_CLAUDE_MODEL_FAST = "CLAUDE_MODEL_FAST"
ENV_KANBUD_DATA_DIR = "KANBUD_DATA_DIR"

# Opcjonalne (tylko niektóre skrypty)
ENV_ENABLE_GEO_DISTANCE_PLZ_FILTER = "ENABLE_GEO_DISTANCE_PLZ_FILTER"
ENV_MAX_DISTANCE_KM_FROM_ANCHOR = "MAX_DISTANCE_KM_FROM_ANCHOR"
ENV_SERPER_SHUFFLE_TERMS = "SERPER_SHUFFLE_TERMS"
ENV_EMAIL_MX_CHECK = "EMAIL_MX_CHECK"

REQUIRED_FOR_EMAIL = (ENV_MAIL_USER, ENV_MAIL_PASSWORD)
REQUIRED_FOR_SERPER = (ENV_SERPER_API_KEY,)

_WINDOWS_ENV_CACHE: dict[str, str] = {}
_LEGACY_ENV_ALIASES = {
    ENV_GMAIL_USER: ENV_MAIL_USER,
    ENV_GMAIL_APP_PASSWORD: ENV_MAIL_PASSWORD,
    ENV_GMAIL_SENDER_NAME: ENV_MAIL_SENDER_NAME,
}


def get_env_value(name: str, default: str = "") -> str:
    """Odczyt zmiennej: proces → cache → PowerShell User → PowerShell Machine."""
    val = os.getenv(name)
    if val:
        return val.strip()
    alias = _LEGACY_ENV_ALIASES.get(name)
    if alias:
        alias_val = os.getenv(alias)
        if alias_val:
            return alias_val.strip()
    if name in _WINDOWS_ENV_CACHE:
        return _WINDOWS_ENV_CACHE[name]
    if os.name == "nt":
        for scope in ("User", "Machine"):
            try:
                cmd = (
                    f"[Environment]::GetEnvironmentVariable('{name}','{scope}')"
                )
                out = subprocess.check_output(
                    ["powershell", "-NoProfile", "-Command", cmd],
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    stderr=subprocess.DEVNULL,
                )
                val = (out or "").strip()
                if val:
                    _WINDOWS_ENV_CACHE[name] = val
                    os.environ.setdefault(name, val)
                    return val
            except Exception:
                continue
    return (default or "").strip()


def get_serper_api_key() -> str:
    return get_env_value(ENV_SERPER_API_KEY)


def get_anthropic_api_key() -> str:
    return get_env_value(ENV_ANTHROPIC_API_KEY)


def get_mail_user() -> str:
    return get_env_value(ENV_MAIL_USER) or get_env_value(ENV_GMAIL_USER)


def get_mail_password() -> str:
    return get_env_value(ENV_MAIL_PASSWORD) or get_env_value(ENV_GMAIL_APP_PASSWORD)


def get_mail_sender_name() -> str:
    return get_env_value(ENV_MAIL_SENDER_NAME) or get_env_value(ENV_GMAIL_SENDER_NAME)


def get_gmail_user() -> str:
    return get_mail_user()


def get_gmail_app_password() -> str:
    return get_mail_password()


def get_gmail_sender_name() -> str:
    return get_mail_sender_name()


def check_env_status() -> dict[str, bool]:
    """Które zmienne są ustawione (bez ujawniania wartości)."""
    all_names = (
        ENV_SERPER_API_KEY,
        ENV_MAIL_USER,
        ENV_MAIL_PASSWORD,
        ENV_MAIL_SENDER_NAME,
        ENV_SMTP_HOST,
        ENV_IMAP_HOST,
        ENV_GMAIL_USER,
        ENV_GMAIL_APP_PASSWORD,
        ENV_GMAIL_SENDER_NAME,
        ENV_ANTHROPIC_API_KEY,
        ENV_CLAUDE_MODEL,
        ENV_CLAUDE_MODEL_VERIFY,
        ENV_CLAUDE_MODEL_FAST,
    )
    return {n: bool(get_env_value(n)) for n in all_names}


# UTF-8 / polskie znaki — od razu przy imporcie modułu wspólnego
from polish_text import configure_utf8_environment

configure_utf8_environment()
