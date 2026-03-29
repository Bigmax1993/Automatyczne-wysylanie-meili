"""Kontekst ze strony WWW: normalizacja URL, cache, merge JSON."""

from __future__ import annotations

import json

import web_page_context as wp


def test_normalize_fetch_url_adds_https() -> None:
    assert wp.normalize_fetch_url("example.com/path") == "https://example.com/path"
    assert wp.normalize_fetch_url("https://firma.pl") == "https://firma.pl"


def test_normalize_fetch_url_rejects_localhost() -> None:
    assert wp.normalize_fetch_url("http://localhost/x") is None
    assert wp.normalize_fetch_url("(brak strony WWW)") is None


def test_html_to_clean_text_strips_scripts() -> None:
    html = """
    <html><head><script>evil()</script></head><body>
    <p>Hello firm</p>
    <style>.x{}</style>
    </body></html>
    """
    t = wp.html_to_clean_text(html)
    assert "evil" not in t.lower()
    assert "Hello firm" in t


def test_fetch_page_excerpt_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setattr(wp, "WEB_CONTEXT_ENABLED", False)
    assert wp.fetch_page_excerpt("https://example.com") is None


def test_append_page_excerpt_merges_json(monkeypatch) -> None:
    monkeypatch.setattr(wp, "WEB_CONTEXT_ENABLED", True)

    def _fake_fetch(_url: str) -> str:
        return "Opis działalności firmy z publicznej strony. " * 5

    monkeypatch.setattr(wp, "fetch_page_excerpt", _fake_fetch)
    base = json.dumps({"Firma": "X"}, ensure_ascii=False)
    out = wp.append_page_excerpt_to_context_json(base, "https://x.pl")
    obj = json.loads(out)
    assert "fragment_publicznej_strony_www" in obj
    assert "Opis działalności" in obj["fragment_publicznej_strony_www"]
    assert obj["Firma"] == "X"


def test_append_page_excerpt_invalid_json_unchanged() -> None:
    bad = "not-json"
    assert wp.append_page_excerpt_to_context_json(bad, "https://x.pl") == bad


def test_build_row_context_for_generation_delegates(monkeypatch) -> None:
    import pandas as pd

    import contact_mailer as cm

    row = pd.Series({"Firma": "A", "E-mail rekrutacyjny": "a@b.pl"})
    monkeypatch.setattr(cm, "_build_row_context", lambda _r: '{"Firma":"A"}')
    calls: list[tuple[str, str]] = []

    def fake_append(base: str, website: str) -> str:
        calls.append((base, website))
        return base + "|extra"

    monkeypatch.setattr(wp, "append_page_excerpt_to_context_json", fake_append)
    out = cm._build_row_context_for_generation(row, "https://firma.pl")
    assert calls == [('{"Firma":"A"}', "https://firma.pl")]
    assert out.endswith("|extra")
