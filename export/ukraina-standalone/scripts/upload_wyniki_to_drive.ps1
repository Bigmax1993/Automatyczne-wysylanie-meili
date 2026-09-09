#Requires -Version 5.1
<#
Pobiera artefakt GU (ta sama kolejnosc co sync-google-drive.yml) i wgrywa na Google Drive.

  powershell -ExecutionPolicy Bypass -File scripts\upload_wyniki_to_drive.ps1

Priorytet artefaktow: thu (backfill) -> mon -> tue -> fri
Bez OAuth Desktop JSON otworzy folder na Pulpicie + link do Drive (reczny drag-drop).
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root
$Repo = "Bigmax1993/Wyszukiwarka-partnerow"
$DriveFolder = "1tP8oUi72t4EHDbE9GnHFdvfNtNsJe4xf"

# Ta sama kolejnosc co .github/workflows/sync-google-drive.yml
$ArtifactOrder = @(
    "de-gu-wyniki-thu",
    "de-gu-wyniki-mon",
    "de-gu-wyniki-tue",
    "de-gu-wyniki-fri"
)

Write-Host "=== Szukam artefaktu GU (thu -> mon -> tue -> fri) ===" -ForegroundColor Cyan
$artifactName = $null
$runId = $null
foreach ($name in $ArtifactOrder) {
    $runId = gh api "repos/$Repo/actions/artifacts?per_page=100" `
        --jq "[.artifacts[] | select(.name==`"$name`" and .expired==false)] | sort_by(.created_at) | reverse | .[0].workflow_run.id // empty" `
        2>$null
    if ($runId) {
        $artifactName = $name
        break
    }
}
if (-not $runId) {
    throw "Brak artefaktu GU (thu/mon/tue/fri) — uruchom backfill lub discovery"
}
Write-Host "Pobieram $artifactName z run $runId" -ForegroundColor Cyan

$tmp = Join-Path $env:TEMP "gu-drive-upload"
Remove-Item $tmp -Recurse -Force -EA SilentlyContinue
New-Item -ItemType Directory -Path $tmp | Out-Null
gh run download $runId -R $Repo -n $artifactName -D $tmp

New-Item -ItemType Directory -Force -Path "$Root\Wyniki" | Out-Null
New-Item -ItemType Directory -Force -Path "$Root\wyslane" | Out-Null
Copy-Item "$tmp\Wyniki\*" "$Root\Wyniki\" -Force
if (Test-Path "$tmp\wyslane") {
    Copy-Item "$tmp\wyslane\*" "$Root\wyslane\" -Recurse -Force
}
Write-Host "OK: Wyniki + wyslane w repo" -ForegroundColor Green

$oauthClient = Join-Path $Root "secrets\gdrive-oauth-client.json"
if (Test-Path $oauthClient) {
    Write-Host "=== Upload przez OAuth ===" -ForegroundColor Cyan
    python -m pip install -q -r requirements-drive.txt
    python scripts\gdrive_oauth_setup.py --client-json $oauthClient 2>$null
    $env:GDRIVE_SERVICE_ACCOUNT_FILE = ""
    python scripts\gdrive_upload_wyniki.py --campaign-dir .
    if ($LASTEXITCODE -eq 0) {
        Write-Host "GOTOWE: https://drive.google.com/drive/folders/$DriveFolder" -ForegroundColor Green
        exit 0
    }
}

$env:GDRIVE_SERVICE_ACCOUNT_FILE = Join-Path $Root "secrets\gdrive-service-account.json"
if (Test-Path $env:GDRIVE_SERVICE_ACCOUNT_FILE) {
    Write-Host "=== Proba uploadu (konto uslugowe) ===" -ForegroundColor Cyan
    python -m pip install -q -r requirements-drive.txt
    python scripts\gdrive_upload_wyniki.py --campaign-dir .
    if ($LASTEXITCODE -eq 0) {
        Write-Host "GOTOWE: https://drive.google.com/drive/folders/$DriveFolder" -ForegroundColor Green
        exit 0
    }
}

$desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "GU_Wyniki_Niemcy"
Remove-Item $desktop -Recurse -Force -EA SilentlyContinue
New-Item -ItemType Directory -Path "$desktop\Wyniki" -Force | Out-Null
Copy-Item "$Root\Wyniki\*" "$desktop\Wyniki\" -Force
if (Test-Path "$Root\wyslane") {
    Copy-Item "$Root\wyslane" "$desktop\wyslane" -Recurse -Force
}
Write-Host ""
Write-Host "API upload zablokowany (konto uslugowe nie ma quota na Moj dysk)." -ForegroundColor Yellow
Write-Host "Pliki gotowe na Pulpicie: $desktop" -ForegroundColor Green
Write-Host "Otwieram folder Drive - przeciagnij Wyniki + wyslane:" -ForegroundColor Cyan
Start-Process "https://drive.google.com/drive/folders/$DriveFolder"
Start-Process explorer.exe $desktop
Write-Host ""
Write-Host "Trwaly fix: utworz OAuth Desktop w NOWYM projekcie Google Cloud," -ForegroundColor Cyan
Write-Host "zapisz jako secrets\gdrive-oauth-client.json i uruchom:" -ForegroundColor Cyan
Write-Host "  python scripts\gdrive_oauth_setup.py" -ForegroundColor White
exit 2
