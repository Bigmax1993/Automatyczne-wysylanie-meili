"""Testy klienta publicznej wyszukiwarki IPN Straty (bez prawdziwych danych osobowych)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import search_straty_osoby as sso

TOO_MANY_HTML = """
<html><body>
<h3 class="form_tytul2">Wyniki wyszukiwania</h3>
<form method="post" action="szukaj-osoby.php">
<div class="section_wynik1">
<input type="hidden" name="nazwisko" value="Kowalski">
<h3 class="heading-3">Za dużo wyników wyszukiwania - uściślij kryteria.</h3>
</div>
<input type="submit" name="powrot" value="powrót">
</form>
</body></html>
"""

NO_CRITERIA_HTML = """
<html><body>
<h3 class="form_tytul2">Wyniki wyszukiwania</h3>
<h3 class="heading-3">Brak kryteriów wyszukiwania.</h3>
</body></html>
"""

NO_MATCHES_HTML = """
<html><body>
<h3 class="form_tytul2">Wyniki wyszukiwania</h3>
<h3 class="heading-3">Nie ma danych spełniajacych kryteria.</h3>
</body></html>
"""

RESULTS_HTML = """
<html><body>
<h3 class="form_tytul2">Wyniki wyszukiwania</h3>
<form id="email-form-2" method="post" action="szukaj-osoby.php">
<div class="section_wynik1 wf-section">
<input type="hidden" name="nazwisko" value="Przykladski">
<input type="hidden" name="imie" value="Anna">
<div class="w-layout-grid grid-3">
<div class="tekst_szukaj_wynik_lp">Lp.</div>
<div class="tekst_szukaj_wynik">Nazwisko</div>
<div class="tekst_szukaj_wynik">Imię</div>
<div class="tekst_szukaj_wynik">Nazwisko panieńskie</div>
<div class="tekst_szukaj_wynik">Data urodzenia</div>
<div class="tekst_szukaj_wynik">Miejsce urodzenia</div>
<div class="tekst_szukaj_wynik">Imię ojca</div>
<div class="tekst_szukaj_wynik">Imię matki</div>
<div class="tekst_szukaj_wynik">Data śmierci</div>
<input type="submit" id="lp" class="tekst_szukaj_wynik_lp" name="id111" value="1">
<input type="submit" class="tekst_szukaj_wynik_lista" name="id111" value="Przykladski">
<input type="submit" class="tekst_szukaj_wynik_lista" name="id111" value="Anna">
<input type="submit" class="tekst_szukaj_wynik_lista" name="id111" value="Nowak">
<input type="submit" class="tekst_szukaj_wynik_lista" name="id111" value="1912-05-01">
<input type="submit" class="tekst_szukaj_wynik_lista" name="id111" value="Warszawa">
<input type="submit" class="tekst_szukaj_wynik_lista" name="id111" value="Jan">
<input type="submit" class="tekst_szukaj_wynik_lista" name="id111" value="Maria">
<input type="submit" class="tekst_szukaj_wynik_lista" name="id111" value="1943-01-02">
<input type="submit" id="lp" class="tekst_szukaj_wynik_lp" name="id222" value="2">
<input type="submit" class="tekst_szukaj_wynik_lista" name="id222" value="Przykladski">
<input type="submit" class="tekst_szukaj_wynik_lista" name="id222" value="Anna">
<input type="submit" class="tekst_szukaj_wynik_lista" name="id222" value="">
<input type="submit" class="tekst_szukaj_wynik_lista" name="id222" value="1915">
<input type="submit" class="tekst_szukaj_wynik_lista" name="id222" value="Lublin">
<input type="submit" class="tekst_szukaj_wynik_lista" name="id222" value="Piotr">
<input type="submit" class="tekst_szukaj_wynik_lista" name="id222" value="">
<input type="submit" class="tekst_szukaj_wynik_lista" name="id222" value="">
</div>
<input type="submit" name="powrot" value="powrót">
</div>
</form>
</body></html>
"""

DETAIL_HTML = """
<html><body>
<div class="section-4">
  <div class="div-block-18"><h3 class="form_tytul2">Dane osobowe</h3></div>
  <div class="daneosobowe">
    <div class="trzylabel">nazwisko</div><div class="trzydane">PRZYKLADSKI</div>
    <div class="trzylabel">imię</div><div class="trzydane">ANNA</div>
    <div class="trzylabel">imię ojca</div><div class="trzydane">JAN</div>
    <div class="trzylabel">data urodzenia</div><div class="trzydane">1912-05-01</div>
    <div class="trzylabel">miejsce urodzenia</div><div class="trzydane">WARSZAWA</div>
  </div>
  <h3 class="form_tytul2">Informacje o prześladowaniach</h3>
  <div class="zrodlo">
    <div><div class="text-block-7">Źródło:&nbsp;</div></div>
    <div>
      <div><a href="https://example.invalid/archiwum" class="link_zrodlo">Archiwum testowe</a></div>
      <div>SYG-1</div>
    </div>
  </div>
  <div class="danerepresji">
    <div class="trzylabel">więzień obozu</div><div class="trzydane">zginął</div>
    <div class="trzylabel">miejsce</div><div class="trzydane">AUSCHWITZ</div>
  </div>
