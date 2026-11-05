# Killer prompt — raport due diligence PDF + e-mail

Skopiuj poniższy blok do Cursora / ChatGPT (z dostępem do sieci i opcjonalnie do skryptów w repo).

---

## Prompt

```
Zadanie: przygotuj profesjonalny raport due diligence w języku polskim (PDF) o firmie [NAZWA / KRS / link ALEO] w kontekście mojej aplikacji na stanowisko [STANOWISKO].

Wymagania treści:
1. Streszczenie wykonawcze (1 strona) — werdykt: czy iść na rozmowę, jako pracodawca.
2. Dane rejestrowe (KRS, NIP, REGON, adres KRS vs operacyjny, VAT, PKD).
3. Władze, wspólnicy, sposób reprezentacji.
4. Finanse z ostatnich 3 lat ze sprawozdań KRS/RDF: przychody, zysk netto, aktywa, kapitał własny, płynność — tabela.
5. Mapa powiązań kapitałowych: wszystkie spółki tych samych osób + krótki opis branży i kondycji finansowej każdej.
6. KRZ / upadłość / restrukturyzacja — czy figuruje w publicznych źródłach.
7. Sygnały HR (opinie pracowników, ogłoszenia) — osobno dla mojego stanowiska ([STANOWISKO]).
8. Lista pytań na rozmowę kwalifikacyjną (min. 8).
9. Zastrzeżenie prawne (dane publiczne, nie porada prawna).

Źródła (minimum): ALEO lub odpis KRS, firmy.ai / BizRaport / RDF, oferty Pracuj.pl jeśli dotyczy.

Format PDF:
- A4, czcionka z polskimi znakami (UTF-8), nagłówki sekcji, tabela finansów, stopka ze stronami.
- Nazwa pliku: Raport_[SKROT_FIRMY]_[stanowisko]_due_diligence.pdf

Dostarczenie:
- Wygeneruj PDF (np. skrypt Python fpdf2 w repo: scripts/generate_*_pdf.py).
- Wyślij na e-mail: [TWÓJ_EMAIL] z tematem „Raport due diligence — [FIRMA] ([stanowisko])”.
- Jeśli brak GMAIL_APP_PASSWORD w środowisku: zapisz PDF w artifacts i podaj ścieżkę + komendę:
  python scripts/send_abtm_report_email.py --to [TWÓJ_EMAIL]

Mój przypadek (wypełnione):
- Firma: ABTM Sp. z o.o., KRS 0000870567, https://aleo.com/pl/firma/abtm-sp-z-oo-leszno
- Stanowisko: spedytor
- E-mail: svinchak1993@gmail.com
```

---

## Szybkie wykonanie w tym repozytorium

```bash
pip install fpdf2
python scripts/generate_abtm_due_diligence_pdf.py
# lokalnie z hasłem aplikacji Gmail:
export GMAIL_APP_PASSWORD='....'   # 16 znaków, bez spacji
python scripts/send_abtm_report_email.py --to svinchak1993@gmail.com
```
