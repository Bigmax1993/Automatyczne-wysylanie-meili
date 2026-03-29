"""Testy contact_mailer: generowanie treści, SMTP, kontekst wiersza, CV, OpenAI."""

from __future__ import annotations

import json
import smtplib

import pandas as pd
import pytest

import contact_mailer as cm


class FakeSMTP:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.sent_messages = []

    def send_message(self, msg) -> None:
        if self.should_fail:
            raise RuntimeError("smtp fail")
        self.sent_messages.append(msg)


def _base_df() -> pd.DataFrame:
    df = pd.DataFrame(
        [
            {
                cm.COL_EMAIL: "jan@example.com",
                cm.COL_COMPANY: "Firma Test",
                cm.COL_ROLE: "Data Analyst",
                cm.COL_CITY: "Wroclaw",
                cm.COL_PHONE: "123456789",
                cm.STATUS_COL: pd.NA,
            }
        ]
    )
    # Utrzymaj wysoką precyzję czasu, zgodną z datetime.now().
    df[cm.DATE_COL] = pd.Series([pd.NaT], dtype="datetime64[ns]")
    return df


def test_smtp_quit_safe_calls_close_when_quit_disconnected() -> None:
    class BoomSMTP:
        def quit(self) -> None:
            raise smtplib.SMTPServerDisconnected("please run connect() first")

        def close(self) -> None:
            self.closed = True

    s = BoomSMTP()
    cm._smtp_quit_safe(s)
    assert getattr(s, "closed", False) is True


def test_smtp_quit_safe_none_noop() -> None:
    cm._smtp_quit_safe(None)


def test_smtp_quit_safe_swallows_when_close_also_raises() -> None:
    class BothBad:
        def quit(self) -> None:
            raise smtplib.SMTPServerDisconnected("dc")

        def close(self) -> None:
            raise RuntimeError("close tez padl")

    cm._smtp_quit_safe(BothBad())


def test_send_message_with_retry_succeeds_on_second_attempt(monkeypatch) -> None:
    monkeypatch.setattr(cm, "SMTP_MAX_RETRIES", 3)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)

    class FlakySMTP:
        def __init__(self) -> None:
            self.attempts = 0

        def send_message(self, _msg) -> None:
            self.attempts += 1
            if self.attempts < 2:
                raise smtplib.SMTPServerDisconnected("tymczasowy brak polaczenia")

    smtp = FlakySMTP()
    msg = cm.EmailMessage()
    msg["Subject"] = "T"
    msg["From"] = "a@b.com"
    msg["To"] = "c@d.com"
    msg.set_content("body")
    cm._send_message_with_retry(smtp, msg)
    assert smtp.attempts == 2


