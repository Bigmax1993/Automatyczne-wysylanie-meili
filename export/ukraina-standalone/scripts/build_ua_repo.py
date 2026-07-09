#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build standalone UA repo from wyszukiwarka-materialow-budowlanych-polska."""
from __future__ import annotations

import shutil
from pathlib import Path

SRC = Path("/tmp/wyszukiwarka-materialow-budowlanych-polska")
DST = Path("/tmp/wyszukiwarka-materialow-budowlanych-ukraina")

ROOT_PY = [
    "kanbud_bootstrap.py",
    "campaign_data_paths.py",
    "claude_client.py",
    "claude_contact_extract.py",
    "claude_page_text.py",
    "claude_row_cleanup.py",
    "commercial_contact_filter.py",
    "contact_extract_utils.py",
    "de_contractor_exclusions.py",
    "discovery_run_state.py",
    "email_targeting.py",
    "http_page_guard.py",
    "playwright_cookie_consent.py",
    "scraper_run_config.py",
    "scraper_runtime_limit.py",
    "scraper_schedule_config.py",
    "scraper_web_config.py",
    "website_full_crawl.py",
]

UA_PY = sorted(p.name for p in SRC.glob("ua_*.py"))

SCRIPT_EXCLUDE = {
    "build_pl_from_ua.py",
    "build_pl_schedule.py",
    "build_ua_scraper.py",
    "export_mfg_slides_attachment.py",
    "save_excel_seven_from_pi.py",
    "export_week_discovery_all_to_excel.py",
    "sync_week_single_excel_gdrive.py",
    "recover_pi_cache_contacts.py",
    "analyze_mail_jobs.py",
    "apply_prior_send_state.py",
    "run_full_pipeline_gha.ps1",
    "watch_discovery_then_pipeline.ps1",
    "watch_backfill_then_pipeline.ps1",
    "clear_pipeline_cache.ps1",
    "resume_pipeline_after_pi.ps1",
}

TEST_FILES = [
    "tests/__init__.py",
    "tests/conftest.py",
    "tests/test_ua_supplier_filter.py",
    "tests/test_ua_inquiry_email_uk.py",
    "tests/test_ua_claude_inquiry_email.py",
    "tests/test_ua_materialy_regression.py",
    "tests/test_ua_materialy_integration.py",
    "tests/test_ua_oblast_keywords.py",
    "tests/test_discovery_run_state.py",
    "tests/test_scraper_runtime_limit.py",
    "tests/test_website_full_crawl.py",
    "tests/test_claude_client_retry.py",
    "tests/test_claude_model_tiers.py",
    "tests/test_gdrive_upload.py",
]

WORKFLOWS = [
    "ua_materialy_pi.yml",
    "ua_materialy_thu.yml",
    "ua_materialy_mon.yml",
    "ua_materialy_tue.yml",
    "ua_materialy_fri.yml",
    "sync-google-drive-ua.yml",
    "tests.yml",
    "ci-deploy.yml",
]


def copy_file(rel: str) -> None:
    src = SRC / rel
    dst = DST / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> None:
    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir()

    for name in ROOT_PY + UA_PY:
        copy_file(name)

    shutil.copytree(SRC / "libs", DST / "libs")
    DST.joinpath("libs", "secrets").mkdir(exist_ok=True)
    (DST / "libs" / "secrets" / ".gitkeep").touch()

    for cfg in (SRC / "run_config").glob("ua_*.json"):
        copy_file(f"run_config/{cfg.name}")

    for script in (SRC / "scripts").iterdir():
        if script.name in SCRIPT_EXCLUDE:
            continue
        copy_file(f"scripts/{script.name}")

  # schedule/ua -> schedule/
    for item in (SRC / "schedule" / "ua").iterdir():
        rel_src = f"schedule/ua/{item.name}"
        dst = DST / "schedule" / item.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SRC / rel_src, dst)

    for wf in WORKFLOWS:
        copy_file(f".github/workflows/{wf}")

    shutil.copytree(SRC / ".github/actions", DST / ".github/actions")

    for rel in TEST_FILES:
        copy_file(rel)

    for doc in (SRC / "docs").iterdir():
        copy_file(f"docs/{doc.name}")

    for name in (".gitignore", "requirements.txt", "requirements-drive.txt", ".env.example"):
        copy_file(name)

    patch_schedule_common()
    patch_shared_modules()
    patch_tests_yml()
    patch_ci_deploy()
    patch_run_all_tests()
    patch_docs()
    write_readme()

    print(f"Built {DST}")


