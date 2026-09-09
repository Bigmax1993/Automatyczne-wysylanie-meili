# Rejestracja zadan Harmonogramu Windows — kampania UA (jak DE GU).
param([switch]$Unregister)

$ScheduleDir = $PSScriptRoot
$Pwsh = (Get-Command powershell.exe).Source

function Register-WeekdayTask {
    param([string]$Name, [string]$Script, [string]$Weekday, [string]$Time)
    $action = New-ScheduledTaskAction -Execute $Pwsh -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Script`""
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Weekday -At $Time
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "OK: $Name -> $Weekday $Time"
}

$tasks = @(
    @{ Name = "Kanbud_UA_Poniedzialek_Discovery"; Script = Join-Path $ScheduleDir "run_poniedzialek_discovery.ps1"; Day = "Monday"; Time = "17:00" }
    @{ Name = "Kanbud_UA_Wtorek_Discovery"; Script = Join-Path $ScheduleDir "run_wtorek_discovery.ps1"; Day = "Tuesday"; Time = "15:00" }
    @{ Name = "Kanbud_UA_Sroda_Discovery"; Script = Join-Path $ScheduleDir "run_sroda_discovery.ps1"; Day = "Wednesday"; Time = "19:00" }
    @{ Name = "Kanbud_UA_Czwartek_Discovery"; Script = Join-Path $ScheduleDir "run_czwartek_discovery.ps1"; Day = "Thursday"; Time = "20:00" }
    @{ Name = "Kanbud_UA_Piatek_Discovery"; Script = Join-Path $ScheduleDir "run_piatek_discovery.ps1"; Day = "Friday"; Time = "16:00" }
    @{ Name = "Kanbud_UA_Niedziela_Backfill"; Script = Join-Path $ScheduleDir "run_niedziela_backfill.ps1"; Day = "Sunday"; Time = "06:00" }
    @{ Name = "Kanbud_UA_Poniedzialek_Prep"; Script = Join-Path $ScheduleDir "run_poniedzialek_prep.ps1"; Day = "Monday"; Time = "07:00" }
    @{ Name = "Kanbud_UA_Poniedzialek_Send"; Script = Join-Path $ScheduleDir "run_poniedzialek_send.ps1"; Day = "Monday"; Time = "09:00" }
    @{ Name = "Kanbud_UA_Wtorek_Send"; Script = Join-Path $ScheduleDir "run_wtorek_send.ps1"; Day = "Tuesday"; Time = "09:00" }
)

if ($Unregister) {
    foreach ($t in $tasks) {
        Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false -ErrorAction SilentlyContinue
        Write-Host "Usunieto: $($t.Name)"
    }
    exit 0
}

foreach ($t in $tasks) { Register-WeekdayTask @t }
Write-Host "Gotowe. Sprawdz taskschd.msc (Kanbud_UA_*)"