def test_mail_signatory_name_in_user_prompt(monkeypatch) -> None:
    captured: dict = {}

    class _Msg:
        content = "OK"

    class _Choice:
        def __init__(self) -> None:
            self.message = _Msg()

    class _Resp:
        def __init__(self) -> None:
            self.choices = [_Choice()]

    class _Completions:
        def create(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            return _Resp()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    monkeypatch.setattr(cm, "_get_openai_client", lambda: _Client())
    monkeypatch.setattr(cm, "MAIL_SIGNATORY_NAME", "Jan Testowy")
    cm.wygeneruj_tresc_maila(
        company="X",
        role="R",
        city="W",
        industry="I",
        website="w",
        phone="p",
        mode="m",
        source="s",
        notes="n",
        row_context="{}",
        offer_b2b=False,
        contract_preference="AUTO",
        locale="pl",
    )
    user_content = captured["messages"][1]["content"]
    assert "Jan Testowy" in user_content


def test_clean_text_handles_empty_values() -> None:
    assert cm._clean_text(pd.NA, "x") == "x"
    assert cm._clean_text("  ", "x") == "x"
    assert cm._clean_text("None", "x") == "x"
    assert cm._clean_text("  abc  ", "x") == "abc"


def test_email_validation_and_already_sent() -> None:
    assert cm._is_valid_email("a@b.com")
    assert not cm._is_valid_email("a@@b")
    assert cm._already_sent("Tak")
    assert cm._already_sent("1")
    assert not cm._already_sent(pd.NA)


def test_is_valid_email_plus_addressing_and_subdomain() -> None:
    assert cm._is_valid_email("user+folder@firma.pl")
    assert cm._is_valid_email("kontakt@jobs.example.co.uk")
    assert cm._is_valid_email("a.b_c+d@sub.domena.de")


def test_is_valid_email_angle_brackets_and_whitespace() -> None:
    assert cm._is_valid_email("  kontakt@firma.pl  ")
    assert cm._is_valid_email('HR <hr@company.example.com>')


def test_normalize_recipient_email_extracts_angle_brackets() -> None:
    assert cm.normalize_recipient_email('Jan <jan.nowak@firma.pl>') == "jan.nowak@firma.pl"


def test_is_valid_email_rejects_rfc_length_and_no_tld_dot() -> None:
    long_local = "a" * 65
    assert not cm._is_valid_email(f"{long_local}@x.com")
    too_long = "a" * 250 + "@bc.co"
    assert len(too_long) > cm.MAX_EMAIL_ADDRESS_LEN
    assert not cm._is_valid_email(too_long)
    assert not cm._is_valid_email("user@localhost")
    assert not cm._is_valid_email("user@nodot")


def test_is_valid_email_rejects_bad_local_shape() -> None:
    assert not cm._is_valid_email(".bad@firma.pl")
    assert not cm._is_valid_email("bad.@firma.pl")
    assert not cm._is_valid_email("@firma.pl")


def test_mail_locale_german_website() -> None:
    assert cm._mail_locale("https://firma.de/karriere", "") == "de"
    assert cm._mail_locale("www.example.at", "") == "de"


def test_mail_locale_german_recipient_email() -> None:
    assert cm._mail_locale("", "kontakt@partner.de") == "de"


def test_mail_locale_polish_default() -> None:
    assert cm._mail_locale("https://firma.pl", "a@b.com") == "pl"
    assert cm._mail_locale("(brak strony www)", "x@y.com") == "pl"


def test_website_hostname_adds_scheme_and_parses() -> None:
    assert cm._website_hostname("firma.de") == "firma.de"
    assert cm._website_hostname("https://jobs.firma.de/list") == "jobs.firma.de"


def test_process_rows_passes_locale_de_for_german_website(monkeypatch) -> None:
    monkeypatch.setattr(cm, "DRY_RUN", True)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "zapisz_excel", lambda _df, _path: None)
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)

    subj_kw: dict = {}

    def _cap_subj(**kwargs):
        subj_kw.update(kwargs)
        return "T"

    mail_kw: dict = {}

    def _cap_mail(**kwargs):
        mail_kw.update(kwargs)
        return "ok"

    monkeypatch.setattr(cm, "_generate_subject_with_retry", _cap_subj)
    monkeypatch.setattr(cm, "_generate_mail_with_retry", _cap_mail)

    df = _base_df()
    df[cm.COL_WEBSITE] = "https://partner.de"
    stats = cm._process_rows(df, excel_path="dummy.xlsx", smtp=None, cv_path="cv.pdf")

    assert stats["sent"] == 1
    assert subj_kw.get("locale") == "de"
    assert mail_kw.get("locale") == "de"


def test_process_rows_passes_locale_pl_for_polish_site(monkeypatch) -> None:
    monkeypatch.setattr(cm, "DRY_RUN", True)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "zapisz_excel", lambda _df, _path: None)
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)

    subj_kw: dict = {}
    mail_kw: dict = {}

    def _cap_subj(**kwargs):
        subj_kw.update(kwargs)
        return "T"

    def _cap_mail(**kwargs):
        mail_kw.update(kwargs)
        return "ok"

    monkeypatch.setattr(cm, "_generate_subject_with_retry", _cap_subj)
    monkeypatch.setattr(cm, "_generate_mail_with_retry", _cap_mail)

    df = _base_df()
    df[cm.COL_WEBSITE] = "https://firma.pl"
    cm._process_rows(df, excel_path="dummy.xlsx", smtp=None, cv_path="cv.pdf")

    assert subj_kw.get("locale") == "pl"
    assert mail_kw.get("locale") == "pl"


def test_safe_status_truncates_long_error() -> None:
    long = "x" * 500
    status = cm._safe_status(long)
    assert len(status) <= cm.MAX_STATUS_LEN
    assert status.endswith("...")


def test_process_rows_marks_invalid_email(monkeypatch) -> None:
    monkeypatch.setattr(cm, "DRY_RUN", True)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "zapisz_excel", lambda _df, _path: None)
    monkeypatch.setattr(cm, "wygeneruj_tresc_maila", lambda *_a, **_k: "test")
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat")

    df = _base_df()
    df.at[0, cm.COL_EMAIL] = "zly-email"
    stats = cm._process_rows(df, excel_path="dummy.xlsx", smtp=None, cv_path="cv.pdf")

    assert stats["invalid_email"] == 1
    assert df.at[0, cm.STATUS_COL] == "Błąd: niepoprawny e-mail"


