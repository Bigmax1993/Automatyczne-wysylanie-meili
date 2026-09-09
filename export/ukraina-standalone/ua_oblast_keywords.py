# -*- coding: utf-8 -*-
"""
Słowniki kampanii UA — hurtownie / składy / producenci materiałów budowlanych.
Frazy Serper per obwód; rotacja kategorii materiałów.
"""
from __future__ import annotations

# --- Role / kontekst dostawcy ---
SUPPLIER_ROLE_KEYWORDS: tuple[str, ...] = (
    "будматеріали",
    "будівельні матеріали",
    "оптом",
    "оптовий",
    "склад",
    "магазин будматеріалів",
    "постачальник",
    "дистриб'ютор",
    "виробник",
    "продаж",
    "доставка",
    "будівельний магазин",
    "будмаркет",
    "будівельна база",
)

MATERIAL_CATEGORY_KEYWORDS: tuple[str, ...] = (
    "цемент",
    "пісок",
    "щебінь",
    "керамзит",
    "цегла",
    "блок",
    "газоблок",
    "піноблок",
    "арматура",
    "металопрокат",
    "дошка",
    "брус",
    "фанера",
    "osb",
    "утеплювач",
    "мінвата",
    "пінопласт",
    "плитка",
    "кераміка",
    "гіпсокартон",
    "штукатурка",
    "фарба",
    "покрівля",
    "металочерепиця",
    "профнастил",
    "цементно-піщана суміш",
    "бетон",
    "гравій",
    "щебень",
)

REQUIRED_MATERIAL_CATEGORY_KEYWORDS = MATERIAL_CATEGORY_KEYWORDS

MATERIAL_SUPPLY_KEYWORDS = SUPPLIER_ROLE_KEYWORDS
MATERIAL_TRADE_ACTIVITY_KEYWORDS = (
    "каталог",
    "прайс",
    "ціни",
    "асортимент",
    "в наявності",
    "складська програма",
    "доставка по україні",
    "самовивіз",
)
MATERIAL_CATALOG_KEYWORDS = (
    "каталог товарів",
    "наш асортимент",
    "продукція",
    "товари",
    "прайс-лист",
    "ціни на",
)
MATERIAL_URL_PRIORITY_KEYWORDS = (
    "kontakt",
    "контакт",
    "contacts",
    "produkcja",
    "produkty",
    "каталог",
    "asortyment",
    "price",
    "прайс",
)
IMPRESSUM_GUESS_PATHS = (
    "/kontakt",
    "/contact",
    "/contacts",
    "/контакти",
    "/pro-kompaniyu",
    "/about",
    "/o-nas",
    "/imprint",
    "/impressum",
)
SUPPLIER_CONTACT_LINK_KEYWORDS = (
    "контакт",
    "зв'язатися",
    "звязатися",
    "email",
    "e-mail",
    "телефон",
    "замовити",
    "заявка",
)

SERPER_POSITIVE_TERMS = (
    *SUPPLIER_ROLE_KEYWORDS,
    *MATERIAL_CATEGORY_KEYWORDS[:20],
)
SERPER_NEGATIVE_TERMS = (
    "новини",
    "блог",
    "форум",
    "вакансії",
    "робота",
    "державна",
    "міністерство",
    "портал",
    "енциклопедія",
    "wikipedia",
    "olx оголошення",
    "б/у",
    "вживаний",
    "ремонт квартир",
    "дизайн інтер'єру",
    "архітектурне бюро",
    "проєктування будинків",
    "банк",
    "страхова",
    "кредит",
    "автосалон",
    "ресторан",
    "готель",
    "туризм",
)

LARGE_COMPANY_DOMAINS_EXTRA: frozenset[str] = frozenset()
LARGE_COMPANY_NAME_MARKERS_EXTRA: tuple[str, ...] = ()
SMALL_COMPANY_PAGE_MARKERS_EXTRA: tuple[str, ...] = (
    "сімейне підприємство",
    "приватне підприємство",
    "фоп",
    "тов",
    "пп",
    "регіональний",
    "місцевий",
)
SMALL_COMPANY_DISCOVERY_TERMS_EXTRA: tuple[str, ...] = (
    "невеликий склад",
    "регіональний постачальник",
    "місцевий виробник",
)

