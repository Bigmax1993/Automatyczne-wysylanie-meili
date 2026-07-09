# -*- coding: utf-8 -*-
"""
Testy regresyjne kampanii UA — discovery, filtry, maile, rotacja obwodów.

  python -m unittest tests.test_ua_materialy_regression -v
  python -m pytest tests/test_ua_materialy_regression.py -v
"""
from __future__ import annotations

import logging
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ua_materialy_scraper as scraper
from ua_materialy_inquiry_email_uk import (
    DEFAULT_INQUIRY_PHONE_UK,
    DEFAULT_INQUIRY_SENDER_NAME_UK,
    build_fixed_material_inquiry_uk,
    build_inquiry_signature_uk,
)
from ua_oblast_keywords import (
    ALL_OBLASTS,
    MATERIAL_CATEGORIES_ROTATION,
    SERPER_DISCOVERY_BROAD_TERMS,
    SERPER_DISCOVERY_FALLBACK_TERMS,
    SERPER_DISCOVERY_LANDKREIS_TERMS,
    SERPER_DISCOVERY_PLACES_TERMS,
    SERPER_DISCOVERY_TERMS,
    build_discovery_terms,
    build_region_suffix,
    default_max_discovery_terms_for,
)
from ua_materialy_supplier_filter import (
    is_loose_serper_discovery_candidate,
    is_serper_only_pending_candidate,
    is_valid_retail_store_builder_contact,
    qualifies_as_gu_for_campaign,
)
from ua_oblast_rotation import (
    OBLAST_ROTATION_ORDER,
    commit_rotation_after_run,
    get_rotation_start_date,
    load_rotation_state,
    peek_next_oblast,
    rotation_is_active,
    rotation_state_path,
)

_LOGGER = logging.getLogger("test_ua_materialy_regression")


class OblastCoverageRegression(unittest.TestCase):
    def test_all_oblasts_configured(self):
        self.assertEqual(len(ALL_OBLASTS), 25)
        self.assertEqual(len(scraper.CAMPAIGN_ACTIVE_BUNDESLAENDER), 25)

    def test_countrywide_region_suffix(self):
        self.assertEqual(build_region_suffix(list(ALL_OBLASTS)), "Україна")
        self.assertEqual(build_region_suffix(["Kyiv", "Lvivska"]), "Україна KY LV")

    def test_discovery_terms_scale(self):
        self.assertGreaterEqual(len(SERPER_DISCOVERY_TERMS), 100)
        self.assertGreaterEqual(default_max_discovery_terms_for(list(ALL_OBLASTS)), 2000)

    def test_discovery_waves_exported(self):
        self.assertGreaterEqual(len(SERPER_DISCOVERY_FALLBACK_TERMS), 5)
        self.assertGreaterEqual(len(SERPER_DISCOVERY_BROAD_TERMS), 10)
        self.assertGreaterEqual(len(SERPER_DISCOVERY_LANDKREIS_TERMS), 5)
        self.assertGreaterEqual(len(SERPER_DISCOVERY_PLACES_TERMS), 5)

    def test_material_rotation_in_terms(self):
        terms = build_discovery_terms(["Kyiv"], max_terms=21)
        mats = [m.lower() for m in MATERIAL_CATEGORIES_ROTATION]
        for term in terms:
            self.assertTrue(
                any(m in term.lower() for m in mats),
                msg=f"brak kategorii materiału w: {term}",
            )