def test_process_rows_handles_openai_error(monkeypatch) -> None:
    monkeypatch.setattr(cm, "DRY_RUN", True)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "zapisz_excel", lambda _df, _path: None)
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat")

    def _raise_openai(*_args, **_kwargs):
        raise RuntimeError("openai fail")

    monkeypatch.setattr(cm, "wygeneruj_tresc_maila", _raise_openai)

    df = _base_df()
    stats = cm._process_rows(df, excel_path="dummy.xlsx", smtp=None, cv_path="cv.pdf")

    assert stats["openai_errors"] == 1
    assert "Błąd OpenAI" in str(df.at[0, cm.STATUS_COL])


def test_process_rows_handles_smtp_error(monkeypatch) -> None:
    monkeypatch.setattr(cm, "DRY_RUN", False)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "zapisz_excel", lambda _df, _path: None)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_CHARS", 0)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_SENTENCES", 0)
    monkeypatch.setattr(cm, "wygeneruj_tresc_maila", lambda *_a, **_k: "tresc")
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat")

    df = _base_df()
    smtp = FakeSMTP(should_fail=True)
    stats = cm._process_rows(df, excel_path="dummy.xlsx", smtp=smtp, cv_path="cv.pdf")

    assert stats["smtp_errors"] == 1
    assert "Błąd SMTP" in str(df.at[0, cm.STATUS_COL])


def test_process_rows_success(monkeypatch) -> None:
    monkeypatch.setattr(cm, "DRY_RUN", False)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "zapisz_excel", lambda _df, _path: None)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_CHARS", 0)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_SENTENCES", 0)
    monkeypatch.setattr(cm, "wygeneruj_tresc_maila", lambda *_a, **_k: "tresc")
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat")

    df = _base_df()
    smtp = FakeSMTP(should_fail=False)
    stats = cm._process_rows(df, excel_path="dummy.xlsx", smtp=smtp, cv_path="cv.pdf")

    assert stats["sent"] == 1
    assert df.at[0, cm.STATUS_COL] == "Tak"
    assert pd.notna(df.at[0, cm.DATE_COL])
    assert len(smtp.sent_messages) == 1


def test_generate_mail_with_retry_makes_three_attempts(monkeypatch) -> None:
    monkeypatch.setattr(cm, "OPENAI_MAX_RETRIES", 3)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_CHARS", 0)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_SENTENCES", 0)
    calls = {"n": 0}

    def _flaky(**_kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("temporary")
        return "ok"

    monkeypatch.setattr(cm, "wygeneruj_tresc_maila", _flaky)
    content = cm._generate_mail_with_retry(
        company="A",
        role="R",
        city="C",
        industry="I",
        website="W",
        phone="P",
        mode="M",
        source="S",
        notes="N",
        row_context="{}",
        offer_b2b=False,
        contract_preference="AUTO",
    )

    assert content == "ok"
    assert calls["n"] == 3


def test_generate_mail_with_retry_raises_after_max_attempts(monkeypatch) -> None:
    monkeypatch.setattr(cm, "OPENAI_MAX_RETRIES", 3)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_CHARS", 0)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_SENTENCES", 0)

    def _always_fail(**_kwargs):
        raise RuntimeError("permanent")

    monkeypatch.setattr(cm, "wygeneruj_tresc_maila", _always_fail)

    with pytest.raises(RuntimeError, match="po 3 próbach"):
        cm._generate_mail_with_retry(
            company="A",
            role="R",
            city="C",
            industry="I",
            website="W",
            phone="P",
            mode="M",
            source="S",
            notes="N",
            row_context="{}",
            offer_b2b=False,
            contract_preference="AUTO",
        )


def test_mail_body_too_short_and_count_sentences(monkeypatch) -> None:
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_CHARS", 120)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_SENTENCES", 2)
    assert cm._mail_body_too_short("Krótko.")
    blob = (
        "Chciałbym zgłosić swoją kandydaturę na wskazane stanowisko w Państwa firmie. "
        "Posiadam doświadczenie w obszarze analityki danych oraz raportowania. "
        "W załączeniu przesyłam CV i jestem otwarty na rozmowę rekrutacyjną."
    )
    assert not cm._mail_body_too_short(blob)
    assert cm._count_probable_sentences(blob) >= 2


