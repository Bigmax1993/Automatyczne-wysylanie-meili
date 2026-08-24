# Plan tygodniowy UA — identyczny harmonogram jak DE GU

Kampania **UA materiały budowlane** (`ua_materialy_scraper.py`, `run_config/ua_materialy.json`).
Wysyłka **pon 09:00** + **wt 09:00** (2×300 maili/dzień). **Bez załączników PPTX.**

## Rotacja obwodów (od 2026-07-13)

Discovery (`--rotate-oblast`) skanuje **1 obwód na tydzień** (kolejność: Kyiv → Lvivska → … → Luhanska, 25 tygodni).

| Okres | Zachowanie |
|-------|------------|
| **Do 12.07.2026** | `--rotate-oblast` włączone, ale **bez zawężenia** — discovery po **wszystkich 25 obwodach** (bieżący tydzień) |
| **Od 13.07.2026** (pon 17:00) | Pierwszy tydzień z rotacją — obwód **Kyiv** |
| **Niedziela backfill** | Przesunięcie rotacji dopiero po ≥20 verified/pending w aktywnym obwodzie |

Kolumna Excel: **Obwód** (import nadal akceptuje starą nazwę „Oblast”).

Stan rotacji: `Wyniki/ua_materialy_oblast_rotation.json`. Status: `python ua_materialy_scraper.py --rotation-status`.

## Cykl tygodniowy

```
Tydzień N (discovery):
  pon 17:00 → wt 15:00 → śr 19:00 → czw 20:00 → pt 16:00   [ua-materialy-wyniki-pi]

Tydzień N (przetwarzanie + wysyłka poprzedniej fali):
  nd 05:30 backfill → pon 06:00 sync Drive → pon 07:00 prep → pon 09:00 send → wt 09:00 send
```

**Poniedziałek ma dwa tryby:** rano (06–09) kończy poprzednią falę (backfill → wysyłka), wieczorem (17:00) startuje **nowy** tydzień discovery (cache z `fri`).

## Tabela harmonogramu

| Dzień | Godzina (PL) | Skrypt PC | GitHub Actions |
|-------|--------------|-----------|----------------|
| **Poniedziałek** | **17:00** | `schedule/ua/run_poniedzialek_discovery.ps1` | `UA discovery` (faza mon) |
| **Wtorek** | **15:00** | `schedule/ua/run_wtorek_discovery.ps1` | `UA discovery` (faza tue) |
| **Środa** | **19:00** | `schedule/ua/run_sroda_discovery.ps1` | `UA discovery` (faza wed) |
| **Czwartek** | **20:00** | `schedule/ua/run_czwartek_discovery.ps1` | `UA discovery` (faza thu) |
| **Piątek** | **16:00** | `schedule/ua/run_piatek_discovery.ps1` | `UA discovery` (faza fri) |
| **Niedziela** | 06:00 | `schedule/ua/run_niedziela_backfill.ps1` | `UA niedziela backfill` (~05:30 Actions) |
| **Poniedziałek** | **06:00** | — | `Sync wyniki Google Drive UA` |
| **Poniedziałek** | **07:00** | `schedule/ua/run_poniedzialek_prep.ps1` | `UA poniedzialek prep` |
| **Poniedziałek** | **09:00** | `schedule/ua/run_poniedzialek_send.ps1` | `UA poniedzialek send` (partia 1) |
| **Wtorek** | **09:00** | `schedule/ua/run_wtorek_send.ps1` | `UA wtorek send` (partia 2) |

| Dzień | Co robi |
|-------|---------|
| **Poniedziałek 17:00** | Discovery część 1 — nowy tydzień, cache z `fri` → `ua-materialy-wyniki-pi` |
| **Wtorek 15:00** | Discovery część 2 — `--respect-cache` |
| **Środa 19:00** | Discovery część 3 — `--respect-cache` |
| **Czwartek 20:00** | Discovery część 4 — `--respect-cache` |
| **Piątek 16:00** | Discovery część 5 — `--respect-cache`, domknięcie tygodnia |
| **Niedziela 05:30** | Verify www + backfill e-maili + Excel (`ua-materialy-wyniki-thu`) z piątkowego `pi` |
| **Poniedziałek 06:00** | Upload Excel na Drive UA (artefakt `thu`) |
| **Poniedziałek 07:00** | Rebuild Excel z cache (`ua-materialy-wyniki-mon`), **bez wysyłki** |
| **Poniedziałek 09:00** | Wysyłka partia 1 (max **300**) |
| **Wtorek 09:00** | Wysyłka partia 2 (kolejne **300** + zaległe) |

## Task Scheduler (Windows)

```powershell
powershell -ExecutionPolicy Bypass -File "schedule\ua\register_tasks_5_dni.ps1"
```

Usunięcie zadań:

```powershell
powershell -ExecutionPolicy Bypass -File "schedule\ua\register_tasks_5_dni.ps1" -Unregister
```

## GitHub Actions — artefakty

```
pon→pi | wt→pi | sro→pi | czw→pi | pt→pi → niedziela→thu → sync Drive UA → pon prep→mon → pon send→tue → wt send→fri
```

| Workflow | Plik | Cron (Europe/Warsaw) |
|----------|------|----------------------|
| discovery | `ua_materialy_pi.yml` | `0 17 * * 1` **pon 17:00**, `0 15 * * 2` **wt 15:00**, `0 19 * * 3` **śr 19:00**, `0 20 * * 4` **czw 20:00**, `0 16 * * 5` **pt 16:00** |
| backfill | `ua_materialy_thu.yml` | `30 5 * * 0` → **05:30** niedziela |
| sync Drive | `sync-google-drive-ua.yml` | `0 6 * * 1` → **06:00** poniedziałek |
| prep | `ua_materialy_mon.yml` | `0 7 * * 1` → **07:00** poniedziałek |
| send 1 | `ua_materialy_tue.yml` | `0 9 * * 1` → **09:00** poniedziałek |
| send 2 | `ua_materialy_fri.yml` | `0 9 * * 2` → **09:00** wtorek |

**Sync Drive UA:** pon 06:00 PL, artefakt **`thu`** (backfill); fallback: `mon` → `tue` → `fri`. Secret: `GDRIVE_FOLDER_ID_UA`.

**Wznowienie discovery:**

```powershell
gh workflow run "UA discovery" -R Bigmax1993/Wyszukiwarka-partnerow -f resume_artifact_run_id=RUN_ID
```

Porównanie z harmonogramem DE GU: [`PLAN_5_DNI.md`](PLAN_5_DNI.md).