class SerperConfigRegression(unittest.TestCase):
    def test_serper_ua_locale(self):
        self.assertEqual(scraper.SERPER_COUNTRY, "ua")
        self.assertEqual(scraper.SERPER_LANGUAGE, "uk")
        self.assertEqual(scraper.COUNTRY_RESTRICTION, "UA")

    def test_serper_only_target_uses_new_rows(self):
        rows = [{"url": f"https://budmat.ua/{i}"} for i in range(200)]
        self.assertFalse(
            scraper._discovery_target_reached(
                rows, total_new_rows=10, rotate_mode=False, serper_only=True
            )
        )
        self.assertTrue(
            scraper._discovery_target_reached(
                rows,
                total_new_rows=scraper.MIN_CONTACTS_TARGET,
                rotate_mode=False,
                serper_only=True,
            )
        )

    def test_reset_clears_serper_discovery_cache(self):
        cache = scraper._empty_cache()
        today = scraper.campaign_today()
        cache["serper_daily"][today] = 300
        cache["serper_limit_reached"][today] = True
        cache["serper"] = {"q1": {"rows": []}}
        cache["serper_discovery"] = {"q2": {"empty": True, "rows": []}}
        scraper.reset_serper_daily_for_discovery(cache)
        self.assertEqual(cache["serper_daily"][today], 0)
        self.assertEqual(cache["serper"], {})
        self.assertEqual(cache["serper_discovery"], {})

    def test_empty_serper_cache_ttl(self):
        cache = scraper._empty_cache()
        key = scraper._serper_discovery_cache_key("будматеріали Київ", use_places_endpoint=False)
        cache.setdefault("serper_discovery", {})[key] = {
            "empty": True,
            "at": datetime.now().isoformat(),
            "rows": [],
        }
        self.assertEqual(
            scraper.get_cached_serper_discovery_rows(
                cache, "будматеріали Київ", use_places_endpoint=False
            ),
            [],
        )
        stale = datetime.now() - timedelta(days=scraper.SERPER_DISCOVERY_EMPTY_CACHE_DAYS + 1)
        cache["serper_discovery"][key]["at"] = stale.isoformat()
        self.assertIsNone(
            scraper.get_cached_serper_discovery_rows(
                cache, "будматеріали Київ", use_places_endpoint=False
            )
        )


class SupplierFilterRegression(unittest.TestCase):
    def test_accepts_building_materials_supplier(self):
        ok, marker = qualifies_as_gu_for_campaign(
            "ТОВ Будматеріали Київ — оптовий склад цементу та піску"
        )
        self.assertTrue(ok)
        self.assertTrue(marker)

    def test_rejects_architecture_bureau(self):
        ok, reason = qualifies_as_gu_for_campaign(
            "Архітектурне бюро — проєктування будинків"
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "excluded_role")

    def test_loose_serper_accepts_budmarket(self):
        self.assertTrue(
            is_loose_serper_discovery_candidate(
                name="Будмаркет Львів",
                url="https://budmarket.lviv.ua",
                text="Оптовий склад будматеріалів, цемент, пісок",
            )
        )

    def test_rejects_news_portal(self):
        self.assertFalse(
            is_loose_serper_discovery_candidate(
                url="https://news.ua/budivelni-materialy",
                name="Новинний портал",
                text="Новини ринку будматеріалів",
            )
        )

    def test_valid_contact_requires_supplier_context(self):
        self.assertTrue(
            is_valid_retail_store_builder_contact(
                name="Склад будматеріалів ТОВ",
                url="https://sklad-bud.ua",
                text="Постачальник цементу оптом",
                email="info@sklad-bud.ua",
            )
        )
        self.assertFalse(
            is_valid_retail_store_builder_contact(
                name="Ремонт квартир",
                url="https://remont.ua",
                text="Ремонт під ключ без продажу матеріалів",
                email="info@remont.ua",
            )
        )

    def test_serper_only_pending_matches_loose(self):
        kwargs = dict(
            name="Будбаза Одеса",
            url="https://budbaza.odesa.ua",
            text="Будівельна база, опт, склад",
        )
        self.assertTrue(is_serper_only_pending_candidate(**kwargs))
        self.assertTrue(is_loose_serper_discovery_candidate(**kwargs))


