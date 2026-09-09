#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root
$env:KANBUD_PROJECT_ROOT = Join-Path $Root "libs"
$env:PYTHONUTF8 = "1"

$failed = @()
$passed = @()

function Test-Step {
    param([string]$Name, [scriptblock]$Block)
    Write-Host "`n>> $Name" -ForegroundColor Cyan
    try {
        & $Block
        if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "exit $LASTEXITCODE" }
        $script:passed += $Name
        Write-Host "OK: $Name" -ForegroundColor Green
    } catch {
        $script:failed += "${Name}: $_"
        Write-Host "FAIL: $Name - $_" -ForegroundColor Red
    }
}

Test-Step "py_compile (wszystkie .py)" {
    Get-ChildItem -Recurse -Filter *.py |
        Where-Object { $_.FullName -notmatch '\\.venv\\' } |
        ForEach-Object {
            python -m py_compile $_.FullName
            if ($LASTEXITCODE -ne 0) { throw $_.FullName }
        }
}

Test-Step "smoke --test (UA materialy)" { python ua_materialy_scraper.py --test }

Test-Step "regresja UA materialy" {
    python -m unittest tests.test_ua_materialy_regression -v
}

Test-Step "pytest UA (jednostkowe + integracyjne)" {
    python -m pytest tests/test_ua_oblast_keywords.py tests/test_ua_inquiry_email_uk.py tests/test_ua_claude_inquiry_email.py tests/test_ua_supplier_filter.py tests/test_ua_materialy_integration.py -q
}

Test-Step "ua_oblast_rotation" {
    python -c @"
from pathlib import Path
import tempfile
from ua_oblast_rotation import (
    load_rotation_state, peek_next_oblast, commit_rotation_after_run,
    rotation_state_path, OBLAST_ROTATION_ORDER,
)
d = Path(tempfile.mkdtemp())
p = rotation_state_path(d)
s = load_rotation_state(p)
oblast = peek_next_oblast(s)
assert oblast in OBLAST_ROTATION_ORDER
commit_rotation_after_run(p, s, oblast)
"@
}

Test-Step "ua_materialy — brak zalacznikow i MFG" {
    python -c @"
from ua_materialy_inquiry_email_uk import DEFAULT_INQUIRY_PHONE_UK, build_fixed_material_inquiry_uk
import ua_materialy_scraper as ua
assert ua.get_email_attachments_ua_materialy() == []
assert ua.UA_EMAIL_ALLOW_ATTACHMENTS is False
assert DEFAULT_INQUIRY_PHONE_UK == '+380977091141'
body = build_fixed_material_inquiry_uk()
assert 'mfg' not in body.lower()
assert '+380977091141' in body
"@
}

Test-Step "run_config JSON (UA)" {
    python -c @"
from pathlib import Path
from scraper_run_config import load_run_config_file
for cfg in ['run_config/ua_materialy.json','run_config/ua_kyiv_test.json']:
    d = load_run_config_file(cfg, Path('.'))
    assert d['config_type'] == 'ua_materialy'
"@
}

Test-Step "dry-run wysylki UA" {
    python ua_materialy_scraper.py --dry-run-email --send-emails-only | Out-Null
}

Test-Step "gdrive_upload_wyniki --help" {
    python scripts/gdrive_upload_wyniki.py --help | Out-Null
}

Write-Host "`n======== PODSUMOWANIE ========" -ForegroundColor Yellow
Write-Host "Passed: $($passed.Count)"
$passed | ForEach-Object { Write-Host "  + $_" }
if ($failed.Count) {
    Write-Host "Failed: $($failed.Count)" -ForegroundColor Red
    $failed | ForEach-Object { Write-Host "  - $_" }
    exit 1
}
Write-Host "Wszystkie testy OK" -ForegroundColor Green
