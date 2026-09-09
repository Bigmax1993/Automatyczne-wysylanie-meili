# -*- coding: utf-8 -*-

"""

Wspólna konfiguracja dla wszystkich scraperów w „Automatyczna wyszukiwarka…”.



Strony www: requests + BeautifulSoup; baner cookie — Playwright (DE: „Alle akzeptieren” itd.).

Kontakty www: regex + mailto; bei fehlendem E-Mail-Ziel zusätzlich Claude auf Crawl-Text.
Weryfikacja www + cleanup wiersza: Claude Sonnet (Anthropic API).

"""

from __future__ import annotations



ENABLE_CLAUDE_PAGE_VERIFY = True

ENABLE_CLAUDE_CONTACT_EXTRACT = True

# Brak dziennego limitu wywołań Claude (verify, cleanup, kontakty, discovery).
CLAUDE_UNLIMITED = True

ENABLE_CLAUDE_ROW_CLEANUP = True

ENABLE_CLAUDE_INQUIRY_EMAIL = True

ENABLE_CLAUDE_DISCOVERY_TERMS = False



# Playwright: wyłącznie zamknięcie banerów cookie (bez CAPTCHA / map)

ENABLE_PLAYWRIGHT_COOKIE_CONSENT = True


