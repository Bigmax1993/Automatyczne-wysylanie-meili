# -*- coding: utf-8 -*-
"""Prompty Claude — kampania UA: hurtownie materiałów budowlanych."""
from __future__ import annotations

import re

from ua_campaign_keyword_profile import (
    SERPER_TEMPLATE_PATTERNS,
    gu_required_keywords_sample,
    large_company_markers_sample,
    negative_keywords_sample,
    retail_chain_keywords_sample,
    retail_context_keywords_sample,
    small_company_markers_sample,
)

_REQUIRED_MATERIALS = "цемент, пісок, щебінь, цегла, блок, арматура, утеплювач, плитка, гіпсокартон"
PAGE_VERIFY_MAX_CHARS = 18000
CONTACT_EXTRACT_MAX_CHARS = 16000
_CONTACT_EXTRACT_TEXT_PRIORITY = (
    "контакт",
    "kontakt",
    "contact",
    "mailto",
    "@",
    "тел",
    "телефон",
    "phone",
    "email",
    "e-mail",
    "адреса",
)
_PAGE_VERIFY_TEXT_PRIORITY = (
    "будматеріали",
    "будівельні",
    "каталог",
    "асортимент",
    "продукція",
    "прайс",
    "ціни",
    "опт",
    "склад",
    "доставка",
    "цемент",
    "пісок",
    "щебінь",
    "цегла",
    "утеплювач",
    "плитка",
)


def prioritize_page_text_for_verify(
    page_text: str,
    *,
    max_chars: int = PAGE_VERIFY_MAX_CHARS,
    priority_keywords: tuple[str, ...] | None = None,
) -> str:
    keys = priority_keywords or _PAGE_VERIFY_TEXT_PRIORITY
    raw = (page_text or "").strip()
    if len(raw) <= max_chars:
        return raw
    if "=== http" in raw:
        sections = re.split(r"(?=\n=== https?://)", "\n" + raw)
        sections = [s.strip() for s in sections if s.strip()]
        priority_sec: list[str] = []
        other_sec: list[str] = []
        for sec in sections:
            low = sec.lower()
            if any(k in low for k in keys):
                priority_sec.append(sec)
            else:
                other_sec.append(sec)
        merged = "\n\n".join(priority_sec + other_sec)
    else:
        lines = [ln.strip() for ln in re.split(r"[\n\r]+", raw) if ln.strip()]
        if not lines:
            return raw[:max_chars]
        priority: list[str] = []
        other: list[str] = []
        for ln in lines:
            low = ln.lower()
            if any(k in low for k in keys):
                priority.append(ln)
            else:
                other.append(ln)
        merged = " ".join(priority + other)
    if len(merged) <= max_chars:
        return merged
    return merged[: max_chars - 3] + "..."


