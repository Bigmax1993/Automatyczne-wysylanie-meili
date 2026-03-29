# Automatyczne wysyłanie meili

Skrypty zbierają leady (opcjonalnie SerpAPI), czyszczą i walidują kontakty (OpenAI), generują treść maili i wysyłają ją przez Gmail z załączonym CV.

**Repozytorium GitHub:** po utworzeniu repozytorium pod adresem `https://github.com/<twoj-login>/Automatyczne-wysylanie-meili` sklonuj je lub dodaj `origin` i wypchnij gałąź (patrz [Publikacja na GitHub](#publikacja-na-github)).

- Główny plik kontaktów Excel: wzorzec `Kontakty*.xlsx` w `Documents` (szczegóły w dokumentacji).
- **Pełna dokumentacja:** [`docs/DOKUMENTACJA_PROJEKTU.md`](docs/DOKUMENTACJA_PROJEKTU.md).
- **Szablon zmiennych środowiskowych:** [`env.example`](env.example) (skopiuj do `.env` lub ustaw w systemie / `local_env.ps1`).

## Instalacja

```powershell
python -m pip install -r requirements.txt
```

## Zalecany start: `run_with_env.ps1`

1. Skopiuj `local_env.ps1.example` → `local_env.ps1` i wklej **pełne** klucze (nie placeholder `...`).
2. Z katalogu projektu:

```powershell
cd "C:\Users\svinc\Automatyczna wysylka meili"
.\run_with_env.ps1 -CheckOnly          # test OpenAI
.\run_with_env.ps1                     # pełny przebieg (SerpAPI + clean + wysyłka)
.\run_with_env.ps1 -SkipBuild          # bez SerpAPI — od clean/validate/send
.\run_with_env.ps1 -SkipBuild -DryRun  # jak wyżej, bez SMTP
```

`local_env.ps1` jest w `.gitignore` — nie commituj sekretów.

**Klucze z `setx`:** po `setx ...` otwórz **nowe** okno PowerShell. `run_with_env.ps1` uzupełnia **puste** zmienne z profilu użytkownika (`User`). Dodatkowo:

- **`OPENAI_API_KEY`:** jeśli w `local_env.ps1` jest podejrzanie krótki klucz, a w profilu **dłuższy** — użyty zostanie klucz z profilu.
- **`GMAIL_APP_PASSWORD`:** hasło aplikacji Google ma **16 znaków** po usunięciu spacji; jeśli w pliku jest błędna długość, a w profilu **poprawne 16** — użyta zostanie wartość z `setx`.

Jeśli w `local_env.ps1` ustawisz złą **niepustą** wartość, może ona nadal blokować `setx` (dopóki nie jest „krótsza” niż profil w logice OpenAI / dopóki Gmail nie przejdzie walidacji 16 znaków — wtedy lepiej poprawić plik lub usunąć linię).

**Wersja:** plik `VERSION`. Sprawdzenie: `python clean_validate_send_pipeline.py --version`.

## GUI (opcjonalnie)

Proste okno **Tkinter** do uruchamiania `run_with_env.ps1` z przełącznikami i podglądem logu:

```powershell
cd "C:\Users\svinc\Automatyczna wysylka meili"
python pipeline_launcher_gui.py
```

Bez dodatkowej konsoli: `pythonw pipeline_launcher_gui.py`. Wymaga `local_env.ps1` (jak przy `run_with_env.ps1`).

## Zmienne środowiskowe (skrót)

Pełna lista i opisy: **`env.example`**.

| Zmienna | Opis |
|--------|------|
| `OPENAI_API_KEY` | Wymagane do czyszczenia i generowania treści |
| `GMAIL_APP_PASSWORD` | Hasło **aplikacji** Google (16 znaków bez spacji); wysyłka (nie w `-DryRun`) |
| `GMAIL_SENDER_EMAIL` | Opcjonalnie: adres nadawcy SMTP / `From` (domyślnie wartość wbudowana w `contact_mailer`) |
| `SENDER_EMAIL` | Alternatywa dla `GMAIL_SENDER_EMAIL` (niższy priorytet niż `GMAIL_SENDER_EMAIL`) |
| `SERPAPI_API_KEY` | Do `build_contacts_serpapi.py` (pomijane przy `-SkipBuild`) |
| `CV_PATH` | Opcjonalnie: PDF, ścieżka bez `.pdf` lub folder z PDF |
| `OPENAI_MODEL` | Domyślnie `gpt-4o-mini` |
| `DRY_RUN` | `1` / `true` — bez SMTP w warstwie Python |
| `MAX_EMAILS_PER_DAY` | Limit dzienny (domyślnie `100`) |
| `EXTRA_CONTACTS_DIR` | Folder z dodatkowymi `.xlsx`/`.csv` (domyślnie `Documents\kontakty`) |
| `CAMPAIGN_LOG_ENABLED`, `CAMPAIGN_LOG_PATH` | Log kampanii CSV |
| `PIPELINE_LOG_LEVEL`, `PIPELINE_LOG_TO_FILE`, `PIPELINE_LOG_FILE` | Logowanie Python (`logging`) |
| `PIPELINE_JSON_BACKUP`, `PIPELINE_JSON_BACKUP_DIR` | Kopie zapasowe DataFrame do JSON po zapisie |
| `PIPELINE_PYTHON_EXE` | (PowerShell) inna ścieżka do `python.exe` w `run_pipeline.ps1` |

## Pojedyncze skrypty Python

```powershell
python contact_mailer.py
python clean_validate_send_pipeline.py --input "ścieżka\plik.xlsx" --output-csv "ścieżka\out.csv"
python build_contacts_serpapi.py --help
```

Przed ręcznym wywołaniem ustaw zmienne (`$env:...` lub `. .\local_env.ps1`).

## Pipeline: clean → walidacja → CSV → wysyłka

`clean_validate_send_pipeline.py`: czyta CSV/XLSX, czyści przez OpenAI, waliduje, zapisuje CSV, wysyła maile. **Kolejność:** najpierw kończy wysyłkę z głównego `--input` (np. `Kontakty_serpapi.xlsx`), potem **w tym samym uruchomieniu** przetwarza pozostałe pliki `.xlsx`/`.xls`/`.csv` z `Documents\kontakty` (pomija tylko plik, który był głównym wejściem, jeśli leży w tym folderze). `run_pipeline.ps1` przekazuje `--extra-contacts-dir` jawnie. Zob. też `--skip-extra-contacts`, `--skip-clean`, `--validate-only`, `--dry-run`.

## Rejestr wysłanych maili (JSON) i follow-up

Po każdej **udanej** wysyłce (nie w dry-run, wyłączone pod pytest) dopisywany jest wpis do pliku **JSON Lines** (`.jsonl`) w katalogu domyślnie `Documents\pipeline_logs\sent_mail_registry\`. Nazwa pliku odpowiada partii wejściowej (np. `Kontakty_serpapi.jsonl`). Wpis zawiera m.in. e-mail, firmę, pola do ponownej personalizacji, `sent_at`, flagi `reply_received` i `follow_up_sent_at`.

Program **nie sprawdza skrzynki** — „brak odpowiedzi” oznacza: nie oznaczono odpowiedzi. Po tygodniu (lub innym progu):

```powershell
python follow_up_mail.py list --days 7
python follow_up_mail.py export --days 7 -o "$env:USERPROFILE\Documents\kontakty\follow_up.xlsx"
```

Następnie uruchom `clean_validate_send_pipeline.py` (lub cały pipeline) na wygenerowanym pliku. Gdy kandydat odpowie:

```powershell
python follow_up_mail.py mark-reply --email kandydat@firma.pl
```

Pliki `.jsonl` są **automatycznie usuwane**, gdy **najnowszy** `sent_at` w pliku jest starszy niż **14 dni** (przy starcie `clean_validate_send_pipeline`, `contact_mailer` i `follow_up_mail`). Ustaw `SENT_MAIL_REGISTRY_RETENTION_DAYS=0`, żeby wyłączyć usuwanie.

Zmienne: `SENT_MAIL_REGISTRY_ENABLED`, `SENT_MAIL_REGISTRY_DIR`, `SENT_MAIL_REGISTRY_RETENTION_DAYS`, `FOLLOW_UP_MIN_DAYS` (opis w `env.example`).

## CV

Szukane są m.in. wzorce `CV*.pdf` w `Documents` oraz w podfolderach **`CV`**, `cv`, `Curriculum`, `Resume`, `resumes`. Można wymusić ścieżkę przez `CV_PATH`.

## SerpAPI (zbiór leadów)

`build_contacts_serpapi.py` — wymaga `SERPAPI_API_KEY`. Przy braku klucza lub limicie dziennej zwraca kod `2`; pipeline może użyć istniejącego Excela lub folderu `kontakty`.

## Testy

**Python (pytest)** — cały katalog `tests` (w tym e2e, integracja, testy subprocess dla `contact_mailer`, parser PS1):

```powershell
cd "C:\Users\svinc\Automatyczna wysylka meili"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest tests -v --tb=short
Remove-Item Env:PYTEST_DISABLE_PLUGIN_AUTOLOAD -ErrorAction SilentlyContinue
```

**PowerShell (Pester 3.4+ lub 5)** — składnia zgodna ze starszym Pesterem z `Program Files`:

```powershell
Invoke-Pester -Path ".\tests\powershell\RunPipeline.Tests.ps1"
Invoke-Pester -Path ".\tests\powershell\RunWithEnv.Tests.ps1"
```

**Wszystko naraz (pytest + Pester):**

```powershell
$proj = "C:\Users\svinc\Automatyczna wysylka meili"
Set-Location -LiteralPath $proj
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest tests -v --tb=short
Remove-Item Env:PYTEST_DISABLE_PLUGIN_AUTOLOAD -ErrorAction SilentlyContinue
if (Get-Command Invoke-Pester -ErrorAction SilentlyContinue) {
    Invoke-Pester -Path (Join-Path $proj "tests\powershell\RunPipeline.Tests.ps1")
    Invoke-Pester -Path (Join-Path $proj "tests\powershell\RunWithEnv.Tests.ps1")
}
```

## Dokumentacja dodatkowa

- [`docs/DOKUMENTACJA_PROJEKTU.md`](docs/DOKUMENTACJA_PROJEKTU.md) — architektura, logi, harmonogram, diagnostyka.
- [`docs/COMPLIANCE_NOTE.md`](docs/COMPLIANCE_NOTE.md) — uwagi prawne / RODO / ToS.

## Publikacja na GitHub

Nazwa repozytorium na GitHubie (bez spacji, znaki łacińskie): **`Automatyczne-wysylanie-meili`** — odpowiada nazwie projektu „Automatyczne wysyłanie meili”.

1. Zainstaluj [GitHub CLI](https://cli.github.com/) (`winget install GitHub.cli`), następnie w PowerShell:
   ```powershell
   gh auth login
   ```
2. W katalogu projektu (ten folder z `README.md`). Jeśli **nie** masz jeszcze lokalnego `.git`, uruchom `git init`, `git add -A`, `git commit -m "..."` (sprawdź `git status` — nie powinno być `local_env.ps1` ani `.env`). Następnie:
   ```powershell
   cd "C:\Users\svinc\Automatyczna wysylka meili"
   gh repo create Automatyczne-wysylanie-meili --public --source=. --remote=origin --push --description "Automatyczne wysyłanie meili: SerpAPI, OpenAI, Gmail SMTP, PowerShell"
   ```
   Jeśli repozytorium **już istnieje** na koncie (puste), zamiast `gh repo create` użyj:
   ```powershell
   git remote add origin https://github.com/<twoj-login>/Automatyczne-wysylanie-meili.git
   git branch -M main
   git push -u origin main
   ```
3. W ustawieniach repozytorium na GitHubie możesz ustawić **Repository display name** / opis wyświetlany na profilu na „Automatyczne wysyłanie meili” (GitHub obsługuje polskie znaki w opisie, nie w ścieżce URL).
