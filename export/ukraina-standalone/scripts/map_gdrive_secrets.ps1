#Requires -Version 5.1
<#
Mapuje JSON z Pobranych do secrets/ (lokalnie, NIE w git).

  secrets/gdrive-service-account.json  — konto uslugowe (type=service_account)
  secrets/gdrive-oauth-client.json     — OAuth Desktop (sekcja installed)

Uruchom: powershell -ExecutionPolicy Bypass -File scripts\map_gdrive_secrets.ps1
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Secrets = Join-Path $Root "secrets"
New-Item -ItemType Directory -Force -Path $Secrets | Out-Null

$dl = @(
    (Join-Path $env:USERPROFILE "Downloads"),
    (Join-Path $env:USERPROFILE "Pobrane")
) | Where-Object { Test-Path $_ } | Select-Object -Unique

function Read-JsonFile($path) {
    Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Find-JsonByPredicate($predicate) {
    foreach ($dir in $dl) {
        Get-ChildItem $dir -Filter "*.json" -EA SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            ForEach-Object {
                try {
                    $j = Read-JsonFile $_.FullName
                    if (& $predicate $j) { return $_ }
                } catch { }
            }
    }
    return $null
}

$saDest = Join-Path $Secrets "gdrive-service-account.json"
$oauthDest = Join-Path $Secrets "gdrive-oauth-client.json"

$saSrc = Find-JsonByPredicate { param($j) $j.type -eq "service_account" -and $j.client_email }
if ($saSrc) {
    Copy-Item $saSrc.FullName $saDest -Force
    Write-Host "OK: konto uslugowe -> $saDest" -ForegroundColor Green
    $saMeta = Read-JsonFile $saSrc.FullName
    Write-Host "     $($saSrc.Name) ($($saMeta.client_email))" -ForegroundColor DarkGray
} elseif (Test-Path $saDest) {
    Write-Host "OK: juz jest $saDest" -ForegroundColor Green
} else {
    Write-Host "BRAK: JSON konta uslugowego (type=service_account) w Pobranych" -ForegroundColor Yellow
}

function Test-OAuthDesktopJson($j) {
    if ($j.PSObject.Properties.Name -contains "installed") { return $true }
    return $null -ne $j.installed -and $null -ne $j.installed.client_id
}
$oauthSrc = Find-JsonByPredicate { param($j) Test-OAuthDesktopJson $j }
if ($oauthSrc) {
    Copy-Item $oauthSrc.FullName $oauthDest -Force
    Write-Host "OK: OAuth Desktop -> $oauthDest" -ForegroundColor Green
    Write-Host "     $($oauthSrc.Name)" -ForegroundColor DarkGray
} elseif (Test-Path $oauthDest) {
    Write-Host "OK: juz jest $oauthDest" -ForegroundColor Green
} else {
    Write-Host "BRAK: OAuth Desktop (client_secret / installed) - utworz w Google Cloud" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Folder secrets/ jest w .gitignore - NIE commituj tych plikow do repo." -ForegroundColor Cyan
Write-Host "Lokalnie ustaw w .env:" -ForegroundColor Cyan
Write-Host "  GDRIVE_SERVICE_ACCOUNT_FILE=secrets/gdrive-service-account.json"
