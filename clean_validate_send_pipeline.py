"""
Główny etap pipeline: clean -> walidacja -> zapis CSV -> opcjonalna wysyłka.

Skrypt czyta pliki kontaktów, porządkuje rekordy, waliduje je i przekazuje
gotowe dane do warstwy mailingowej.
"""

import argparse
import json
import logging
import os
import re
import smtplib
from glob import glob
from datetime import datetime
from typing import Dict, Optional, Set

import pandas as pd
from openai import OpenAI

import contact_mailer as cm
import pipeline_version as pv
from domain_blocklist import recipient_domain_is_blocked
from excel_workbook_reader import read_excel_workbook

logger = logging.getLogger(__name__)


def _pipeline_progress_every_n() -> int:
    """Co ile wierszy logować postęp (OpenAI clean / wysyłka). Domyślnie 50; 0 = wyłączone."""
    raw = (os.environ.get("PIPELINE_PROGRESS_EVERY_N") or "50").strip()
    try:
        n = int(raw)
    except ValueError:
        return 50
    if n <= 0:
        return 0
    return n


CLEAN_SYSTEM_PROMPT = """Czyścisz rekordy kontaktów rekrutacyjnych.
Zwracasz tylko poprawny JSON. Nie dodawaj komentarzy ani markdown.
Nie wymyślaj faktów - używaj wyłącznie danych z wejścia.
Jeśli pole jest nieznane, zwróć pusty string."""

OUTPUT_COLUMNS = [
    cm.COL_COMPANY,
    cm.COL_CITY,
    cm.COL_INDUSTRY,
    cm.COL_ROLE,
    cm.COL_WEBSITE,
    cm.COL_EMAIL,
    cm.COL_PHONE,
    cm.COL_MODE,
    cm.COL_SOURCE,
    cm.COL_NOTES,
    cm.STATUS_COL,
    cm.DATE_COL,
    "Walidacja",
    "Uwagi walidacji",
]
# Dodatkowe pliki kontaktów (xlsx/xls/csv) — domyślnie Documents/kontakty użytkownika.
# Nadpisanie: zmienna środowiskowa EXTRA_CONTACTS_DIR (np. jawna ścieżka).
_EXTRA_CONTACTS_DEFAULT = os.path.join(os.path.expanduser("~"), "Documents", "kontakty")
EXTRA_CONTACTS_DIR = os.path.abspath(
    os.environ.get("EXTRA_CONTACTS_DIR", "").strip() or _EXTRA_CONTACTS_DEFAULT
)


def _default_output_csv_path() -> str:
    return os.path.join(
        os.path.expanduser("~"),
        "Documents",
        f"Kontakty_cleaned_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
    )


def _ensure_cleaned_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in OUTPUT_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    for col in (cm.STATUS_COL, cm.DATE_COL, "Walidacja", "Uwagi walidacji"):
        if col in out.columns:
            out[col] = out[col].fillna("").astype("object")
    return out


def _resolve_input_path(explicit_path: str) -> str:
    if explicit_path:
        return explicit_path
    return cm._resolve_excel_path()


def _find_latest_contacts_file(directory: str) -> str:
    patterns = ("*.xlsx", "*.xls", "*.csv")
    candidates = []
    for p in patterns:
        candidates.extend(glob(os.path.join(directory, p)))
    if not candidates:
        raise FileNotFoundError(f"Brak pliku kontaktów w katalogu: {directory}")
    return max(candidates, key=os.path.getmtime)


def _list_extra_contacts_files(directory: str, exclude_paths: Set[str]) -> list[str]:
    """Wszystkie pliki kontaktów w katalogu (xlsx/xls/csv), poza ścieżkami z exclude_paths (abspath)."""
    patterns = ("*.xlsx", "*.xls", "*.csv")
    candidates: list[str] = []
    for p in patterns:
        candidates.extend(glob(os.path.join(directory, p)))
    excluded = {os.path.abspath(x) for x in exclude_paths if x}
    out = [c for c in candidates if os.path.abspath(c) not in excluded]
    out.sort(key=lambda f: (os.path.getmtime(f), os.path.abspath(f).lower()))
    return out


def _safe_stem_for_output(path: str) -> str:
    base = os.path.basename(path)
    stem, ext = os.path.splitext(base)
    if ext == "" and stem.startswith("."):
        return "kontakty"
    stem = re.sub(r"[^\w\-.]+", "_", stem, flags=re.UNICODE).strip("._")
    return (stem or "kontakty")[:80]