def build_page_verify_prompt(
    company_name: str,
    website: str,
    page_text: str,
    *,
    max_chars: int = PAGE_VERIFY_MAX_CHARS,
    serper_blob: str = "",
    pages_crawled: int = 0,
) -> str:
    from claude_page_text import (
        build_automatic_evidence_excerpt,
        build_claude_context_header,
        extract_crawl_section_urls,
    )

    raw = page_text or ""
    priority_urls = extract_crawl_section_urls(raw)
    header = build_claude_context_header(
        company_name,
        website,
        serper_blob=serper_blob,
        pages_crawled=pages_crawled or max(raw.count("=== http"), 1 if raw else 0),
        priority_urls=priority_urls,
    )
    evidence = build_automatic_evidence_excerpt(raw)
    snippet = prioritize_page_text_for_verify(raw, max_chars=max_chars)
    supplier_kw = ", ".join(gu_required_keywords_sample())
    material_kw = ", ".join(retail_context_keywords_sample())
    category_kw = ", ".join(retail_chain_keywords_sample())
    neg_kw = ", ".join(negative_keywords_sample())
    small_kw = ", ".join(small_company_markers_sample())
    large_kw = ", ".join(large_company_markers_sample())
    return f"""РОЛЬ
Ти — аналітик B2B для пошуку постачальників будівельних матеріалів в Україні.
Ціль: гуртові склади, магазини будматеріалів, виробники та дистриб'ютори.
НЕ ціль: портали новин, держустанови, чисті підрядники без продажу матеріалів, оголошення OLX.

ЗАВДАННЯ
Прочитай витяг сайту (усі підсторінки, позначені «=== URL ===»).
Чи це комерційний постачальник будматеріалів? Відповідай ЛИШЕ JSON — без markdown.

ЩО ВВАЖАЄТЬСЯ ДОКАЗОМ
• Продаж/опт будматеріалів, склад, доставка, каталог, прайс
• Згадка категорій: {_REQUIRED_MATERIALS}
• Роль: постачальник, виробник, дистриб'ютор, будмаркет, будівельна база

ВІДХИЛИТИ (is_gu=false / has_retail_context=false)
• Архітектурне бюро, дизайн інтер'єру, ремонт квартир без продажу матеріалів
• Новини, медіа, держоргани, банки, вакансії без комерційної пропозиції
• OLX/оголошення б/у без стабільного бізнесу постачальника

ПОЛЯ JSON (ті самі ключі для сумісності з pipeline)
• is_gu = true якщо це постачальник/виробник/склад будматеріалів
• has_retail_context = true якщо є комерційна пропозиція матеріалів (каталог, асортимент, ціни, опт)
• matched_chains = категорії матеріалів з тексту (цемент, пісок, …) — лише якщо згадані
• is_small_firm = регіональна/мала фірма (не велика міжнародна мережа)

МАЛІ ОЗНАКИ: {small_kw}
ВЕЛИКІ ОЗНАКИ (is_small_firm=false): {large_kw}

КЛЮЧОВІ СЛОВА ПОСТАЧАЛЬНИКА: {supplier_kw}
КОНТЕКСТ МАТЕРІАЛІВ: {material_kw}
КАТЕГОРІЇ: {category_kw}
НЕГАТИВ: {neg_kw}

СХЕМА JSON
{{
  "matched_gu_keywords": [],
  "matched_retail_keywords": [],
  "matched_chains": [],
  "matched_negative_keywords": [],
  "is_gu": false,
  "has_retail_context": false,
  "is_small_firm": false,
  "primary_role": "",
  "reason": ""
}}

КОНТЕКСТ
{header}

АВТОДОКАЗИ
{evidence}

ВИТЯГ САЙТУ
{snippet or "(порожньо)"}
"""


def build_row_cleanup_prompt(
    *,
    company: str,
    address: str,
    phone: str,
    email: str,
    website: str,
    states: str,
    handelsketten: str = "",
    url: str = "",
) -> str:
    return f"""РОЛЬ
Ти готуєш рядок Excel для B2B-бази постачальників будматеріалів в Україні.
Відповідай ЛИШЕ JSON.

СХЕМА
{{"company_name_clean":"","address":"","phone":"","website":"","bundesland":"","handelsketten":"","url":""}}

ПРАВИЛА
• company_name_clean — офіційна назва + форма (ТОВ, ПП, ФОП) або ""
• address — адреса в Україні або ""
• phone — один номер UA (+380 або 0…) або ""
• website — https://domain (корінь) або ""
• bundesland — один з: [{states}] або ""
• handelsketten — категорії матеріалів (цемент, пісок, …) через кому або ""
• url — як website

ВХІД
company={company!r}
address={address!r}
phone={phone!r}
email={email!r}
website={website!r}
handelsketten={handelsketten!r}
url={url!r}
"""