UA_PLACE_MARKERS: tuple[str, ...] = ()
UA_REGION_KEYWORDS = (
    "україна",
    "ukraine",
    "украина",
)
UA_RURAL_HINTS: tuple[str, ...] = ()

# Rotacja kategorii materiałów w szablonach Serper
MATERIAL_CATEGORIES_ROTATION = (
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
)

CHAIN_SIMPLE_TERM_TEMPLATES = (
    "будматеріали {city} {material} опт",
    "будівельні матеріали {city} {material}",
    "склад будматеріалів {city} {material}",
    "магазин будматеріалів {city} {material}",
    "постачальник {material} {city}",
    "оптовий склад {material} {city}",
    "будівельна база {city} {material}",
    "будмаркет {city} {material}",
)

TERM_TEMPLATES = (
    "будматеріали {city} {oblast} {material} доставка",
    "інтернет-магазин будматеріалів {city} {material}",
    "виробник {material} {city} {oblast}",
    "дистриб'ютор будматеріалів {city} {material}",
    "продаж {material} оптом {city}",
    "будівельні матеріали {oblast} {city} {material}",
)

SIMPLE_TERM_TEMPLATES = CHAIN_SIMPLE_TERM_TEMPLATES

OBLAST_CONFIG: dict[str, dict] = {
    "Kyiv": {
        "short": "KY",
        "cities": ("Київ", "Бровари", "Буча", "Ірпінь", "Вишневе", "Бориспіль"),
    },
    "Kyivska": {
        "short": "KV",
        "cities": ("Біла Церква", "Фастів", "Васильків", "Обухів", "Переяслав"),
    },
    "Lvivska": {
        "short": "LV",
        "cities": ("Львів", "Дрогобич", "Стрий", "Червоноград", "Самбір", "Борислав"),
    },
    "Odeska": {
        "short": "OD",
        "cities": ("Одеса", "Ізмаїл", "Чорноморськ", "Білгород-Дністровський", "Южне"),
    },
    "Kharkivska": {
        "short": "KH",
        "cities": ("Харків", "Лозова", "Ізюм", "Куп'янськ", "Чугуїв"),
    },
    "Dnipropetrovska": {
        "short": "DP",
        "cities": ("Дніпро", "Кривий Ріг", "Кам'янське", "Нікополь", "Павлоград"),
    },
    "Zaporizka": {
        "short": "ZP",
        "cities": ("Запоріжжя", "Мелітополь", "Бердянськ", "Енергодар"),
    },
    "Vinnytska": {
        "short": "VN",
        "cities": ("Вінниця", "Жмеринка", "Хмільник", "Козятин"),
    },
    "Poltavska": {
        "short": "PL",
        "cities": ("Полтава", "Кременчук", "Лубни", "Миргород"),
    },
    "Cherkaska": {
        "short": "CK",
        "cities": ("Черкаси", "Умань", "Сміла", "Золотоноша"),
    },
    "Zhytomyrska": {
        "short": "ZT",
        "cities": ("Житомир", "Бердичів", "Коростень", "Новоград-Волинський"),
    },
    "Rivnenska": {
        "short": "RV",
        "cities": ("Рівне", "Дубно", "Костопіль", "Сарни"),
    },
    "Volyn": {
        "short": "VL",
        "cities": ("Луцьк", "Ковель", "Нововолинськ", "Володимир"),
    },
    "Ternopilska": {
        "short": "TP",
        "cities": ("Тернопіль", "Чортків", "Кременець", "Бережани"),
    },
    "Ivano-Frankivska": {
        "short": "IF",
        "cities": ("Івано-Франківськ", "Калуш", "Коломия", "Долина"),
    },
    "Chernivetska": {
        "short": "CV",
        "cities": ("Чернівці", "Хотин", "Новодністровськ"),
    },
    "Zakarpatska": {
        "short": "ZK",
        "cities": ("Ужгород", "Мукачево", "Хуст", "Берегове"),
    },
    "Khmelnytska": {
        "short": "KM",
        "cities": ("Хмельницький", "Кам'янець-Подільський", "Шепетівка", "Нетішин"),
    },
    "Chernihivska": {
        "short": "CN",
        "cities": ("Чернігів", "Ніжин", "Прилуки", "Бахмач"),
    },
    "Sumska": {
        "short": "SM",
        "cities": ("Суми", "Конотоп", "Шостка", "Охтирка"),
    },
    "Mykolaivska": {
        "short": "MK",
        "cities": ("Миколаїв", "Первомайськ", "Вознесенськ", "Очаків"),
    },
    "Kirovohradska": {
        "short": "KR",
        "cities": ("Кропивницький", "Олександрія", "Світловодськ", "Знам'янка"),
    },
    "Donetska": {
        "short": "DN",
        "cities": ("Краматорськ", "Слов'янськ", "Покровськ", "Маріуполь"),
    },
    "Luhanska": {
        "short": "LG",
        "cities": ("Сєвєродонецьк", "Лисичанськ", "Рубіжне", "Кремінна"),
    },
    "Khersonska": {
        "short": "KS",
        "cities": ("Херсон", "Нова Каховка", "Каховка", "Скадовськ"),
    },
}

