<#
  Tylko etap clean_validate_send_pipeline (bez SerpAPI / bez build_contacts_serpapi).

  Przykłady:
    .\run_clean_only.ps1 -ValidateOnly
    .\run_clean_only.ps1 -ValidateOnly -Input "C:\sciezka\plik.xlsx"
    .\run_clean_only.ps1 -SkipClean -DryRun
    .\run_clean_only.ps1 -SkipClean -DryRun -SkipExtra
#>

param(
    [string]$Input = "",
    [switch]$ValidateOnly,
    [switch]$DryRun,
    [switch]$SkipClean,
    [switch]$SkipExtra
)

$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = "C:\Users\svinc\AppData\Local\Programs\Python\Python313\python.exe"
if ($env:PIPELINE_PYTHON_EXE -and $env:PIPELINE_PYTHON_EXE.Trim()) {
    $pythonExe = $env:PIPELINE_PYTHON_EXE.Trim()
}
if (-not (Test-Path -LiteralPath $pythonExe)) {
    $pythonExe = "python"
}

Set-Location $projectDir

$docsDir = Join-Path $env:USERPROFILE "Documents"
$defaultSerp = Join-Path $docsDir "Kontakty_serpapi.xlsx"
$kontaktyDir = if ($env:EXTRA_CONTACTS_DIR -and $env:EXTRA_CONTACTS_DIR.Trim()) {
    $env:EXTRA_CONTACTS_DIR.Trim()
} else {
    Join-Path $env:USERPROFILE "Documents\kontakty"
}

function Resolve-InputPath {
    if ($Input -and $Input.Trim()) {
        $p = $Input.Trim()
        if (-not (Test-Path -LiteralPath $p)) {
            throw "Brak pliku wejściowego: $p"
        }
        return (Resolve-Path -LiteralPath $p).Path
    }
    if (Test-Path -LiteralPath $defaultSerp) {
        return $defaultSerp
    }
    if (Test-Path -LiteralPath $kontaktyDir) {
        $latest = Get-ChildItem -LiteralPath $kontaktyDir -File -ErrorAction SilentlyContinue |
            Where-Object {
                $ext = $_.Extension.ToLowerInvariant()
                ($ext -eq ".xlsx") -or ($ext -eq ".xls") -or ($ext -eq ".csv")
            } |
            Sort-Object LastWriteTime |
            Select-Object -Last 1
        if ($null -ne $latest) {
            return $latest.FullName
        }
    }
    throw "Brak pliku wejściowego: podaj -Input lub umieść Kontakty_serpapi.xlsx w Documents albo plik .xlsx/.csv w: $kontaktyDir"
}

$inPath = Resolve-InputPath

if ($ValidateOnly) {
    $pyArgs = @(
        "clean_validate_send_pipeline.py",
        "--input", $inPath,
        "--validate-only"
    )
} else {
    $outCsv = Join-Path $docsDir "Kontakty_cleaned.csv"
    $pyArgs = @(
        "clean_validate_send_pipeline.py",
        "--input", $inPath,
        "--output-csv", $outCsv
    )
    if ($SkipClean) {
        $pyArgs += "--skip-clean"
    }
    if ($DryRun) {
        $pyArgs += "--dry-run"
    }
    if ($SkipExtra) {
        $pyArgs += "--skip-extra-contacts"
    }
}

Write-Host "[run_clean_only] Wejście: $inPath" -ForegroundColor Cyan
& $pythonExe @pyArgs
exit $LASTEXITCODE
