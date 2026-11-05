from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import build_contacts_serpapi as serp
import import_company_profile as icp

FIXTURE = Path(__file__).parent / "fixtures" / "aleo_company_profile.html"
ABTM_URL = "https://aleo.com/pl/firma/abtm-sp-z-oo-leszno"


@pytest.fixture
def abtm_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "url, expected",
    [
        (ABTM_URL, True),
        ("https://www.aleo.com/pl/firma/abtm-sp-z-oo-leszno/", True),
        ("https://aleo.com/int/company/abtm-sp-z-oo-leszno", True),
        ("https://aleo.com/pl/firmy/logistyka-spedycja-transport", False),
        ("https://www.olx.pl/oferta/praca/spedytor-CID4-ID1.html", False),
        ("https://notaleo.com/pl/firma/x", False),
        ("", False),
    ],
)
def test_is_aleo_company_url(url: str, expected: bool) -> None:
    assert icp.is_aleo_company_url(url) is expected


def test_parse_abtm_profile(abtm_html: str) -> None:
    profile = icp.parse_aleo_profile(abtm_html, ABTM_URL)

    assert profile["legal_name"] == "ABTM SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ"
    assert profile["city"] == "LESZNO"
    assert profile["postal_code"] == "64-100"
    assert profile["nip"] == "6972379473"
    assert profile["regon"] == "387557501"
    assert profile["krs"] == "0000870567"
    assert profile["address"] == "UL. RYNEK 33 / 3, 64-100 LESZNO"
    assert profile["categories"] == [
        "Logistyka, spedycja, transport",
        "Transport i spedycja drogowa",
        "Mieszany",
    ]
    assert profile["pkd"][0] == "49.41.Z - Transport drogowy towarów"
    assert len(profile["pkd"]) == 8
    assert profile["email"] == ""
    assert profile["website"] == ""


def test_abtm_contact_row_matches_mailer_columns(abtm_html: str) -> None:
    profile = icp.parse_aleo_profile(abtm_html, ABTM_URL)
    row = icp.profile_to_contact_row(profile, email="biuro@abtm.pl", website="abtm.pl")

    assert list(row) == serp.MAILER_COLUMNS
    assert row["Firma"] == "ABTM sp. z o.o."
    assert row["Miasto"] == "Leszno"
    assert row["Branża"] == "Logistyka, spedycja, transport / Transport i spedycja drogowa"
    assert row["Stanowisko / Rola"] == "Spedytor"
    assert row["Strona WWW"] == "https://abtm.pl"
    assert row["E-mail rekrutacyjny"] == "biuro@abtm.pl"
    assert row["Źródło / Portal"] == icp.ALEO_SOURCE_LABEL
    assert "NIP 6972379473" in row["Uwagi"]
    assert "KRS 0000870567" in row["Uwagi"]
    assert "Profil: " + ABTM_URL in row["Uwagi"]
    assert "69.20" not in row["Uwagi"]


def test_explicit_role_and_portal_website_rejected(abtm_html: str) -> None:
    profile = icp.parse_aleo_profile(abtm_html, ABTM_URL)
    row = icp.profile_to_contact_row(profile, role="Specjalista ds. logistyki", website=ABTM_URL)

    assert row["Stanowisko / Rola"] == "Specjalista ds. logistyki"
    assert row["Strona WWW"] == ""
    assert row["E-mail rekrutacyjny"] == ""


def test_profile_mailto_and_website_rows_are_used() -> None:
    html = """
    <script type="application/ld+json">{"@type": "Organization", "name": "PRZYKŁAD SPÓŁKA AKCYJNA",
      "address": {"addressLocality": "BIELSKO-BIAŁA"}}</script>
    <div class="registry-details__row"><h3 class="registry-details__row__label">Strona www</h3>
      <div class="registry-details__row__value"> www.przyklad.pl </div></div>
    <a href="mailto:kariera@przyklad.pl?subject=CV">napisz</a>
    """
    profile = icp.parse_aleo_profile(html)
    row = icp.profile_to_contact_row(profile)

    assert row["Firma"] == "PRZYKŁAD S.A."
    assert row["Miasto"] == "Bielsko-Biała"
    assert row["Strona WWW"] == "https://www.przyklad.pl"
    assert row["E-mail rekrutacyjny"] == "kariera@przyklad.pl"
    assert row["Stanowisko / Rola"] == "(do ustalenia)"


def test_parse_rejects_page_without_company_data() -> None:
    with pytest.raises(icp.ProfileParseError):
        icp.parse_aleo_profile("<html><body>Zweryfikuj reCAPTCHA</body></html>")


def test_main_writes_xlsx_from_html_file(tmp_path: Path) -> None:
    out = tmp_path / "abtm.xlsx"
    code = icp.main(
        [
            "--url",
            ABTM_URL,
            "--html-file",
            str(FIXTURE),
            "--email",
            "biuro@abtm.pl",
            "--company-website",
            "https://www.abtm.pl/",
            "--output",
            str(out),
        ]
    )

    assert code == 0
    df = pd.read_excel(out)
    assert list(df.columns) == serp.MAILER_COLUMNS
    assert df.loc[0, "Firma"] == "ABTM sp. z o.o."
    assert df.loc[0, "E-mail rekrutacyjny"] == "biuro@abtm.pl"


def test_main_enrich_email_from_company_website(tmp_path: Path, monkeypatch) -> None:
    calls = []

    def fake_extract(url: str, timeout: float = 8.0) -> str:
        calls.append(url)
        return "biuro@abtm.pl"

    monkeypatch.setattr(serp, "_extract_recruit_email_from_site", fake_extract)
    out = tmp_path / "abtm.csv"
    code = icp.main(
        [
            "--url",
            ABTM_URL,
            "--html-file",
            str(FIXTURE),
            "--company-website",
            "abtm.pl",
            "--enrich-email",
            "--output",
            str(out),
        ]
    )

    assert code == 0
    assert calls == ["https://abtm.pl"]
    assert pd.read_csv(out).loc[0, "E-mail rekrutacyjny"] == "biuro@abtm.pl"


def test_main_rejects_non_aleo_url() -> None:
    assert icp.main(["--url", "https://example.com/firma/x"]) == 1


def test_main_blocked_fetch_returns_2(monkeypatch, tmp_path: Path) -> None:
    def blocked(url: str, timeout: float = 0) -> str:
        raise icp.ProfileFetchBlocked("HTTP 403")

    monkeypatch.setattr(icp, "fetch_profile_html", blocked)
    assert icp.main(["--url", ABTM_URL, "--output", str(tmp_path / "x.xlsx")]) == 2
