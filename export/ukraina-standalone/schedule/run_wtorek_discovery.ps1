# WTOREK — discovery czesc 2 (UA).
. "$PSScriptRoot\_common.ps1"
Enter-UaCampaign
$env:SCRAPER_TIMEZONE = "Europe/Warsaw"
Write-Host "[UA WT] Discovery czesc 2 (--respect-cache)"
python ua_materialy_scraper.py --run-config run_config\ua_materialy.json --serper-only-discovery --no-auto-email --rotate-oblast --respect-cache @args
