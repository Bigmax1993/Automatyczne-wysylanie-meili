<#
  Orkiestrator pipeline uruchamiany z PowerShell:
  1) opcjonalne budowanie leadów przez SerpAPI,
  2) clean/validate/send w Pythonie,
  3) logowanie całego przebiegu do pliku.
#>

param(
    [switch]$SkipBuild,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Katalog projektu i interpreter Pythona (PIPELINE_PYTHON_EXE lub pierwszy python z PATH).
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = if ($env:PIPELINE_PYTHON_EXE -and $env:PIPELINE_PYTHON_EXE.Trim()) {
    $env:PIPELINE_PYTHON_EXE.Trim()
} else {
    "python"
}
try {
    $pythonExe = (Get-Command -Name $pythonExe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
} catch {
    throw "Nie znaleziono interpretera Python: ustaw PIPELINE_PYTHON_EXE albo dodaj python.exe do PATH."
}
# Standardowe ścieżki danych wej./wyj.
$docsDir = Join-Path $env:USERPROFILE "Documents"
$outputXlsx = Join-Path $docsDir "Kontakty_serpapi.xlsx"
$outputCsv = Join-Path $docsDir "Kontakty_cleaned.csv"

$kontaktyDir = if ($env:EXTRA_CONTACTS_DIR -and $env:EXTRA_CONTACTS_DIR.Trim()) {
    $env:EXTRA_CONTACTS_DIR.Trim()
} else {
    Join-Path $env:USERPROFILE "Documents\kontakty"
}

Set-Location $projectDir

$versionPath = Join-Path $projectDir "VERSION"
$pipelineVersion = "unknown"
if (Test-Path $versionPath) {
    $pipelineVersion = (Get-Content -LiteralPath $versionPath -Raw).Trim()
}

$logsDir = Join-Path $docsDir "pipeline_logs"
if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir | Out-Null
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logsDir "pipeline_$stamp.log"

"[$(Get-Date -Format s)] Start pipeline wersja=$pipelineVersion (SkipBuild=$SkipBuild DryRun=$DryRun)" | Out-File -FilePath $logPath -Encoding utf8

# Na runnerze CI często nie ma sekretu SMTP; automatycznie przełącz na DryRun, zamiast kończyć błędem.
if (-not $DryRun) {
    $gmailRaw = if ($env:GMAIL_APP_PASSWORD) { $env:GMAIL_APP_PASSWORD } else { "" }
    $gmailNorm = ($gmailRaw -replace '\s+', '').Trim()
    if ([string]::IsNullOrWhiteSpace($gmailNorm) -or $gmailNorm.Length -ne 16) {
        $DryRun = $true
        "[$(Get-Date -Format s)] Brak poprawnego GMAIL_APP_PASSWORD (16 znakow) - wymuszam DryRun." | Out-File -FilePath $logPath -Append -Encoding utf8
        Write-Host "[pipeline] Brak poprawnego GMAIL_APP_PASSWORD - wymuszam DryRun." -ForegroundColor Yellow
    }
}

$buildExit = 0
# Etap 1: budowanie kontaktów (może być pominięte przez -SkipBuild).
if (-not $SkipBuild) {
    # Jeden pelny przebieg SerpAPI na dzien (plik stanu w Documents\kontakty); przy braku API / limicie kod 2.
    $env:SERPAPI_DAILY_LIMIT_ENABLED = "1"
    $serpArgs = @(
        "build_contacts_serpapi.py",
        "--firm-target", "1000",
        "--agency-target", "1000",
        "--ecommerce-target", "1000",
        "--cities", "Bialystok,Bydgoszcz,Gdansk,Gorzow Wielkopolski,Katowice,Kielce,Krakow,Lublin,Lodz,Olsztyn,Opole,Poznan,Rzeszow,Szczecin,Torun,Warszawa,Wroclaw,Zielona Gora",
        "--max-requests-per-group", "800",
        "--pages-per-query", "6",
        "--num-per-request", "20",
        "--enrich-email",
        "--output", $outputXlsx
    )
    # Przy $ErrorActionPreference=Stop stderr z Pythona konczy skrypt zanim zbierzemy output — na czas wywolania Continue.
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $buildOut = & $pythonExe @serpArgs 2>&1
        $buildExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEap
    }
    $buildOut = @($buildOut | ForEach-Object { "$_" })
    $buildOut | Out-File -FilePath $logPath -Append -Encoding utf8
    if ($buildExit -eq 2) {
        "[$(Get-Date -Format s)] SerpAPI pominiety (limit dzienny lub brak klucza/biblioteki) kod=2" | Out-File -FilePath $logPath -Append -Encoding utf8
        Write-Host "[pipeline] SerpAPI pominiety — uzywam istniejacego pliku lub folderu kontakty." -ForegroundColor DarkYellow
    } elseif ($buildExit -ne 0) {
        "[$(Get-Date -Format s)] SerpAPI blad kod=$buildExit" | Out-File -FilePath $logPath -Append -Encoding utf8
        Write-Host "[pipeline] SerpAPI zwrocil blad ($buildExit) — jesli brak pliku wyjsciowego, uzyje folderu kontakty." -ForegroundColor Yellow
    }
}

# Etap 2: wybór wejścia dla clean/validate/send.
$inputForClean = $outputXlsx
if (-not (Test-Path -LiteralPath $inputForClean)) {
    if (Test-Path -LiteralPath $kontaktyDir) {
        $latest = Get-ChildItem -LiteralPath $kontaktyDir -File -ErrorAction SilentlyContinue |
            Where-Object {
                $ext = $_.Extension.ToLowerInvariant()
                ($ext -eq ".xlsx") -or ($ext -eq ".xls") -or ($ext -eq ".csv")
            } |
            Sort-Object LastWriteTime |
            Select-Object -Last 1
        if ($null -ne $latest) {
            $inputForClean = $latest.FullName
        }
    }
}

if (-not (Test-Path -LiteralPath $inputForClean)) {
    throw "Brak pliku wejsciowego: nie znaleziono $($outputXlsx) ani zadnego .xlsx/.xls/.csv w katalogu: $kontaktyDir"
}

"[$(Get-Date -Format s)] clean_validate_send_pipeline --input $inputForClean" | Out-File -FilePath $logPath -Append -Encoding utf8
Write-Host "[pipeline] Wejscie: $inputForClean" -ForegroundColor Cyan
Write-Host "[pipeline] W tym samym przebiegu Python przetworzy tez pozostale pliki .xlsx/.xls/.csv z folderu:" -ForegroundColor DarkCyan
Write-Host "         $kontaktyDir" -ForegroundColor DarkCyan
Write-Host "         (pomija tylko plik, ktory jest glownym wejsciem, jesli lezy w tym folderze)." -ForegroundColor DarkCyan

# Etap 3: uruchomienie głównego pipeline Python.
$cleanArgs = @(
    "clean_validate_send_pipeline.py",
    "--input", $inputForClean,
    "--output-csv", $outputCsv,
    "--extra-contacts-dir", $kontaktyDir
)
if ($DryRun) {
    $cleanArgs += "--dry-run"
}

$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    $cleanOut = & $pythonExe @cleanArgs 2>&1
    $cleanExit = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $prevEap
}
$cleanOut = @($cleanOut | ForEach-Object { "$_" })
$cleanOut | Out-File -FilePath $logPath -Append -Encoding utf8
if ($cleanExit -ne 0) {
    Write-Host ""
    Write-Host "--- Python (pelny komunikat ponizej) ---" -ForegroundColor Yellow
    foreach ($line in $cleanOut) {
        Write-Host $line
    }
    Write-Host "--- Koniec outputu Pythona ---" -ForegroundColor Yellow
    Write-Host ""
    throw "clean_validate_send_pipeline zakonczyl sie kodem $cleanExit (log: $logPath)"
}

"[$(Get-Date -Format s)] Koniec pipeline" | Out-File -FilePath $logPath -Append -Encoding utf8