ALL_OBLASTS: tuple[str, ...] = tuple(OBLAST_CONFIG.keys())
DEFAULT_ACTIVE_OBLASTS: list[str] = list(ALL_OBLASTS)
CAMPAIGN_ACTIVE_OBLASTS: list[str] = list(DEFAULT_ACTIVE_OBLASTS)

# Aliasy kompatybilności z pipeline GU (scraper używa tych samych nazw funkcji)
BUNDESLAND_CONFIG = OBLAST_CONFIG
ALL_BUNDESLAENDER = ALL_OBLASTS
DEFAULT_ACTIVE_BUNDESLAENDER = DEFAULT_ACTIVE_OBLASTS
CAMPAIGN_ACTIVE_BUNDESLAENDER = CAMPAIGN_ACTIVE_OBLASTS

COUNTRYWIDE_MAX_DISCOVERY_TERMS = 2400


def default_max_discovery_terms_for(active: list[str] | None = None) -> int:
    n = len(resolve_active_oblasts(active))
    if n <= 1:
        return 120
    if n <= 3:
        return 360
    return COUNTRYWIDE_MAX_DISCOVERY_TERMS


def _normalize_oblast_key(name: str) -> str:
    n = (name or "").strip()
    aliases = {
        "kyiv": "Kyiv",
        "kiev": "Kyiv",
        "київ": "Kyiv",
        "ky": "Kyiv",
        "lviv": "Lvivska",
        "lv": "Lvivska",
        "львів": "Lvivska",
        "odesa": "Odeska",
        "odessa": "Odeska",
        "od": "Odeska",
        "kharkiv": "Kharkivska",
        "kh": "Kharkivska",
        "dnipro": "Dnipropetrovska",
        "dp": "Dnipropetrovska",
        "zaporizhzhia": "Zaporizka",
        "zp": "Zaporizka",
    }
    low = n.lower()
    if low in aliases:
        return aliases[low]
    for key in OBLAST_CONFIG:
        if key.lower() == low:
            return key
    return n


def resolve_active_oblasts(names: list[str] | None = None) -> list[str]:
    if not names:
        return list(CAMPAIGN_ACTIVE_OBLASTS)
    out: list[str] = []
    for raw in names:
        for part in str(raw).replace(";", ",").split(","):
            key = _normalize_oblast_key(part)
            if key in OBLAST_CONFIG and key not in out:
                out.append(key)
    return out or list(DEFAULT_ACTIVE_OBLASTS)


resolve_active_bundeslaender = resolve_active_oblasts


def _append_unique_term(terms: list[str], seen: set[str], text: str, *, max_terms: int) -> bool:
    t = (text or "").strip()
    if not t or t in seen:
        return False
    seen.add(t)
    terms.append(t)
    return len(terms) >= max_terms


def _rotating_material(counter: list[int]) -> str:
    material = MATERIAL_CATEGORIES_ROTATION[counter[0] % len(MATERIAL_CATEGORIES_ROTATION)]
    counter[0] += 1
    return material


def _format_material_term(
    tmpl: str,
    *,
    city: str,
    oblast: str,
    material: str,
) -> str:
    return tmpl.format(city=city, oblast=oblast, material=material, land=oblast, chain=material)