</div>
</body></html>
"""

EMPTY_FORM_HTML = """
<html><body>
<form method="post" action="szukaj-osoby.php">
<label for="nazwisko">Nazwisko:</label>
<input type="text" name="nazwisko" id="nazwisko">
<input type="submit" name="szukaj" value="Szukaj">
</form>
</body></html>
"""


class _FakeResp:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code


def test_validate_query_requires_surname() -> None:
    with pytest.raises(sso.StratySearchError):
        sso.validate_query(sso.SearchQuery(nazwisko="A"))
    with pytest.raises(sso.StratySearchError):
        sso.validate_query(sso.SearchQuery(nazwisko=""))


def test_validate_query_rejects_bad_dates() -> None:
    with pytest.raises(sso.StratySearchError):
        sso.validate_query(sso.SearchQuery(nazwisko="Nowak", ur_dzien="40"))
    with pytest.raises(sso.StratySearchError):
        sso.validate_query(sso.SearchQuery(nazwisko="Nowak", ur_miesiac="13"))
    with pytest.raises(sso.StratySearchError):
        sso.validate_query(sso.SearchQuery(nazwisko="Nowak", ur_rok="1700"))
    q = sso.validate_query(sso.SearchQuery(nazwisko="Nowak", sm_rok="1993"))
    assert q.sm_rok == "1993"


def test_parse_too_many() -> None:
    result = sso.parse_search_html(TOO_MANY_HTML)
    assert result.kind == "too_many"
    assert not result.matches


def test_parse_no_criteria() -> None:
    assert sso.parse_search_html(NO_CRITERIA_HTML).kind == "no_criteria"


def test_parse_no_matches() -> None:
    result = sso.parse_search_html(NO_MATCHES_HTML)
    assert result.kind == "no_matches"
    assert result.matches == []


def test_parse_results_groups_submit_buttons() -> None:
    result = sso.parse_search_html(RESULTS_HTML)
    assert result.kind == "results"
    assert len(result.matches) == 2
    first = result.matches[0]
    assert first.record_id == "111"
    assert first.nazwisko == "Przykladski"
    assert first.imie == "Anna"
    assert first.panienskie == "Nowak"
    assert first.data_urodzenia == "1912-05-01"
    assert first.miejsce_urodzenia == "Warszawa"
    assert first.imie_ojca == "Jan"
    assert first.imie_matki == "Maria"
    assert first.data_smierci == "1943-01-02"
    assert result.matches[1].record_id == "222"
    assert result.matches[1].miejsce_urodzenia == "Lublin"


def test_parse_detail_nested_source_wrapper() -> None:
    html = """
    <html><body>
      <div class="section-4">
        <div class="daneosobowe">
          <div class="trzylabel">nazwisko</div><div class="trzydane">TEST</div>
        </div>
        <h3>Informacje o prześladowaniach</h3>
        <div>
          <div class="zrodlo">
            <div><div class="text-block-7">Źródło:</div></div>
            <div>
              <div><a href="https://example.invalid" class="link_zrodlo">Archiwum X</a></div>
              <div>ABC-9</div>
            </div>
          </div>
          <div class="danerepresji">
            <div class="trzylabel">robotnik przymusowy</div><div class="trzydane">przeżył</div>
          </div>
        </div>
      </div>
    </body></html>
    """
    detail = sso.parse_detail_html(html, record_id="9")
    assert detail.dane_osobowe["nazwisko"] == "TEST"
    assert len(detail.przesladowania) == 1
    assert detail.przesladowania[0].zrodlo == "Archiwum X"
    assert detail.przesladowania[0].zrodlo_sygnatura == "ABC-9"
    assert detail.przesladowania[0].pola["robotnik przymusowy"] == "przeżył"


def test_parse_empty_form() -> None:
    assert sso.parse_search_html(EMPTY_FORM_HTML).kind == "form"


def test_parse_detail_card() -> None:
    detail = sso.parse_detail_html(DETAIL_HTML, record_id="111")
    assert detail.dane_osobowe["nazwisko"] == "PRZYKLADSKI"
    assert detail.dane_osobowe["imię"] == "ANNA"
    assert len(detail.przesladowania) == 1
    rec = detail.przesladowania[0]
    assert rec.zrodlo == "Archiwum testowe"
    assert rec.zrodlo_url == "https://example.invalid/archiwum"
    assert rec.zrodlo_sygnatura == "SYG-1"
    assert rec.pola["więzień obozu"] == "zginął"
    assert rec.pola["miejsce"] == "AUSCHWITZ"


def test_search_person_posts_public_form(monkeypatch) -> None:
    posted: list[dict] = []

    def fake_post(payload, **kwargs):
        posted.append(dict(payload))
        return RESULTS_HTML

    monkeypatch.setattr(sso, "post_form", fake_post)
    result = sso.search_person(sso.SearchQuery(nazwisko="Przykladski", imie="Anna"))
    assert result.kind == "results"
    assert posted[0]["nazwisko"] == "Przykladski"
    assert posted[0]["imie"] == "Anna"
    assert posted[0]["szukaj"] == "Szukaj"


def test_search_person_fetches_details_with_record_id(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_post(payload, **kwargs):
        calls.append(dict(payload))
        if any(k.startswith("id") for k in payload):
            return DETAIL_HTML
        return RESULTS_HTML

    monkeypatch.setattr(sso, "post_form", fake_post)
    result = sso.search_person(
        sso.SearchQuery(nazwisko="Przykladski", imie="Anna"),
        fetch_details=True,
        max_details=1,
    )
    assert result.kind == "results"
    assert len(result.details) == 1
    assert result.details[0].record_id == "111"
    assert result.details[0].dane_osobowe["nazwisko"] == "PRZYKLADSKI"
    assert any("id111" in c for c in calls)
    assert len(calls) == 2


def test_max_details_respects_hard_cap(monkeypatch) -> None:
    monkeypatch.setattr(sso, "HARD_MAX_DETAILS", 1)
    calls: list[dict] = []

    def fake_post(payload, **kwargs):
        calls.append(dict(payload))
        if any(k.startswith("id") for k in payload):
            return DETAIL_HTML
        return RESULTS_HTML

    monkeypatch.setattr(sso, "post_form", fake_post)
    result = sso.search_person(
        sso.SearchQuery(nazwisko="Przykladski"),
        fetch_details=True,
        max_details=999,
    )
    assert len(result.details) == 1
    assert sum(1 for c in calls if any(k.startswith("id") for k in c)) == 1


def test_post_form_does_not_bypass_blocks(monkeypatch) -> None:
    class _Sess:
        def post(self, url, data, timeout):
            return _FakeResp("<html>captcha verify you are human</html>", 200)

    monkeypatch.setattr(sso, "throttle_hostname_before_http", lambda _url: None)
    with pytest.raises(sso.StratySearchError, match="odrzucił"):
        sso.post_form({"nazwisko": "X"}, session=_Sess())


def test_post_form_http_error(monkeypatch) -> None:
    class _Sess:
        def post(self, url, data, timeout):
            return _FakeResp("oops", 500)

    monkeypatch.setattr(sso, "throttle_hostname_before_http", lambda _url: None)
    with pytest.raises(sso.StratySearchError, match="HTTP 500"):
        sso.post_form({"nazwisko": "X"}, session=_Sess())


def test_looks_like_block_on_status() -> None:
    assert sso._looks_like_block(429, "")
    assert sso._looks_like_block(200, "Please complete the CAPTCHA")
    assert not sso._looks_like_block(200, "<h3>Wyniki wyszukiwania</h3>")


def test_cli_json_and_csv(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sso, "post_form", lambda *a, **k: RESULTS_HTML)
    out_json = tmp_path / "out.json"
    out_csv = tmp_path / "out.csv"
    code = sso.main(
        [
            "--nazwisko",
            "Przykladski",
            "--imie",
            "Anna",
            "--json",
            "--output",
            str(out_json),
        ]
    )
    assert code == 0
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["kind"] == "results"
    assert payload["matches"][0]["record_id"] == "111"
    printed = json.loads(capsys.readouterr().out)
    assert printed["matches"][1]["lp"] == "2"

    code = sso.main(["--nazwisko", "Przykladski", "--output", str(out_csv)])
    assert code == 0
    csv_text = out_csv.read_text(encoding="utf-8-sig")
    assert "Przykladski" in csv_text
    assert "record_id" in csv_text


def test_cli_too_many_exit_code(monkeypatch) -> None:
    monkeypatch.setattr(sso, "post_form", lambda *a, **k: TOO_MANY_HTML)
    assert sso.main(["--nazwisko", "Kowalski"]) == 3


def test_cli_no_matches_exit_code(monkeypatch) -> None:
    monkeypatch.setattr(sso, "post_form", lambda *a, **k: NO_MATCHES_HTML)
    assert sso.main(["--nazwisko", "Zzznonexistent"]) == 1


def test_cli_rejects_short_name(capsys) -> None:
    with pytest.raises(SystemExit):
        sso.build_arg_parser().parse_args([])
    assert sso.main(["--nazwisko", "A"]) == 2
    assert "nazwisko" in capsys.readouterr().err.lower()


def test_format_table_includes_source() -> None:
    result = sso.parse_search_html(RESULTS_HTML)
    result.query = sso.SearchQuery(nazwisko="Przykladski", imie="Anna")
    text = sso.format_table(result)
    assert "Przykladski" in text
    assert "straty.pl" in text
    assert "id111" in text or "111" in text


def test_query_as_form_omits_empty_submit_for_details() -> None:
    payload = sso.SearchQuery(nazwisko="Nowak").as_form("szukaj")
    assert payload["szukaj"] == "Szukaj"
    assert payload["nazwisko"] == "Nowak"
