# Wyszukiwarka materiałów budowlanych — Ukraina

Repozytorium: [Bigmax1993/wyszukiwarka-materialow-budowlanych-ukraina](https://github.com/Bigmax1993/wyszukiwarka-materialow-budowlanych-ukraina)

Pipeline: **Serper (gl=ua) → crawl www → Claude verify → Excel → maile UA**.

| Moduł | Plik |
|-------|------|
| Scraper | `ua_materialy_scraper.py` |
| Frazy per obwód | `ua_oblast_keywords.py` |
| Rotacja obwodów | `ua_oblast_rotation.py` |
| Filtr dostawców | `ua_materialy_supplier_filter.py` |
| Treść maila UK | `ua_materialy_inquiry_email_uk.py` |

## Szybki start

```powershell
git clone https://github.com/Bigmax1993/wyszukiwarka-materialow-budowlanych-ukraina.git
cd wyszukiwarka-materialow-budowlanych-ukraina
pip install -r requirements.txt
$env:KANBUD_PROJECT_ROOT = "$PWD\libs"

python ua_materialy_scraper.py --test
python ua_materialy_scraper.py --rotate-oblast
python ua_materialy_scraper.py --rotation-status
python ua_materialy_scraper.py --oblast Kyiv,Lvivska
python ua_materialy_scraper.py --run-config run_config\ua_kyiv_test.json
python ua_materialy_scraper.py --dry-run-email --send-emails-only
```

Skopiuj `.env.example` → `.env` (lokalnie) lub ustaw sekrety w GitHub Actions.

## Testy

```powershell
python ua_materialy_scraper.py --test
python -m unittest tests.test_ua_materialy_regression -v
python -m pytest tests/test_ua_oblast_keywords.py tests/test_ua_inquiry_email_uk.py tests/test_ua_claude_inquiry_email.py tests/test_ua_supplier_filter.py tests/test_ua_materialy_integration.py -q
```

Pełna bateria: `powershell -ExecutionPolicy Bypass -File scripts\RUN_ALL_TESTS.ps1`

## Wyniki

| Plik / folder | Opis |
|---------------|------|
| `Wyniki/ua_materialy_cache.json` | Cache Serper + kontakty |
| `Wyniki/ua_materialy_kontakte.xlsx` | Excel (append) |
| `Wyniki/ua_materialy_oblast_rotation.json` | Stan rotacji obwodów |
| `wyslane/` | Kopie wysłanych maili (.eml) |

## Harmonogram

Szczegóły: [`schedule/PLAN_5_DNI_UA.md`](schedule/PLAN_5_DNI_UA.md)

| Dzień | Godzina (PL) | PC | GitHub Actions |
|-------|--------------|-----|----------------|
| **Pon–Pt** | 17:00 / 15:00 / 19:00 / 20:00 / 16:00 | `schedule/run_*_discovery.ps1` | `UA discovery` |
| **Niedziela** | 06:00 | `schedule/run_niedziela_backfill.ps1` | `UA niedziela backfill` |
| **Poniedziałek** | 06:00 / 07:00 / 09:00 | prep + send | `Sync wyniki Google Drive UA` → prep → send |
| **Wtorek** | 09:00 | `schedule/run_wtorek_send.ps1` | `UA wtorek send` |

Task Scheduler:

```powershell
powershell -ExecutionPolicy Bypass -File schedule\register_tasks_5_dni.ps1
```

## GitHub Actions

Dokumentacja: [`docs/GITHUB_ACTIONS.md`](docs/GITHUB_ACTIONS.md), [`docs/GOOGLE_DRIVE.md`](docs/GOOGLE_DRIVE.md)

| Secret | Wymagany | Opis |
|--------|----------|------|
| `SERPER_API_KEY` | tak (discovery) | API Serper |
| `ANTHROPIC_API_KEY` | tak | Claude API |
| `MAIL_USER`, `MAIL_PASSWORD` | tak (pon+wt) | Gmail / SMTP |
| `GDRIVE_FOLDER_ID_UA` | zalecany | Upload wyników na Drive |

## Maile UA

- Treść: `ua_materialy_inquiry_email_uk.py` + **Claude Sonnet** (unikalny list ukraiński per firma)
- Wymaga `ANTHROPIC_API_KEY`; wyłączenie: `ENABLE_CLAUDE_INQUIRY_EMAIL=0`
- **Bez załączników** — tylko plain-text
- Nadawca: `MAIL_SENDER_NAME` (domyślnie Свінчак Максим), telefon `+380977091141`
