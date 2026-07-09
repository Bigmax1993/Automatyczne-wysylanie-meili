# -*- coding: utf-8 -*-
"""
Tekst maila — zapytanie ofertowe do postawalcy budmatów UA (ukraiński).
Nadawca z .env (MAIL_SENDER_NAME, opcjonalnie INQUIRY_*).
Domyślny telefon kontaktowy: +380977091141 (numery DE +49 są odfiltrowywane).
"""
from __future__ import annotations

import re

_GERMAN_PHONE_INLINE_RE = re.compile(
    r"(?:\+49|0049)\s*[\d\s()./-]{5,}\d",
    re.IGNORECASE,
)
_GERMAN_TEL_LINE_RE = re.compile(
    r"^\s*(?:tel\.?|telefon|phone)\s*[.:]?\s*(?:\+49|0049)[\d\s()./-]*\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_DE_CAMPAIGN_BRANDING_RE = re.compile(
    r"\b(?:mfg|moderner\s*fliesen\w*|fliesenboden|gmbh|firma)\b",
    re.IGNORECASE,
)


def is_german_phone(phone: str) -> bool:
    raw = (phone or "").strip()
    if not raw:
        return False
    low = raw.lower().replace(" ", "")
    if low.startswith("+49") or low.startswith("0049"):
        return True
    digits = re.sub(r"\D", "", raw)
    return digits.startswith("49") and len(digits) >= 11


def strip_german_phones_from_text(text: str) -> str:
    """Usuwa numery DE (+49) z tekstu — linie Tel. i fragmenty inline."""
    if not text:
        return ""
    out = _GERMAN_TEL_LINE_RE.sub("", text)
    out = _GERMAN_PHONE_INLINE_RE.sub("", out)
    out = re.sub(r"\b(?:tel\.?|telefon|phone)\s*[.:]?\s*(?=\s|$)", "", out, flags=re.IGNORECASE)
    out = re.sub(r"[ \t]+,", ",", out)
    out = re.sub(r",\s*,", ",", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip(" ,\n")


def strip_de_campaign_branding(text: str) -> str:
    """Usuwa pozostałości kampanii DE (MFG, GmbH) z tekstu maila UA."""
    if not text:
        return ""
    out = strip_german_phones_from_text(text)
    out = _DE_CAMPAIGN_BRANDING_RE.sub("", out)
    out = re.sub(r"\s+", " ", out).strip(" ,;-")
    return out


def _is_legacy_de_sender_name(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return True
    if any(x in low for x in ("mfg", "fliesen", "moderner", "gmbh")):
        return True
    normalized = re.sub(r"[^a-zа-яіїєґ\s]", "", low, flags=re.IGNORECASE).strip()
    if normalized in ("maksym swinczak", "maxym swinczak"):
        return True
    return False


def _clean_sender_display_name(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    text = re.sub(r"\b(tel|telefon|phone)\b.*$", "", text, flags=re.IGNORECASE).strip()
    text = strip_german_phones_from_text(text)
    text = re.sub(r"https?://\S+|\bwww\.\S+|\S+@\S+", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\+?\d[\d\s()./-]{5,}\d", "", text).strip()
    text = strip_de_campaign_branding(text)
    text = re.sub(r"\s+", " ", text).strip(" ,;-")
    return text


DEFAULT_INQUIRY_SENDER_NAME_UK = "Свінчак Максим"
DEFAULT_INQUIRY_PHONE_UK = "+380977091141"


def inquiry_sender_name() -> str:
    from scraper_env import get_mail_sender_name

    cleaned = _clean_sender_display_name(get_mail_sender_name() or "")
    if _is_legacy_de_sender_name(cleaned):
        return DEFAULT_INQUIRY_SENDER_NAME_UK
    return cleaned or DEFAULT_INQUIRY_SENDER_NAME_UK


def inquiry_company_name() -> str:
    from scraper_env import get_env_value

    company = strip_de_campaign_branding(get_env_value("INQUIRY_COMPANY_NAME").strip())
    if _is_legacy_de_sender_name(company):
        return ""
    return company


def inquiry_phone() -> str:
    from scraper_env import get_env_value

    phone = get_env_value("INQUIRY_PHONE").strip()
    if phone and not is_german_phone(phone):
        return phone
    return DEFAULT_INQUIRY_PHONE_UK


def inquiry_website() -> str:
    from scraper_env import get_env_value

    return get_env_value("INQUIRY_WEBSITE").strip()


def build_inquiry_signature_uk() -> str:
    lines = ["З повагою,", ""]
    name = inquiry_sender_name()
    if name:
        lines.append(name)
    company = inquiry_company_name()
    if company:
        lines.extend(["", company])
    web = inquiry_website()
    if web:
        lines.extend(["", web])
    phone = inquiry_phone()
    lines.extend(["", f"Tel.: {phone}"])
    return strip_de_campaign_branding(strip_german_phones_from_text("\n".join(lines).strip()))


def build_inquiry_sender_brief_uk() -> str:
    company = inquiry_company_name()
    who = company if company else "Покупець будівельних матеріалів"
    return (
        f"{who} шукає постачальників будівельних матеріалів в Україні для регулярних "
        "оптових закупівель (цемент, пісок, щебінь, цегла, блоки, арматура, утеплювач, "
        "сухі суміші, покрівля тощо)."
    )


def build_sender_contact_line_uk() -> str:
    parts: list[str] = []
    name = inquiry_sender_name()
    if name:
        parts.append(name)
    company = inquiry_company_name()
    if company:
        parts.append(company)
    web = inquiry_website()
    if web:
        parts.append(web)
    phone = inquiry_phone()
    parts.append(f"Tel. {phone}")
    return strip_de_campaign_branding(strip_german_phones_from_text(", ".join(parts)))


def build_fixed_material_inquiry_uk() -> str:
    intro = (
        "звертаюся до Вас щодо можливості постачання будівельних матеріалів в Україні "
        "на умовах опту."
    )
    if inquiry_company_name():
        intro = (
            f"звертаюся до Вас від імені {inquiry_company_name()}. "
            "Ми шукаємо надійних постачальників будівельних матеріалів в Україні "
            "для регулярних закупівель."
        )
    return f"""Шановні пані та панове,

{intro}

Нас цікавить широкий асортимент: цемент, пісок, щебінь, цегла, блоки, арматура, утеплювачі, сухі суміші, покрівельні матеріали та суміжна продукція. Важливі умови оптових цін, наявність на складі та можливість доставки.

Будь ласка, надішліть актуальний прайс-лист або вкажіть контактну особу з відділу продажів / опту.

Дякуємо за співпрацю.

{build_inquiry_signature_uk()}"""


FIXED_MATERIAL_INQUIRY_UK = build_fixed_material_inquiry_uk()

# Kompatybilność wsteczna — wywołania dynamiczne (env może się zmienić)
def inquiry_email_signature_uk() -> str:
    return build_inquiry_signature_uk()


def inquiry_sender_brief_uk() -> str:
    return build_inquiry_sender_brief_uk()


INQUIRY_EMAIL_SIGNATURE_UK = build_inquiry_signature_uk()
INQUIRY_SENDER_BRIEF_UK = build_inquiry_sender_brief_uk()
