# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json

from website_full_crawl import (
    WebsiteCrawlResult,
    crawl_entire_website,
    extract_all_internal_links,
    format_crawl_text_for_claude,
    website_crawl_result_from_dict,
    website_crawl_result_to_dict,
)


def _norm(url: str) -> str:
    u = url.strip()
    if not u.startswith("http"):
        u = "https://" + u
    return u.rstrip("/") if u.endswith("/") and u.count("/") > 2 else u


class WebsiteFullCrawlTest(unittest.TestCase):
    def test_extract_internal_links_same_domain(self):
        html = '<a href="/karriere/stelle">Jobs</a><a href="https://other.com/x">X</a>'
        links = extract_all_internal_links(
            "https://wijcobau.de/",
            html,
            site_domain="wijcobau.de",
            normalize_website=_norm,
        )
        self.assertTrue(any("karriere" in u for u in links))
        self.assertFalse(any("other.com" in u for u in links))

    def test_crawl_visits_all_internal_pages(self):
        pages = {
            "https://example.de": (
                '<a href="https://example.de/ueber-uns">About</a>'
                "<p>Generalunternehmer Einzelhandel</p>"
            ),
            "https://example.de/ueber-uns": (
                '<a href="https://example.de/karriere">Karriere</a>'
                "<p>Auftraggeber Netto</p>"
            ),
            "https://example.de/karriere": "<p>Retail Projekte</p>",
        }

        def fetch(url: str) -> str:
            key = url.rstrip("/")
            return pages.get(key, pages.get(key + "/", ""))

        def parse(url: str, html: str) -> dict:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            return {
                "emails": [],
                "phones": [],
                "company_name": "",
                "contact_urls": [],
                "page_text": soup.get_text(" ", strip=True),
            }

        result = crawl_entire_website(
            "https://example.de",
            logger=MagicMock(),
            fetch_page_html=fetch,
            parse_html_page=parse,
            normalize_website=_norm,
            max_pages=10,
        )
        self.assertEqual(len(result.urls_visited), 3)
        text = format_crawl_text_for_claude(result)
        self.assertIn("=== https://example.de/karriere", text)
        self.assertIn("Netto", text)

    def test_crawl_result_json_roundtrip(self):
        original = WebsiteCrawlResult(
            pages={"https://firma.de/impressum": {"emails": ["info@firma.de"]}},
            urls_visited=["https://firma.de/impressum"],
            urls_skipped=["https://firma.de/feed"],
            capped=True,
        )
        payload = {"website_crawl": {"https://firma.de": website_crawl_result_to_dict(original)}}
        raw = json.dumps(payload)
        loaded = json.loads(raw)
        restored = website_crawl_result_from_dict(loaded["website_crawl"]["https://firma.de"])
        self.assertEqual(restored.urls_visited, original.urls_visited)
        self.assertEqual(restored.pages, original.pages)
        self.assertTrue(restored.capped)


if __name__ == "__main__":
    unittest.main(verbosity=2)