def build_personalized_inquiry_email_prompt_uk(
    *,
    company_name: str,
    website: str = "",
    oblast: str = "",
    address: str = "",
    materials: str = "",
    page_snippet: str = "",
    style_hint: str = "",
) -> str:
    from ua_materialy_inquiry_email_uk import (
        build_inquiry_sender_brief_uk,
        build_inquiry_signature_uk,
        build_sender_contact_line_uk,
    )

    snippet = (page_snippet or "").strip()
    if len(snippet) > 3500:
        snippet = snippet[:3497] + "..."
    style = (style_hint or "професійний, природний B2B-стиль, без шаблонних фраз").strip()
    mats = materials or "будматеріали (загальний асортимент)"
    sender_brief = build_inquiry_sender_brief_uk()
    sender_contact = build_sender_contact_line_uk()
    signature_block = build_inquiry_signature_uk()
    return f"""РОЛЬ
Ти — автор B2B-листів українською. Пишеш УНІКАЛЬНИЙ лист для КОНКРЕТНОЇ фірми-постачальника будматеріалів в Україні.
Кожен лист має відрізнятися формулюваннями — не копіюй один шаблон для всіх.

ВІДПРАВНИК (контекст, не вигадуй інших фактів)
{sender_brief}
Контакт: {sender_contact or "менеджер закупівель"}

ОДЕРЖУВАЧ
Назва: {company_name}
Сайт: {website or "(немає)"}
Область: {oblast or "(невідомо)"}
Адреса: {address or "(немає)"}
Категорії матеріалів (з бази): {mats}

ФРАГМЕНТ САЙТУ / ОПИС (використай для персоналізації — згадай їхній асортимент, регіон, спеціалізацію):
{snippet or "(немає — звернися загально до постачальника будматеріалів)"}

ЗАВДАННЯ
Напиши повністю персоналізований лист ЗАПИТУ про співпрацю / оптові ціни / прайс.
• Мова: ВИКЛЮЧНО українська.
• Звернення: «Шановні пані та панове» або персоналізоване до {company_name}.
• Обов'язково згадай щось конкретне про цю фірму (асортимент, регіон, тип діяльності) — на основі даних вище.
• Попроси прайс-лист або контакт відділу опту / продажів.
• Не вигадуй цін, знижок, термінів доставки, яких немає у вхідних даних.
• Стиль: {style}
• Довжина тіла: 120–220 слів (без підпису).

ЗАБОРОНЕНО
• Російська мова
• Німецькі номери (+49, 0049) — заборонено; єдиний контактний телефон: +380977091141 (у підписі)
• Слова: безкоштовно, акція, терміново, клікніть, знижка 50%
• Один і той самий текст для різних фірм
• Заборонено додавати вкладення / файли / посилання на завантаження
• HTML, markdown

ПІДПИС (додай у поле body наприкінці, БЕЗ змін):
{signature_block}

ВИХІД — ЛИШЕ JSON (без markdown):
{{"subject":"...","body":"..."}}

subject: унікальний, до 78 символів, українською, з назвою або спеціалізацією фірми
body: повний лист готовий до відправки (plain text), включно з підписом вище
"""


def build_custom_email_prompt_uk(
    draft: str,
    company_name: str,
    *,
    city_name: str = "",
    delivery_address: str = "",
) -> str:
    ctx_city = f"Регіон: {city_name}. " if city_name else ""
    ctx_addr = f"Адреса доставки (без змін): {delivery_address}. " if delivery_address else ""
    return f"""РОЛЬ
Ти редактор B2B-листів українською. Мінімально адаптуй шаблон під конкретну фірму.

ОДЕРЖУВАЧ
{company_name}
{ctx_city}{ctx_addr}

ЗАВДАННЯ
Адаптуй шаблон (1–2 речення контексту про фірму). Збережи ВСІ факти: обсяги, адреси, телефони, підпис.

ЗАБОРОНЕНО
• Вигадані ціни
• gratis, акція, терміново
• Зміна підпису

ВИХІД (лише JSON)
{{"subject":"...","body":"..."}}

ШАБЛОН
{draft}
"""
