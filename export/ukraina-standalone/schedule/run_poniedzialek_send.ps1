# PONIEDZIALEK — wysylka partia 1 (UA).
. "$PSScriptRoot\_common.ps1"
Enter-UaCampaign
$env:SCRAPER_TIMEZONE = "Europe/Warsaw"
Write-Host "[UA PON] Wysylka partia 1"
python ua_materialy_scraper.py --run-config run_config\ua_materialy.json --send-emails-only @args