def _read_table(path: str) -> pd.DataFrame:
    lower = path.lower()
    if lower.endswith(".csv"):
        return pd.read_csv(path)
    if lower.endswith((".xlsx", ".xlsm", ".xls")):
        return read_excel_workbook(path)
    return pd.read_excel(path)


def _save_csv(df: pd.DataFrame, path: str) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")
    try:
        from json_data_backup import maybe_backup_dataframe

        maybe_backup_dataframe(df, path, reason="csv_save")
    except Exception:
        logger.exception("Kopia JSON po zapisie CSV nie powiodła się")


def _clean_scalar(value) -> str:
    return cm._clean_text(value, "")


def _build_raw_row_payload(row: pd.Series) -> Dict[str, str]:
    payload: Dict[str, str] = {}
    for col in row.index:
        val = _clean_scalar(row.get(col))
        if val:
            payload[str(col)] = val
    return payload


def _extract_json_object(text: str) -> Dict[str, str]:
    content = (text or "").strip()
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model nie zwrócił obiektu JSON.")
    return json.loads(content[start : end + 1])


def _clean_row_with_openai(client: OpenAI, row_payload: Dict[str, str], model: str) -> Dict[str, str]:
    prompt = f"""Ustandaryzuj dane do tego schematu pól:
- {cm.COL_COMPANY}
- {cm.COL_CITY}
- {cm.COL_INDUSTRY}
- {cm.COL_ROLE}
- {cm.COL_WEBSITE}
- {cm.COL_EMAIL}
- {cm.COL_PHONE}
- {cm.COL_MODE}
- {cm.COL_SOURCE}
- {cm.COL_NOTES}

Zasady:
- zwróć tylko obiekt JSON z powyższymi kluczami,
- usuwaj zbędne spacje i śmieci,
- zachowaj oryginalny sens, bez dopowiadania nowych danych,
- jeśli brak wartości, wpisz pusty string.

Dane wejściowe (JSON):
{json.dumps(row_payload, ensure_ascii=False)}"""

    r = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": CLEAN_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )
    content = r.choices[0].message.content or ""
    parsed = _extract_json_object(content)
    cleaned: Dict[str, str] = {}
    for key in [
        cm.COL_COMPANY,
        cm.COL_CITY,
        cm.COL_INDUSTRY,
        cm.COL_ROLE,
        cm.COL_WEBSITE,
        cm.COL_EMAIL,
        cm.COL_PHONE,
        cm.COL_MODE,
        cm.COL_SOURCE,
        cm.COL_NOTES,
    ]:
        cleaned[key] = _clean_scalar(parsed.get(key, ""))
    return cleaned


def _validate_row(cleaned: Dict[str, str]) -> tuple[str, str]:
    issues = []
    if not cleaned.get(cm.COL_COMPANY):
        issues.append("Brak firmy")
    if not cleaned.get(cm.COL_ROLE):
        issues.append("Brak stanowiska/roli")
    email = cleaned.get(cm.COL_EMAIL, "")
    if not email:
        issues.append("Brak e-maila")
    elif not cm._is_valid_email(email):
        issues.append("Niepoprawny e-mail")
    return ("OK", "") if not issues else ("Błąd", "; ".join(issues))


def _clean_and_validate(df: pd.DataFrame, client: OpenAI, model: str) -> pd.DataFrame:
    out_rows = []
    total = len(df)
    every = _pipeline_progress_every_n()
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        raw_payload = _build_raw_row_payload(row)
        cleaned = _clean_row_with_openai(client=client, row_payload=raw_payload, model=model)
        validation, notes = _validate_row(cleaned)
        cleaned[cm.STATUS_COL] = ""
        cleaned[cm.DATE_COL] = ""
        cleaned["Walidacja"] = validation
        cleaned["Uwagi walidacji"] = notes
        out_rows.append(cleaned)
        if every and (i == 1 or i == total or i % every == 0):
            logger.info("Czyszczenie OpenAI: %s/%s wierszy", i, total)

    out_df = pd.DataFrame(out_rows)
    for col in OUTPUT_COLUMNS:
        if col not in out_df.columns:
            out_df[col] = ""
    return out_df[OUTPUT_COLUMNS]


