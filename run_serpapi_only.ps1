<#
  Uruchamia wyłącznie etap budowania leadów SerpAPI (bez clean/send).
  Przeznaczone do harmonogramu tygodniowego, np. niedziela 21:00.
#>
param()

$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$localEnvPath = Join-Path $projectDir "local_env.ps1"
$pythonExe = "C:\Users\svinc\AppData\Local\Programs\Python\Python313\python.exe"
if ($env:PIPELINE_PYTHON_EXE -and $env:PIPELINE_PYTHON_EXE.Trim()) {
    $pythonExe = $env:PIPELINE_PYTHON_EXE.Trim()
} elseif (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
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
    "--cities" "Wroclaw,Zielona Gora,Poznan" `
    "--max-requests-per-group" "800" `
    "--pages-per-query" "6" `
    "--num-per-request" "20" `
    "--enrich-email" `
    "--output" $outputXlsx

exit $LASTEXITCODE
