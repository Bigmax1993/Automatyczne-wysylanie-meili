"""
Testy skladni i regresji run_with_env.ps1 (Windows / PowerShell Parser).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUN_WITH_ENV = PROJECT_ROOT / "run_with_env.ps1"


def _powershell_parse_file(path: Path) -> tuple[int, str]:
    ps1 = path.resolve()
    cmd = rf"""
$ErrorActionPreference = 'Stop'
$p = '{str(ps1).replace("'", "''")}'
$tokens = $null
$errors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($p, [ref]$tokens, [ref]$errors)
if ($null -ne $errors -and $errors.Count -gt 0) {{
    $errors | ForEach-Object {{ $_.ToString() }}
    exit 1
}}
exit 0
"""
    r = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            cmd,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )
    return r.returncode, (r.stdout or "") + (r.stderr or "")


@pytest.mark.skipif(sys.platform != "win32", reason="run_with_env.ps1 tylko Windows")
def test_run_with_env_ps1_exists() -> None:
    assert RUN_WITH_ENV.is_file()


@pytest.mark.skipif(sys.platform != "win32", reason="Parser PowerShell")
def test_run_with_env_ps1_parses() -> None:
    code, out = _powershell_parse_file(RUN_WITH_ENV)
    assert code == 0, out


@pytest.mark.skipif(sys.platform != "win32", reason="tresc PS1")
def test_run_with_env_merges_user_env_for_keys() -> None:
    raw = RUN_WITH_ENV.read_text(encoding="utf-8")
    assert "GetEnvironmentVariable" in raw
    assert '"User"' in raw or "'User'" in raw
    assert "OPENAI_API_KEY" in raw
    assert "GMAIL_SENDER_EMAIL" in raw
    assert "Normalize-GmailAppPassword" in raw


@pytest.mark.skipif(sys.platform != "win32", reason="tresc PS1")
def test_run_with_env_dot_sources_local_env() -> None:
    raw = RUN_WITH_ENV.read_text(encoding="utf-8")
    assert ". $localEnvPath" in raw


@pytest.mark.skipif(sys.platform != "win32", reason="tresc PS1")
def test_run_with_env_openai_short_key_merge_from_user() -> None:
    raw = RUN_WITH_ENV.read_text(encoding="utf-8")
    assert "openaiMinRealisticLen" in raw or "$openaiMinRealisticLen" in raw
    assert "80" in raw


@pytest.mark.skipif(sys.platform != "win32", reason="tresc PS1")
def test_run_with_env_gmail_merge_and_length_check() -> None:
    raw = RUN_WITH_ENV.read_text(encoding="utf-8")
    assert "normProcG" in raw
    assert "normUserG" in raw
    assert "16" in raw
    assert "GMAIL_APP_PASSWORD" in raw
    assert "haslem aplikacji" in raw or "haslo aplikacji" in raw.lower()


@pytest.mark.skipif(sys.platform != "win32", reason="tresc PS1")
def test_run_with_env_assert_openai_key_minimum_length() -> None:
    raw = RUN_WITH_ENV.read_text(encoding="utf-8")
    assert "Assert-OpenAiKey" in raw
    assert "40" in raw