def _run_validate_only_report(input_path: str) -> None:
    """Offline: bez OpenAI, SMTP i pobierania stron — rozkład wierszy po regułach wysyłki."""
    df = _read_table(input_path)
    col_map = cm._resolve_column_map(df)
    email_col = col_map.get("email")
    has_walidacja = "Walidacja" in df.columns
    counts = {
        "walidacja_nie_ok": 0,
        "juz_wyslane": 0,
        "brak_lub_zly_email": 0,
        "domena_zablokowana": 0,
        "nadaje_sie_do_wysylki": 0,
    }
    total_v = len(df)
    every_v = _pipeline_progress_every_n()
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        if every_v and (i == 1 or i == total_v or i % every_v == 0):
            logger.info("Walidacja offline (--validate-only): %s/%s wierszy", i, total_v)
        if has_walidacja and str(row.get("Walidacja", "")).strip().lower() != "ok":
            counts["walidacja_nie_ok"] += 1
            continue
        if cm._already_sent(row.get(cm.STATUS_COL)):
            counts["juz_wyslane"] += 1
            continue
        email = cm._row_value(row, email_col, "") if email_col else ""
        if not email or not cm._is_valid_email(email):
            counts["brak_lub_zly_email"] += 1
            continue
        if recipient_domain_is_blocked(email):
            counts["domena_zablokowana"] += 1
            continue
        counts["nadaje_sie_do_wysylki"] += 1
    logger.info("Raport walidacji (offline, bez OpenAI / SMTP / pobierania WWW):")
    for k, v in counts.items():
        logger.info("  %s=%s", k, v)


