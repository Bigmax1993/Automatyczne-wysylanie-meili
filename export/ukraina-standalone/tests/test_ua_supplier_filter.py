# -*- coding: utf-8 -*-
from __future__ import annotations

from ua_materialy_supplier_filter import (
    is_loose_serper_discovery_candidate,
    is_valid_retail_store_builder_contact,
    qualifies_as_gu_for_campaign,
)


def test_supplier_positive():
    ok, _ = qualifies_as_gu_for_campaign(
        "ТОВ Склад будматеріалів — опт цементу, піску, щебеню"
    )
    assert ok


def test_supplier_rejects_hotel():
    ok, reason = qualifies_as_gu_for_campaign("Готель Престиж — номери та ресторан")
    assert not ok
    assert reason == "excluded_role"


def test_loose_discovery_budmarket():
    assert is_loose_serper_discovery_candidate(
        name="Будмаркет",
        text="Оптовий склад будматеріалів у Києві",
        url="https://budmarket.ua",
    )


def test_valid_contact_email():
    assert is_valid_retail_store_builder_contact(
        name="Будбаза",
        text="Постачальник цементу",
        email="info@budbaza.ua",
        url="https://budbaza.ua",
    )