class EmailBrandingRegression(unittest.TestCase):
    def test_no_mfg_in_fixed_template(self):
        body = build_fixed_material_inquiry_uk()
        low = body.lower()
        self.assertNotIn("mfg", low)
        self.assertNotIn("fliesen", low)
        self.assertNotIn("moderner", low)

    def test_default_sender_and_phone(self):
        self.assertEqual(DEFAULT_INQUIRY_SENDER_NAME_UK, "Свінчак Максим")
        self.assertEqual(DEFAULT_INQUIRY_PHONE_UK, "+380977091141")

    def test_signature_has_ua_phone(self):
        sig = build_inquiry_signature_uk()
        self.assertIn("+380977091141", sig)
        self.assertIn("Свінчак Максим", sig)
        self.assertNotIn("+49", sig)

    def test_subject_without_mfg(self):
        self.assertNotIn("MFG", scraper.FIXED_EMAIL_SUBJECT_UK)
        self.assertIn("будівельних матеріалів", scraper.FIXED_EMAIL_SUBJECT_UK)

    def test_no_email_attachments(self):
        self.assertFalse(scraper.ENABLE_EMAIL_ATTACHMENT)
        self.assertFalse(scraper.UA_EMAIL_ALLOW_ATTACHMENTS)
        self.assertEqual(scraper.get_email_attachments_ua_materialy(), [])

    @patch("mail_transport.send_smtp_email")
    @patch("scraper_env.get_mail_password", return_value="secret")
    @patch("scraper_env.get_mail_user", return_value="test@gmail.com")
    def test_send_email_passes_empty_attachments(self, mock_user, mock_pwd, mock_send):
        mock_send.return_value = (True, "gesendet")
        ok, _ = scraper.send_email_ua_materialy(
            "test@budmat.ua", "Тема", "Тіло", _LOGGER
        )
        self.assertTrue(ok)
        kwargs = mock_send.call_args.kwargs
        self.assertEqual(kwargs.get("attachment_paths"), [])

    def test_sanitize_strips_german_phone_from_body(self):
        _, body = scraper.sanitize_generated_email(
            "Запит",
            "Текст\nTel.: +49 1522 3655 399\n\nЗ повагою",
            "ТОВ Тест",
        )
        self.assertNotIn("+49", body)
        self.assertNotIn("1522", body)


class OblastRotationRegression(unittest.TestCase):
    def test_rotation_order_length(self):
        self.assertEqual(len(OBLAST_ROTATION_ORDER), 25)
        self.assertEqual(peek_next_oblast(), OBLAST_ROTATION_ORDER[0])

    def test_rotation_start_date_default(self):
        self.assertEqual(get_rotation_start_date().isoformat(), "2026-07-13")

    def test_rotation_inactive_before_start(self):
        self.assertFalse(rotation_is_active(date(2026, 7, 12)))
        self.assertTrue(rotation_is_active(date(2026, 7, 13)))

    def test_excel_obwod_column(self):
        row = {"company_name_clean": "ТОВ Тест", "bundesland": "Kyiv", "telefon": "+380"}
        cols = scraper.row_to_excel_kontakte_columns(row)
        self.assertIn("Obwód", cols)
        self.assertEqual(cols["Obwód"], "Kyiv")
        self.assertNotIn("Oblast", cols)

    def test_commit_advances_index(self):
        tmp = Path(tempfile.mkdtemp())
        path = rotation_state_path(tmp)
        state = load_rotation_state(path)
        land = peek_next_oblast(state)
        nxt = commit_rotation_after_run(path, state, land)
        self.assertIn(nxt, OBLAST_ROTATION_ORDER)
        self.assertNotEqual(nxt, land)


class CampaignPathsRegression(unittest.TestCase):
    def test_ua_output_paths_basename(self):
        from campaign_data_paths import campaign_output_paths

        paths = campaign_output_paths(ROOT, "ua_materialy")
        self.assertTrue(str(paths["cache_file"]).endswith("ua_materialy_cache.json"))
        self.assertTrue(str(paths["output_file"]).endswith("ua_materialy_kontakte.xlsx"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
