# PONIEDZIALEK — prep (UA).
. "$PSScriptRoot\_common.ps1"
Enter-UaCampaign
$env:SCRAPER_TIMEZONE = "Europe/Warsaw"
Write-Host "[UA PON] Prep — rebuild Excel"
python ua_materialy_scraper.py --run-config run_config\ua_materialy.json --rebuild-from-cache @args
