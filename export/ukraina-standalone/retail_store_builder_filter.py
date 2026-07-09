# -*- coding: utf-8 -*-
"""
Kampania UA: hurtownie / składy / producenci / dystrybutorzy materiałów budowlanych.
Nie: portale informacyjne, urzędy, czyste firmy wykonawcze bez sprzedaży materiałów.
"""
from __future__ import annotations

from commercial_contact_filter import (
    is_non_commercial_contact,
    is_valid_commercial_company_contact,
)

REQUIRE_GENERALUNTERNEHMER = True  # alias: wymagaj roli dostawcy materiałów

REQUIRED_RETAIL_CHAIN_KEYWORDS = (
    "цемент",
    "пісок",
    "щебінь",
    "цегла",
    "блок",
    "арматура",
    "утеплювач",
    "плитка",
    "гіпсокартон",
    "дошка",
    "металопрокат",
    "покрівля",
    "бетон",
    "гравій",
)

STRICT_GU_MARKERS = (
    "будматеріали",
    "будівельні матеріали",
    "оптом",
    "оптовий",
    "склад",
    "постачальник",
    "дистриб'ютор",
    "виробник",
    "будмаркет",
    "будівельна база",
    "будівельний магазин",
)

NON_GU_ROLE_EXCLUSION_MARKERS = (
    "архітектурне бюро",
    "проєктування",
    "дизайн інтер'єру",
    "дизайн интерьера",
    "банк",
    "страхова",
    "новинний портал",
    "енциклопедія",
    "державна установа",
    "міністерство",
    "біржа праці",
    "вакансії",
    "туристична агенція",
    "ресторан",
    "готель",
    "автосалон",
)

INTERIOR_FITOUT_MARKERS = (
    "дизайн інтер'єру",
    "ремонт квартир під ключ",
    "оздоблення інтер'єру",
    "меблевий салон",
)

STORE_SHELL_BUILD_MARKERS = MATERIAL_CATALOG_MARKERS = (
    "каталог товарів",
    "наш асортимент",
    "продукція",
    "прайс-лист",
    "ціни на",
    "в наявності",
    "складська програма",
)

RETAIL_STORE_BUILD_MARKERS = STRICT_GU_MARKERS
RETAIL_STORE_UMBAU_MARKERS = MATERIAL_CATALOG_MARKERS
FILIALBAU_SPECIALIST_MARKERS = STRICT_GU_MARKERS
GU_BUILDER_MARKERS = STRICT_GU_MARKERS

RETAIL_OPERATOR_DOMAIN_MARKERS = (
    "olx.ua",
    "prom.ua",
    "rozetka.",
    "allo.ua",
)
RETAIL_OPERATOR_PAGE_MARKERS = (
    "оголошення",
    "купити б/у",
    "вживаний",
    "барахолка",
)
RETAIL_STORE_CONTEXT_MARKERS = STRICT_GU_MARKERS + MATERIAL_CATALOG_MARKERS

MEDIA_PUBLISHER_DOMAIN_MARKERS = (
    "news.",
    "novosti",
    "gazeta",
    "portal",
    "wikipedia",
)
MEDIA_PUBLISHER_NAME_MARKERS = (
    "новини",
    "портал",
    "видання",
    "редакція",
    "медіа",
)
MEDIA_PUBLISHER_URL_PATH_MARKERS = (
    "/news/",
    "/novosti/",
    "/article/",
    "/blog/",
)

PORTFOLIO_SECTION_MARKERS = MATERIAL_CATALOG_MARKERS
RETAIL_CHAIN_IN_PORTFOLIO_MARKERS = REQUIRED_RETAIL_CHAIN_KEYWORDS
MARKET_PROJECT_IN_PORTFOLIO_MARKERS = REQUIRED_RETAIL_CHAIN_KEYWORDS
MARKET_PHOTO_GALLERY_MARKERS = ("каталог", "галерея", "асортимент", "продукція")
RETAIL_PROJECT_DESCRIPTION_MARKERS = MATERIAL_CATALOG_MARKERS
RETAIL_PROJECT_BUILD_ACTIVITY_MARKERS = STRICT_GU_MARKERS
RETAIL_IMAGE_FILE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")
PURE_RENOVATION_WITHOUT_STORE_BUILD = (
    "дизайн інтер'єру",
    "ремонт квартир",
    "оздоблювальні роботи",
)


def _blob(*parts: str) -> str:
    return " ".join(p for p in parts if p).lower()


def detect_required_retail_chains(text: str) -> list[str]:
    low = (text or "").lower()
    return [c for c in REQUIRED_RETAIL_CHAIN_KEYWORDS if c in low]


def has_required_retail_chain_mention(text: str) -> bool:
    return bool(detect_required_retail_chains(text))


def has_store_shell_build_evidence(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in STRICT_GU_MARKERS) or any(
        m in low for m in MATERIAL_CATALOG_MARKERS
    )


def is_interior_fitout_specialist(text: str) -> tuple[bool, str]:
    low = (text or "").lower()
    for m in INTERIOR_FITOUT_MARKERS:
        if m in low:
            return True, f"interior_fitout:{m}"
    return False, ""