def _send_from_cleaned_csv(
    df: pd.DataFrame,
    csv_path: str,
    dry_run: bool,
    cv_path: str,
    batch_source_path: str = "",
) -> Dict[str, int]:
    stats = {
        "sent": 0,
        "skipped": 0,
        "openai_errors": 0,
        "smtp_errors": 0,
        "daily_limit_reached": 0,
        "email_from_web": 0,
        "skip_validation_failed": 0,
        "skip_already_sent": 0,
        "skip_invalid_or_missing_email": 0,
        "skip_blocked_domain": 0,
        "skip_daily_limit": 0,
    }

    col_map = cm._resolve_column_map(df)
    sent_today = cm._count_sent_today(df)
    daily_limit = max(1, cm.MAX_EMAILS_PER_DAY)
    smtp: Optional[smtplib.SMTP_SSL] = None
    try:
        if not dry_run:
            if not cm.password:
                raise RuntimeError("Brak GMAIL_APP_PASSWORD w zmiennych środowiskowych.")
            smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465)
            smtp.login(cm.SENDER_EMAIL, cm.password)

        total_rows = len(df)
        every_send = _pipeline_progress_every_n()
        for pos, (idx, row) in enumerate(df.iterrows(), start=1):
            if every_send and (pos == 1 or pos == total_rows or pos % every_send == 0):
                logger.info("Przetwarzanie wierszy (wysyłka / dry-run): %s/%s", pos, total_rows)
            company_for_log = cm._row_value(row, col_map.get("company"), "(brak firmy)")
            if str(row.get("Walidacja", "")).strip().lower() != "ok":
                stats["skipped"] += 1
                stats["skip_validation_failed"] += 1
                cm._append_campaign_log(
                    cm.CAMPAIGN_LOG_PATH,
                    email=cm._row_value(row, col_map.get("email")),
                    company=company_for_log,
                    subject="",
                    status="skipped",
                    reason="validation_failed",
                )
                continue
            if cm._already_sent(row.get(cm.STATUS_COL)):
                stats["skipped"] += 1
                stats["skip_already_sent"] += 1
                cm._append_campaign_log(
                    cm.CAMPAIGN_LOG_PATH,
                    email=cm._row_value(row, col_map.get("email")),
                    company=company_for_log,
                    subject="",
                    status="skipped",
                    reason="already_sent",
                )
                continue

            email_col = col_map.get("email")
            website_early = cm._row_value(row, col_map.get("website"), "")
            email_raw = cm._row_value(row, email_col)
            email, filled_web = cm.try_resolve_email_from_website(
                email_raw, website_early
            )
            if filled_web and email_col:
                df.at[idx, email_col] = email
                _save_csv(df, csv_path)
                stats["email_from_web"] += 1
            if not email or not cm._is_valid_email(email):
                stats["skipped"] += 1
                stats["skip_invalid_or_missing_email"] += 1
                cm._append_campaign_log(
                    cm.CAMPAIGN_LOG_PATH,
                    email=email,
                    company=company_for_log,
                    subject="",
                    status="invalid_email",
                    reason="invalid_email_or_missing",
                )
                continue

            if recipient_domain_is_blocked(email):
                stats["skipped"] += 1
                stats["skip_blocked_domain"] += 1
                df.at[idx, cm.STATUS_COL] = "Pominięto: domena zablokowana"
                _save_csv(df, csv_path)
                cm._append_campaign_log(
                    cm.CAMPAIGN_LOG_PATH,
                    email=email,
                    company=company_for_log,
                    subject="",
                    status="skipped",
                    reason="blocked_domain",
                )
                continue

            if sent_today >= daily_limit:
                stats["skipped"] += 1
                stats["daily_limit_reached"] += 1
                stats["skip_daily_limit"] += 1
                df.at[idx, cm.STATUS_COL] = "Pominięto: limit dzienny"
                _save_csv(df, csv_path)
                cm._append_campaign_log(
                    cm.CAMPAIGN_LOG_PATH,
                    email=email,
                    company=company_for_log,
                    subject="",
                    status="skipped",
                    reason="daily_limit_reached",
                )
                continue

            company = cm._row_value(row, col_map.get("company"), "(brak firmy)")
            role = cm._row_value(row, col_map.get("role"), "(brak stanowiska)")
            city = cm._row_value(row, col_map.get("city"), "(brak miasta)")
            industry = cm._row_value(row, col_map.get("industry"), "(brak branży)")
            website = cm._row_value(row, col_map.get("website"), "(brak strony WWW)")
            phone = cm._row_value(row, col_map.get("phone"), "(nie podano)")
            mode = cm._row_value(row, col_map.get("mode"), "(brak informacji)")
            source = cm._row_value(row, col_map.get("source"), "(brak źródła)")
            notes = cm._row_value(row, col_map.get("notes"), "(brak uwag)")
            contract_preference = cm._detect_contract_preference(
                mode=mode, source=source, notes=notes
            )
            offer_b2b = cm._should_offer_b2b(industry=industry, source=source, notes=notes)
            if contract_preference == "UOP":
                offer_b2b = False
            elif contract_preference == "B2B":
                offer_b2b = True

            mail_locale = cm._mail_locale(website, email)

            try:
                subject = cm._generate_subject_with_retry(
                    company=company,
                    role=role,
                    city=city,
                    industry=industry,
                    mode=mode,
                    source=source,
                    offer_b2b=offer_b2b,
                    contract_preference=contract_preference,
                    locale=mail_locale,
                )
                mail_text = cm._generate_mail_with_retry(
                    company=company,
                    role=role,
                    city=city,
                    industry=industry,
                    website=website,
                    phone=phone,
                    mode=mode,
                    source=source,
                    notes=notes,
                    row_context=cm._build_row_context_for_generation(row, website),
                    offer_b2b=offer_b2b,
                    contract_preference=contract_preference,
                    locale=mail_locale,
                )
            except Exception as e:
                stats["openai_errors"] += 1
                df.at[idx, cm.STATUS_COL] = cm._safe_status(f"Błąd OpenAI: {e}")
                _save_csv(df, csv_path)
                cm._append_campaign_log(
                    cm.CAMPAIGN_LOG_PATH,
                    email=email,
                    company=company,
                    subject="",
                    status="openai_error",
                    reason=str(e),
                )
                continue

            msg = cm.EmailMessage()
            msg["Subject"] = subject
            msg["From"] = cm.SENDER_EMAIL
            msg["To"] = email
            msg.set_content(mail_text)
            cm._attach_cv(msg, cv_path)

            try:
                if dry_run:
                    logger.info("[DRY_RUN] %s | %s", email, msg["Subject"])
                else:
                    assert smtp is not None
                    cm._send_message_with_retry(smtp, msg)
            except Exception as e:
                stats["smtp_errors"] += 1
                df.at[idx, cm.STATUS_COL] = cm._safe_status(f"Błąd SMTP: {e}")
                _save_csv(df, csv_path)
                cm._append_campaign_log(
                    cm.CAMPAIGN_LOG_PATH,
                    email=email,
                    company=company,
                    subject=subject,
                    status="smtp_error",
                    reason=str(e),
                )
                continue

            stats["sent"] += 1
            sent_today += 1
            df.at[idx, cm.STATUS_COL] = "Tak"
            df.at[idx, cm.DATE_COL] = str(cm._now_for_excel())
            _save_csv(df, csv_path)
            cm._append_campaign_log(
                cm.CAMPAIGN_LOG_PATH,
                email=email,
                company=company,
                subject=subject,
                status="sent",
                reason="",
            )
            try:
                from sent_mail_registry import append_sent_record

                batch_label = batch_source_path or csv_path
                append_sent_record(
                    batch_path=batch_label,
                    output_csv_path=csv_path,
                    email=email,
                    company=company,
                    role=role,
                    city=city,
                    industry=industry,
                    website=website,
                    phone=phone,
                    mode=mode,
                    source=source,
                    notes=notes,
                    subject=subject,
                    locale=mail_locale,
                    dry_run=dry_run,
                )
            except Exception:
                logger.exception("Zapis rejestru JSON wysłanych maili nie powiódł się")
            if not dry_run:
                cm._apply_send_delay()

    finally:
        cm._smtp_quit_safe(smtp)

    return stats


