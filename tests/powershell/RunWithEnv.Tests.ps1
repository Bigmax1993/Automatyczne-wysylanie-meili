# Testy Pester dla run_with_env.ps1 (opcjonalnie).
# Skladnia Pester 3.4+ / 5.
#
#   Invoke-Pester -Path .\tests\powershell\RunWithEnv.Tests.ps1

$__proj = $null
foreach ($__k in @("REPO_ROOT", "GITHUB_WORKSPACE")) {
    $__v = [Environment]::GetEnvironmentVariable($__k)
    if (-not [string]::IsNullOrWhiteSpace($__v)) {
        $__proj = $__v.Trim()
        break
    }
}
if ([string]::IsNullOrWhiteSpace($__proj)) {
    $__here = $PSScriptRoot
    if ([string]::IsNullOrWhiteSpace($__here)) {
        if ($MyInvocation.MyCommand.Path) {
            $__here = Split-Path -Parent $MyInvocation.MyCommand.Path
        } else {
            throw "Nie mozna ustalic katalogu projektu (ustaw REPO_ROOT / GITHUB_WORKSPACE albo uruchom z pliku .Tests.ps1)."
        }
    }
    $__proj = (Resolve-Path (Join-Path $__here "..\..")).Path
}
$script:RunWithEnvPath = Join-Path $__proj "run_with_env.ps1"

Describe "run_with_env.ps1" {

    It "istnieje" {
        Test-Path -LiteralPath $script:RunWithEnvPath | Should Be $true
    }

    It "parsuje sie bez bledow (Language.Parser)" {
        $tokens = $null
        $errors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile(
            $script:RunWithEnvPath,
            [ref]$tokens,
            [ref]$errors
        )
        if ($null -ne $errors -and $errors.Count -gt 0) {
            $errors | ForEach-Object { $_.ToString() } | Write-Host
        }
        ($null -eq $errors -or $errors.Count -eq 0) | Should Be $true
    }

    It "laczy zmienne z profilu User" {
        $raw = Get-Content -LiteralPath $script:RunWithEnvPath -Raw
        $raw | Should Match 'GetEnvironmentVariable'
        $raw | Should Match 'GMAIL_APP_PASSWORD'
        $raw | Should Match 'Normalize-GmailAppPassword'
    }

    It "ma Assert-OpenAiKey i prog Gmail 16 znakow" {
        $raw = Get-Content -LiteralPath $script:RunWithEnvPath -Raw
        $raw | Should Match 'Assert-OpenAiKey'
        $raw | Should Match '16'
    }
}
