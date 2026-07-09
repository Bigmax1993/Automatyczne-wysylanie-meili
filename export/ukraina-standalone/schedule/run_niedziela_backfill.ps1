# NIEDZIELA — backfill (UA), jak DE GU run_czwartek.ps1.
. "$PSScriptRoot\_common.ps1"
Enter-UaCampaign
$env:SCRAPER_TIMEZONE = "Europe/Warsaw"
Remove-Item Env:DISABLE_SEND_WINDOW -ErrorAction SilentlyContinue
Write-Host "[UA ND] Weryfikacja www (pending z discovery pon-pt)..."
python ua_materialy_scraper.py --run-config run_config\ua_materialy.json --verify-pending-contacts
Write-Host "[UA ND] Backfill e-maili z cache..."
python ua_materialy_scraper.py --run-config run_config\ua_materialy.json --backfill-emails-from-cache
Write-Host "[UA ND] Rebuild Excel z cache..."
python ua_materialy_scraper.py --run-config run_config\ua_materialy.json --rebuild-from-cache
