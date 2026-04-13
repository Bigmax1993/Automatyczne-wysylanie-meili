<#
  Uruchamia wyłącznie etap budowania leadów SerpAPI (bez clean/send).
  Przeznaczone do harmonogramu tygodniowego, np. niedziela 21:00.
#>
param()

$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$localEnvPath = Join-Path $projectDir "local_env.ps1"
$pythonExe = if ($env:PIPELINE_PYTHON_EXE -and $env:PIPELINE_PYTHON_EXE.Trim()) {
    $env:PIPELINE_PYTHON_EXE.Trim()
} else {
    "python"
}
try {
    $pythonExe = (Get-Command -Name $pythonExe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
} catch {
    Write-Host "Nie znaleziono interpretera Python: ustaw PIPELINE_PYTHON_EXE albo dodaj python.exe do PATH." -ForegroundColor Red
    exit 1
}

if (Test-Path $localEnvPath) {
    . $localEnvPath
}

# Uzupełnij brakujący klucz z profilu użytkownika (setx), jeśli nie ma go w tej sesji.
if ([string]::IsNullOrWhiteSpace($env:SERPAPI_API_KEY)) {
    $userVal = [Environment]::GetEnvironmentVariable("SERPAPI_API_KEY", "User")
    if (-not [string]::IsNullOrWhiteSpace($userVal)) {
        Set-Item -Path "env:SERPAPI_API_KEY" -Value $userVal.Trim()
    }
}

if ([string]::IsNullOrWhiteSpace($env:SERPAPI_API_KEY)) {
    throw "SERPAPI_API_KEY jest pusty (local_env.ps1 lub setx)."
}

$docsDir = Join-Path $env:USERPROFILE "Documents"
$outputXlsx = Join-Path $docsDir "Kontakty_serpapi.xlsx"

Set-Location $projectDir
$env:SERPAPI_DAILY_LIMIT_ENABLED = "1"

& $pythonExe `
    "build_contacts_serpapi.py" `
    "--firm-target" "1000" `
    "--agency-target" "1000" `
    "--ecommerce-target" "1000" `
    "--cities" "Bialystok,Bydgoszcz,Gdansk,Gorzow Wielkopolski,Katowice,Kielce,Krakow,Lublin,Lodz,Olsztyn,Opole,Poznan,Rzeszow,Szczecin,Torun,Warszawa,Wroclaw,Zielona Gora" `
    "--max-requests-per-group" "800" `
    "--pages-per-query" "6" `
    "--num-per-request" "20" `
    "--enrich-email" `
    "--output" $outputXlsx

exit $LASTEXITCODE
