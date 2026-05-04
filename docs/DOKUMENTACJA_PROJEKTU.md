# Dokumentacja projektu

## 1. Cel projektu

Projekt automatyzuje pozyskanie leadów i wysyłkę spersonalizowanych wiadomości e-mail:

- zbiera firmy / agencje / e-commerce przez **SerpAPI** (opcjonalnie),
- czyści i waliduje rekordy przez **OpenAI**,
- generuje temat i treść wiadomości przez **OpenAI**,
- wysyła maile z załączonym **CV** przez **Gmail SMTP** (hasło **aplikacji**, nie zwykłe hasło konta),
- prowadzi **log kampanii**, **logowanie aplikacyjne**, opcjonalnie **kopie JSON** po zapisie arkuszy,
- respektuje **limity dzienne** i **blokadę domen**.

## 2. Struktura projektu

### Skrypty główne (Python)

| Plik | Rola |
|------|------|
| `build_contacts_serpapi.py` | Zbiór leadów z SerpAPI, enrichment e-mail ze stron |
| `clean_validate_send_pipeline.py` | Pipeline: czyszczenie OpenAI → walidacja → CSV → wysyłka |
| `contact_mailer.py` | Rdzeń wysyłki (retry, limity, personalizacja, statusy, CV, SMTP Gmail) |
| `excel_workbook_reader.py` | Wczytywanie wieloarkuszowych raportów Excel (nagłówki, pomijane arkusze) |
| `domain_blocklist.py` | Blokada domen odbiorców (`config/blocked_domains.txt` + env) |
| `web_page_context.py` | Opcjonalny kontekst z publicznej strony WWW dla OpenAI |
| `fetch_throttle.py` | Odstępy HTTP per host przy pobieraniu stron |
| `pipeline_logging.py` | Konfiguracja `logging` (stdout + opcjonalny plik rotowany) |
| `json_data_backup.py` | Kopie zapasowe `DataFrame` do JSON po zapisie CSV/XLSX |
| `pipeline_version.py` | Wersja zestawu (czyta plik `VERSION`) |
| `pipeline_launcher_gui.py` | Opcjonalne GUI (Tkinter): uruchamianie `run_with_env.ps1`, podgląd wyjścia, foldery |
| `sent_mail_registry.py` | Rejestr wysłanych maili (JSONL na partię) pod follow-up; retencja plików (domyślnie 14 dni od ostatniego `sent_at`); `follow_up_mail.py` — lista / eksport / `mark-reply` |

### Skrypty PowerShell

| Plik | Rola |
|------|------|
| `run_with_env.ps1` | Wczytuje `local_env.ps1`, scala zmienne z profilu `User` (`setx`), **walidacja** OpenAI (długość klucza) i **Gmail** (16 znaków hasła aplikacji po normalizacji), opcjonalnie nadpisanie krótkiego OpenAI / błędnego Gmail z profilu; wywołuje `run_pipeline.ps1` |
| `run_pipeline.ps1` | Krok SerpAPI (opcjonalnie) → wybór pliku wejściowego → `clean_validate_send_pipeline.py`. Katalog projektu = folder skryptu. Obsługa stderr Pythona przy `$ErrorActionPreference=Stop`. |

### Konfiguracja i dokumentacja

- `VERSION` — wersja pipeline (np. `1.0.0`).
- `env.example` — opis zmiennych środowiskowych (kopiuj do `.env` lub `local_env.ps1`).
- `config/blocked_domains.txt` — domeny do wykluczenia z wysyłki.
- `requirements.txt` — zależności Python.
- `tests/` — pytest: jednostkowe, integracyjne, regresyjne, e2e; **subprocess** dla izolowanego importu `contact_mailer`; testy treści/składni **PowerShell** (`test_run_pipeline_ps1.py`, `test_run_with_env_ps1.py`).
- `tests/powershell/RunPipeline.Tests.ps1` — Pester: `run_pipeline.ps1` (składnia Pester **3.4+** i 5).
- `tests/powershell/RunWithEnv.Tests.ps1` — Pester: `run_with_env.ps1`.

## 3. Przepływ danych

