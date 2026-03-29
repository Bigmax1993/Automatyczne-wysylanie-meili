param(
    [switch]$SkipBuild,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = "C:\Users\svinc\AppData\Local\Programs\Python\Python313\python.exe"
if ($env:PIPELINE_PYTHON_EXE -and $env:PIPELINE_PYTHON_EXE.Trim()) {
    $pythonExe = $env:PIPELINE_PYTHON_EXE.Trim()
}
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

if (-not (Test-Path $pythonExe)) {
    throw "Nie znaleziono interpretera Python: $pythonExe"
}

$logsDir = Join-Path $docsDir "pipeline_logs"
if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir | Out-Null
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logsDir "pipeline_$stamp.log"

"[$(Get-Date -Format s)] Start pipeline wersja=$pipelineVersion (SkipBuild=$SkipBuild DryRun=$DryRun)" | Out-File -FilePath $logPath -Encoding utf8

$buildExit = 0
if (-not $SkipBuild) {
    # Jeden pelny przebieg SerpAPI na dzien (plik stanu w Documents\kontakty); przy braku API / limicie kod 2.
    $env:SERPAPI_DAILY_LIMIT_ENABLED = "1"
    $serpArgs = @(
        "build_contacts_serpapi.py",
        "--firm-target", "1000",
        "--agency-target", "1000",
        "--ecommerce-target", "1000",
        "--cities", "Wroclaw,Zielona Gora,Poznan",
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
