# -*- coding: utf-8 -*-
"""Dziennik operacji e-mail (odczyt / wysyłka) — widoczny w GUI."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pipeline_registry import BASE_DIR

JOURNAL_PATH = BASE_DIR / "gui_data" / "email_journal.json"
MAX_ENTRIES = 400

KIND_READ = "odczyt"
KIND_MATCH = "dopasowanie"
KIND_SEND = "wysyłka"
KIND_SCAN = "skan"
KIND_ERROR = "błąd"


def _load() -> list[dict[str, Any]]:
    if not JOURNAL_PATH.exists():
        return []
    try:
        with open(JOURNAL_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        return raw if isinstance(raw, list) else []
    except Exception:
        return []


def _save(items: list[dict[str, Any]]) -> None:
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    trimmed = items[-MAX_ENTRIES:]
    with open(JOURNAL_PATH, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)


def log_email_event(
    kind: str,
    summary: str,
    *,
    detail: str = "",
    campaign: str = "",
    address: str = "",
    subject: str = "",
) -> None:
    items = _load()
    items.append(
        {
            "at": datetime.now().isoformat(timespec="seconds"),
            "kind": kind,
            "summary": summary[:500],
            "detail": (detail or "")[:1000],
            "campaign": campaign,
            "address": address,
            "subject": (subject or "")[:200],
        }
    )
    _save(items)


def log_imap_scan_start(since: datetime, campaign: str = "") -> None:
    log_email_event(
        KIND_SCAN,
        f"Łączenie ze skrzynką Gmail — szukam maili od {since.strftime('%Y-%m-%d')}",
        campaign=campaign,
    )


def log_imap_scan_end(message_count: int, campaign: str = "") -> None:
    log_email_event(
        KIND_SCAN,
        f"Pobrano {message_count} wiadomości ze skrzynki",
        campaign=campaign,
    )


def log_mail_read(
    from_addr: str,
    subject: str,
    *,
    matched: bool,
    reply_status: str = "",
    company: str = "",
    campaign: str = "",
) -> None:
    subj = (subject or "(bez tematu)")[:120]
    if matched:
        co = (company or from_addr)[:80]
        st = f" ({reply_status})" if reply_status else ""
        log_email_event(
            KIND_MATCH,
            f"Odpowiedź od {co}{st}",
            detail=subj,
            address=from_addr,
            subject=subject,
            campaign=campaign,
        )
    else:
        log_email_event(
            KIND_READ,
            f"Odczytano mail od {from_addr} — nie przypisano do listy firm",
            detail=subj,
            address=from_addr,
            subject=subject,
            campaign=campaign,
        )


def log_mail_sent(
    to_addr: str,
    subject: str,
    *,
    mail_type: str = "wiadomość",
    campaign: str = "",
    ok: bool = True,
    error: str = "",
) -> None:
    if ok:
        log_email_event(
            KIND_SEND,
            f"Wysłano {mail_type} → {to_addr}",
            detail=(subject or "")[:200],
            address=to_addr,
            subject=subject,
            campaign=campaign,
        )
    else:
        log_email_event(
            KIND_ERROR,
            f"Nie wysłano {mail_type} → {to_addr}",
            detail=error[:500],
            address=to_addr,
            subject=subject,
            campaign=campaign,
        )


def log_sync_summary(updated: int, campaign: str = "") -> None:
    log_email_event(
        KIND_SCAN,
        f"Zaktualizowano {updated} kontakt(ów) na podstawie maili",
        campaign=campaign,
    )


def list_journal_entries(limit: int = 80) -> list[dict[str, Any]]:
    items = _load()
    out = []
    for row in reversed(items[-limit:]):
        at = str(row.get("at", ""))
        time_short = at[11:19] if len(at) >= 19 else at
        out.append(
            {
                "Godzina": time_short,
                "Data": at[:10] if len(at) >= 10 else "",
                "Typ": _kind_label(str(row.get("kind", ""))),
                "Opis": row.get("summary", ""),
                "Szczegóły": row.get("detail", ""),
                "Adres": row.get("address", ""),
            }
        )
    return out


def _kind_label(kind: str) -> str:
    return {
        KIND_READ: "Odczyt",
        KIND_MATCH: "Odpowiedź",
        KIND_SEND: "Wysyłka",
        KIND_SCAN: "Skan skrzynki",
        KIND_ERROR: "Błąd",
    }.get(kind, kind)


def clear_journal() -> int:
    n = len(_load())
    _save([])
    return n
