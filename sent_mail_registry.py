"""
Rejestr wysłanych maili (JSON Lines) — jeden plik .jsonl na partię (np. Kontakty_serpapi.xlsx).

Umożliwia po ~7 dniach wylistowanie kontaktów bez oznaczonej odpowiedzi i eksport do XLSX pod ponowną wysyłkę.
Nie wykrywa odpowiedzi z skrzynki: pole reply_received ustawiasz ręcznie (follow_up_mail.py) lub edycją pliku.

Domyślnie pliki .jsonl z najnowszym wpisem starszym niż 14 dni są usuwane przy starcie pipeline / mailera / follow_up_mail
(zmienna SENT_MAIL_REGISTRY_RETENTION_DAYS, 0 = bez usuwania).
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)


def _running_pytest() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def registry_enabled() -> bool:
    if _running_pytest():
        return False
    return os.environ.get("SENT_MAIL_REGISTRY_ENABLED", "1").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def registry_dir() -> str:
    raw = os.environ.get("SENT_MAIL_REGISTRY_DIR", "").strip()
    if raw:
        return os.path.abspath(raw)
    return os.path.abspath(
        os.path.join(
            os.path.expanduser("~"),
            "Documents",
            "pipeline_logs",
            "sent_mail_registry",
        )
    )


def safe_batch_stem(batch_path: str) -> str:
    base = os.path.basename(batch_path or "") or "batch"
    stem, _ = os.path.splitext(base)
    stem = re.sub(r"[^\w\-.]+", "_", stem, flags=re.UNICODE).strip("._")
    return (stem or "batch")[:80]


def jsonl_path_for_batch(batch_path: str) -> str:
    d = registry_dir()
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{safe_batch_stem(batch_path)}.jsonl")


def registry_retention_days() -> int:
    """Liczba dni przechowywania plików .jsonl; 0 = nie usuwaj."""
    if _running_pytest():
        return 0
    raw = os.environ.get("SENT_MAIL_REGISTRY_RETENTION_DAYS", "14").strip()
    try:
        n = int(raw if raw != "" else "14")
    except ValueError:
        return 14
    return max(0, n)


def _max_sent_at_in_jsonl(path: str) -> Optional[datetime]:
    max_dt: Optional[datetime] = None
    for r in _load_jsonl_file(path):
        ts = _parse_sent_at(r.get("sent_at"))
        if ts is None:
            continue
        if max_dt is None or ts > max_dt:
            max_dt = ts
    return max_dt


def cleanup_stale_registry_files(registry_directory: Optional[str] = None) -> int:
    """
    Usuwa pliki .jsonl, w których najnowszy sent_at jest starszy niż registry_retention_days().
    Gdy brak poprawnych sent_at, decyduje data modyfikacji pliku na dysku.
    Zwraca liczbę usuniętych plików.
    """
    days = registry_retention_days()
    if days <= 0:
        return 0
    d = registry_directory or registry_dir()
    if not os.path.isdir(d):
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    removed = 0
    for fn in os.listdir(d):
        if not fn.endswith(".jsonl"):
            continue
        path = os.path.join(d, fn)
        if not os.path.isfile(path):
            continue
        max_ts = _max_sent_at_in_jsonl(path)
        if max_ts is not None:
            stale = max_ts < cutoff
        else:
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
            except OSError:
                continue
            stale = mtime < cutoff
        if not stale:
            continue
        try:
            os.remove(path)
            removed += 1
            logger.info("Usunięto przeterminowany rejestr wysyłek (>%s dni): %s", days, fn)
        except OSError as e:
            logger.warning("Nie udało się usunąć %s: %s", path, e)
    return removed


def _parse_sent_at(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def iter_registry_records(registry_directory: Optional[str] = None) -> Iterator[Dict[str, Any]]:
    d = registry_directory or registry_dir()
    if not os.path.isdir(d):
        return
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".jsonl"):
            continue
        fp = os.path.join(d, fn)
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        obj["_registry_file"] = fn
                        yield obj
                except json.JSONDecodeError:
                    logger.warning("Pominięto uszkodzoną linię w %s", fp)


def _load_jsonl_file(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not os.path.isfile(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
                if isinstance(o, dict):
                    rows.append(o)
            except json.JSONDecodeError:
                logger.warning("Pominięto uszkodzoną linię w %s", path)
    return rows


def _atomic_write_jsonl(path: str, records: List[Dict[str, Any]]) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def _rewrite_registry_file(path: str, mutator: Callable[[List[Dict[str, Any]]], bool]) -> None:
    if not os.path.isfile(path):
        return
    recs = _load_jsonl_file(path)
    if not mutator(recs):
        return
    _atomic_write_jsonl(path, recs)


def close_prior_pending_same_email(email: str, exclude_record_id: str) -> None:
    """Ustawia follow_up_sent_at na wcześniejszych, jeszcze otwartych wpisach z tym samym e-mailem."""
    em = (email or "").strip().lower()
    if not em or not exclude_record_id:
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    d = registry_dir()
    if not os.path.isdir(d):
        return

    def mutator(recs: List[Dict[str, Any]]) -> bool:
        changed = False
        for r in recs:
            if (r.get("email") or "").strip().lower() != em:
                continue
            if r.get("record_id") == exclude_record_id:
                continue
            if r.get("reply_received"):
                continue
            if r.get("follow_up_sent_at"):
                continue
            r["follow_up_sent_at"] = now_iso
            changed = True
        return changed

    for fn in os.listdir(d):
        if not fn.endswith(".jsonl"):
            continue
        _rewrite_registry_file(os.path.join(d, fn), mutator)


def append_sent_record(
    *,
    batch_path: str,
    output_csv_path: str,
    email: str,
    company: str,
    role: str,
    city: str,
    industry: str,
    website: str,
    phone: str,
    mode: str,
    source: str,
    notes: str,
    subject: str,
    locale: str,
    dry_run: bool,
) -> None:
    if not registry_enabled() or dry_run:
        return
    em = (email or "").strip().lower()
    if not em:
        return

    path = jsonl_path_for_batch(batch_path)
    prior = _has_open_pending_initial(em)
    kind = "follow_up" if prior else "initial"

    rec: Dict[str, Any] = {
        "record_id": str(uuid.uuid4()),
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "email": em,
        "company": company,
        "role": role,
        "city": city,
        "industry": industry,
        "website": website,
        "phone": phone,
        "mode": mode,
        "source": source,
        "notes": notes,
        "subject": subject,
        "locale": locale,
        "batch_file": os.path.basename(batch_path),
        "output_csv": os.path.basename(output_csv_path),
        "kind": kind,
        "reply_received": False,
        "follow_up_sent_at": None,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    close_prior_pending_same_email(em, rec["record_id"])


def _has_open_pending_initial(email: str) -> bool:
    em = (email or "").strip().lower()
    for r in iter_registry_records():
        if (r.get("email") or "").strip().lower() != em:
            continue
        if r.get("reply_received"):
            continue
        if r.get("follow_up_sent_at"):
            continue
        return True
    return False


def follow_up_candidates(
    min_age_days: int,
    registry_directory: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Wpisy nadające się na przypomnienie: min_age_days od sent_at, brak reply_received,
    brak follow_up_sent_at (nie wysłano jeszcze drugiej fazy z tego łańcucha).
    """
    if min_age_days < 0:
        min_age_days = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=min_age_days)
    pending: List[Dict[str, Any]] = []
    for r in iter_registry_records(registry_directory):
        if r.get("reply_received"):
            continue
        if r.get("follow_up_sent_at"):
            continue
        ts = _parse_sent_at(r.get("sent_at"))
        if ts is None or ts > cutoff:
            continue
        pending.append(r)

    # Jedna pozycja na e-mail: najstarsze sent_at (pierwsza wysyłka do follow-upu)
    by_email: Dict[str, Dict[str, Any]] = {}
    for r in sorted(pending, key=lambda x: x.get("sent_at") or ""):
        e = (r.get("email") or "").strip().lower()
        if e and e not in by_email:
            by_email[e] = r
    return list(by_email.values())


def mark_reply_received(email: str, registry_directory: Optional[str] = None) -> int:
    """Oznacza reply_received=True dla wszystkich wpisów z tym e-mailem we wszystkich .jsonl."""
    em = (email or "").strip().lower()
    if not em:
        return 0
    d = registry_directory or registry_dir()
    if not os.path.isdir(d):
        return 0
    total = 0
    for fn in os.listdir(d):
        if not fn.endswith(".jsonl"):
            continue
        path = os.path.join(d, fn)

        def mutator(recs: List[Dict[str, Any]]) -> bool:
            nonlocal total
            changed = False
            for r in recs:
                if (r.get("email") or "").strip().lower() != em:
                    continue
                if r.get("reply_received"):
                    continue
                r["reply_received"] = True
                total += 1
                changed = True
            return changed

        _rewrite_registry_file(path, mutator)
    return total