def patch_schedule_common() -> None:
    path = DST / "schedule" / "_common.ps1"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "$script:RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent",
        "$script:RepoRoot = Split-Path $PSScriptRoot -Parent",
    )
    path.write_text(text, encoding="utf-8")


def patch_tests_yml() -> None:
    path = DST / ".github/workflows/tests.yml"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        """      - name: Compile core modules
        run: |
          python -m py_compile kanbud_bootstrap.py
          python -m py_compile campaign_data_paths.py
          python -m py_compile ua_materialy_scraper.py
          python -m py_compile ua_oblast_keywords.py
          python -m py_compile ua_materialy_inquiry_email_uk.py
          python -m py_compile pl_materialy_scraper.py
          python -m py_compile pl_wojewodztwo_keywords.py
          python -m py_compile pl_materialy_inquiry_email_pl.py""",
        """      - name: Compile core modules
        run: |
          python -m py_compile kanbud_bootstrap.py
          python -m py_compile campaign_data_paths.py
          python -m py_compile ua_materialy_scraper.py
          python -m py_compile ua_oblast_keywords.py
          python -m py_compile ua_materialy_inquiry_email_uk.py""",
    )
    pl_block = """

      - name: Scraper smoke PL materialy (--test)
        run: python pl_materialy_scraper.py --test

      - name: Regresja i testy UA (pytest + unittest)"""
    text = text.replace(pl_block, """

      - name: Regresja i testy UA (pytest + unittest)""")
    pl_regress = """

      - name: Regresja i testy PL (pytest + unittest)
        run: |
          python -m unittest tests.test_pl_materialy_regression -v
          python -m pytest \\
            tests/test_pl_inquiry_email_pl.py \\
            tests/test_pl_materialy_integration.py \\
            -q"""
    text = text.replace(pl_regress, "")
    path.write_text(text, encoding="utf-8")


def patch_ci_deploy() -> None:
    path = DST / ".github/workflows/ci-deploy.yml"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "python de_gu_bauunternehmen_scraper.py --test",
        "python ua_materialy_scraper.py --test",
    )
    text = text.replace(
        "python de_gu_bauunternehmen_scraper.py --dry-run-email --send-emails-only",
        "python ua_materialy_scraper.py --dry-run-email --send-emails-only",
    )
    path.write_text(text, encoding="utf-8")


