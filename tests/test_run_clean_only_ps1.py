"""Testy pliku run_clean_only.ps1: składnia PowerShell (Parser)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUN_CLEAN_ONLY_PS1 = PROJECT_ROOT / "run_clean_only.ps1"


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
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode, out


@pytest.mark.skipif(sys.platform != "win32", reason="run_clean_only.ps1 jest dla Windows")
def test_run_clean_only_ps1_exists() -> None:
    assert RUN_CLEAN_ONLY_PS1.is_file(), f"Brak pliku: {RUN_CLEAN_ONLY_PS1}"


@pytest.mark.skipif(sys.platform != "win32", reason="Parser PowerShell tylko na Windows")
def test_run_clean_only_ps1_parses_without_errors() -> None:
    code, out = _powershell_parse_file(RUN_CLEAN_ONLY_PS1)
    assert code == 0, f"Błąd parsowania PowerShell:\n{out}"


@pytest.mark.skipif(sys.platform != "win32", reason="Treść skryptu Windows")
def test_run_clean_only_invokes_clean_validate_pipeline() -> None:
    text = RUN_CLEAN_ONLY_PS1.read_text(encoding="utf-8")
    assert "clean_validate_send_pipeline.py" in text
    assert "PIPELINE_PYTHON_EXE" in text