def build_discovery_terms(
    active: list[str] | None = None, *, max_terms: int | None = None
) -> list[str]:
    oblasts = resolve_active_oblasts(active)
    if max_terms is None:
        max_terms = default_max_discovery_terms_for(oblasts)
    seen: set[str] = set()
    terms: list[str] = []
    material_counter = [0]
    all_templates = (*CHAIN_SIMPLE_TERM_TEMPLATES, *TERM_TEMPLATES)
    for oblast in oblasts:
        cfg = OBLAST_CONFIG[oblast]
        cities = cfg["cities"]
        for city in cities:
            for tmpl in all_templates:
                material = _rotating_material(material_counter)
                if _append_unique_term(
                    terms,
                    seen,
                    _format_material_term(
                        tmpl, city=city, oblast=oblast, material=material
                    ),
                    max_terms=max_terms,
                ):
                    return terms
    if len(oblasts) >= 10:
        countrywide = (
            "будматеріали Україна {material} опт",
            "оптовий склад будматеріалів Україна {material}",
            "постачальник {material} Україна",
            "будівельні матеріали Україна {material} доставка",
            "будмаркет Україна {material}",
        )
        for tmpl in countrywide:
            material = _rotating_material(material_counter)
            if _append_unique_term(
                terms,
                seen,
                tmpl.format(material=material),
                max_terms=max_terms,
            ):
                return terms
    return terms


def build_raion_discovery_terms(active: list[str] | None = None) -> list[str]:
    """Frazy z rajonem / okolicą — czwarta fala discovery."""
    oblasts = resolve_active_oblasts(active)
    seen: set[str] = set()
    terms: list[str] = []
    material_counter = [0]
    for oblast in oblasts:
        short = OBLAST_CONFIG[oblast]["short"]
        for city in OBLAST_CONFIG[oblast]["cities"][:6]:
            for tmpl in (
                "будматеріали {city} район {material}",
                "склад будматеріалів {city} {short} {material}",
                "будівельна база {city} {material}",
            ):
                material = _rotating_material(material_counter)
                _append_unique_term(
                    terms,
                    seen,
                    tmpl.format(city=city, short=short, material=material),
                    max_terms=10_000,
                )
        material = _rotating_material(material_counter)
        _append_unique_term(
            terms,
            seen,
            f"будматеріали {oblast} {material} опт",
            max_terms=10_000,
        )
    return terms


build_landkreis_discovery_terms = build_raion_discovery_terms


def build_places_discovery_terms(active: list[str] | None = None) -> list[str]:
    oblasts = resolve_active_oblasts(active)
    seen: set[str] = set()
    terms: list[str] = []
    material_counter = [0]
    for oblast in oblasts:
        for city in OBLAST_CONFIG[oblast]["cities"][:8]:
            for tmpl in (
                "будматеріали {city} {material}",
                "магазин будматеріалів {city} {material}",
                "склад {material} {city}",
                "будмаркет {city} {material}",
            ):
                material = _rotating_material(material_counter)
                _append_unique_term(
                    terms,
                    seen,
                    tmpl.format(city=city, material=material),
                    max_terms=10_000,
                )
        material = _rotating_material(material_counter)
        _append_unique_term(
            terms,
            seen,
            f"будматеріали {oblast} {material}",
            max_terms=10_000,
        )
    return terms


def build_broad_discovery_terms(active: list[str] | None = None) -> list[str]:
    oblasts = resolve_active_oblasts(active)
    seen: set[str] = set()
    terms: list[str] = []
    material_counter = [0]
    for oblast in oblasts:
        short = OBLAST_CONFIG[oblast]["short"]
        for city in OBLAST_CONFIG[oblast]["cities"]:
            for tmpl in (
                "будматеріали {city} {material}",
                "будівельні матеріали {city} {material}",
                "постачальник {material} {city}",
            ):
                material = _rotating_material(material_counter)
                _append_unique_term(
                    terms,
                    seen,
                    tmpl.format(city=city, material=material),
                    max_terms=10_000,
                )
        for tmpl in (
            "будматеріали {oblast} {material} опт",
            "склад будматеріалів {oblast} {material}",
            "будмаркет {short} {material}",
        ):
            material = _rotating_material(material_counter)
            _append_unique_term(
                terms,
                seen,
                tmpl.format(oblast=oblast, short=short, material=material),
                max_terms=10_000,
            )
    return terms


def build_region_suffix(active: list[str] | None = None) -> str:
    oblasts = resolve_active_oblasts(active)
    if len(oblasts) <= 1:
        return "Україна"
    if len(oblasts) >= 4:
        return "Україна"
    shorts = " ".join(OBLAST_CONFIG[o]["short"] for o in oblasts[:4])
    return f"Україна {shorts}"


