#Requires -Version 5.1
<#
.SYNOPSIS
  Konfiguracja GDRIVE_SERVICE_ACCOUNT_JSON (GitHub secret + test upload).

.PARAMETER JsonPath
  Sciezka do pobranego klucza JSON konta uslugowego Google.

.PARAMETER WaitSeconds
  Czekaj na plik w secrets\gdrive-service-account.json (domyslnie 0 = bez czekania).

.PARAMETER OpenBrowser
  Otworz strony Google Cloud i Drive (domyslnie: true przy braku pliku).
#>
param(
    [string]$JsonPath = "",
    [int]$WaitSeconds = 0,
    [switch]$OpenBrowser,
    [string]$Repo = "Bigmax1993/Wyszukiwarka-partnerow",
    [string]$DriveFolderId = "1tP8oUi72t4EHDbE9GnHFdvfNtNsJe4xf",
    [string]$SlidesId = "1kBnp5x0pdgXZSPzVte9e92IUgn2A5gSe"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$SecretsDir = Join-Path $Root "secrets"
$DefaultJson = Join-Path $SecretsDir "gdrive-service-account.json"
New-Item -ItemType Directory -Force -Path $SecretsDir | Out-Null

function Test-ServiceAccountJson([string]$Path) {
    if (-not (Test-Path $Path)) { return $null }
    try {
        $j = Get-Content $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        throw "Niepoprawny JSON: $Path"
    }
    if ($j.type -ne "service_account" -or -not $j.client_email) {
        throw "To nie jest klucz konta uslugowego (brak type=service_account / client_email): $Path"
    }
    return $j
}

function Find-DownloadedKey {
    $dl = Join-Path $env:USERPROFILE "Downloads"
    Get-ChildItem $dl -Filter "*.json" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        ForEach-Object {
            try {
                $j = Get-Content $_.FullName -Raw | ConvertFrom-Json
                if ($j.type -eq "service_account" -and $j.client_email) { return $_.FullName }
            } catch { }
        }
    return $null
}

if (-not $JsonPath) {
    if (Test-Path $DefaultJson) { $JsonPath = $DefaultJson }
    else { $JsonPath = Find-DownloadedKey }
}

if (-not $JsonPath -and $WaitSeconds -gt 0) {
    Write-Host "Czekam do $WaitSeconds s na: $DefaultJson"
    Write-Host "Albo pobierz klucz JSON z Google Cloud do folderu Pobrane."
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path $DefaultJson) { $JsonPath = $DefaultJson; break }
        $found = Find-DownloadedKey
        if ($found) {
            Copy-Item $found $DefaultJson -Force
            $JsonPath = $DefaultJson
            Write-Host "Skopiowano z Pobrane: $found"
            break
        }
        Start-Sleep -Seconds 3
    }
}

if (-not $JsonPath) {
    if ($OpenBrowser) {
        Write-Host "Otwieram Google Cloud (Drive API + konta uslugowe)..."
        Start-Process "https://console.cloud.google.com/apis/library/drive.googleapis.com"
        Start-Sleep -Seconds 2
        Start-Process "https://console.cloud.google.com/iam-admin/serviceaccounts"
    }
    Write-Host ""
    Write-Host "=== JEDYNY KROK RECZNY (Google) ==="
    Write-Host "1. Wlacz Google Drive API"
    Write-Host "2. IAM -> Service Accounts -> Create -> Keys -> Add key -> JSON"
    Write-Host "3. Zapisz plik jako:"
    Write-Host "   $DefaultJson"
    Write-Host "4. Uruchom ponownie:"
    Write-Host "   .\scripts\setup_gdrive_github_secret.ps1"
    Write-Host ""
    exit 2
}

$info = Test-ServiceAccountJson $JsonPath
$email = $info.client_email
Write-Host "Konto uslugowe: $email"

Write-Host ""
Write-Host "=== Udostepnij w Google Drive (Edytor) ==="
Write-Host "Folder wynikow:"
Start-Process "https://drive.google.com/drive/folders/$DriveFolderId"
Write-Host "Prezentacja Slides (Przegladajacy):"
Start-Process "https://docs.google.com/presentation/d/$SlidesId/edit"
Write-Host "Wklej e-mail: $email"
Write-Host ""

Write-Host "Ustawiam secret GitHub: GDRIVE_SERVICE_ACCOUNT_JSON ..."
$jsonRaw = Get-Content $JsonPath -Raw -Encoding UTF8
$jsonRaw | gh secret set GDRIVE_SERVICE_ACCOUNT_JSON -R $Repo
Write-Host "OK: secret zapisany w $Repo"

Write-Host ""
Write-Host "Test lokalny upload (jesli folder Wyniki istnieje)..."
$env:GDRIVE_SERVICE_ACCOUNT_FILE = $JsonPath
$env:KANBUD_PROJECT_ROOT = Join-Path $Root "libs"
Push-Location $Root
try {
    pip install -q -r requirements.txt -r requirements-drive.txt 2>$null
    python scripts/gdrive_upload_wyniki.py --campaign-dir . 2>&1
} catch {
    Write-Warning "Upload test: $_ (udostepnij folder kontu uslugowemu i sprobuj ponownie)"
}
Pop-Location

Write-Host ""
Write-Host "Uruchamiam workflow Sync wyniki Google Drive..."
gh workflow run "Sync wyniki Google Drive" -R $Repo
Write-Host "Gotowe. Sprawdz: https://github.com/$Repo/actions"
