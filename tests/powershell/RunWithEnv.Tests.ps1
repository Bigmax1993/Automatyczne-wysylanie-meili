# Testy Pester dla run_with_env.ps1 (opcjonalnie).
# Skladnia Pester 3.4+ / 5.
#
#   Invoke-Pester -Path .\tests\powershell\RunWithEnv.Tests.ps1

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RunWithEnvPath = Join-Path $ProjectRoot "run_with_env.ps1"

Describe "run_with_env.ps1" {
    It "istnieje" {
        Test-Path -LiteralPath $RunWithEnvPath | Should Be $true
    }

    It "parsuje sie bez bledow (Language.Parser)" {
        $tokens = $null
        $errors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile(
            $RunWithEnvPath,
            [ref]$tokens,
            [ref]$errors
        )
        if ($null -ne $errors -and $errors.Count -gt 0) {
            $errors | ForEach-Object { $_.ToString() } | Write-Host
        }
        ($null -eq $errors -or $errors.Count -eq 0) | Should Be $true
    }

    It "laczy zmienne z profilu User" {
        $raw = Get-Content -LiteralPath $RunWithEnvPath -Raw
        $raw | Should Match 'GetEnvironmentVariable'
        $raw | Should Match 'GMAIL_APP_PASSWORD'
        $raw | Should Match 'Normalize-GmailAppPassword'
    }

    It "ma Assert-OpenAiKey i prog Gmail 16 znakow" {
        $raw = Get-Content -LiteralPath $RunWithEnvPath -Raw
        $raw | Should Match 'Assert-OpenAiKey'
        $raw | Should Match '16'
    }
}
