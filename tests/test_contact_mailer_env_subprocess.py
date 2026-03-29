"""
Import contact_mailer w osobnym procesie — `password` i `SENDER_EMAIL` z env przy starcie modułu.

Środowisko pytest może już zaimportować contact_mailer; te testy sprawdzają zachowanie „czystego” importu.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _run_isolated(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=90,
        encoding="utf-8",
        errors="replace",
    )


def test_subprocess_import_normalizes_gmail_app_password() -> None:
    root = str(PROJECT_ROOT)
    code = f"""
import os, sys
sys.path.insert(0, {root!r})
os.environ["GMAIL_APP_PASSWORD"] = "aa bb cc dd ee ff gg hh"
import contact_mailer as cm
assert cm.password == "aabbccddeeffgghh", (cm.password, len(cm.password))
print("ok")
"""
    r = _run_isolated(code)
    assert r.returncode == 0, r.stdout + r.stderr


def test_subprocess_import_sender_from_gmail_sender_email() -> None:
    code = f"""
import os, sys
sys.path.insert(0, {str(PROJECT_ROOT)!r})
for k in ("GMAIL_SENDER_EMAIL", "SENDER_EMAIL", "GMAIL_APP_PASSWORD"):
    os.environ.pop(k, None)
os.environ["GMAIL_SENDER_EMAIL"] = "  nadawca@test.example  "
import contact_mailer as cm
assert cm.SENDER_EMAIL == "nadawca@test.example"
print("ok")
"""
    r = _run_isolated(code)
    assert r.returncode == 0, r.stdout + r.stderr


def test_subprocess_import_sender_from_sender_email_alias() -> None:
    code = f"""
import os, sys
sys.path.insert(0, {str(PROJECT_ROOT)!r})
for k in ("GMAIL_SENDER_EMAIL", "SENDER_EMAIL"):
    os.environ.pop(k, None)
os.environ["SENDER_EMAIL"] = "alias@example.org"
import contact_mailer as cm
assert cm.SENDER_EMAIL == "alias@example.org"
print("ok")
"""
    r = _run_isolated(code)
    assert r.returncode == 0, r.stdout + r.stderr


def test_subprocess_import_default_sender_when_env_cleared() -> None:
    code = f"""
import os, sys
sys.path.insert(0, {str(PROJECT_ROOT)!r})
for k in ("GMAIL_SENDER_EMAIL", "SENDER_EMAIL"):
    os.environ.pop(k, None)
import contact_mailer as cm
assert cm.SENDER_EMAIL == cm.DEFAULT_GMAIL_SENDER_EMAIL
print("ok")
"""
    r = _run_isolated(code)
    assert r.returncode == 0, r.stdout + r.stderr
