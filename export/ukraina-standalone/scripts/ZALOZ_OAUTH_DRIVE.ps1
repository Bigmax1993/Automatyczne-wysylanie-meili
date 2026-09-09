#Requires -Version 5.1
<#
Jednorazowy setup OAuth Google Drive (upload na folder "Moj dysk" z GitHub Actions).
Uruchom z katalogu repo:  powershell -ExecutionPolicy Bypass -File scripts\ZALOZ_OAUTH_DRIVE.ps1
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root
$Secrets = Join-Path $Root "secrets"
$ClientPath = Join-Path $Secrets "gdrive-oauth-client.json"
New-Item -ItemType Directory -Force -Path $Secrets | Out-Null

Write-Host "=== OAuth Drive - setup (repo: $Root) ===" -ForegroundColor Cyan

# 1) Szukaj OAuth client JSON w Pobranych (NIE plik service_account)
$dl = Join-Path $env:USERPROFILE "Downloads"
$oauthJson = Get-ChildItem $dl -Filter "*.json" -EA SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    ForEach-Object {
        try {
            $j = Get-Content $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($j.PSObject.Properties.Name -contains "installed") { return $_ }
            if ($j.installed.client_id) { return $_ }
        } catch {}
    } | Select-Object -First 1

if (-not $oauthJson -and -not (Test-Path $ClientPath)) {
    Write-Host ""
    Write-Host "BRAK pliku OAuth Desktop JSON." -ForegroundColor Yellow
    Write-Host "Otwieram Google Cloud (Dane logowania)..." -ForegroundColor Yellow
    Write-Host "  1. Zaloguj sie na WLASCIWE konto Google (wlasciciel projektu)"
    Write-Host "  2. + Utworz dane logowania -> Identyfikator klienta OAuth"
    Write-Host "  3. Typ: Aplikacja na komputerze (Desktop)"
    Write-Host "  4. Pobierz JSON -> zapisz jako:"
    Write-Host "     $ClientPath" -ForegroundColor Green
    Start-Process "https://console.cloud.google.com/apis/credentials?project=wszelka-meili-do-partnerow"
    Start-Process "https://console.cloud.google.com/iam-admin/iam?project=wszelka-meili-do-partnerow"
    Write-Host ""
    Write-Host "Czekam 5 min na plik (Downloads lub $ClientPath)..." -ForegroundColor Yellow
    $deadline = (Get-Date).AddMinutes(5)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path $ClientPath) { break }
        $oauthJson = Get-ChildItem $dl -Filter "client_secret*.json" -EA SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($oauthJson) {
            Copy-Item $oauthJson.FullName $ClientPath -Force
            Write-Host "Skopiowano: $($oauthJson.Name)" -ForegroundColor Green
            break
        }
        Start-Sleep -Seconds 4
    }
}

if (Test-Path $ClientPath) {
    Write-Host "OAuth client: $ClientPath" -ForegroundColor Green
} elseif ($oauthJson) {
    Copy-Item $oauthJson.FullName $ClientPath -Force
    Write-Host "Skopiowano OAuth client z $($oauthJson.FullName)" -ForegroundColor Green
} else {
    Write-Host "Timeout - zapisz JSON jako $ClientPath i uruchom ponownie." -ForegroundColor Red
    exit 1
}

Write-Host "Instalacja pakietow..." -ForegroundColor Cyan
python -m pip install -q -r requirements-drive.txt

Write-Host "Logowanie Google (otworzy sie przegladarka)..." -ForegroundColor Cyan
python scripts\gdrive_oauth_setup.py --client-json $ClientPath --repo Bigmax1993/wyszukiwarka-materialow-budowlanych-ukraina

if ($LASTEXITCODE -ne 0) {
    Write-Host "Setup OAuth nie powiodl sie (kod $LASTEXITCODE)." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "GOTOWE. Sprawdz: https://github.com/Bigmax1993/wyszukiwarka-materialow-budowlanych-ukraina/actions" -ForegroundColor Green
