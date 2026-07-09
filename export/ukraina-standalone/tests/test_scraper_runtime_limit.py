# -*- coding: utf-8 -*-
import unittest
from unittest import mock

import scraper_runtime_limit as srl


class ScraperRuntimeLimitTest(unittest.TestCase):
    def setUp(self):
        srl.reset_scraper_runtime_clock_for_tests()

    def test_no_limit_when_disabled(self):
        with mock.patch.object(srl, "SCRAPER_MAX_RUNTIME_SECONDS", 0):
            srl.start_scraper_runtime_clock()
            self.assertFalse(srl.is_scraper_runtime_limit_reached())

    def test_limit_reached_after_elapsed(self):
        with mock.patch.object(srl, "SCRAPER_MAX_RUNTIME_SECONDS", 600):
            with mock.patch(
                "scraper_runtime_limit.time.monotonic", side_effect=[100.0, 701.0]
            ):
                srl.start_scraper_runtime_clock()
                self.assertTrue(srl.is_scraper_runtime_limit_reached())

    def test_request_stop_logs(self):
        with mock.patch.object(srl, "SCRAPER_MAX_RUNTIME_SECONDS", 1):
            with mock.patch(
                "scraper_runtime_limit.time.monotonic", side_effect=[0.0, 2.0]
            ):
                srl.start_scraper_runtime_clock()
                messages: list[str] = []
                self.assertTrue(
                    srl.request_stop_on_runtime_limit(
                        None, console_step_fn=messages.append
                    )
                )
                self.assertEqual(len(messages), 1)
                self.assertIn("Limit czasu scrapera", messages[0])


if __name__ == "__main__":
    unittest.main()