def patch_run_all_tests() -> None:
    content = '''#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root
$env:KANBUD_PROJECT_ROOT = Join-Path $Root "libs"
$env:PYTHONUTF8 = "1"

$failed = @()
$passed = @()

function Test-Step {
    param([string]$Name, [scriptblock]$Block)
    Write-Host "`n>> $Name" -ForegroundColor Cyan
    try {
        & $Block
        if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "exit $LASTEXITCODE" }
        $script:passed += $Name
        Write-Host "OK: $Name" -ForegroundColor Green
    } catch {
        $script:failed += "${Name}: $_"
        Write-Host "FAIL: $Name - $_" -ForegroundColor Red
    }
}

Test-Step "py_compile (wszystkie .py)" {
    Get-ChildItem -Recurse -Filter *.py |
        Where-Object { $_.FullName -notmatch '\\\\.venv\\\\' } |
        ForEach-Object {
            python -m py_compile $_.FullName
            if ($LASTEXITCODE -ne 0) { throw $_.FullName }
        }
}

Test-Step "smoke --test (UA materialy)" { python ua_materialy_scraper.py --test }

Test-Step "regresja UA materialy" {
    python -m unittest tests.test_ua_materialy_regression -v
}

Test-Step "pytest UA (jednostkowe + integracyjne)" {
    python -m pytest tests/test_ua_oblast_keywords.py tests/test_ua_inquiry_email_uk.py tests/test_ua_claude_inquiry_email.py tests/test_ua_supplier_filter.py tests/test_ua_materialy_integration.py -q
}

Test-Step "ua_oblast_rotation" {
    python -c @"
from pathlib import Path
import tempfile
from ua_oblast_rotation import (
    load_rotation_state, peek_next_oblast, commit_rotation_after_run,
    rotation_state_path, OBLAST_ROTATION_ORDER,
)
d = Path(tempfile.mkdtemp())
p = rotation_state_path(d)
s = load_rotation_state(p)
oblast = peek_next_oblast(s)
assert oblast in OBLAST_ROTATION_ORDER
commit_rotation_after_run(p, s, oblast)
"@
}

Test-Step "ua_materialy — brak zalacznikow i MFG" {
    python -c @"
from ua_materialy_inquiry_email_uk import DEFAULT_INQUIRY_PHONE_UK, build_fixed_material_inquiry_uk
import ua_materialy_scraper as ua
assert ua.get_email_attachments_ua_materialy() == []
assert ua.UA_EMAIL_ALLOW_ATTACHMENTS is False
assert DEFAULT_INQUIRY_PHONE_UK == '+380977091141'
body = build_fixed_material_inquiry_uk()
assert 'mfg' not in body.lower()
assert '+380977091141' in body
"@
}

Test-Step "run_config JSON (UA)" {
    python -c @"
from pathlib import Path
from scraper_run_config import load_run_config_file
for cfg in ['run_config/ua_materialy.json','run_config/ua_kyiv_test.json']:
    d = load_run_config_file(cfg, Path('.'))
    assert d['config_type'] == 'ua_materialy'
"@
}

Test-Step "dry-run wysylki UA" {
    python ua_materialy_scraper.py --dry-run-email --send-emails-only | Out-Null
}

Test-Step "gdrive_upload_wyniki --help" {
    python scripts/gdrive_upload_wyniki.py --help | Out-Null
}

Write-Host "`n======== PODSUMOWANIE ========" -ForegroundColor Yellow
Write-Host "Passed: $($passed.Count)"
$passed | ForEach-Object { Write-Host "  + $_" }
if ($failed.Count) {
    Write-Host "Failed: $($failed.Count)" -ForegroundColor Red
    $failed | ForEach-Object { Write-Host "  - $_" }
    exit 1
}
Write-Host "Wszystkie testy OK" -ForegroundColor Green
'''
    (DST / "scripts" / "RUN_ALL_TESTS.ps1").write_text(content, encoding="utf-8")


def _copy_ua_as(dst_name: str, src_name: str, *, replacements: list[tuple[str, str]] | None = None) -> None:
    text = (SRC / src_name).read_text(encoding="utf-8")
    for old, new in replacements or []:
        text = text.replace(old, new)
    (DST / dst_name).write_text(text, encoding="utf-8")


def patch_shared_modules() -> None:
    _copy_ua_as(
        "campaign_keyword_profile.py",
        "ua_campaign_keyword_profile.py",
        replacements=[("from ua_oblast_keywords", "from ua_oblast_keywords"),
                      ("from ua_materialy_supplier_filter", "from ua_materialy_supplier_filter")],
    )
    _copy_ua_as(
        "claude_prompts.py",
        "ua_claude_prompts.py",
        replacements=[("from ua_campaign_keyword_profile", "from campaign_keyword_profile")],
    )
    _append_claude_prompts_helpers()
    _copy_ua_as(
        "page_verify.py",
        "ua_page_verify.py",
        replacements=[
            ("from ua_campaign_keyword_profile", "from campaign_keyword_profile"),
            ("from ua_claude_prompts", "from claude_prompts"),
        ],
    )
    _copy_ua_as(
        "claude_page_verify.py",
        "ua_claude_page_verify.py",
        replacements=[
            ("from ua_page_verify", "from page_verify"),
            ("from ua_materialy_supplier_filter", "from ua_materialy_supplier_filter"),
        ],
    )
    shutil.copy2(SRC / "ua_materialy_supplier_filter.py", DST / "retail_store_builder_filter.py")
    write_claude_discovery_terms_ua()