1. **`build_contacts_serpapi.py`** (jeśli uruchomiony) zapisuje m.in. `Documents\Kontakty_serpapi.xlsx`.
2. **`run_pipeline.ps1`**:
   - bez `-SkipBuild` wywołuje build SerpAPI; kod wyjścia `2` = pominięcie (brak klucza / limit dzienny),
   - wybiera wejście: najpierw `Kontakty_serpapi.xlsx`, inaczej **najnowszy** `.xlsx`/`.xls`/`.csv` z `Documents\kontakty` (lub `EXTRA_CONTACTS_DIR`),
   - uruchamia `clean_validate_send_pipeline.py` z `--input` i `--output-csv`.
3. **`clean_validate_send_pipeline.py`** czyści i waliduje, zapisuje CSV, wysyła; domyślnie przetwarza **pozostałe** pliki kontaktów z katalogu dodatkowego (bez powtórzenia głównego `--input`).
4. **`contact_mailer`** (używany z pipeline) aktualizuje statusy w pliku wyjściowym i log kampanii.

## 4. Personalizacja i reguły biznesowe

- Temat i treść generuje OpenAI (osobne prompty PL/DE wg domeny e-mail / strony).
- Dla e-commerce preferowana jest komunikacja B2B (wg logiki w kodzie).
- Reguła kontraktu (UOP vs B2B) z pól ogłoszenia / uwag.
- Rekordy z niepoprawnym e-mailem lub niespełniające walidacji są pomijane i oznaczane.

## 5. Źródła danych i strategia pozyskania

- Portale pracy służą do nazw firm / agencji.
- Strona WWW i kontakt są doprecyzowywane osobno.
- Przy podejrzeniu CAPTCHA / blokady stosowany jest bezpieczny fallback (bez obchodzenia zabezpieczeń).

## 6. Konfiguracja (zmienne środowiskowe)

**Źródło prawdy:** plik **`env.example`** w repozytorium (aktualizowany wraz z kodem).

### Wymagane w typowym przebiegu

- **`OPENAI_API_KEY`** — czyszczenie i generowanie treści.
- **`GMAIL_APP_PASSWORD`** — **hasło aplikacji** Google (w panelu: 16 znaków; spacje z wyświetlania są usuwane przy logowaniu). Wysyłka SMTP (niepotrzebne przy `--dry-run` / `DRY_RUN`).

### Gmail: nadawca i zgodność z hasłem

- **`GMAIL_SENDER_EMAIL`** lub **`SENDER_EMAIL`** — opcjonalnie adres używany w `smtp.login` i w polu **From** (priorytet: `GMAIL_SENDER_EMAIL`, potem `SENDER_EMAIL`, potem domyślny adres w kodzie). **Musi być tym samym kontem Gmail**, dla którego wygenerowano hasło aplikacji.
- W **`contact_mailer.py`**: `normalize_gmail_app_password()` — usuwa białe znaki i spacje z hasła przed użyciem.

### Wymagane tylko przy kroku SerpAPI

- **`SERPAPI_API_KEY`** — gdy uruchamiasz `build_contacts_serpapi.py` lub pełny `run_pipeline.ps1` **bez** `-SkipBuild`.

### CV

- **`CV_PATH`** (opcjonalnie): plik PDF, ścieżka bez `.pdf`, lub folder z plikami pasującymi do wzorców (`CV*.pdf`, `*CV*.pdf`, `*resume*.pdf`, itd.).
- Bez `CV_PATH` szukane są pliki w **`%USERPROFILE%\Documents`** oraz w podfolderach: **`CV`**, `cv`, `Curriculum`, `Resume`, `resumes`.

### Klucze i hasła: `local_env.ps1` vs `setx` vs `run_with_env.ps1`

