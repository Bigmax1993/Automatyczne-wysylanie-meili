# -*- coding: utf-8 -*-
"""
Wspólna warstwa poczty: yagmail (Gmail / SMTP) + archiwum IMAP i lokalne .eml.
"""
from __future__ import annotations

import logging
import mimetypes
import re
import imaplib
import shutil
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Any

from polish_text import sanitize_email_body, sanitize_special_text
from scraper_env import (
    ENV_GMAIL_APP_PASSWORD,
    ENV_GMAIL_USER,
    ENV_IMAP_HOST,
    ENV_IMAP_PORT,
    ENV_IMAP_SSL,
    ENV_MAIL_ARCHIVE_IMAP,
    ENV_MAIL_BCC,
    ENV_MAIL_CC,
    ENV_MAIL_PASSWORD,
    ENV_MAIL_SENDER_NAME,
    ENV_MAIL_USER,
    ENV_SMTP_HOST,
    ENV_SMTP_PORT,
    ENV_SMTP_SSL,
    get_env_value,
    get_mail_password,
    get_mail_sender_name,
    get_mail_user,
)

_DEFAULT_HOMEPL_SMTP = "serwer.home.pl"
_DEFAULT_HOMEPL_IMAP = "serwer.home.pl"
_DEFAULT_SMTP_PORT_SSL = 465
_DEFAULT_SMTP_PORT_STARTTLS = 587
_DEFAULT_IMAP_PORT_SSL = 993


def _truthy(raw: str) -> bool:
    return str(raw or "").strip().lower() in ("1", "true", "yes", "tak", "on")


def _mail_address() -> str:
    return (get_mail_user() or "").strip().lower()


def _is_gmail_address(addr: str) -> bool:
    return bool(addr) and ("@gmail.com" in addr or "@googlemail.com" in addr)


def get_smtp_host() -> str:
    host = get_env_value(ENV_SMTP_HOST).strip()
    if host:
        return host
    if _is_gmail_address(_mail_address()):
        return "smtp.gmail.com"
    return _DEFAULT_HOMEPL_SMTP


def get_imap_host() -> str:
    host = get_env_value(ENV_IMAP_HOST).strip()
    if host:
        return host
    if _is_gmail_address(_mail_address()):
        return "imap.gmail.com"
    return _DEFAULT_HOMEPL_IMAP


def mail_provider_label() -> str:
    smtp = get_smtp_host().lower()
    addr = _mail_address()
    if "home.pl" in smtp or (addr and addr.endswith("@home.pl")):
        return "home.pl"
    if _is_gmail_address(addr) or "gmail" in smtp:
        return "Gmail"
    if smtp:
        return smtp
    if addr and "@" in addr:
        domain = addr.split("@", 1)[1]
        return domain or "SMTP"
    return ""


def _smtp_port() -> int:
    raw = get_env_value(ENV_SMTP_PORT).strip()
    if raw.isdigit():
        return int(raw)
    if _truthy(get_env_value(ENV_SMTP_SSL)):
        return _DEFAULT_SMTP_PORT_SSL
    return _DEFAULT_SMTP_PORT_STARTTLS


def _imap_port() -> int:
    raw = get_env_value(ENV_IMAP_PORT).strip()
    if raw.isdigit():
        return int(raw)
    return _DEFAULT_IMAP_PORT_SSL


def _smtp_use_ssl() -> bool:
    if get_env_value(ENV_SMTP_SSL).strip():
        return _truthy(get_env_value(ENV_SMTP_SSL))
    return _smtp_port() == _DEFAULT_SMTP_PORT_SSL


def _sanitize_sender_name(name: str) -> str:
    return " ".join((name or "").replace("\n", " ").split()).strip()


def _split_recipients(raw: str) -> list[str]:
    if not raw:
        return []
    if str(raw).strip().lower() in ("0", "off", "false", "no", "nie"):
        return []
    parts = re.split(r"[,;]+", raw)
    return [p.strip() for p in parts if p.strip()]


# Opcjonalna stała Cc — pusta; użyj MAIL_CC w .env jeśli potrzebujesz kopii.
EMAIL_ALWAYS_CC: tuple[str, ...] = ()


