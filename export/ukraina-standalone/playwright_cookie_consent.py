# -*- coding: utf-8 -*-
"""
Playwright: wyłącznie zamknięcie banerów cookie (bez CAPTCHA, bez map).

Priorytet: niemieckie CMP (Alle akzeptieren, Borlabs, Cookiebot, Usercentrics, …).
Kontekst przeglądarki: locale de-DE, Accept-Language: de.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

try:
    from scraper_web_config import ENABLE_PLAYWRIGHT_COOKIE_CONSENT
except ImportError:
    ENABLE_PLAYWRIGHT_COOKIE_CONSENT = True

# Wykrywanie banera – najpierw typowe niemieckie sformułowania
_DE_COOKIE_MARKERS: tuple[str, ...] = (
    "cookie",
    "cookies",
    "cookie-einstellungen",
    "cookie einstellungen",
    "cookie-richtlinie",
    "cookie richtlinie",
    "cookie-hinweis",
    "cookie hinweis",
    "cookie-banner",
    "cookie banner",
    "cookie-zustimmung",
    "datenschutz",
    "datenschutzeinstellungen",
    "datenschutz-einstellungen",
    "datenschutz präferenzen",
    "datenschutzpraferenzen",
    "datenschutz-präferenzen",
    "einwilligung",
    "zustimmung",
    "einwilligungen verwalten",
    "consent",
    "alle akzeptieren",
    "alles akzeptieren",
    "cookies akzeptieren",
    "cookies zulassen",
    "cookies erlauben",
    "nur erforderliche",
    "notwendige cookies",
    "borlabs-cookie",
    "onetrust",
    "cookiebot",
    "usercentrics",
    "klaro",
    "ccm19",
    "cmplz",
    "etracker",
    "privacy-manager",
)

# Zapasowo (inne moduły PL/IT) – niższy priorytet przy wykrywaniu
_FALLBACK_COOKIE_MARKERS: tuple[str, ...] = (
    "accept all",
    "cookie settings",
    "akceptuj",
    "zaakceptuj",
)

_CMP_HTML_HINTS: tuple[str, ...] = (
    "onetrust-accept",
    "CybotCookiebotDialogBodyButtonAccept",
    "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "cookiebot",
    "CybotCookiebot",
    "cmplz-cookiebanner",
    "cmplz-accept",
    "borlabs-cookie",
    "borlabs-cookie-btn-accept",
    "usercentrics",
    "uc-accept-all",
    "fc-cta-consent",
    "sp_message_container",
    "ccm--accept",
    "ccm-widget",
    "klaro",
    "klaro-cookie-notice",
    "privacy-manager",
    "cookie-law-info",
    "cli_settings_button",
)

_CAPTCHA_MARKERS: tuple[str, ...] = (
    "recaptcha",
    "g-recaptcha",
    "hcaptcha",
    "ungewöhnlichen traffic",
    "unusual traffic",
    "robot check",
    "ich bin kein roboter",
    "i am not a robot",
)

# Przyciski „Akzeptuj” (DE) – kolejność od najczęstszych CMP
_DE_ACCEPT_EXACT: tuple[str, ...] = (
    "Alle akzeptieren",
    "Alle Cookies akzeptieren",
    "Alles akzeptieren",
    "Allen zustimmen",
    "Akzeptieren",
    "Zustimmen",
    "Einverstanden",
    "Verstanden",
    "OK",
    "Okay",
    "Ich stimme zu",
    "Cookies akzeptieren",
    "Cookies zulassen",
    "Cookies erlauben",
    "Zulassen",
    "Consent erteilen",
    "Auswahl bestätigen",
    "Speichern & schließen",
    "Speichern und schließen",
    "Verstanden und fortfahren",
    "Weiter",
    "Fortfahren",
)

_DE_ACCEPT_BUTTON_RE = re.compile(
    r"^("
    r"alle\s+cookies?\s+akzeptieren|"
    r"alle\s+akzeptieren|"
    r"alles\s+akzeptieren|"
    r"allen\s+zustimmen|"
    r"cookies?\s+akzeptieren|"
    r"cookies?\s+zulassen|"
    r"cookies?\s+erlauben|"
    r"akzeptieren|"
    r"zustimmen|"
    r"einverstanden|"
    r"verstanden(\s+und\s+fortfahren)?|"
    r"ich\s+stimme\s+zu|"
    r"consent\s+erteilen|"
    r"auswahl\s+bestätigen|"
    r"speichern\s*[&+]\s*schließen|"
    r"zulassen|"
    r"fortfahren|"
    r"weiter|"
    r"^ok(?:ay)?$"
    r")\s*$",
    re.IGNORECASE,
)

_DE_REJECT_BUTTON_RE = re.compile(
    r"ablehnen|"
    r"verweigern|"
    r"nicht\s+akzeptieren|"
    r"nur\s+(?:erforderliche|notwendige|technische)|"
    r"nur\s+essentielle|"
    r"essentielle\s+only|"
    r"einstellungen|"
    r"auswahl|"
    r"anpassen|"
    r"konfigurieren|"
    r"mehr\s+optionen|"
    r"details|"
    r"reject|"
    r"decline|"
    r"refuse|"
    r"settings|"
    r"preferences",
    re.IGNORECASE,
)

# Selektory ID/klas – typowe niemieckie wtyczki WordPress / CMP
_DE_CONSENT_SELECTORS: tuple[str, ...] = (
    "#onetrust-accept-btn-handler",
    "#CybotCookiebotDialogBodyButtonAccept",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "button[data-testid='uc-accept-all-button']",
    "button[data-testid='uc-accept-all']",
    ".uc-accept-all-button",
    ".borlabs-cookie-btn-accept-all",
    ".borlabs-cookie-btn[data-cookie-accept-all]",
    "a.borlabs-cookie-btn-accept-all",
    "button.cmplz-accept",
    ".cmplz-btn.cmplz-accept",
    ".cmplz-accept",
    "#cookie_action_close_header",
    ".cc-allow",
    ".cc-btn.cc-allow",
    "[data-cookie-accept]",
    "[data-cookie-accept-all]",
    ".fc-cta-consent",
    ".ccm--accept-all",
    ".ccm-widget button.ccm--accept-all",
    "#ccm-widget .ccm--accept-all",
    ".klaro .cm-btn-success",
    "button.klaro-cookie-notice-button",
    ".cli_action_button.cli_accept_button",
    "#cookie-law-info-again",
    "button.privacy-manager-accept",
    "button[data-accept-cookies]",
    "button[aria-label*='akzeptieren' i]",
    "button[aria-label*='zustimmen' i]",
    "a[aria-label*='akzeptieren' i]",
)

# Playwright get_by_role – regex po niemiecku
_DE_ROLE_BUTTON_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"alle\s+cookies?\s+akzeptieren",
        r"alle\s+akzeptieren",
        r"alles\s+akzeptieren",
        r"^akzeptieren$",
        r"^zustimmen$",
        r"cookies?\s+akzeptieren",
        r"^einverstanden$",
        r"^verstanden$",
        r"^zulassen$",
    )
)

_DEFAULT_TIMEOUT_MS = 22_000
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_ACCEPT_LANGUAGE = "de-DE,de;q=0.9,en;q=0.5"


def should_use_playwright_cookie_fallback(page_text: str, html: str = "") -> bool:
    """True gdy widać baner cookie (DE lub ogólny CMP) — nie przy samej CAPTCHA."""
    t = (page_text or "").lower()
    h = (html or "").lower()[:14_000]
    combined = f"{t} {h}"
    has_cookie = (
        any(m in combined for m in _DE_COOKIE_MARKERS)
        or any(m in combined for m in _FALLBACK_COOKIE_MARKERS)
        or any(hint in h for hint in _CMP_HTML_HINTS)
    )
    if not has_cookie:
        return False
    if any(m in combined for m in _CAPTCHA_MARKERS) and not has_cookie:
        return False
    return True


def _is_reject_label(label: str) -> bool:
    return bool(label and _DE_REJECT_BUTTON_RE.search(label))


def _is_german_accept_label(label: str) -> bool:
    if not label or len(label) > 90:
        return False
    t = label.strip()
    if _is_reject_label(t):
        return False
    if t in _DE_ACCEPT_EXACT:
        return True
    return bool(_DE_ACCEPT_BUTTON_RE.match(t))


def _click_locator_safe(locator, logger: logging.Logger) -> bool:
    try:
        if locator.count() == 0:
            return False
        el = locator.first
        try:
            label = (el.inner_text(timeout=600) or "").strip()[:90]
        except Exception:
            label = ""
        if label and _is_reject_label(label):
            return False
        if label and not _is_german_accept_label(label):
            # Inne języki tylko jeśli wygląda jak globalne „accept all”
            if not re.match(r"^(accept all|accept cookies|i agree)$", label, re.I):
                return False
        el.click(timeout=3000)
        return True
    except Exception as e:
        logger.debug("Playwright cookie click: %s", e)
        return False


def _click_by_exact_german_text(page, logger: logging.Logger) -> bool:
    for phrase in _DE_ACCEPT_EXACT:
        try:
            btn = page.get_by_role("button", name=phrase, exact=True)
            if _click_locator_safe(btn, logger):
                return True
        except Exception:
            pass
        try:
            link = page.get_by_role("link", name=phrase, exact=True)
            if _click_locator_safe(link, logger):
                return True
        except Exception:
            pass
        try:
            loc = page.locator(
                f"button:has-text('{phrase}'), a:has-text('{phrase}'), "
                f"[role='button']:has-text('{phrase}')"
            )
            if _click_locator_safe(loc, logger):
                return True
        except Exception:
            continue
    return False


def _click_by_german_role_regex(page, logger: logging.Logger) -> bool:
    for pat in _DE_ROLE_BUTTON_PATTERNS:
        try:
            loc = page.get_by_role("button", name=pat)
            if _click_locator_safe(loc, logger):
                return True
        except Exception:
            continue
    return False


def _click_de_selectors(page, logger: logging.Logger) -> bool:
    for sel in _DE_CONSENT_SELECTORS:
        try:
            loc = page.locator(sel)
            if _click_locator_safe(loc, logger):
                return True
        except Exception:
            continue
    return False


def _click_buttons_scan_german(page, logger: logging.Logger) -> bool:
    try:
        buttons = page.get_by_role("button")
        n = min(buttons.count(), 50)
    except Exception:
        return False

    for i in range(n):
        try:
            btn = buttons.nth(i)
            text = (btn.inner_text(timeout=500) or "").strip()
        except Exception:
            continue
        if not _is_german_accept_label(text):
            continue
        try:
            btn.click(timeout=3000)
            return True
        except Exception:
            continue
    return False


def _dismiss_cookie_banner(page, logger: logging.Logger) -> bool:
    """Kolejność: DE selektory CMP → dokładny tekst DE → role regex → skan przycisków."""
    steps = (
        _click_de_selectors,
        _click_by_exact_german_text,
        _click_by_german_role_regex,
        _click_buttons_scan_german,
    )
    for step in steps:
        if step(page, logger):
            return True
    return False


def fetch_html_with_cookie_consent(
    url: str,
    logger: logging.Logger,
    *,
    timeout_ms: int = _DEFAULT_TIMEOUT_MS,
) -> str:
    """Chromium de-DE: ładuje stronę, klika niemieckie „Akzeptieren”, zwraca HTML."""
    if not ENABLE_PLAYWRIGHT_COOKIE_CONSENT:
        return ""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.info(
            "Playwright niedostępny (pip install playwright && playwright install chromium)"
        )
        return ""

    html = ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent=_USER_AGENT,
                    locale="de-DE",
                    timezone_id="Europe/Berlin",
                    extra_http_headers={"Accept-Language": _ACCEPT_LANGUAGE},
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(1100)
                _dismiss_cookie_banner(page, logger)
                page.wait_for_timeout(700)
                html = page.content()
            finally:
                browser.close()
    except Exception as e:
        logger.warning("Playwright cookie consent %s: %s", url, e)
    return html


def apply_playwright_cookie_fallback(
    url: str,
    logger: logging.Logger,
    html: str,
    parsed: dict[str, Any],
    parse_contacts_from_html: Callable[[str, str], dict],
    *,
    on_step: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Po requests: ponowny parse HTML po niemieckim banerze cookie."""
    if not ENABLE_PLAYWRIGHT_COOKIE_CONSENT:
        return parsed
    page_text = parsed.get("page_text", "")
    if not should_use_playwright_cookie_fallback(page_text, html):
        return parsed
    if on_step:
        on_step("Cookie-Banner (DE) – Playwright, nur Zustimmung")
    pw_html = fetch_html_with_cookie_consent(url, logger)
    if not pw_html:
        return parsed
    return parse_contacts_from_html(url, pw_html)
