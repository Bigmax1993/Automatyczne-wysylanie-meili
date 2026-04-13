<#
  Jedno miejsce na klucze: skopiuj local_env.ps1.example -> local_env.ps1 i uzupelnij.
  (Nie uruchamiaj samego .\local_env.ps1 bez kropki - potrzebny jest plik; run_with_env laduje go sam.)

  Przyklady:
    .\run_with_env.ps1 -CheckOnly          # tylko test OpenAI (bez pipeline)
    .\run_with_env.ps1                     # caly pipeline (SerpAPI + czyszczenie + wysylka)
    .\run_with_env.ps1 -SkipBuild          # od kroku clean/validate/send (bez SerpAPI)
    .\run_with_env.ps1 -SkipBuild -DryRun  # jak wyzej, bez faktycznej wysylki SMTP
#>
param(
    [switch]$CheckOnly,
    [switch]$SkipBuild,
    [switch]$DryRun
)

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

if (-not (Test-Path $localEnvPath)) {
    Write-Host ""
    Write-Host "Brak pliku local_env.ps1." -ForegroundColor Yellow
    Write-Host "Wykonaj w katalogu projektu:" -ForegroundColor Yellow
    Write-Host '  Copy-Item -Path "local_env.ps1.example" -Destination "local_env.ps1"' -ForegroundColor Cyan
    Write-Host "Potem edytuj local_env.ps1 i wklej PELNE klucze (nie doslownie trzy kropki)." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

. $localEnvPath

# Uzupelnij puste zmienne wartosciami z profilu uzytkownika (np. po setx), jesli local_env ich nie ustawil.
foreach ($name in @("OPENAI_API_KEY", "SERPAPI_API_KEY", "GMAIL_APP_PASSWORD", "GMAIL_SENDER_EMAIL", "CV_PATH")) {
    $cur = [Environment]::GetEnvironmentVariable($name, "Process")
    if ([string]::IsNullOrWhiteSpace($cur)) {
        $userVal = [Environment]::GetEnvironmentVariable($name, "User")
        if (-not [string]::IsNullOrWhiteSpace($userVal)) {
            Set-Item -Path "env:$name" -Value $userVal.Trim()
        }
    }
}

# Jesli w local_env jest krotki / obciety OPENAI_API_KEY, a w profilu uzytkownika (setx) jest dluzszy — uzyj z profilu.
$openaiMinRealisticLen = 80
$procKey = if ([string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) { "" } else { $env:OPENAI_API_KEY.Trim() }
$rawUserKey = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "User")
$userKey = if ([string]::IsNullOrWhiteSpace($rawUserKey)) { "" } else { $rawUserKey.Trim() }
if ($procKey.Length -lt $openaiMinRealisticLen -and $userKey.Length -gt $procKey.Length) {
    Set-Item -Path "env:OPENAI_API_KEY" -Value $userKey
    Write-Host "OPENAI_API_KEY: zastapiono krotka wartosc z local_env kluczem z profilu uzytkownika (setx)." -ForegroundColor DarkYellow
}

function Normalize-GmailAppPassword([string]$s) {
    if ([string]::IsNullOrWhiteSpace($s)) { return "" }
    return ($s.Trim() -replace '\s+', '')
}

# GMAIL_APP_PASSWORD: bledna wartosc w local_env (np. zly skrot), poprawne 16 znakow w profilu User (setx)
$rawProcG = $env:GMAIL_APP_PASSWORD
$normProcG = Normalize-GmailAppPassword $rawProcG
$rawUserG = [Environment]::GetEnvironmentVariable("GMAIL_APP_PASSWORD", "User")
$normUserG = Normalize-GmailAppPassword $rawUserG
if ($normProcG.Length -ne 16 -and $normUserG.Length -eq 16) {
    Set-Item -Path "env:GMAIL_APP_PASSWORD" -Value $rawUserG.Trim()
    Write-Host "GMAIL_APP_PASSWORD: zastapiono wartoscia z profilu uzytkownika (haslo aplikacji, 16 znakow bez spacji)." -ForegroundColor DarkYellow
}

function Assert-OpenAiKey {
    $k = $env:OPENAI_API_KEY
    if ([string]::IsNullOrWhiteSpace($k)) {
        throw "OPENAI_API_KEY jest pusty. Ustaw w local_env.ps1 lub: setx OPENAI_API_KEY `"twoj_klucz`" (potem nowe okno PowerShell)."
    }
    if ($k.Trim() -eq "...") {
        throw "OPENAI_API_KEY to doslownie '...' - wklej prawdziwy klucz z panelu OpenAI (zaczyna sie od sk-)."
    }
    if ($k.Trim().Length -lt 40) {
        throw "OPENAI_API_KEY jest podejrzanie krotki ($($k.Trim().Length) znakow). Prawidlowy klucz ma zwykle 80+ znakow. Wklej caly klucz w local_env.ps1 lub: setx OPENAI_API_KEY `"...`" (nowe okno)."
    }
    if (-not $k.Trim().StartsWith("sk-")) {
        Write-Warning "OPENAI_API_KEY zwykle zaczyna sie od 'sk-'. Sprawdz wartosc w local_env.ps1."
    }
}

Assert-OpenAiKey

if (-not $SkipBuild -and -not $CheckOnly) {
    if ([string]::IsNullOrWhiteSpace($env:SERPAPI_API_KEY)) {
        Write-Warning (
            "SERPAPI_API_KEY jest pusty - pierwszy krok SerpAPI zostanie pominiety; " +
            "pipeline wezmie dane z Documents\Kontakty_serpapi.xlsx (jesli istnieje) lub z folderu kontakty."
        )
    }
}

if (-not $DryRun -and -not $CheckOnly) {
    if ([string]::IsNullOrWhiteSpace($env:GMAIL_APP_PASSWORD)) {
        throw "GMAIL_APP_PASSWORD jest pusty - potrzebny do wysylki. Uzupelnij local_env.ps1 lub: setx GMAIL_APP_PASSWORD `"haslo_aplikacji`" (nowe okno). Mozesz uzyc -DryRun."
    }
    $gNorm = Normalize-GmailAppPassword $env:GMAIL_APP_PASSWORD
    if ($gNorm.Length -ne 16) {
        throw (
            "GMAIL_APP_PASSWORD: po usunieciu spacji musi miec 16 znakow (haslo aplikacji Google). " +
            "Teraz: $($gNorm.Length) znakow. Wygeneruj nowe haslo aplikacji (2FA) i wklej do local_env.ps1 lub setx. " +
            "Adres nadawcy (GMAIL_SENDER_EMAIL) musi byc tym samym kontem Gmail."
        )
    }
}

Set-Location $projectDir

$versionPath = Join-Path $projectDir "VERSION"
if (Test-Path $versionPath) {
    $pv = (Get-Content -LiteralPath $versionPath -Raw).Trim()
    Write-Host "Pipeline wersja: $pv" -ForegroundColor DarkGray
}

if ($CheckOnly) {
    Write-Host "Test polaczenia z OpenAI..." -ForegroundColor Cyan
    $code = @'
import os
from openai import OpenAI
k = (os.environ.get("OPENAI_API_KEY") or "").strip()
OpenAI(api_key=k).models.list()
print("OpenAI OK")
'@
    & $pythonExe -c $code
    exit $LASTEXITCODE
}

$rp = Join-Path $projectDir "run_pipeline.ps1"
$rpArgs = @{}
if ($SkipBuild) { $rpArgs['SkipBuild'] = $true }
if ($DryRun) { $rpArgs['DryRun'] = $true }

& $rp @rpArgs
