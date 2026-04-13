"""
Testy pliku run_pipeline.ps1: skladnia PowerShell (Parser) i regresje tresci.

Parser wymaga powershell.exe w PATH (Windows).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUN_PIPELINE_PS1 = PROJECT_ROOT / "run_pipeline.ps1"


def _powershell_parse_file(path: Path) -> tuple[int, str]:
    """Zwraca (exit_code, polaczony stdout+stderr). 0 = brak bledow parsowania."""
    ps1 = path.resolve()
    # Join-Path w PS: bezpieczniejsze niz wklejanie sciezki w cudzyslow
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


@pytest.mark.skipif(sys.platform != "win32", reason="run_pipeline.ps1 jest dla Windows")
def test_run_pipeline_ps1_exists() -> None:
    assert RUN_PIPELINE_PS1.is_file(), f"Brak pliku: {RUN_PIPELINE_PS1}"


@pytest.mark.skipif(sys.platform != "win32", reason="Parser PowerShell tylko na Windows")
def test_run_pipeline_ps1_parses_without_errors() -> None:
    code, out = _powershell_parse_file(RUN_PIPELINE_PS1)
    assert code == 0, f"Blad parsowania PowerShell:\n{out}"


@pytest.mark.skipif(sys.platform != "win32", reason="Tresc skryptu Windows")
def test_run_pipeline_uses_script_root_for_project_dir() -> None:
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert "Split-Path -Parent $MyInvocation.MyCommand.Path" in text


@pytest.mark.skipif(sys.platform != "win32", reason="Tresc skryptu Windows")
def test_run_pipeline_respects_pipeline_python_exe_env() -> None:
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert "PIPELINE_PYTHON_EXE" in text
    assert "Get-Command" in text


@pytest.mark.skipif(sys.platform != "win32", reason="Tresc skryptu Windows")
def test_run_pipeline_python_stderr_uses_continue_not_only_stop() -> None:
    """Regresja: Stop przerywa na stderr Pythona przed zebraniem $cleanOut."""
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert '$ErrorActionPreference = "Continue"' in text
    assert "clean_validate_send_pipeline.py" in text
    # blok clean: Continue, potem finally przywraca
    assert re.search(r"finally\s*\{[^}]*\$ErrorActionPreference\s*=\s*\$prevEap", text, re.DOTALL)


@pytest.mark.skipif(sys.platform != "win32", reason="Tresc skryptu Windows")
def test_run_pipeline_prints_python_output_on_clean_failure() -> None:
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert "Python (pelny komunikat" in text
    assert "foreach ($line in $cleanOut)" in text


@pytest.mark.skipif(sys.platform != "win32", reason="Tresc skryptu Windows")
def test_run_pipeline_fallback_kontakty_dir_and_extensions() -> None:
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert "EXTRA_CONTACTS_DIR" in text
    assert r"Documents\kontakty" in text
    assert ".xlsx" in text and ".csv" in text
    assert "--extra-contacts-dir" in text
    assert '"--extra-contacts-dir", $kontaktyDir' in text


@pytest.mark.skipif(sys.platform != "win32", reason="Tresc skryptu Windows")
def test_run_pipeline_serpapi_block_also_uses_continue_for_stderr() -> None:
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert "build_contacts_serpapi.py" in text
    # jeden blok Continue przy build (nie tylko przy clean)
    assert text.count('$ErrorActionPreference = "Continue"') >= 2


@pytest.mark.skipif(sys.platform != "win32", reason="Tresc skryptu Windows")
def test_run_pipeline_normalizes_clean_output_to_string_array() -> None:
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert '$cleanOut = @($cleanOut | ForEach-Object { "$_" })' in text
