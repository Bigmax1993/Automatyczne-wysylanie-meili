# Publikacja repozytorium Ukraina

Ten katalog (`export/ukraina-standalone/`) zawiera gotowy, samodzielny projekt
**wyszukiwarka-materialow-budowlanych-ukraina**, wyodrębniony z kampanii UA w
`wyszukiwarka-materialow-budowlanych-polska`.

## Utworzenie repozytorium na GitHub

```powershell
cd export\ukraina-standalone
git init -b master
git add -A
git commit -m "Initial commit: wyszukiwarka materiałów budowlanych Ukraina"
gh repo create wyszukiwarka-materialow-budowlanych-ukraina --public --source=. --remote=origin --push --description "Wyszukiwarka materiałów budowlanych Ukraina: Serper, Claude, Excel, maile UA"
```

Adres docelowy: https://github.com/Bigmax1993/wyszukiwarka-materialow-budowlanych-ukraina

## Sekrety GitHub Actions

Ustaw w *Settings → Secrets and variables → Actions*:

- `SERPER_API_KEY`
- `ANTHROPIC_API_KEY`
- `MAIL_USER`, `MAIL_PASSWORD`
- `GDRIVE_FOLDER_ID_UA` (opcjonalnie OAuth / service account — patrz `docs/GOOGLE_DRIVE.md`)

## Regeneracja z monorepo PL

W repozytorium polskim uruchom: `python scripts/build_ua_repo.py`