def _append_claude_prompts_helpers() -> None:
    extra = '''

def build_contact_extract_prompt(
    company_name: str,
    website: str,
    page_text: str,
) -> str:
    from claude_page_text import build_claude_context_header, extract_crawl_section_urls

    raw = page_text or ""
    header = build_claude_context_header(
        company_name,
        website,
        pages_crawled=max(raw.count("=== http"), 1 if raw else 0),
        priority_urls=extract_crawl_section_urls(raw),
    )
    snippet = prioritize_page_text_for_verify(
        raw,
        max_chars=CONTACT_EXTRACT_MAX_CHARS,
        priority_keywords=_CONTACT_EXTRACT_TEXT_PRIORITY,
    )
    return f"""ROLLE
Du bist Kontakt-Rechercheur für B2B-Outreach an Baustoffhändler in der Ukraine.
Deine einzige Aufgabe: E-Mail-Adressen und Telefonnummern aus dem Website-Auszug finden.

KONTEXT
{header}

REGELN (streng)
• Nur Daten extrahieren, die WÖRTLICH im Auszug stehen — nichts erfinden, nichts raten.
• Impressum- und Kontaktseiten haben höchste Priorität.
• mailto:-Links und sichtbare @-Adressen zählen.
• Telefon: ukrainische Nummern (+380 oder 0…), keine Fax-Zeilen wenn eine normale Tel.-Zeile existiert.
• Keine Portale, keine noreply/no-reply, keine PDF-Viewer-Adressen.
• Wenn nichts gefunden: leere Listen.

OUTPUT (nur JSON, kein Markdown)
{{"company_name":"","emails":[],"phones":[],"impressum_emails":[],"reason":""}}

WEBSITE-AUSZUG (vollständiger Domain-Crawl)
{snippet or "(leer)"}
"""


def build_discovery_terms_prompt(
    lands: list[str],
    *,
    city_str: str,
    land_str: str,
    terms_requested: int,
    exclude_block: str = "",
    max_term_len: int = 55,
) -> str:
    templates = "\\n".join(f"- {t}" for t in SERPER_TEMPLATE_PATTERNS[:10])
    gu_kw = ", ".join(gu_required_keywords_sample(max_items=6))
    retail_kw = ", ".join(retail_context_keywords_sample(max_items=8))
    neg_kw = ", ".join(negative_keywords_sample(max_items=8))
    return f"""ROLLE
Du generierst Google-Suchanfragen (Serper API) für die Discovery von Baustoffhändlern in der Ukraine.
Jede Zeile = eine Suchanfrage. Qualität vor Quantität.

KONTEXT
Oblast: {land_str}
Städte: {city_str}

VORLAGEN
{templates}

PFLICHT pro Zeile
• Mindestens ein Lieferanten-Marker: {gu_kw}
• Mindestens eine Materialkategorie WÖRTLICH: {_REQUIRED_MATERIALS}
• Retail/Baustoff-Kontext erwünscht: {retail_kw}
• Max {max_term_len} Zeichen
• Ukrainisch oder Russisch, keine Nummerierung, keine Anführungszeichen

VERBOTEN
• {neg_kw}
• Doppelte oder fast identische Zeilen
{exclude_block}

Antworte mit genau {terms_requested} Zeilen — nur die Suchanfragen, nichts anderes.
"""
'''
    path = DST / "claude_prompts.py"
    path.write_text(path.read_text(encoding="utf-8") + extra, encoding="utf-8")


