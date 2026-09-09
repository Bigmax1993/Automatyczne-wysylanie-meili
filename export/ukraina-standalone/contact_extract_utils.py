# -*- coding: utf-8 -*-
"""Normalizacja e-maili i telefonów ze stron www (regex / mailto)."""
from __future__ import annotations

import json
import re

from commercial_contact_filter import filter_commercial_emails

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)
_PHONE_SKIP_DIGIT_PREFIXES = ("19", "20")


def normalize_email_contact(raw: str) -> str:
    low = (raw or "").strip().lower()
    low = re.sub(r"^mailto:\s*", "", low)
    low = low.split("?")[0].split("#")[0].strip(".,;:()[]{}<>\"'`")
    if "@" not in low:
        return ""
    local, _, domain = low.partition("@")
    local, domain = local.strip(), domain.strip().rstrip(".")
    if not local or not domain or "." not in domain:
        return ""
    if len(local) < 1 or len(local) > 50:
        return ""
    return f"{local}@{domain}"


def normalize_phone_contact(raw: str) -> str:
    normalized = " ".join((raw or "").split()).strip(".,;:()[]")
    if not normalized:
        return ""
    digits = re.sub(r"\D", "", normalized)
    if len(digits) < 7:
        return ""
    if len(digits) in (4, 8) and digits.startswith(_PHONE_SKIP_DIGIT_PREFIXES):
        return ""
    if digits.startswith("49") and len(digits) < 10:
        return ""
    if digits.startswith("0049"):
        digits = "49" + digits[4:]
    if digits.startswith("49") and not normalized.startswith("+"):
        rest = digits[2:]
        if len(rest) >= 9:
            normalized = f"+49 {rest[:3]} {rest[3:]}".strip()
    return normalized


def parse_contact_extract_response(text: str) -> dict:
    raw = (text or "").strip()
    match = _JSON_BLOCK_RE.search(raw)
    payload = match.group(0) if match else raw
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("Contact extract: not a JSON object")

    emails: list[str] = []
    for item in data.get("emails") or []:
        norm = normalize_email_contact(str(item))
        if norm and norm not in emails:
            emails.append(norm)
    emails = filter_commercial_emails(emails)

    impressum_emails: list[str] = []
    for item in data.get("impressum_emails") or []:
        norm = normalize_email_contact(str(item))
        if norm and norm not in impressum_emails:
            impressum_emails.append(norm)
    impressum_emails = filter_commercial_emails(impressum_emails)

    phones: list[str] = []
    for item in data.get("phones") or []:
        norm = normalize_phone_contact(str(item))
        if norm and norm not in phones:
            phones.append(norm)

    company_name = " ".join(str(data.get("company_name") or "").split()).strip()
    reason = str(data.get("reason") or "").strip()
    company_names = [company_name] if company_name else []
    return {
        "company_name": company_name,
        "company_names": company_names,
        "emails": emails,
        "impressum_emails": impressum_emails,
        "phones": phones,
        "reason": reason,
    }
