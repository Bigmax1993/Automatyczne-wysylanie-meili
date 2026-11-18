# Uwagi prawne i rekrutacyjne (skrót)

To narzędzie techniczne: **Ty odpowiadasz** za legalność wysyłki (RODO, prawo pracy, regulaminy portali, zgody tam, gdzie są wymagane).

### Pętla maili między własnymi Gmailami

Jeśli w wątku widać ciąg wiadomości `svinchak1993@gmail.com` → `Swinczakaleksy@gmail.com` z samym „Pokaż cytowany tekst”, to zwykle **auto-forward / filtr Gmail** między dwoma kontami, a nie kampania CV. Pipeline **nie** powinien wysyłać na te adresy (`config/blocked_emails.txt`). Żeby zatrzymać pętlę: w obu kontach Gmail wyłącz przekazywanie / filtry „prześlij dalej” i usuń wątek.

- Wysyłaj tylko tam, gdzie masz **uzasadnioną podstawę** (np. odpowiedź na ogłoszenie o pracę, zapytanie biznesowe zgodne z prawem).
- **Nie obchodź** logowań, paywalli ani warunków ToS stron trzecich.
- **Listy blokady domen** (`config/blocked_domains.txt`) służą do wykluczania adresów, których nie chcesz kontaktować (np. własna organizacja).
- Pobieranie treści ze stron (`ENABLE_WEB_PAGE_CONTEXT`, `FETCH_EMAIL_FROM_WEBSITE`) dotyczy wyłącznie **publicznie dostępnych** fragmentów; nie zastępuje oceny prawnej.
- **Logi i kopie zapasowe** (`pipeline_logs`, log kampanii CSV, opcjonalne kopie JSON) mogą przechowywać adresy e-mail, nazwy firm i fragmenty treści — stosuj odpowiednie środki techniczne i organizacyjne (dostęp, retencja, RODO).
- W CI (`GitHub Actions`) artefakty `pipeline-json-backup-*` oraz `pipeline-logs-*` są przechowywane czasowo (retencja 30 dni) — traktuj je jako dane operacyjne z możliwymi danymi osobowymi.
- **GUI** (`pipeline_launcher_gui.py`) wyświetla wyjście procesu w oknie — unikaj udostępniania ekranu, gdy w logu widać dane wrażliwe; sekrety trzymaj w `local_env.ps1` / profilu systemu, nie w repozytorium.

W razie wątpliwości skonsultuj się z prawnikiem lub działem HR.