def write_claude_discovery_terms_ua() -> None:
    content = '''# -*- coding: utf-8 -*-
"""Claude Haiku: generowanie fraz Serper (UA materiały budowlane)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from claude_prompts import build_discovery_terms_prompt as _build_discovery_terms_prompt
from claude_client import claude_generate_text
from ua_oblast_keywords import OBLAST_CONFIG, RETAIL_CHAINS_ROTATION, SERPER_NEGATIVE_TERMS
from ua_materialy_supplier_filter import STRICT_GU_MARKERS, is_generalunternehmer
from scraper_env import get_anthropic_api_key

DISCOVERY_MAX_TERM_LEN = 55
DISCOVERY_MIN_TERM_LEN = 12
_PARSE_LINE_RE = re.compile(r"^\\s*(?:\\d+[\\.\\)]\\s*)?(.+?)\\s*$")


def parse_discovery_term_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("{") or line.startswith("["):
            continue
        m = _PARSE_LINE_RE.match(line)
        candidate = (m.group(1) if m else line).strip().strip(\'"\').strip("\'")
        if candidate and candidate not in lines:
            lines.append(candidate)
    return lines


def validate_discovery_term(term: str) -> bool:
    t = (term or "").strip()
    if len(t) < DISCOVERY_MIN_TERM_LEN or len(t) > DISCOVERY_MAX_TERM_LEN:
        return False
    low = t.lower()
    if not is_generalunternehmer(low)[0]:
        return False
    if not any(m.strip() in low for m in STRICT_GU_MARKERS if m.strip()):
        return False
    if any(neg in low for neg in SERPER_NEGATIVE_TERMS if len(neg) >= 4):
        return False
    materials_low = [c.lower() for c in RETAIL_CHAINS_ROTATION]
    if not any(mat in low for mat in materials_low):
        return False
    return True


def _cities_for_lands(lands: list[str], *, max_cities: int = 8) -> list[str]:
    cities: list[str] = []
    for land in lands:
        cfg = OBLAST_CONFIG.get(land) or {}
        for city in cfg.get("cities") or ():
            if city not in cities:
                cities.append(city)
            if len(cities) >= max_cities:
                return cities
    return cities


def build_discovery_terms_prompt(
    lands: list[str],
    *,
    cities: list[str] | None = None,
    terms_requested: int = 10,
    exclude_terms: list[str] | None = None,
) -> str:
    city_list = cities or _cities_for_lands(lands)
    land_str = ", ".join(lands) if lands else "Україна"
    city_str = ", ".join(city_list[:8]) if city_list else "—"
    exclude_block = ""
    if exclude_terms:
        exclude_block = (
            "\\nBereits verwendet (nicht wiederholen):\\n"
            + "\\n".join(f"- {t}" for t in exclude_terms[:20])
        )
    return _build_discovery_terms_prompt(
        lands,
        city_str=city_str,
        land_str=land_str,
        terms_requested=terms_requested,
        exclude_block=exclude_block,
        max_term_len=DISCOVERY_MAX_TERM_LEN,
    )


def _cache_bucket(cache: dict) -> dict:
    return cache.setdefault("claude_discovery_terms", {})


def get_cached_discovery_terms(
    cache: dict,
    land: str,
    *,
    cache_days: int,
) -> list[str] | None:
    bucket = _cache_bucket(cache)
    entry = bucket.get((land or "").strip())
    if entry is None:
        legacy = (cache.get("gemini_discovery_terms") or {}).get((land or "").strip())
        if isinstance(legacy, dict):
            entry = legacy
    if not isinstance(entry, dict):
        return None
    at_raw = entry.get("at") or ""
    try:
        at = datetime.fromisoformat(at_raw)
    except (TypeError, ValueError):
        return None
    if datetime.now() - at > timedelta(days=cache_days):
        return None
    terms = entry.get("terms")
    if isinstance(terms, list) and terms:
        return [str(t) for t in terms if str(t).strip()]
    return None


def store_cached_discovery_terms(cache: dict, land: str, terms: list[str]) -> None:
    land_key = (land or "").strip() or "Україна"
    _cache_bucket(cache)[land_key] = {
        "at": datetime.now().isoformat(),
        "terms": list(terms),
    }


def generate_claude_discovery_terms(
    cache: dict,
    logger,
    lands: list[str],
    *,
    terms_requested: int = 10,
    cache_days: int = 7,
    use_cache: bool = True,
    exclude_terms: list[str] | None = None,
) -> list[str]:
    land_key = (lands[0] if lands else "").strip() or "Україна"
    if use_cache:
        cached = get_cached_discovery_terms(cache, land_key, cache_days=cache_days)
        if cached:
            logger.info("Claude discovery: cache %s (%s fraz)", land_key, len(cached))
            return cached[:terms_requested]

    api_key = get_anthropic_api_key()
    if not api_key:
        logger.warning("Claude discovery: brak ANTHROPIC_API_KEY")
        return []

    prompt = build_discovery_terms_prompt(
        lands,
        terms_requested=terms_requested,
        exclude_terms=exclude_terms,
    )
    try:
        logger.info("Claude discovery: generowanie %s fraz", terms_requested)
        text, model = claude_generate_text(prompt, logger, api_key, cache=cache, model_tier="fast")
        logger.info("Claude discovery terms, model=%s", model)
    except Exception as exc:
        logger.warning("Claude discovery terms: %s", exc)
        return []

    validated: list[str] = []
    for line in parse_discovery_term_lines(text):
        if validate_discovery_term(line) and line not in validated:
            validated.append(line)
        if len(validated) >= terms_requested:
            break

    if validated and use_cache:
        store_cached_discovery_terms(cache, land_key, validated)
    return validated
'''
    (DST / "claude_discovery_terms.py").write_text(content, encoding="utf-8")


