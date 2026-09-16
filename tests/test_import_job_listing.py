"""Import ogłoszeń OLX / JSON-LD JobPosting do formatu kontaktów mailera."""

from __future__ import annotations

from pathlib import Path

import pytest

import build_contacts_serpapi as serp
import import_job_listing as ijl

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "olx_job_listing.html"
OLX_URL = (
    "https://www.olx.pl/oferta/praca/"
    "pracownik-biurowy-ze-znajomoscia-jez-niemieckiego-CID4-ID1c8lEt.html"
)


def test_olx_is_job_portal_domain() -> None:
    assert serp._is_job_portal_domain("https://www.olx.pl/oferta/praca/x")
    assert serp._is_job_portal_domain("olx.pl")
    assert ijl.is_olx_listing_url(OLX_URL)
    assert not ijl.is_olx_listing_url("https://med-pol.example.pl/kontakt")


def test_extract_organic_clears_olx_website() -> None:
    row = serp._extract_organic(
        {
            "title": "Med-Pol - pracownik biurowy",
            "link": "https://www.olx.pl/oferta/praca/abc",
        },
        category="Administracja",
        query="olx",
        city="Zielona Gora",
    )
    assert row["Strona WWW"] == ""
    assert row["Firma"] == "Med-Pol"


def test_parse_olx_jsonld_fixture() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    row = ijl.parse_job_listing_html(html, OLX_URL)
    assert row["Firma"] == "Med - Pol"
    assert row["Miasto"] == "Zielona Góra"
    assert row["Stanowisko / Rola"] == (
        "Pracownik biurowy ze znajomością jęz. niemieckiego"
    )
    assert row["Branża"] == "Opieka / usługi opiekuńcze"
    assert row["Tryb pracy"] == "Pełny etat"
    assert row["Źródło / Portal"] == "olx.pl"
    assert row["E-mail rekrutacyjny"] == "rekrutacja@med-pol.example.pl"
    assert "68 453 16 36" in row["Tel / Kontakt"]
    assert "1095438721" not in row["Tel / Kontakt"]
    assert row["Strona WWW"] == "https://med-pol.example.pl"
    assert "5000 - 8000" in row["Uwagi"]
    assert "Umowa o pracę" in row["Uwagi"]
    assert OLX_URL in row["Uwagi"]
    assert "koordynatora usług" in row["Uwagi"]


def test_parse_job_posting_in_graph() -> None:
    html = """
    <html><head><script type="application/ld+json">
    {"@graph": [
      {"@type": "WebPage", "name": "x"},
      {"@type": ["JobPosting"], "title": "Recepcjonista",
       "hiringOrganization": {"name": "Firma Test"},
       "jobLocation": {"address": {"addressLocality": "Poznań"}},
       "description": "Praca biurowa"}
    ]}
    </script></head><body><h1>Recepcjonista</h1></body></html>
    """
    row = ijl.parse_job_listing_html(html, "https://www.olx.pl/oferta/praca/x.html")
    assert row["Stanowisko / Rola"] == "Recepcjonista"
    assert row["Firma"] == "Firma Test"
    assert row["Miasto"] == "Poznań"


def test_parse_falls_back_to_h1_when_jsonld_missing() -> None:
    html = """
    <html><body>
      <h1 data-cy="ad_title">Specjalista ds. administracji</h1>
      <div data-cy="seller-name">Biuro Zielone</div>
      <div>Lokalizacja
      Warszawa</div>
      <div>Wymiar pracy
      Część etatu</div>
      <div data-cy="ad_description">Praca administracyjna w biurze.</div>
    </body></html>
    """
    row = ijl.parse_job_listing_html(html, OLX_URL)
    assert row["Stanowisko / Rola"] == "Specjalista ds. administracji"
    assert row["Firma"] == "Biuro Zielone"
    assert row["Tryb pracy"] == "Część etatu"
    assert row["Miasto"] == "Warszawa"
    assert row["Branża"] == "Administracja / biuro"