def configure_campaign_oblasts(
    module,
    names: list[str],
    *,
    max_discovery_terms: int | None = None,
) -> list[str]:
    global CAMPAIGN_ACTIVE_OBLASTS, CAMPAIGN_ACTIVE_BUNDESLAENDER
    active = resolve_active_oblasts(names)
    if max_discovery_terms is None:
        max_discovery_terms = default_max_discovery_terms_for(active)
    CAMPAIGN_ACTIVE_OBLASTS = active
    CAMPAIGN_ACTIVE_BUNDESLAENDER = active
    module.CAMPAIGN_ACTIVE_OBLASTS = active
    module.CAMPAIGN_ACTIVE_BUNDESLAENDER = active
    module.SERPER_DISCOVERY_TERMS = build_discovery_terms(
        active, max_terms=max_discovery_terms
    )
    module.SERPER_DISCOVERY_FALLBACK_TERMS = build_fallback_terms(active)
    module.SERPER_DISCOVERY_BROAD_TERMS = build_broad_discovery_terms(active)
    module.SERPER_DISCOVERY_LANDKREIS_TERMS = build_raion_discovery_terms(active)
    module.SERPER_DISCOVERY_PLACES_TERMS = build_places_discovery_terms(active)
    module.SERPER_DISCOVERY_REGION_SUFFIX = build_region_suffix(active)
    return active


configure_campaign_bundeslaender = configure_campaign_oblasts


def build_fallback_terms(active: list[str] | None = None) -> list[str]:
    oblasts = resolve_active_oblasts(active)
    fb: list[str] = []
    material_counter = [0]
    for oblast in oblasts:
        short = OBLAST_CONFIG[oblast]["short"]
        for tmpl in (
            "будматеріали {oblast} {material} опт",
            "будівельні матеріали {short} {material}",
            "склад будматеріалів {oblast} {material}",
            "будмаркет {oblast} {material}",
        ):
            material = _rotating_material(material_counter)
            fb.append(tmpl.format(oblast=oblast, short=short, material=material))
    for tmpl in (
        "будматеріали Україна {material} опт",
        "оптовий склад будматеріалів Україна {material}",
        "постачальник будматеріалів Україна {material}",
        "будівельна база Україна {material}",
    ):
        material = _rotating_material(material_counter)
        fb.append(tmpl.format(material=material))
    seen: set[str] = set()
    out: list[str] = []
    for t in fb:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


SERPER_DISCOVERY_TERMS = build_discovery_terms()
SERPER_DISCOVERY_FALLBACK_TERMS = build_fallback_terms()
SERPER_DISCOVERY_BROAD_TERMS = build_broad_discovery_terms()
SERPER_DISCOVERY_LANDKREIS_TERMS = build_raion_discovery_terms()
SERPER_DISCOVERY_PLACES_TERMS = build_places_discovery_terms()
SERPER_DISCOVERY_REGION_SUFFIX = build_region_suffix()

# Aliasy dla importów ze scrapera GU
GU_ROLE_KEYWORDS = SUPPLIER_ROLE_KEYWORDS
RETAIL_CHAIN_KEYWORDS = MATERIAL_CATEGORY_KEYWORDS
REQUIRED_RETAIL_CHAIN_KEYWORDS = REQUIRED_MATERIAL_CATEGORY_KEYWORDS
RETAIL_BUILD_KEYWORDS = MATERIAL_SUPPLY_KEYWORDS
RETAIL_TRADE_ACTIVITY_KEYWORDS = MATERIAL_TRADE_ACTIVITY_KEYWORDS
RETAIL_HOCHBAU_CORE_KEYWORDS = MATERIAL_CATALOG_KEYWORDS
RETAIL_REFERENCE_KEYWORDS = MATERIAL_CATALOG_KEYWORDS
RETAIL_URL_PRIORITY_KEYWORDS = MATERIAL_URL_PRIORITY_KEYWORDS
RETAIL_CONTACT_LINK_KEYWORDS = SUPPLIER_CONTACT_LINK_KEYWORDS
DE_OST_PLACE_MARKERS = UA_PLACE_MARKERS
DE_OST_REGION_KEYWORDS = UA_REGION_KEYWORDS
DE_OST_RURAL_HINTS = UA_RURAL_HINTS
RETAIL_CHAINS_ROTATION = MATERIAL_CATEGORIES_ROTATION
