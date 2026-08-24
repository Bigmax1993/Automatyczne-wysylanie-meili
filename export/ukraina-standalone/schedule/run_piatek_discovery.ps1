# PIATEK — discovery czesc 5 (UA).
. "$PSScriptRoot\_common.ps1"
Enter-UaCampaign
$env:SCRAPER_TIMEZONE = "Europe/Warsaw"
Write-Host "[UA PT] Discovery czesc 5 (--respect-cache)"
python ua_materialy_scraper.py --run-config run_config\ua_materialy.json --serper-only-discovery --no-auto-email --rotate-oblast --respect-cache @args
