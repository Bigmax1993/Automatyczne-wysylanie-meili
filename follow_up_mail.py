"""
Lista i eksport kontaktów do ponownej wysyłki na podstawie rejestru JSONL (sent_mail_registry).

Program nie czyta skrzynki — „brak odpowiedzi” = nie ustawiono reply_received (patrz: mark-reply).
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

import contact_mailer as cm
import pipeline_version as pv
from sent_mail_registry import (
    cleanup_stale_registry_files,
    follow_up_candidates,
    mark_reply_received,
    registry_dir,
)


def _strip_internal_keys(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if not str(k).startswith("_")}


def cmd_list(args: argparse.Namespace) -> int:
    rows = follow_up_candidates(
        min_age_days=args.days,
        registry_directory=args.registry_dir or None,
    )
    if not rows:
        print("(brak kandydatów — sprawdź wiek w dniach, katalog rejestru lub oznaczenia reply_received)")
        return 0
    for r in sorted(rows, key=lambda x: x.get("sent_at") or ""):
        print(
            f"{r.get('sent_at', '')}\t{r.get('email', '')}\t{r.get('company', '')}\t"
            f"{r.get('batch_file', '')}\t{r.get('_registry_file', '')}"
        )
    print(f"\nŁącznie: {len(rows)}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    rows = follow_up_candidates(
        min_age_days=args.days,
        registry_directory=args.registry_dir or None,
    )
    if not rows:
        print("Brak kandydatów do eksportu.", file=sys.stderr)
        return 1
    out_path = os.path.abspath(args.output)
    records = []
    for r in rows:
        clean = _strip_internal_keys(r)
        extra = (
            f"follow-up po wysyłce z {clean.get('sent_at', '')}; "
            f"poprzedni temat: {clean.get('subject', '')}"
        )
        base = str(clean.get("notes", "") or "").strip()
        notes_val = f"{base} | {extra}" if base else extra
        records.append(
            {
                cm.COL_COMPANY: clean.get("company", ""),
                cm.COL_CITY: clean.get("city", ""),
                cm.COL_INDUSTRY: clean.get("industry", ""),
                cm.COL_ROLE: clean.get("role", ""),
                cm.COL_WEBSITE: clean.get("website", ""),
                cm.COL_EMAIL: clean.get("email", ""),
                cm.COL_PHONE: clean.get("phone", ""),
                cm.COL_MODE: clean.get("mode", ""),
                cm.COL_SOURCE: clean.get("source", ""),
                cm.COL_NOTES: notes_val,
                cm.STATUS_COL: "",
                cm.DATE_COL: "",
                "Walidacja": "OK",
                "Uwagi walidacji": "",
            }
        )
    df = pd.DataFrame(records)
    if out_path.lower().endswith(".csv"):
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
    else:
        df.to_excel(out_path, index=False)
    print(f"Zapisano {len(df)} wierszy: {out_path}")
    print(
        "Następnie uruchom pipeline na tym pliku (np. clean_validate_send_pipeline.py --input ...). "
        "Po otrzymaniu odpowiedzi: follow_up_mail.py mark-reply --email ADRES"
    )
    return 0


def cmd_mark_reply(args: argparse.Namespace) -> int:
    n = mark_reply_received(
        args.email,
        registry_directory=args.registry_dir or None,
    )
    print(f"Oznaczono reply_received dla {n} wpisów (e-mail: {args.email}).")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Follow-up: rejestr wysłanych maili (JSONL) — lista / eksport / oznaczenie odpowiedzi"
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"follow_up_mail {pv.PIPELINE_VERSION}",
    )
    sub = p.add_subparsers(dest="command", required=True)

    pl = sub.add_parser("list", help="Wypisz kandydatów (min. N dni od wysyłki, bez follow_up_sent / reply)")
    pl.add_argument(
        "--days",
        type=int,
        default=int(os.environ.get("FOLLOW_UP_MIN_DAYS", "7")),
        help="Minimalna liczba dni od sent_at (domyślnie 7 lub FOLLOW_UP_MIN_DAYS)",
    )
    pl.add_argument(
        "--registry-dir",
        dest="registry_dir",
        default="",
        help=f"Katalog z plikami .jsonl (domyślnie: {registry_dir()})",
    )
    pl.set_defaults(func=cmd_list)

    pe = sub.add_parser("export", help="Eksport kandydatów do XLSX lub CSV pod ponowną wysyłkę")
    pe.add_argument(
        "--days",
        type=int,
        default=int(os.environ.get("FOLLOW_UP_MIN_DAYS", "7")),
    )
    pe.add_argument(
        "--registry-dir",
        dest="registry_dir",
        default="",
    )
    pe.add_argument(
        "--output",
        "-o",
        required=True,
        help="Ścieżka wyjściowa .xlsx lub .csv",
    )
    pe.set_defaults(func=cmd_export)

    pm = sub.add_parser(
        "mark-reply",
        help="Oznacz, że na ten adres przyszła odpowiedź (wykluczy z kolejnych follow-upów)",
    )
    pm.add_argument("--email", required=True)
    pm.add_argument(
        "--registry-dir",
        dest="registry_dir",
        default="",
    )
    pm.set_defaults(func=cmd_mark_reply)

    args = p.parse_args()
    try:
        rd = (args.registry_dir or "").strip() or None
        n_del = cleanup_stale_registry_files(registry_directory=rd)
        if n_del:
            print(f"Rejestr JSON: usunięto {n_del} przeterminowanych plików .jsonl (retencja dni).")
    except Exception as e:
        print(f"Ostrzeżenie: czyszczenie rejestru .jsonl: {e}", file=sys.stderr)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
