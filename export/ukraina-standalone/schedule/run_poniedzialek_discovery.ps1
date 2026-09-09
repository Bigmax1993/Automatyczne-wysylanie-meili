# PONIEDZIALEK — discovery czesc 1 (UA), bez wysylki.
. "$PSScriptRoot\_common.ps1"
Enter-UaCampaign
$env:SCRAPER_TIMEZONE = "Europe/Warsaw"
Remove-Item Env:DISABLE_SEND_WINDOW -ErrorAction SilentlyContinue
Write-Host "[UA PON] Discovery czesc 1 (serper-only)"
python ua_materialy_scraper.py --run-config run_config\ua_materialy.json --serper-only-discovery --no-auto-email --rotate-oblast @args