def merge_mail_cc_recipients(primary_to: str, extra_env_cc: str = "") -> list[str]:
    """MAIL_CC z .env + EMAIL_ALWAYS_CC (bez duplikatu i bez adresu głównego odbiorcy)."""
    out: list[str] = []
    to_norm = (primary_to or "").strip().lower()
    seen: set[str] = set()
    for addr in list(_split_recipients(extra_env_cc)) + list(EMAIL_ALWAYS_CC):
        a = (addr or "").strip()
        if not a:
            continue
        key = a.lower()
        if key == to_norm or key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def get_wyslane_dir() -> Path:
    """Lokalny folder kopii wysłanych maili (.eml)."""
    try:
        from project_config import get_data_root

        root = get_data_root()
    except Exception:
        root = Path(__file__).resolve().parent
    return root / "wyslane"


def _safe_eml_stem(text: str, max_len: int = 48) -> str:
    stem = re.sub(r"[^\w.\-]+", "_", (text or "").strip(), flags=re.UNICODE)
    return (stem[:max_len] or "mail").strip("._")


def _build_sent_email_message(
    username: str,
    to_email: str,
    subject: str,
    body: str,
    *,
    cc: list[str],
    attachment_paths: list[str] | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    sender_name = _sanitize_sender_name(get_mail_sender_name())
    if sender_name:
        msg["From"] = f"{sender_name} <{username}>"
    else:
        msg["From"] = username
    msg["To"] = to_email
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.set_content(body)
    for ap in attachment_paths or []:
        p = Path(ap)
        if not p.is_file():
            continue
        data = p.read_bytes()
        ctype, _enc = mimetypes.guess_type(str(p))
        if ctype and "/" in ctype:
            maintype, subtype = ctype.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"
        msg.add_attachment(
            data,
            maintype=maintype,
            subtype=subtype,
            filename=p.name,
        )
    return msg


def _save_wyslane_eml(
    msg: EmailMessage,
    to_email: str,
    subject: str,
    attachment_paths: list[str] | None,
) -> Path:
    folder = get_wyslane_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    recipient = _safe_eml_stem(to_email.replace("@", "_at_"))
    subj = _safe_eml_stem(subject)
    path = folder / f"{stamp}_{recipient}_{subj}.eml"
    path.write_bytes(msg.as_bytes())
    if attachment_paths:
        att_dir = folder / "zalaczniki" / f"{stamp}_{recipient}"
        att_dir.mkdir(parents=True, exist_ok=True)
        for src in attachment_paths:
            src_path = Path(src)
            if src_path.is_file():
                shutil.copy2(src_path, att_dir / src_path.name)
    return path


def _imap_mailbox_names(mail: imaplib.IMAP4_SSL) -> list[str]:
    try:
        typ, data = mail.list()
    except Exception:
        return []
    if typ != "OK" or not data:
        return []
    names: list[str] = []
    for raw in data:
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace")
        if ' "' in line:
            name = line.rsplit(' "', 1)[-1].rstrip('"')
        else:
            parts = line.split(" ")
            name = parts[-1].strip('"') if parts else ""
        if name:
            names.append(name)
    return names


def _resolve_sent_mailbox(
    mail: imaplib.IMAP4_SSL,
    logger: logging.Logger | None = None,
) -> str | None:
    """Znajdź folder Wysłane / Sent na serwerze IMAP."""
    mailbox_names = _imap_mailbox_names(mail)
    if logger and mailbox_names:
        logger.debug("IMAP foldery: %s", ", ".join(mailbox_names[:20]))

    preferred = (
        "Wysłane",
        "Wyslane",
        "INBOX.Wysłane",
        "INBOX.Wyslane",
        "Sent",
        "Sent Items",
        "INBOX.Sent",
        "INBOX.Sent Items",
        "[Gmail]/Sent Mail",
        "Gesendet",
        "INBOX.Gesendet",
    )
    lowered = {m.lower(): m for m in mailbox_names}
    for candidate in preferred:
        found = lowered.get(candidate.lower())
        if found:
            return found
    for name in mailbox_names:
        low = name.lower()
        if "sent" in low or "wys" in low or "gesendet" in low:
            return name
    return None


def _try_create_sent_mailbox(mail: imaplib.IMAP4_SSL) -> str | None:
    for candidate in (
        "INBOX.Wyslane",
        "Wyslane",
        "INBOX.Sent",
        "Sent",
    ):
        try:
            typ, _ = mail.create(candidate)
            if typ == "OK":
                return candidate
        except Exception:
            continue
    return None


def _append_to_imap_sent(
    username: str,
    password: str,
    msg: EmailMessage,
    logger: logging.Logger,
) -> bool:
    """Dopisz wysłaną wiadomość do folderu Wysłane na serwerze IMAP."""
    if not _truthy(get_env_value(ENV_MAIL_ARCHIVE_IMAP) or "1"):
        return True
    imap_host = get_imap_host()
    if not imap_host:
        logger.warning("Brak IMAP_HOST — pominięto zapis do folderu Wysłane na serwerze.")
        return False

    mail = imaplib.IMAP4_SSL(imap_host, _imap_port())
    try:
        mail.login(username, password)
        mailbox = _resolve_sent_mailbox(mail, logger)
        if not mailbox:
            mailbox = _try_create_sent_mailbox(mail)
        if not mailbox:
            names = _imap_mailbox_names(mail)
            logger.warning(
                "Nie znaleziono folderu Wysłane/Sent na IMAP (dostępne: %s). "
                "Kopia jest w folderze lokalnym: %s",
                ", ".join(names[:12]) or "(brak listy)",
                get_wyslane_dir(),
            )
            return False
        payload = msg.as_bytes()
        typ, data = mail.append(
            mailbox,
            "\\Seen",
            imaplib.Time2Internaldate(time.time()),
            payload,
        )
        if typ != "OK":
            logger.warning(
                "IMAP APPEND do '%s' nie powiódł się: %s %s",
                mailbox,
                typ,
                data,
            )
            return False
        logger.info("Zapisano kopię w folderze Wysłane (IMAP): %s", mailbox)
        return True
    except Exception as e:
        logger.warning(
            "Błąd zapisu do folderu Wysłane (IMAP %s): %s — kopia lokalna: %s",
            imap_host,
            e,
            get_wyslane_dir(),
        )
        return False
    finally:
        try:
            mail.logout()
        except Exception:
            pass


def archive_sent_message(
    to_email: str,
    subject: str,
    body: str,
    logger: logging.Logger,
    *,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    attachment_paths: list[str] | None = None,
) -> None:
    """
    Po udanej wysyłce SMTP: kopia .eml w folderze wyslane/ oraz dopisanie do IMAP Wysłane.
    """
    username = get_mail_user()
    password = get_mail_password()
    if not username:
        return
    cc_list = list(cc or [])
    msg = _build_sent_email_message(
        username,
        to_email,
        subject,
        body,
        cc=cc_list,
        attachment_paths=attachment_paths,
    )
    try:
        local_path = _save_wyslane_eml(msg, to_email, subject, attachment_paths)
        logger.info("Kopia wysłanego maila (folder wyslane): %s", local_path)
    except Exception as e:
        logger.warning("Nie zapisano kopii w folderze wyslane: %s", e)
    if password:
        _append_to_imap_sent(username, password, msg, logger)


def archive_sent_email_message(
    msg: EmailMessage,
    logger: logging.Logger,
    *,
    to_email: str = "",
    subject: str = "",
    attachment_paths: list[str] | None = None,
) -> None:
    """
    Po SMTP: kopia .eml (wyslane/) + ten sam Message do folderu Wysłane (IMAP).
    Użyj tej samej instancji msg co wysłano — widać Cc, załącznik i treść w skrzynce.
    """
    username = get_mail_user()
    password = get_mail_password()
    to_email = to_email or str(msg.get("To", ""))
    subject = subject or str(msg.get("Subject", ""))
    try:
        local_path = _save_wyslane_eml(msg, to_email, subject, attachment_paths)
        logger.info("Kopia wysłanego maila (folder wyslane): %s", local_path)
    except Exception as e:
        logger.warning("Nie zapisano kopii w folderze wyslane: %s", e)
    if not password:
        logger.warning("Brak MAIL_PASSWORD — pominięto zapis IMAP Wysłane.")
        return
    if not _truthy(get_env_value(ENV_MAIL_ARCHIVE_IMAP) or "1"):
        logger.warning(
            "MAIL_ARCHIVE_IMAP=0 — wiadomość nie trafi do folderu Wysłane na serwerze. "
            "Ustaw MAIL_ARCHIVE_IMAP=1 w .env."
        )
        return
    ok = _append_to_imap_sent(username, password, msg, logger)
    if not ok:
        logger.warning(
            "Sprawdź IMAP_HOST (%s) i folder Wysłane/Sent w webmailu.",
            get_imap_host(),
        )


def _yagmail_smtp() -> Any:
    import yagmail  # pyright: ignore[reportMissingImports]

    username = get_mail_user()
    password = get_mail_password()
    if not (username and password):
        raise ValueError("brak MAIL_USER / MAIL_PASSWORD (lub GMAIL_*)")

    # Gmail: yagmail sam wybiera smtp.gmail.com + TLS (hasło aplikacji w Google).
    if _is_gmail_address(username):
        return yagmail.SMTP(user=username, password=password)

    host = get_smtp_host()
    if not host:
        return yagmail.SMTP(user=username, password=password)

    port = _smtp_port()
    use_ssl = _smtp_use_ssl()
    return yagmail.SMTP(
        user=username,
        password=password,
        host=host,
        port=port,
        smtp_ssl=use_ssl,
        smtp_starttls=not use_ssl,
    )


def send_smtp_email(
    to_email: str,
    subject: str,
    body: str,
    logger: logging.Logger,
    *,
    mail_type: str = "wiadomość",
    campaign: str = "",
    attachment_paths: list[str] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> tuple[bool, str]:
    """Wysyłka przez yagmail (Gmail lub SMTP z .env). Zwraca (ok, info)."""
    try:
        import yagmail  # pyright: ignore[reportMissingImports]  # noqa: F401
    except ImportError:
        return False, "brak yagmail (pip install yagmail)"

    username = get_mail_user()
    password = get_mail_password()
    if not (username and password):
        return False, "brak MAIL_USER / MAIL_PASSWORD"

    subject_clean = sanitize_special_text(subject)
    body_clean = sanitize_email_body(body)
    bcc_list = list(bcc) if bcc is not None else _split_recipients(get_env_value(ENV_MAIL_BCC))
    cc_list = (
        list(cc)
        if cc is not None
        else merge_mail_cc_recipients(to_email, get_env_value(ENV_MAIL_CC))
    )
    attach_files = [p for p in (attachment_paths or []) if p and Path(p).is_file()]

    try:
        yag = _yagmail_smtp()
        kwargs: dict[str, Any] = {
            "to": to_email,
            "subject": subject_clean,
            "contents": [body_clean],
        }
        if bcc_list:
            kwargs["bcc"] = bcc_list
        if cc_list:
            kwargs["cc"] = cc_list
        if attach_files:
            kwargs["attachments"] = attach_files
        yag.send(**kwargs)
        archive_sent_message(
            to_email,
            subject_clean,
            body_clean,
            logger,
            cc=cc_list,
            bcc=bcc_list,
            attachment_paths=attach_files or None,
        )
        provider = mail_provider_label() or get_smtp_host() or "yagmail"
        logger.info(
            "Wysłano %s → %s via %s (yagmail) | temat: %s%s",
            mail_type,
            to_email,
            provider,
            (subject or "")[:60],
            f" | załączniki: {len(attach_files)}" if attach_files else "",
        )
        try:
            from email_journal import log_mail_sent

            log_mail_sent(
                to_email,
                subject,
                mail_type=mail_type,
                campaign=campaign,
                ok=True,
            )
        except Exception:
            pass
        return True, "gesendet"
    except Exception as e:
        logger.warning("Błąd wysyłki (yagmail) do %s: %s", to_email, e)
        try:
            from email_journal import log_mail_sent

            log_mail_sent(
                to_email,
                subject,
                mail_type=mail_type,
                campaign=campaign,
                ok=False,
                error=str(e),
            )
        except Exception:
            pass
        return False, str(e)
