# -*- coding: utf-8 -*-
from __future__ import annotations

from ua_claude_prompts import build_personalized_inquiry_email_prompt_uk
from ua_materialy_inquiry_email_uk import DEFAULT_INQUIRY_PHONE_UK, DEFAULT_INQUIRY_SENDER_NAME_UK


def test_prompt_ukrainian_personalization():
    p = build_personalized_inquiry_email_prompt_uk(
        company_name="ТОВ Будмаркет Львів",
        website="https://budmarket.lviv.ua",
        oblast="Lvivska",
        materials="цегла, блок",
        page_snippet="Продаж цегли та блоків оптом у Львові",
    )
    assert "ТОВ Будмаркет Львів" in p
    assert "україн" in p.lower()
    assert "цегла" in p or "блок" in p


def test_prompt_no_mfg_branding(monkeypatch):
    monkeypatch.setenv("MAIL_SENDER_NAME", "Тестовий Менеджер")
    monkeypatch.setenv("INQUIRY_COMPANY_NAME", "")
    monkeypatch.setenv("INQUIRY_PHONE", "")
    monkeypatch.setenv("INQUIRY_WEBSITE", "")
    p = build_personalized_inquiry_email_prompt_uk(company_name="Test ТОВ")
    lowered = p.lower()
    assert "mfg" not in lowered
    assert "fliesen" not in lowered
    assert "moderner" not in lowered


def test_prompt_includes_ua_phone_and_sender(monkeypatch):
    from ua_materialy_inquiry_email_uk import build_inquiry_signature_uk, build_sender_contact_line_uk

    monkeypatch.setenv("MAIL_SENDER_NAME", "Свінчак Максим Tel.+4915223655399")
    monkeypatch.setenv("INQUIRY_PHONE", "+49 1522 3655 399")
    monkeypatch.setenv("INQUIRY_COMPANY_NAME", "")
    monkeypatch.setenv("INQUIRY_WEBSITE", "")
    contact = build_sender_contact_line_uk()
    signature = build_inquiry_signature_uk()
    p = build_personalized_inquiry_email_prompt_uk(company_name="Test ТОВ")
    assert contact in p
    assert signature in p
    assert DEFAULT_INQUIRY_PHONE_UK in contact
    assert DEFAULT_INQUIRY_PHONE_UK in signature
    assert DEFAULT_INQUIRY_SENDER_NAME_UK in signature
    assert "+49" not in contact
    assert "+49" not in signature


def test_prompt_forbids_attachments():
    p = build_personalized_inquiry_email_prompt_uk(company_name="Test")
    assert "вкладення" in p.lower() or "файли" in p.lower()


def test_prompt_requires_json_output():
    p = build_personalized_inquiry_email_prompt_uk(company_name="Test")
    assert '"subject"' in p
    assert '"body"' in p