- Skrypt wczytuje **`local_env.ps1`**, potem dla wybranych nazw uzupełnia **puste** zmienne z profilu użytkownika Windows (**`User`**), np. po **`setx`**.
- Po **`setx`** otwórz **nowe** okno konsoli, żeby zmienne były w bieżącym procesie.
- **OpenAI:** jeśli klucz z pliku jest krótszy niż ~80 znaków, a w profilu jest **dłuższy**, proces użyje klucza z profilu (komunikat w konsoli).
- **Gmail:** jeśli po usunięciu spacji hasło z procesu **nie ma 16 znaków**, a w profilu **ma 16**, użyta zostanie wartość z profilu. Przed wysyłką (bez `-DryRun`) **run_with_env** wymusza dokładnie **16 znaków** po normalizacji — w przeciwnym razie czytelny błąd zamiast `535` z Gmaila.
- Pusta lub błędna **niepusta** wartość w `local_env.ps1` może nadal powodować problemy — najpewniej: poprawny wpis w pliku albo pusta linia + `setx`.

### Logowanie (`logging`)

- **`PIPELINE_LOG_LEVEL`** — domyślnie `INFO`.
- **`PIPELINE_LOG_TO_FILE=1`** — zapis do pliku (domyślna ścieżka: `Documents\pipeline_logs\python_pipeline.log` lub **`PIPELINE_LOG_FILE`**).
- **`PIPELINE_LOG_MAX_BYTES`**, **`PIPELINE_LOG_BACKUP_COUNT`** — rotacja pliku.

### Kopie zapasowe JSON

- **`PIPELINE_JSON_BACKUP`** — domyślnie włączone poza pytest; wyłączenie: `0`.
- **`PIPELINE_JSON_BACKUP_DIR`** — katalog kopii (domyślnie `Documents\pipeline_json_backups`).
- **`PIPELINE_JSON_BACKUP_MAX_FILES`** — limit plików (przycinanie najstarszych).

### PowerShell

- **`PIPELINE_PYTHON_EXE`** — jawna ścieżka do interpretera Python w **`run_pipeline.ps1`**.

## 7. Uruchamianie

### 7.1. Zalecane: `run_with_env.ps1`

```powershell
cd "$env:USERPROFILE\Automatyczne-wysylanie-meili"
.\run_with_env.ps1 -SkipBuild -DryRun
```

### 7.2. GUI

```powershell
cd "$env:USERPROFILE\Automatyczne-wysylanie-meili"
python pipeline_launcher_gui.py
```

Wywołuje ten sam `run_with_env.ps1` co konsola; wymaga `local_env.ps1`.

### 7.3. Pozyskanie leadów (SerpAPI)

```powershell
cd "$env:USERPROFILE\Automatyczne-wysylanie-meili"
python build_contacts_serpapi.py --firm-target 1000 --agency-target 1000 --ecommerce-target 1000 --cities "Wroclaw,Zielona Gora,Poznan" --pages-per-query 6 --num-per-request 20 --max-requests-per-group 800 --enrich-email --output "$env:USERPROFILE\Documents\Kontakty_serpapi.xlsx"
```

### 7.4. Pipeline clean / validate / send

```powershell
python clean_validate_send_pipeline.py --input "$env:USERPROFILE\Documents\Kontakty_serpapi.xlsx" --output-csv "$env:USERPROFILE\Documents\Kontakty_cleaned.csv"
```

Tryb bez wysyłki:

```powershell
python clean_validate_send_pipeline.py --input "..." --output-csv "..." --dry-run
```

Tylko raport offline (bez OpenAI / SMTP):

```powershell
python clean_validate_send_pipeline.py --validate-only --input "ścieżka\plik.csv"
```

### 7.5. Kontynuacja od wyczyszczonego CSV

```powershell
python clean_validate_send_pipeline.py --skip-clean --input "ścieżka\Kontakty_cleaned.csv" --skip-extra-contacts
```

## 8. Harmonogram (opcjonalnie)

Przykład zadania zaplanowanego:

- nazwa: `PipelineMailing1900`
- uruchomienie: codziennie o 19:00
- akcja: `powershell.exe -File "C:\...\Automatyczna wysylka meili\run_with_env.ps1"` (zalecane) lub `run_pipeline.ps1` z wcześniej ustawionym środowiskiem

Przydatne komendy:

```powershell
Get-ScheduledTask -TaskName "PipelineMailing1900"
Start-ScheduledTask -TaskName "PipelineMailing1900"
```

## 9. Logi i diagnostyka

