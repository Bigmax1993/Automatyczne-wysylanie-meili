#!/usr/bin/env python3
"""Wyślij wygenerowany raport PDF na wskazany adres (Gmail SMTP)."""

from __future__ import annotations

import argparse
import os
import re
import smtplib
from email.message import EmailMessage
from pathlib import Path

DEFAULT_SENDER = "svinchak1993@gmail.com"


def normalize_gmail_app_password(raw: str | None) -> str:
    if not raw:
        return ""
    return re.sub(r"\s+", "", raw.strip())


def resolve_sender_email() -> str:
    return (
        os.environ.get("GMAIL_SENDER_EMAIL")
        or os.environ.get("SENDER_EMAIL")
        or DEFAULT_SENDER
    ).strip()


def send_pdf(pdf_path: Path, to_email: str, subject: str, body: str) -> None:
    password = normalize_gmail_app_password(os.environ.get("GMAIL_APP_PASSWORD"))
    if not password:
        raise SystemExit(
            "Brak GMAIL_APP_PASSWORD. Ustaw hasło aplikacji Gmail (16 znaków) w środowisku "
            "lub uruchom lokalnie: .\\run_with_env.ps1 po skonfigurowaniu local_env.ps1."
        )
    sender = resolve_sender_email()
    if not pdf_path.is_file():
        raise SystemExit(f"Brak pliku PDF: {pdf_path}")

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    msg.add_attachment(
        pdf_path.read_bytes(),
        maintype="application",
        subtype="pdf",
        filename=pdf_path.name,
    )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)
    print(f"Wysłano: {pdf_path.name} → {to_email} (From: {sender})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pdf",
        type=Path,
        default=Path("/opt/cursor/artifacts/Raport_ABTM_spedytor_due_diligence.pdf"),
    )
    parser.add_argument("--to", default="svinchak1993@gmail.com")
    parser.add_argument(
        "--subject",
        default="Raport due diligence — ABTM Sp. z o.o. (spedytor)",
    )
    args = parser.parse_args()
    body = (
        "W załączniku raport PDF: due diligence pracodawcy ABTM Sp. z o.o. (Leszno), "
        "kontekst aplikacji na stanowisko spedytora.\n\n"
        "Wygenerowano automatycznie na podstawie publicznych danych KRS/RDF i agregatorów.\n"
    )
    send_pdf(args.pdf, args.to, args.subject, body)


if __name__ == "__main__":
    main()