def patch_docs() -> None:
    gha = DST / "docs" / "GITHUB_ACTIONS.md"
    text = gha.read_text(encoding="utf-8")
    text = text.replace(
        "Repozytorium: [Wyszukiwarka-partnerow](https://github.com/Bigmax1993/Wyszukiwarka-partnerow)",
        "Repozytorium: [wyszukiwarka-materialow-budowlanych-ukraina](https://github.com/Bigmax1993/wyszukiwarka-materialow-budowlanych-ukraina)",
    )
    gha.write_text(text, encoding="utf-8")

    gdrive = DST / "docs" / "GOOGLE_DRIVE.md"
    gtext = gdrive.read_text(encoding="utf-8")
    gtext = gtext.replace("de_gu_bauunternehmen", "ua_materialy")
    gtext = gtext.replace("GU Bauunternehmen", "UA Materialy Budowlane")
    gdrive.write_text(gtext, encoding="utf-8")

    env = DST / ".env.example"
    etext = env.read_text(encoding="utf-8")
    etext = etext.replace(
        "# Wyniki GU (JSON, Excel, log, wyslane/)",
        "# Wyniki UA (JSON, Excel, log, wyslane/)",
    )
    etext = etext.replace("de_gu_bauunternehmen", "ua_materialy")
    env.write_text(etext, encoding="utf-8")

    email_tpl = DST / "libs" / "email_custom_template.py"
    etpl = email_tpl.read_text(encoding="utf-8")
    etpl = etpl.replace(
        """from claude_prompts import (
    build_custom_email_prompt_de,
    build_custom_email_prompt_pl,
)
try:
    from ua_claude_prompts import build_custom_email_prompt_uk
except ImportError:
    build_custom_email_prompt_uk = None  # type: ignore[misc, assignment]""",
        "from claude_prompts import build_custom_email_prompt_uk",
    )
    etpl = etpl.replace(
        """    if lang == "de":
        return build_custom_email_prompt_de(
            draft,
            company_name,
            city_name=city_name,
            delivery_address=delivery_address,
        )
    if lang == "uk" and build_custom_email_prompt_uk is not None:
        return build_custom_email_prompt_uk(
            draft,
            company_name,
            city_name=city_name,
            delivery_address=delivery_address,
        )
    return build_custom_email_prompt_pl(
        draft,
        company_name,
        city_name=city_name,
        delivery_address=delivery_address,
    )""",
        """    if lang not in ("uk", "ua"):
        lang = "uk"
    return build_custom_email_prompt_uk(
        draft,
        company_name,
        city_name=city_name,
        delivery_address=delivery_address,
    )""",
    )
    email_tpl.write_text(etpl, encoding="utf-8")