def _merge_stats(a: Dict[str, int], b: Dict[str, int]) -> Dict[str, int]:
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, 0) + v
    return out


def _process_source(
    source_path: str,
    output_csv: str,
    client: Optional[OpenAI],
    model: str,
    cv_path: str,
    dry_run: bool,
    skip_clean: bool = False,
) -> Dict[str, int]:
    raw_df = _read_table(source_path)
    if skip_clean:
        cleaned_df = _ensure_cleaned_frame(raw_df)
        logger.info("Pominięto czyszczenie OpenAI, wczytano: %s", source_path)
        return _send_from_cleaned_csv(
            df=cleaned_df,
            csv_path=output_csv,
            dry_run=dry_run,
            cv_path=cv_path,
            batch_source_path=source_path,
        )
    if client is None:
        raise RuntimeError("Brak klienta OpenAI (wewnętrzny błąd).")
    cleaned_df = _clean_and_validate(raw_df, client=client, model=model)
    _save_csv(cleaned_df, output_csv)
    logger.info("Zapisano CSV po czyszczeniu i walidacji: %s", output_csv)
    return _send_from_cleaned_csv(
        df=cleaned_df,
        csv_path=output_csv,
        dry_run=dry_run,
        cv_path=cv_path,
        batch_source_path=source_path,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline: OpenAI cleaning -> validation -> CSV -> personalized sending"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"clean_validate_send_pipeline {pv.PIPELINE_VERSION}",
    )
    parser.add_argument("--input", default="", help="Plik wejściowy CSV/XLSX")
    parser.add_argument(
        "--output-csv",
        default=None,
        help="Plik CSV po czyszczeniu i walidacji (domyślnie: Documents/Kontakty_cleaned_YYYYMMDD_HHMMSS.csv)",
    )
    parser.add_argument(
        "--skip-clean",
        action="store_true",
        help="Pomiń czyszczenie OpenAI: --input to już wyczyszczony CSV/XLSX; tylko wysyłka (aktualizacja statusów w --output-csv)",
    )
    parser.add_argument(
        "--extra-contacts-dir",
        default=EXTRA_CONTACTS_DIR,
        help=(
            "Katalog z dodatkowymi plikami kontaktów (xlsx/xls/csv); po głównym --input "
            "przetwarzane są wszystkie pliki z tego folderu (poza bieżącym wejściem). "
            f"Domyślnie: {EXTRA_CONTACTS_DIR} (lub EXTRA_CONTACTS_DIR w środowisku)."
        ),
    )
    parser.add_argument(
        "--skip-extra-contacts",
        action="store_true",
        help="Nie przetwarzaj dodatkowego pliku kontaktów z katalogu",
    )
    parser.add_argument("--dry-run", action="store_true", help="Bez faktycznej wysyłki")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Tylko raport offline (walidacja / e-mail / blokada domen); bez OpenAI, SMTP i pobierania stron",
    )
    args = parser.parse_args()

    from pipeline_logging import setup_logging

    setup_logging("clean_validate_send_pipeline")

    try:
        from sent_mail_registry import cleanup_stale_registry_files

        n_del = cleanup_stale_registry_files()
        if n_del:
            logger.info("Rejestr wysyłek JSON: usunięto %s przeterminowanych plików .jsonl", n_del)
    except Exception:
        logger.exception("Czyszczenie przeterminowanych plików rejestru .jsonl nie powiodło się")

    if args.validate_only:
        inp = (args.input or "").strip()
        if not inp:
            raise RuntimeError("--validate-only wymaga --input ze ścieżką do pliku CSV/XLSX.")
        path = os.path.abspath(inp)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Brak pliku: {path}")
        _run_validate_only_report(path)
        return

    client: Optional[OpenAI] = None
    model = os.environ.get("OPENAI_MODEL", cm.OPENAI_MODEL)

    if args.skip_clean and not (args.input or "").strip():
        raise RuntimeError(
            "--skip-clean wymaga jawnego --input (ścieżka do już wyczyszczonego CSV lub XLSX)."
        )

    default_out = _default_output_csv_path()
    if args.skip_clean:
        input_path = os.path.abspath((args.input or "").strip())
        if not os.path.isfile(input_path):
            raise FileNotFoundError(f"Brak pliku: {input_path}")
        output_csv = (
            os.path.abspath(args.output_csv) if args.output_csv is not None else input_path
        )
        cv_path = cm._resolve_cv_path()
        stats = _process_source(
            source_path=input_path,
            output_csv=output_csv,
            client=None,
            model="",
            cv_path=cv_path,
            dry_run=args.dry_run,
            skip_clean=True,
        )
    else:
        api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("Brak OPENAI_API_KEY w zmiennych środowiskowych.")
        client = OpenAI(api_key=api_key)

        input_path = _resolve_input_path(args.input)
        output_csv = args.output_csv if args.output_csv is not None else default_out
        cv_path = cm._resolve_cv_path()

        stats = _process_source(
            source_path=input_path,
            output_csv=output_csv,
            client=client,
            model=model,
            cv_path=cv_path,
            dry_run=args.dry_run,
            skip_clean=False,
        )

    if not args.skip_extra_contacts:
        extra_dir = args.extra_contacts_dir
        if not os.path.isdir(extra_dir):
            logger.info("Pominięto dodatkowe kontakty: brak katalogu %s", extra_dir)
        else:
            extra_files = _list_extra_contacts_files(
                extra_dir, {os.path.abspath(input_path)}
            )
            if not extra_files:
                logger.info(
                    "Brak dodatkowych plików kontaktów w %s (lub jedyny plik to bieżące wejście).",
                    extra_dir,
                )
            for idx, extra_file in enumerate(extra_files):
                abs_extra = os.path.abspath(extra_file)
                if args.skip_clean:
                    out_ex = (
                        abs_extra
                        if abs_extra.lower().endswith(".csv")
                        else os.path.splitext(abs_extra)[0] + "_wysylka.csv"
                    )
                    logger.info(
                        "Przetwarzam dodatkowy plik z katalogu kontaktów (bez czyszczenia OpenAI): %s",
                        extra_file,
                    )
                    ex_stats = _process_source(
                        source_path=extra_file,
                        output_csv=out_ex,
                        client=None,
                        model="",
                        cv_path=cv_path,
                        dry_run=args.dry_run,
                        skip_clean=True,
                    )
                else:
                    stem = _safe_stem_for_output(extra_file)
                    extra_csv = (
                        os.path.splitext(output_csv)[0] + f"_extra_{idx}_{stem}.csv"
                    )
                    logger.info("Przetwarzam dodatkowy plik kontaktów: %s", extra_file)
                    ex_stats = _process_source(
                        source_path=extra_file,
                        output_csv=extra_csv,
                        client=client,
                        model=model,
                        cv_path=cv_path,
                        dry_run=args.dry_run,
                        skip_clean=False,
                    )
                stats = _merge_stats(stats, ex_stats)
    line = (
        "Wysyłka zakończona: "
        f"wysłano={stats['sent']}, "
        f"pominieto={stats['skipped']}, "
        f"limit_dzienny={stats['daily_limit_reached']}, "
        f"bledy_openai={stats['openai_errors']}, "
        f"bledy_smtp={stats['smtp_errors']}, "
        f"email_ze_strony={stats.get('email_from_web', 0)}"
    )
    if cm.MAIL_PROMPT_VERSION:
        line += f", prompt_wersja={cm.MAIL_PROMPT_VERSION}"
    logger.info("%s", line)
    logger.info(
        "Szczegoly_pominiec: walidacja=%s, juz_wyslane=%s, email_bledny_lub_brak=%s, "
        "domena_zablokowana=%s, limit_dzienny_wiersze=%s",
        stats.get("skip_validation_failed", 0),
        stats.get("skip_already_sent", 0),
        stats.get("skip_invalid_or_missing_email", 0),
        stats.get("skip_blocked_domain", 0),
        stats.get("skip_daily_limit", 0),
    )
    cm.maybe_error_alert(stats, prefix="pipeline: ")


if __name__ == "__main__":
    main()
