"""Import oferty pracy z URL (job_offer_import): parsowanie URL, HTML (JSON-LD / title), zapis."""

from __future__ import annotations

import json

import pandas as pd
import pytest

import contact_mailer as cm
import job_offer_import as joi

OFFER_URL = "https://www.pracuj.pl/praca/spedytor-spedytorka-zielona-gora,oferta,1005115616"

PRACUJ_HTML = """
<html><head>
<title>Spedytor / Spedytorka, Kompas Spedycja Sp. z o. o., Zielona Góra - Oferta pracy | Pracuj.pl</title>
<meta property="og:title" content="Oferta pracy Spedytor / Spedytorka, Kompas Spedycja Sp. z o. o., Zielona Góra" />
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "JobPosting",
  "title": "Spedytor / Spedytorka",
  "description": "<p>skuteczna sprzedaż usług spedycyjnych</p><p>umowa o pracę, kontrakt B2B</p>",
  "hiringOrganization": {"@type": "Organization", "name": "Kompas Spedycja Sp. z o. o.",
                         "sameAs": "https://www.pracuj.pl/firma/kompas"},
  "jobLocation": [{"@type": "Place", "address": {"@type": "PostalAddress",
                   "addressLocality": "Zielona Góra", "addressRegion": "lubuskie"}}],
  "employmentType": ["FULL_TIME", "CONTRACTOR"]
}
</script>
</head><body>
<h1>Spedytor / Spedytorka</h1>
<ul><li>praca stacjonarna, praca zdalna, praca hybrydowa</li><li>umowa o pracę, kontrakt B2B</li></ul>
<script>window.__x = 1</script>
</body></html>
"""


def test_normalize_offer_url_strips_tracking_and_adds_scheme() -> None:
    assert joi.normalize_offer_url("www.pracuj.pl/praca/x,oferta,1?utm_source=a#top") == (
        "https://www.pracuj.pl/praca/x,oferta,1"
    )
    with pytest.raises(ValueError):
        joi.normalize_offer_url("")


def test_detect_portal() -> None:
    assert joi.detect_portal(OFFER_URL) == "pracuj.pl"
    assert joi.detect_portal("https://justjoin.it/offers/abc") == "justjoin.it"
    assert joi.detect_portal("https://firma.pl/kariera/1") == "firma.pl"


def test_parse_offer_url_pracuj_slug() -> None:
    parsed = joi.parse_offer_url(OFFER_URL)
    assert parsed["offer_id"] == "1005115616"
    assert parsed["city"] == "Zielona Góra"
    assert parsed["title"] == "Spedytor Spedytorka"


def test_parse_offer_url_single_word_city() -> None:
    parsed = joi.parse_offer_url("https://www.pracuj.pl/praca/analityk-danych-wroclaw,oferta,123456")
    assert parsed == {"offer_id": "123456", "title": "Analityk Danych", "city": "Wrocław"}


def test_parse_title_line_splits_role_company_city() -> None:
    parsed = joi.parse_title_line(
        "Oferta pracy Spedytor / Spedytorka, Kompas Spedycja Sp. z o. o., Zielona Góra"
    )
    assert parsed == {
        "title": "Spedytor / Spedytorka",
        "company": "Kompas Spedycja Sp. z o. o.",
        "city": "Zielona Góra",
    }


def test_build_offer_from_html_uses_json_ld() -> None:
    offer = joi.build_offer(OFFER_URL, html=PRACUJ_HTML)
    assert offer.company == "Kompas Spedycja Sp. z o. o."
    assert offer.city == "Zielona Góra"
    assert offer.title == "Spedytor / Spedytorka"
    assert offer.website == ""  # link do profilu na portalu nie jest stroną firmy
    assert offer.work_modes == ["stacjonarna", "hybrydowa", "zdalna"]
    assert offer.contracts == ["umowa o pracę", "kontrakt B2B"]
    row = offer.to_row()
    assert row[cm.COL_SOURCE] == "pracuj.pl"
    assert row[cm.COL_MODE] == "praca stacjonarna / hybrydowa / zdalna"
    assert OFFER_URL in row[cm.COL_NOTES]
    assert "umowa o pracę, kontrakt B2B" in row[cm.COL_NOTES]
    assert set(row) == set(joi.MAILER_COLUMNS)


def test_build_offer_without_json_ld_falls_back_to_title() -> None:
    html = (
        "<html><head><title>Analityk BI, Firma X Sp. z o.o., Poznań - Oferta pracy | Pracuj.pl"
        "</title></head><body>praca hybrydowa</body></html>"
    )
    offer = joi.build_offer("https://www.pracuj.pl/praca/analityk-bi-poznan,oferta,99999", html=html)
    assert offer.company == "Firma X Sp. z o.o."
    assert offer.city == "Poznań"
    assert offer.title == "Analityk BI"
    assert offer.work_modes == ["hybrydowa"]