def has_retail_context_without_named_chain(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in STRICT_GU_MARKERS)


def is_excluded_non_gu_role(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in NON_GU_ROLE_EXCLUSION_MARKERS)


def is_generalunternehmer(text: str) -> tuple[bool, str]:
    low = (text or "").lower()
    for m in STRICT_GU_MARKERS:
        if m in low:
            return True, m
    return False, ""


def qualifies_as_gu_for_campaign(text: str) -> tuple[bool, str]:
    low = (text or "").lower()
    if is_excluded_non_gu_role(low):
        return False, "excluded_role"
    supplier, marker = is_generalunternehmer(low)
    if not supplier:
        return False, "kein_lieferant"
    has_material = has_required_retail_chain_mention(low) or any(
        m in low for m in MATERIAL_CATALOG_MARKERS
    )
    if not has_material:
        return False, "kein_materialkontext"
    return True, marker or "lieferant"


def is_gu_or_retail_build_specialist(text: str) -> bool:
    ok, _ = qualifies_as_gu_for_campaign(text)
    return ok


def is_media_publisher_contact(
    *,
    url: str = "",
    name: str = "",
    text: str = "",
    email: str = "",
) -> bool:
    blob = _blob(url, name, text, email)
    if any(m in blob for m in MEDIA_PUBLISHER_DOMAIN_MARKERS):
        return True
    if any(m in blob for m in MEDIA_PUBLISHER_NAME_MARKERS):
        return True
    if any(m in blob for m in MEDIA_PUBLISHER_URL_PATH_MARKERS):
        return True
    return False


def is_retail_store_operator_contact(
    *,
    url: str = "",
    name: str = "",
    text: str = "",
    email: str = "",
) -> bool:
    blob = _blob(url, name, text, email)
    if any(m in blob for m in RETAIL_OPERATOR_DOMAIN_MARKERS):
        return True
    if any(m in blob for m in RETAIL_OPERATOR_PAGE_MARKERS):
        return True
    return False


def portfolio_negates_market_projects(text: str) -> bool:
    return False


def has_market_project_evidence_on_website(text: str) -> bool:
    low = (text or "").lower()
    return has_required_retail_chain_mention(low) or any(
        m in low for m in MATERIAL_CATALOG_MARKERS
    )


def has_retail_references_or_portfolio(text: str) -> bool:
    return has_market_project_evidence_on_website(text)


def is_gu_or_retail_build_specialist_for_serper_discovery(text: str) -> bool:
    return is_gu_or_retail_build_specialist(text)


def mentions_retail_store_build_activity_core(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in STRICT_GU_MARKERS)


def mentions_retail_store_build_activity_serper_discovery(text: str) -> bool:
    return mentions_retail_store_build_activity_core(text)


def mentions_retail_store_build_activity(text: str) -> bool:
    return mentions_retail_store_build_activity_core(text)


def is_serper_only_pending_candidate(
    *,
    name: str = "",
    url: str = "",
    text: str = "",
    search_term: str = "",
) -> bool:
    blob = _blob(name, url, text, search_term)
    if is_media_publisher_contact(url=url, name=name, text=blob):
        return False
    if is_retail_store_operator_contact(url=url, name=name, text=blob):
        return False
    if is_excluded_non_gu_role(blob):
        return False
    return any(m in blob for m in STRICT_GU_MARKERS)


def is_loose_serper_discovery_candidate(
    *,
    name: str = "",
    url: str = "",
    text: str = "",
    search_term: str = "",
) -> bool:
    return is_serper_only_pending_candidate(
        name=name, url=url, text=text, search_term=search_term
    )


def is_valid_retail_store_builder_contact(
    *,
    url: str = "",
    name: str = "",
    text: str = "",
    email: str = "",
    search_term: str = "",
) -> bool:
    blob = _blob(name, url, text, email, search_term)
    if is_media_publisher_contact(url=url, name=name, text=blob, email=email):
        return False
    if is_retail_store_operator_contact(url=url, name=name, text=blob, email=email):
        return False
    if is_excluded_non_gu_role(blob):
        return False
    interior, _ = is_interior_fitout_specialist(blob)
    if interior:
        return False
    if not is_valid_commercial_company_contact(name=name, url=url, email=email):
        return False
    if is_non_commercial_contact(name=name, url=url, email=email):
        return False
    ok, _ = qualifies_as_gu_for_campaign(blob)
    return ok


def is_cache_contact_not_store_builder(place_url: str, info: dict | None) -> bool:
    info = info or {}
    return not is_valid_retail_store_builder_contact(
        url=place_url or info.get("url", ""),
        name=info.get("nazwa") or info.get("name") or info.get("company_name", ""),
        text=" ".join(
            str(info.get(k, ""))
            for k in (
                "page_snippet",
                "snippet",
                "text",
                "verification_reason",
                "retail_chains_found",
            )
        ),
        email=info.get("email_target") or info.get("email", ""),
    )