def test_generate_mail_with_retry_retries_when_body_too_short(monkeypatch) -> None:
    monkeypatch.setattr(cm, "OPENAI_MAX_RETRIES", 4)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_CHARS", 220)
    monkeypatch.setattr(cm, "MAIL_BODY_MIN_SENTENCES", 0)
    calls = {"n": 0}
    long_ok = (
        "Chciałbym zgłosić swoją kandydaturę na stanowisko w Państwa organizacji. "
        "Z ogłoszenia wynika, że szukacie osoby ze wskazanymi kompetencjami. "
        "Moje doświadczenie obejmuje pracę z danymi, raportami oraz współpracę z biznesem. "
        "W załączeniu przesyłam CV i chętnie odpowiem na pytania. "
        "Będę wdzięczny za informację o dalszych krokach procesu rekrutacji."
    )

    def _short_then_long(**kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            return "Za krótko."
        assert "Poprzednia wersja" in (kwargs.get("extra_user_instruction") or "")
        return long_ok

    monkeypatch.setattr(cm, "wygeneruj_tresc_maila", _short_then_long)
    out = cm._generate_mail_with_retry(
        company="A",
        role="R",
        city="C",
        industry="I",
        website="W",
        phone="P",
        mode="M",
        source="S",
        notes="N",
        row_context="{}",
        offer_b2b=False,
        contract_preference="AUTO",
    )
    assert len(out) >= 220
    assert calls["n"] == 3


def test_build_row_context_includes_only_non_empty_values() -> None:
    row = pd.Series(
        {
            cm.COL_COMPANY: "Firma X",
            cm.COL_CITY: "Poznan",
            cm.COL_NOTES: " ",
            "Pusta": pd.NA,
        }
    )

    context_json = cm._build_row_context(row)
    context = json.loads(context_json)

    assert context[cm.COL_COMPANY] == "Firma X"
    assert context[cm.COL_CITY] == "Poznan"
    assert cm.COL_NOTES not in context
    assert "Pusta" not in context


def test_process_rows_passes_row_context_to_generator(monkeypatch) -> None:
    monkeypatch.setattr(cm, "DRY_RUN", True)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(cm, "zapisz_excel", lambda _df, _path: None)
    monkeypatch.setattr(cm, "_attach_cv", lambda _msg, _cv: None)
    monkeypatch.setattr(cm, "_generate_subject_with_retry", lambda **_k: "Temat")

    captured = {}

    def _fake_generate(**kwargs):
        captured.update(kwargs)
        return "test"

    monkeypatch.setattr(cm, "_generate_mail_with_retry", _fake_generate)

    df = _base_df()
    df.at[0, cm.COL_NOTES] = "Kontakt przez portal"
    stats = cm._process_rows(df, excel_path="dummy.xlsx", smtp=None, cv_path="cv.pdf")

    assert stats["sent"] == 1
    assert "row_context" in captured
    assert "Kontakt przez portal" in captured["row_context"]
    assert captured["offer_b2b"] is False


def test_should_offer_b2b_for_ecommerce_notes() -> None:
    assert cm._should_offer_b2b(
        industry="Sklep internetowy / e-commerce",
        source="SerpAPI",
        notes="Oferta współpracy B2B",
    )


def test_detect_contract_preference_prefers_uop_when_both_present() -> None:
    pref = cm._detect_contract_preference(
        mode="UOP / B2B",
        source="pracuj.pl",
        notes="forma zatrudnienia: UOP albo B2B",
    )
    assert pref == "UOP"


def test_detect_contract_preference_b2b_when_only_b2b() -> None:
    pref = cm._detect_contract_preference(
        mode="B2B",
        source="ogloszenie",
        notes="wyłącznie B2B",
    )
    assert pref == "B2B"


def test_detect_contract_preference_auto_when_missing_data() -> None:
    pref = cm._detect_contract_preference(mode="", source="", notes="")
    assert pref == "AUTO"


def test_generate_subject_with_retry_raises_after_failures(monkeypatch) -> None:
    monkeypatch.setattr(cm, "OPENAI_MAX_RETRIES", 2)
    monkeypatch.setattr(cm.time, "sleep", lambda _x: None)
    monkeypatch.setattr(
        cm,
        "wygeneruj_temat_spersonalizowany",
        lambda **_k: (_ for _ in ()).throw(RuntimeError("x")),
    )

    with pytest.raises(RuntimeError, match="tematu po 2 próbach"):
        cm._generate_subject_with_retry(
            company="Firma",
            role="Data Analyst",
            city="Wroclaw",
            industry="IT",
            mode="Hybrid",
            source="pracuj",
        )


def test_generate_subject_with_retry_passes_contract_preference(monkeypatch) -> None:
    monkeypatch.setattr(cm, "OPENAI_MAX_RETRIES", 1)
    captured = {}

    def _subject(**kwargs):
        captured.update(kwargs)
        return "Temat"

    monkeypatch.setattr(cm, "wygeneruj_temat_spersonalizowany", _subject)
    subject = cm._generate_subject_with_retry(
        company="Firma",
        role="Data Analyst",
        city="Wroclaw",
        industry="IT",
        mode="UOP / B2B",
        source="pracuj",
        contract_preference="UOP",
    )
    assert subject == "Temat"
    assert captured["contract_preference"] == "UOP"


def test_generate_subject_with_retry_passes_locale(monkeypatch) -> None:
    monkeypatch.setattr(cm, "OPENAI_MAX_RETRIES", 1)
    captured: dict = {}

    def _subject(**kwargs):
        captured.update(kwargs)
        return "T"

    monkeypatch.setattr(cm, "wygeneruj_temat_spersonalizowany", _subject)
    cm._generate_subject_with_retry(
        company="A",
        role="R",
        city="C",
        industry="I",
        mode="M",
        source="S",
        locale="de",
    )
    assert captured.get("locale") == "de"


def test_wygeneruj_tresc_maila_uses_german_system_when_locale_de(monkeypatch) -> None:
    captured: dict = {}

    class _Msg:
        content = "Mit freundlichen Grüßen"

    class _Choice:
        def __init__(self) -> None:
            self.message = _Msg()

    class _Resp:
        def __init__(self) -> None:
            self.choices = [_Choice()]

    class _Completions:
        def create(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            return _Resp()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    monkeypatch.setattr(cm, "_get_openai_client", lambda: _Client())
    text = cm.wygeneruj_tresc_maila(
        company="X",
        role="R",
        city="Berlin",
        industry="I",
        website="w",
        phone="p",
        mode="m",
        source="s",
        notes="n",
        row_context="{}",
        offer_b2b=False,
        contract_preference="AUTO",
        locale="de",
    )
    assert "Grüßen" in text
    assert "Du formulierst" in captured["messages"][0]["content"]
    assert cm.MAIL_SIGNATORY_NAME in captured["messages"][1]["content"]


def test_wygeneruj_tresc_maila_uses_polish_system_when_locale_pl(monkeypatch) -> None:
    captured: dict = {}

    class _Msg:
        content = "Pozdrawiam"

    class _Choice:
        def __init__(self) -> None:
            self.message = _Msg()

    class _Resp:
        def __init__(self) -> None:
            self.choices = [_Choice()]

    class _Completions:
        def create(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            return _Resp()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    monkeypatch.setattr(cm, "_get_openai_client", lambda: _Client())
    cm.wygeneruj_tresc_maila(
        company="X",
        role="R",
        city="W",
        industry="I",
        website="w",
        phone="p",
        mode="m",
        source="s",
        notes="n",
        row_context="{}",
        offer_b2b=False,
        contract_preference="AUTO",
        locale="pl",
    )
    assert "Jesteś asystentem" in captured["messages"][0]["content"]
    assert cm.MAIL_SIGNATORY_NAME in captured["messages"][1]["content"]


def test_wygeneruj_temat_spersonalizowany_uses_german_subject_system_when_locale_de(
    monkeypatch,
) -> None:
    captured: dict = {}

    class _Msg:
        content = "Bewerbung Data Analyst"

    class _Choice:
        def __init__(self) -> None:
            self.message = _Msg()

    class _Resp:
        def __init__(self) -> None:
            self.choices = [_Choice()]

    class _Completions:
        def create(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            return _Resp()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    monkeypatch.setattr(cm, "_get_openai_client", lambda: _Client())
    sub = cm.wygeneruj_temat_spersonalizowany(
        company="Firma",
        role="Data Analyst",
        city="München",
        industry="IT",
        mode="UOP",
        source="s",
        offer_b2b=False,
        contract_preference="AUTO",
        locale="de",
    )
    assert "Bewerbung" in sub
    assert "Du erstellst" in captured["messages"][0]["content"]
