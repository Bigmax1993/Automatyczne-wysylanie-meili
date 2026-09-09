# -*- coding: utf-8 -*-
import unittest

from discovery_run_state import record_discovery_run_state


class DiscoveryRunStateTest(unittest.TestCase):
    def test_record_state(self):
        cache: dict = {"serper_daily": {"2026-06-06": 500}}
        record_discovery_run_state(
            cache,
            all_rows=[],
            total_new_rows=50,
            serper_only=True,
            rotate_mode=False,
            campaign_today="2026-06-06",
            serper_daily_limit=3000,
            serper_discovery_reserve=1000,
            is_serper_unlimited=False,
            is_serper_limit_reached_today_fn=lambda c: False,
            is_serper_api_exhausted_fn=lambda c: False,
            discovery_target_reached_fn=lambda *a, **k: False,
        )
        self.assertEqual(cache["discovery_run_state"]["serper_used"], 500)
        self.assertFalse(cache["discovery_run_state"]["serper_exhausted"])


if __name__ == "__main__":
    unittest.main()
