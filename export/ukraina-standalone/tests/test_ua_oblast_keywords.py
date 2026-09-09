# -*- coding: utf-8 -*-
from __future__ import annotations

from ua_oblast_keywords import (
    OBLAST_CONFIG,
    SERPER_DISCOVERY_BROAD_TERMS,
    SERPER_DISCOVERY_FALLBACK_TERMS,
    SERPER_DISCOVERY_LANDKREIS_TERMS,
    SERPER_DISCOVERY_PLACES_TERMS,
    SERPER_DISCOVERY_TERMS,
    build_discovery_terms,
    build_region_suffix,
    configure_campaign_oblasts,
)
from ua_oblast_rotation import OBLAST_ROTATION_ORDER, peek_next_oblast


def test_oblast_config_has_cities():
    assert len(OBLAST_CONFIG) >= 24
    assert "Kyiv" in OBLAST_CONFIG
    assert OBLAST_CONFIG["Lvivska"]["cities"]


def test_discovery_terms_ukrainian():
    terms = build_discovery_terms(["Kyiv"], max_terms=20)
    assert len(terms) >= 10
    assert any("будматеріали" in t or "будівельні" in t for t in terms)


def test_discovery_waves_non_empty():
    assert len(SERPER_DISCOVERY_FALLBACK_TERMS) >= 5
    assert len(SERPER_DISCOVERY_BROAD_TERMS) >= 10
    assert len(SERPER_DISCOVERY_LANDKREIS_TERMS) >= 5
    assert len(SERPER_DISCOVERY_PLACES_TERMS) >= 5


def test_region_suffix():
    assert build_region_suffix(["Kyiv"]) == "Україна"


def test_rotation_order():
    assert peek_next_oblast() == OBLAST_ROTATION_ORDER[0]
    assert len(OBLAST_ROTATION_ORDER) == 25


def test_configure_module():
    class M:
        pass

    mod = M()
    active = configure_campaign_oblasts(mod, ["Lvivska"], max_discovery_terms=30)
    assert active == ["Lvivska"]
    assert len(mod.SERPER_DISCOVERY_TERMS) <= 30
    assert mod.SERPER_DISCOVERY_REGION_SUFFIX == "Україна"


def test_default_terms_exported():
    assert len(SERPER_DISCOVERY_TERMS) >= 100