def write_readme() -> None:
    readme = """# Wyszukiwarka materiałów budowlanych — Ukraina

Repozytorium: [Bigmax1993/wyszukiwarka-materialow-budowlanych-ukraina](https://github.com/Bigmax1993/wyszukiwarka-materialow-budowlanych-ukraina)

Pipeline: **Serper (gl=ua) → crawl www → Claude verify → Excel → maile UA**.

| Moduł | Plik |
|-------|------|
| Scraper | `ua_materialy_scraper.py` |
| Frazy per obwód | `ua_oblast_keywords.py` |
| Rotacja obwodów | `ua_oblast_rotation.py` |
| Filtr dostawców | `ua_materialy_supplier_filter.py` |
| Treść maila UK | `ua_materialy_inquiry_email_uk.py` |

## Szybki start

```powershell
git clone https://github.com/Bigmax1993/wyszukiwarka-materialow-budowlanych-ukraina.git
cd wyszukiwarka-materialow-budowlanych-ukraina
pip install -r requirements.txt
$env:KANBUD_PROJECT_ROOT = "$PWD\\libs"

python ua_materialy_scraper.py --test
python ua_materialy_scraper.py --rotate-oblast
python ua_materialy_scraper.py --rotation-status
python ua_materialy_scraper.py --oblast Kyiv,Lvivska
python ua_materialy_scraper.py --run-config run_config\\ua_kyiv_test.json
python ua_materialy_scraper.py --dry-run-email --send-emails-only
```

Skopiuj `.env.example` → `.env` (lokalnie) lub ustaw sekrety w GitHub Actions.

## Testy

```powershell
python ua_materialy_scraper.py --test
python -m unittest tests.test_ua_materialy_regression -v
python -m pytest tests/test_ua_oblast_keywords.py tests/test_ua_inquiry_email_uk.py tests/test_ua_claude_inquiry_email.py tests/test_ua_supplier_filter.py tests/test_ua_materialy_integration.py -q
```

Pełna bateria: `powershell -ExecutionPolicy Bypass -File scripts\\RUN_ALL_TESTS.ps1`

## Wyniki

| Plik / folder | Opis |
|---------------|------|
| `Wyniki/ua_materialy_cache.json` | Cache Serper + kontakty |
| `Wyniki/ua_materialy_kontakte.xlsx` | Excel (append) |
| `Wyniki/ua_materialy_oblast_rotation.json` | Stan rotacji obwodów |
| `wyslane/` | Kopie wysłanych maili (.eml) |

## Harmonogram

Szczegóły: [`schedule/PLAN_5_DNI_UA.md`](schedule/PLAN_5_DNI_UA.md)

| Dzień | Godzina (PL) | PC | GitHub Actions |
|-------|--------------|-----|----------------|
| **Pon–Pt** | 17:00 / 15:00 / 19:00 / 20:00 / 16:00 | `schedule/run_*_discovery.ps1` | `UA discovery` |
| **Niedziela** | 06:00 | `schedule/run_niedziela_backfill.ps1` | `UA niedziela backfill` |
| **Poniedziałek** | 06:00 / 07:00 / 09:00 | prep + send | `Sync wyniki Google Drive UA` → prep → send |
| **Wtorek** | 09:00 | `schedule/run_wtorek_send.ps1` | `UA wtorek send` |

Task Scheduler:

```powershell
powershell -ExecutionPolicy Bypass -File schedule\\register_tasks_5_dni.ps1
```

## GitHub Actions

Dokumentacja: [`docs/GITHUB_ACTIONS.md`](docs/GITHUB_ACTIONS.md), [`docs/GOOGLE_DRIVE.md`](docs/GOOGLE_DRIVE.md)

| Secret | Wymagany | Opis |
|--------|----------|------|
| `SERPER_API_KEY` | tak (discovery) | API Serper |
| `ANTHROPIC_API_KEY` | tak | Claude API |
| `MAIL_USER`, `MAIL_PASSWORD` | tak (pon+wt) | Gmail / SMTP |
| `GDRIVE_FOLDER_ID_UA` | zalecany | Upload wyników na Drive |

## Maile UA

- Treść: `ua_materialy_inquiry_email_uk.py` + **Claude Sonnet** (unikalny list ukraiński per firma)
- Wymaga `ANTHROPIC_API_KEY`; wyłączenie: `ENABLE_CLAUDE_INQUIRY_EMAIL=0`
- **Bez załączników** — tylko plain-text
- Nadawca: `MAIL_SENDER_NAME` (domyślnie Свінчак Максим), telefon `+380977091141`
"""
    (DST / "README.md").write_text(readme, encoding="utf-8")


if __name__ == "__main__":
    main()
