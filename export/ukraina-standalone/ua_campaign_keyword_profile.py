# -*- coding: utf-8 -*-
"""
Wspólny słownik kampanii UA — materiały budowlane (Serper, regex, Claude).
"""
from __future__ import annotations

from ua_oblast_keywords import (
    MATERIAL_CATEGORY_KEYWORDS,
    SERPER_NEGATIVE_TERMS,
    SIMPLE_TERM_TEMPLATES,
    TERM_TEMPLATES,
)
from ua_materialy_supplier_filter import (
    FILIALBAU_SPECIALIST_MARKERS,
    INTERIOR_FITOUT_MARKERS,
    NON_GU_ROLE_EXCLUSION_MARKERS,
    REQUIRED_RETAIL_CHAIN_KEYWORDS,
    RETAIL_STORE_BUILD_MARKERS,
    RETAIL_STORE_UMBAU_MARKERS,
    STRICT_GU_MARKERS,
)

REJECT_PRIMARY_ROLES = frozenset(
    {
        "Медіа",
        "Портал",
        "Держустанова",
        "Банк",
        "Архітектурне бюро",
        "Дизайн інтер'єру",
        "Ремонт під ключ",
        "Підрядник без продажу",
        "Оголошення",
        "Інше",
    }
)

SERPER_TEMPLATE_PATTERNS: tuple[str, ...] = tuple(
    dict.fromkeys((*SIMPLE_TERM_TEMPLATES, *TERM_TEMPLATES))
)


def gu_required_keywords_sample(*, max_items: int = 12) -> list[str]:
    return list(STRICT_GU_MARKERS)[:max_items]


def retail_context_keywords_sample(*, max_items: int = 16) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for group in (
        FILIALBAU_SPECIALIST_MARKERS,
        RETAIL_STORE_BUILD_MARKERS,
        RETAIL_STORE_UMBAU_MARKERS,
    ):
        for item in group:
            key = item.strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(item.strip())
            if len(out) >= max_items:
                return out
    return out


def retail_chain_keywords_sample(*, max_items: int = 12) -> list[str]:
    return list(REQUIRED_RETAIL_CHAIN_KEYWORDS)[:max_items]


def small_company_markers_sample(*, max_items: int = 10) -> list[str]:
    return [
        "сімейне підприємство",
        "приватне підприємство",
        "фоп",
        "регіональний",
        "місцевий",
        "невеликий склад",
        "місцевий виробник",
        "регіональний постачальник",
        "тов",
        "пп",
    ][:max_items]


def large_company_markers_sample(*, max_items: int = 14) -> list[str]:
    return [
        "холдинг",
        "міжнародна мережа",
        "мережа магазинів",
        "понад 500 співробітників",
        "понад 1000 співробітників",
        "євроцемент",
        "knauf",
        "ceramika paradyż",
        "henkel",
        "sika",
        "weber",
        "ceresit",
        "житомирський",
        "будівельний комбінат",
    ][:max_items]


def negative_keywords_sample(*, max_items: int = 14) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in (
        *NON_GU_ROLE_EXCLUSION_MARKERS,
        *INTERIOR_FITOUT_MARKERS,
        *SERPER_NEGATIVE_TERMS[:20],
    ):
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
        if len(out) >= max_items:
            break
    return out
