# -*- coding: utf-8 -*-
"""
Testy integracyjne kampanii UA — smoke scrapera, run_config, prompty Claude.

  python -m pytest tests/test_ua_materialy_integration.py -v
"""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

import ua_materialy_scraper as scraper
from ua_claude_prompts import build_page_verify_prompt, build_personalized_inquiry_email_prompt_uk
from ua_oblast_keywords import configure_campaign_oblasts
from ua_oblast_rotation import apply_rotation_to_module

ROOT = Path(__file__).resolve().parent.parent
_LOGGER = logging.getLogger("test_ua_materialy_integration")


def test_scraper_smoke_test_entrypoint():
    scraper._run_smoke_tests()


def test_run_config_kyiv_test_loads():
    from scraper_run_config import load_run_config_file

    data = load_run_config_file("run_config/ua_kyiv_test.json", ROOT)
    assert "Kyiv" in data.get("active_bundeslaender", [])


def test_apply_rotation_configures_module(tmp_path):
    mod = type("M", (), {})()
    oblast, state, path = apply_rotation_to_module(mod, tmp_path, max_discovery_terms=40)
    assert oblast in scraper.CAMPAIGN_ACTIVE_BUNDESLAENDER
    assert len(mod.SERPER_DISCOVERY_TERMS) <= 40
    assert path.parent == tmp_path


def test_configure_oblasts_sets_discovery_waves():
    mod = type("M", (), {})()
    configure_campaign_oblasts(mod, ["Kyiv"], max_discovery_terms=50)
    assert mod.SERPER_DISCOVERY_TERMS
    assert mod.SERPER_DISCOVERY_FALLBACK_TERMS
    assert mod.SERPER_DISCOVERY_BROAD_TERMS
    assert mod.SERPER_DISCOVERY_LANDKREIS_TERMS
    assert mod.SERPER_DISCOVERY_PLACES_TERMS
    assert mod.SERPER_DISCOVERY_REGION_SUFFIX == "Україна"


def test_page_verify_prompt_ukrainian():
    p = build_page_verify_prompt(
        "ТОВ Будматеріали",
        "https://budmat.ua",
        "Оптовий склад цементу та піску в Києві",
    )
    assert "україн" in p.lower() or "Україн" in p
    assert "is_gu" in p


def test_claude_inquiry_prompt_no_attachments():
    p = build_personalized_inquiry_email_prompt_uk(company_name="ТОВ Тест")
    assert "вкладення" in p.lower() or "файли" in p.lower()


@patch("mail_transport.send_smtp_email")
@patch("scraper_env.get_mail_password", return_value="secret")
@patch("scraper_env.get_mail_user", return_value="test@gmail.com")
def test_send_email_integration_no_attachments(mock_user, mock_pwd, mock_send):
    mock_send.return_value = (True, "gesendet")
    ok, info = scraper.send_email_ua_materialy(
        "kontakt@budmat.ua",
        "Запит щодо постачання",
        "Шановні пані та панове,\n\nТест.",
        _LOGGER,
    )
    assert ok is True
    assert info == "gesendet"
    assert mock_send.call_count == 1
    kwargs = mock_send.call_args.kwargs
    assert kwargs["campaign"] == "ua_materialy"
    assert kwargs["attachment_paths"] == []


def test_generate_email_fallback_template(monkeypatch):
    monkeypatch.setattr(scraper, "ENABLE_CLAUDE_INQUIRY_EMAIL", False)
    monkeypatch.setattr(scraper, "USE_CUSTOM_EMAIL_TEMPLATE", False)
    subject, body = scraper.generate_email_content(
        "ТОВ Будмаркет",
        _LOGGER,
        cache={},
    )
    assert subject
    assert "Шановні" in body or "будівельних" in body.lower()
    assert "+380977091141" in body
    assert "mfg" not in body.lower()


def test_discovery_funnel_counters():
    funnel = scraper.new_discovery_funnel()
    funnel["serper_queries"] = 5
    funnel["pending_saved"] = 12
    scraper.log_discovery_funnel(funnel, _LOGGER)
    assert funnel["pending_saved"] == 12