def test_build_offer_blocked_page_uses_url_and_overrides(monkeypatch) -> None:
    monkeypatch.setattr(joi, "fetch_offer_html", lambda url, timeout=1.0: ("", "blocked"))
    offer = joi.build_offer(
        OFFER_URL,
        overrides={"company": "Kompas Spedycja", "email": "rekrutacja@kompas.pl", "work_mode": "zdalna"},
    )
    assert offer.fetch_status == "blocked"
    assert offer.company == "Kompas Spedycja"
    assert offer.city == "Zielona Góra"
    assert offer.email == "rekrutacja@kompas.pl"
    assert offer.work_modes == ["zdalna"]
    assert "strona: blocked" in offer.notes()


def test_build_offer_no_fetch_does_not_touch_network(monkeypatch) -> None:
    def _boom(*_a, **_k):
        raise AssertionError("nie wołaj sieci")

    monkeypatch.setattr(joi, "fetch_offer_html", _boom)
    offer = joi.build_offer(OFFER_URL, fetch=False)
    assert offer.fetch_status == "not_fetched"
    assert offer.to_row()[cm.COL_COMPANY] == "(brak nazwy)"


def test_looks_blocked() -> None:
    assert joi.looks_blocked(403, "")
    assert joi.looks_blocked(200, "<title>Just a moment...</title>")
    assert not joi.looks_blocked(200, "<html>ok</html>")


def test_append_offer_to_xlsx_and_dedupe(tmp_path) -> None:
    out = tmp_path / "Kontakty_oferty.xlsx"
    offer = joi.build_offer(OFFER_URL, html=PRACUJ_HTML)
    assert joi.append_offer_to_contacts(offer, str(out)) is True
    assert joi.append_offer_to_contacts(offer, str(out)) is False
    assert joi.append_offer_to_contacts(offer, str(out), allow_duplicate=True) is True

    df = pd.read_excel(out, dtype=str).fillna("")
    assert list(df.columns)[: len(joi.MAILER_COLUMNS)] == joi.MAILER_COLUMNS
    assert len(df) == 2
    assert df.iloc[0][cm.COL_COMPANY] == "Kompas Spedycja Sp. z o. o."


def test_append_offer_to_csv_preserves_existing_rows(tmp_path) -> None:
    out = tmp_path / "oferty.csv"
    pd.DataFrame(
        [{cm.COL_COMPANY: "Stara Firma", cm.COL_EMAIL: "hr@stara.pl", cm.COL_NOTES: "x"}]
    ).to_csv(out, index=False)
    offer = joi.build_offer(OFFER_URL, html=PRACUJ_HTML)
    assert joi.append_offer_to_contacts(offer, str(out)) is True
    df = pd.read_csv(out, dtype=str, keep_default_na=False)
    assert len(df) == 2
    assert df.iloc[0][cm.COL_COMPANY] == "Stara Firma"
    assert df.iloc[1][cm.COL_SOURCE] == "pracuj.pl"


def test_main_dry_run_prints_row_and_writes_nothing(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(joi, "fetch_offer_html", lambda url, timeout=1.0: (PRACUJ_HTML, "ok"))
    out = tmp_path / "x.xlsx"
    rc = joi.main([OFFER_URL, "--output", str(out), "--dry-run"])
    assert rc == 0
    out_text = capsys.readouterr().out
    printed = json.loads(out_text[out_text.index("{") : out_text.rindex("}") + 1])
    assert printed[cm.COL_COMPANY] == "Kompas Spedycja Sp. z o. o."
    assert not out.exists()


def test_main_writes_file_with_cli_overrides(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(joi, "fetch_offer_html", lambda url, timeout=1.0: ("", "http 404"))
    out = tmp_path / "oferty.xlsx"
    rc = joi.main(
        [
            OFFER_URL,
            "--output",
            str(out),
            "--company",
            "Kompas Spedycja Sp. z o. o.",
            "--website",
            "https://kompas-spedycja.pl",
            "--contract",
            "umowa o pracę",
        ]
    )
    assert rc == 0
    df = pd.read_excel(out, dtype=str).fillna("")
    assert len(df) == 1
    row = df.iloc[0]
    assert row[cm.COL_COMPANY] == "Kompas Spedycja Sp. z o. o."
    assert row[cm.COL_WEBSITE] == "https://kompas-spedycja.pl"
    assert row[cm.COL_CITY] == "Zielona Góra"
    assert "Umowa: umowa o pracę" in row[cm.COL_NOTES]


def test_main_rejects_bad_url() -> None:
    assert joi.main(["ftp://x", "--no-fetch", "--dry-run"]) == 2


def test_offer_row_is_not_treated_as_b2b_offer() -> None:
    row = joi.build_offer(OFFER_URL, html=PRACUJ_HTML).to_row()
    assert not cm._should_offer_b2b(
        industry=row[cm.COL_INDUSTRY], source=row[cm.COL_SOURCE], notes=row[cm.COL_NOTES]
    )
