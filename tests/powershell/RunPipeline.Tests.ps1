# Testy Pester dla run_pipeline.ps1 (opcjonalnie).
# Skladnia zgodna z Pester 3.4+ (Windows) oraz Pester 5.
#
# Uruchomienie z katalogu projektu:
#   Invoke-Pester -Path .\tests\powershell\RunPipeline.Tests.ps1
#
# Jesli masz tylko Pester 3 z Program Files, powyzsze zadziala.
# Pester 5 (CurrentUser, nowsza skladnia): Install-Module Pester -MinimumVersion 5.0 -Scope CurrentUser -Force

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RunPipelinePath = Join-Path $ProjectRoot "run_pipeline.ps1"

Describe "run_pipeline.ps1" {
    It "istnieje" {
        Test-Path -LiteralPath $RunPipelinePath | Should Be $true
    }

    It "parsuje sie bez bledow (Language.Parser)" {
        $tokens = $null
        $errors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile(
            $RunPipelinePath,
            [ref]$tokens,
            [ref]$errors
        )
        if ($null -ne $errors -and $errors.Count -gt 0) {
            $errors | ForEach-Object { $_.ToString() } | Write-Host
        }
        ($null -eq $errors -or $errors.Count -eq 0) | Should Be $true
    }

    It "ustawia projectDir przez MyInvocation" {
        $raw = Get-Content -LiteralPath $RunPipelinePath -Raw
        $raw | Should Match 'Split-Path\s+-Parent\s+\$MyInvocation\.MyCommand\.Path'
    }

    It "ma PIPELINE_PYTHON_EXE" {
        $raw = Get-Content -LiteralPath $RunPipelinePath -Raw
        $raw | Should Match 'PIPELINE_PYTHON_EXE'
    }

    It "ma Continue + finally przy wywolaniu clean_validate" {
        $raw = Get-Content -LiteralPath $RunPipelinePath -Raw
        $raw | Should Match 'clean_validate_send_pipeline\.py'
        $raw | Should Match '\$ErrorActionPreference\s*=\s*"Continue"'
        $raw | Should Match '\$prevEap'
    }
}