def test_parse_requires_title() -> None:
    with pytest.raises(ijl.ListingParseError):
        ijl.parse_job_listing_html("<html><body>brak oferty</body></html>", OLX_URL)


def test_fetch_blocked_on_403(monkeypatch) -> None:
    class _Resp:
        status_code = 403
        encoding = "utf-8"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_content(self, chunk_size=65536):
            yield b"Request blocked. captcha"

    monkeypatch.setattr(ijl.requests, "get", lambda *a, **k: _Resp())
    with pytest.raises(ijl.ListingFetchBlocked):
        ijl.fetch_public_listing_html(OLX_URL)


def test_import_listing_from_html_file_writes_xlsx(tmp_path, monkeypatch) -> None:
    def _boom(_url: str) -> str:
        raise AssertionError("nie wolno pobierać sieci przy --html-file")

    monkeypatch.setattr(ijl, "fetch_public_listing_html", _boom)
    out = tmp_path / "olx.xlsx"
    row = ijl.import_listing(url=OLX_URL, html=FIXTURE.read_text(encoding="utf-8"))
    path = ijl.write_contacts([row], str(out))
    assert Path(path).is_file()
    import pandas as pd

    df = pd.read_excel(path)
    assert list(df.columns) == serp.MAILER_COLUMNS
    assert df.loc[0, "Firma"] == "Med - Pol"
    assert df.loc[0, "Stanowisko / Rola"].startswith("Pracownik biurowy")


def test_main_html_file_csv(tmp_path) -> None:
    out = tmp_path / "kontakt.csv"
    code = ijl.main(
        [
            "--url",
            OLX_URL,
            "--html-file",
            str(FIXTURE),
            "--output",
            str(out),
        ]
    )
    assert code == 0
    text = out.read_text(encoding="utf-8-sig")
    assert "Med - Pol" in text
    assert "olx.pl" in text


def test_main_blocked_fetch_returns_2(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        ijl,
        "fetch_public_listing_html",
        lambda _u: (_ for _ in ()).throw(ijl.ListingFetchBlocked("blocked")),
    )
    code = ijl.main(
        ["--url", OLX_URL, "--output", str(tmp_path / "x.xlsx")]
    )
    assert code == 2


def test_apply_overrides_and_enrich_email(monkeypatch) -> None:
    row = {
        "Firma": "Med - Pol",
        "Strona WWW": "",
        "E-mail rekrutacyjny": "",
    }
    row = ijl.apply_overrides(
        row,
        company_website="https://www.olx.pl/oferta/x",
        email="",
    )
    assert row["Strona WWW"] == ""

    row = ijl.apply_overrides(
        row, company_website="https://med-pol.example.pl/kontakt"
    )
    assert row["Strona WWW"] == "https://med-pol.example.pl/kontakt"

    monkeypatch.setattr(
        serp,
        "_extract_recruit_email_from_site",
        lambda _u, timeout=8.0: "biuro@med-pol.example.pl",
    )
    row = ijl.enrich_email_from_company_site(row)
    assert row["E-mail rekrutacyjny"] == "biuro@med-pol.example.pl"


def test_main_enrich_email_flag(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        serp,
        "_extract_recruit_email_from_site",
        lambda _u, timeout=8.0: "hr@firma.example.pl",
    )
    html = """
    <html><head><script type="application/ld+json">
    {"@type":"JobPosting","title":"Asystent","hiringOrganization":{"name":"X"}}
    </script></head><body><h1>Asystent</h1></body></html>
    """
    html_path = tmp_path / "job.html"
    html_path.write_text(html, encoding="utf-8")
    out = tmp_path / "out.csv"
    code = ijl.main(
        [
            "--url",
            OLX_URL,
            "--html-file",
            str(html_path),
            "--company-website",
            "https://firma.example.pl",
            "--enrich-email",
            "--output",
            str(out),
        ]
    )
    assert code == 0
    assert "hr@firma.example.pl" in out.read_text(encoding="utf-8-sig")
