"""
Testy pliku run_pipeline.ps1: skladnia PowerShell (Parser) i kontrakt wobec CI (GitHub Actions).

- Asercje na tresc pliku uruchamiane sa tez na Linuxie (job test-python), zeby regresje lapac przed pipeline.
- Parser: powershell.exe na Windows, na innych OS pwsh jesli jest w PATH (runner ubuntu ma zwykle pwsh).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUN_PIPELINE_PS1 = PROJECT_ROOT / "run_pipeline.ps1"


def _powershell_argv() -> list[str] | None:
    """Argumenty do subprocess.run: exe + standardowe flagi + -Command (bez samej komendy)."""
    if sys.platform == "win32":
        return [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
        ]
    pwsh = shutil.which("pwsh")
    if not pwsh:
        return None
    return [pwsh, "-NoProfile", "-NonInteractive", "-Command"]


def _powershell_parse_file(path: Path) -> tuple[int, str]:
    """Zwraca (exit_code, polaczony stdout+stderr). 0 = brak bledow parsowania."""
    argv = _powershell_argv()
    if argv is None:
        return -1, "brak powershell.exe / pwsh w PATH"
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
        [*argv, cmd],
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode, out


def test_run_pipeline_ps1_exists() -> None:
    assert RUN_PIPELINE_PS1.is_file(), f"Brak pliku: {RUN_PIPELINE_PS1}"


@pytest.mark.skipif(_powershell_argv() is None, reason="Brak powershell.exe (Windows) ani pwsh w PATH")
def test_run_pipeline_ps1_parses_without_errors() -> None:
    code, out = _powershell_parse_file(RUN_PIPELINE_PS1)
    assert code == 0, f"Blad parsowania PowerShell:\n{out}"


def test_run_pipeline_uses_script_root_for_project_dir() -> None:
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert "Split-Path -Parent $MyInvocation.MyCommand.Path" in text


def test_run_pipeline_respects_pipeline_python_exe_env() -> None:
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert "PIPELINE_PYTHON_EXE" in text
    assert "Get-Command" in text


def test_run_pipeline_python_stderr_uses_continue_not_only_stop() -> None:
    """Regresja: Stop przerywa na stderr Pythona przed zebraniem $cleanOut."""
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert '$ErrorActionPreference = "Continue"' in text
    assert "clean_validate_send_pipeline.py" in text
    # blok clean: Continue, potem finally przywraca
    assert re.search(r"finally\s*\{[^}]*\$ErrorActionPreference\s*=\s*\$prevEap", text, re.DOTALL)


def test_run_pipeline_prints_python_output_on_clean_failure() -> None:
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert "Python (pelny komunikat" in text
    assert "foreach ($line in $cleanOut)" in text


def test_run_pipeline_fallback_kontakty_dir_and_extensions() -> None:
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert "EXTRA_CONTACTS_DIR" in text
    assert r"Documents\kontakty" in text
    assert ".xlsx" in text and ".csv" in text
    assert "--extra-contacts-dir" in text
    assert '"--extra-contacts-dir", $kontaktyDir' in text


def test_run_pipeline_serpapi_block_also_uses_continue_for_stderr() -> None:
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert "build_contacts_serpapi.py" in text
    # jeden blok Continue przy build (nie tylko przy clean)
    assert text.count('$ErrorActionPreference = "Continue"') >= 2


def test_run_pipeline_normalizes_clean_output_to_string_array() -> None:
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert '$cleanOut = @($cleanOut | ForEach-Object { "$_" })' in text


def test_run_pipeline_forces_dry_run_when_gmail_password_missing() -> None:
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert "Brak poprawnego GMAIL_APP_PASSWORD" in text
    assert "$DryRun = $true" in text
    assert "gmailNorm.Length -ne 16" in text


def test_run_pipeline_declares_skipbuild_dryrun_switches_like_ci() -> None:
    """CI wywoluje ./run_pipeline.ps1 -SkipBuild -DryRun (main.yml / schedule-pipeline-monday.yml)."""
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert "[switch]$SkipBuild" in text
    assert "[switch]$DryRun" in text


def test_run_pipeline_clean_stage_passes_input_output_csv_and_optional_dry_run() -> None:
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert "clean_validate_send_pipeline.py" in text
    assert '"--input", $inputForClean' in text
    assert '"--output-csv", $outputCsv' in text
    assert 'if ($DryRun)' in text
    assert '$cleanArgs += "--dry-run"' in text


def test_run_pipeline_default_paths_match_ci_prepare_input_sample() -> None:
    """Krok Prepare input sample tworzy Documents/kontakty/*.csv — skrypt szuka Kontakty_serpapi.xlsx lub ostatniego pliku w kontakty."""
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert "Kontakty_serpapi.xlsx" in text
    assert "Kontakty_cleaned.csv" in text
    assert "pipeline_logs" in text
    assert "yyyyMMdd_HHmmss" in text


def test_run_pipeline_missing_input_throws_clear_error() -> None:
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert "Brak pliku wejsciowego" in text
    assert ".xlsx/.xls/.csv" in text


def test_run_pipeline_serpapi_daily_limit_and_exit_code_2_branch() -> None:
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert "SERPAPI_DAILY_LIMIT_ENABLED" in text
    assert "$buildExit -eq 2" in text


def test_run_pipeline_build_output_normalized_like_clean() -> None:
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert '$buildOut = @($buildOut | ForEach-Object { "$_" })' in text


def test_run_pipeline_clean_failure_throw_mentions_exit_code_and_log() -> None:
    text = RUN_PIPELINE_PS1.read_text(encoding="utf-8")
    assert "clean_validate_send_pipeline zakonczyl sie kodem" in text
    assert "$cleanExit" in text