| Rodzaj | Lokalizacja / opis |
|--------|-------------------|
| Log uruchomienia PowerShell | `Documents\pipeline_logs\pipeline_YYYYMMDD_HHMMSS.log` |
| Log Python (opcjonalny) | `PIPELINE_LOG_FILE` lub domyślnie przy `PIPELINE_LOG_TO_FILE=1` |
| Log kampanii | CSV wg `CAMPAIGN_LOG_PATH` |
| Kopie JSON | `Documents\pipeline_json_backups` (lub `PIPELINE_JSON_BACKUP_DIR`) |
| Statusy w arkuszu | m.in. `Tak`, błędy OpenAI/SMTP, `Pominięto: limit dzienny`, itd. |

**Błędy Pythona z `run_pipeline.ps1`:** przy niezerowym kodzie wyjścia pełny stderr jest wypisywany w konsoli oraz dopisywany do pliku logu.

**SMTP `535` (Gmail):** zwykle złe hasło aplikacji lub inne konto niż nadawca — zweryfikuj `GMAIL_APP_PASSWORD` (16 znaków) i `GMAIL_SENDER_EMAIL` / domyślny adres w kodzie.

## 10. Testy

### pytest (Python)

```powershell
cd "$env:USERPROFILE\Automatyczne-wysylanie-meili"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest tests -v --tb=short
Remove-Item Env:PYTEST_DISABLE_PLUGIN_AUTOLOAD -ErrorAction SilentlyContinue
```

- **`testpaths`** w `pytest.ini`: `tests`.
- Markery: `integration`, `regression`, `e2e`.
- **`tests/test_contact_mailer_env_subprocess.py`** — osobny proces: `password` / `SENDER_EMAIL` przy imporcie modułu.
- Testy treści **`run_pipeline.ps1`** / **`run_with_env.ps1`**: `tests/test_run_pipeline_ps1.py`, `tests/test_run_with_env_ps1.py`.

### Pester (PowerShell)

Zgodność z **Pester 3.4** (np. z `Program Files`) oraz **Pester 5**:

```powershell
Invoke-Pester -Path ".\tests\powershell\RunPipeline.Tests.ps1"
Invoke-Pester -Path ".\tests\powershell\RunWithEnv.Tests.ps1"
```

### Pełna pętla (pytest + oba pliki Pester)

Patrz sekcja **Testy** w głównym [`README.md`](../README.md).

### GitHub Actions (workflow `CI + Pipeline`)

- `push` / `pull_request`: uruchamiają testy (`test-python`, `test-powershell`).
- `workflow_dispatch`: uruchamia testy; `serpapi-sunday` włącza się przy `skip_build=false`, po czym uruchamia się `pipeline`.
- Harmonogram:
  - niedziela `0 19 * * 0` UTC: `serpapi-sunday`,
  - poniedziałek `0 2 * * 1` UTC: `pipeline`.
- Job `pipeline` działa na `ubuntu-latest` i uruchamia bezpośrednio `python clean_validate_send_pipeline.py` (bez `run_pipeline.ps1` / PowerShell).
- Ustawione limity czasu:
  - `test-python`: 30 min,
  - `test-powershell`: 30 min,
  - `serpapi-sunday`: 45 min,
  - `pipeline`: 180 min.
- Artefakty po jobie `pipeline`:
  - `pipeline-json-backup-<run_id>-<run_attempt>`,
  - `pipeline-logs-<run_id>-<run_attempt>`,
  - retencja: 30 dni.

## 11. Ograniczenia i dobre praktyki

- Nie obchodź CAPTCHA ani warunków ToS serwisów — patrz **`docs/COMPLIANCE_NOTE.md`**.
- Używaj oficjalnych API i publicznych źródeł.
- Zachowaj limity dzienne i opóźnienia między wysyłkami (reputacja domeny).
- Logi i kopie JSON mogą zawierać **dane osobowe** — chroń katalogi `pipeline_logs` i `pipeline_json_backups`.
- **GUI** nie przechowuje haseł — tylko uruchamia skrypt z bieżącym środowiskiem i `local_env.ps1`.

## 12. Powiązane pliki

- [`COMPLIANCE_NOTE.md`](COMPLIANCE_NOTE.md)
- [`../README.md`](../README.md)
- [`../env.example`](../env.example)
