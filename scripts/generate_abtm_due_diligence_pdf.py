#!/usr/bin/env python3
"""Generuje raport due diligence ABTM (PDF, UTF-8 PL)."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fpdf import FPDF

FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
WARSAW = ZoneInfo("Europe/Warsaw")


class ReportPDF(FPDF):
    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, f"Strona {self.page_no()}/{{nb}}", align="C")


def _section(pdf: ReportPDF, title: str) -> None:
    pdf.ln(4)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("DejaVu", "B", 12)
    pdf.set_text_color(20, 60, 100)
    pdf.multi_cell(0, 7, title)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("DejaVu", "", 10)
    pdf.ln(1)


def _body(pdf: ReportPDF, text: str) -> None:
    pdf.set_x(pdf.l_margin)
    pdf.set_font("DejaVu", "", 10)
    pdf.multi_cell(0, 5.5, text)
    pdf.ln(1)


def _bullet(pdf: ReportPDF, text: str) -> None:
    pdf.set_x(pdf.l_margin + 2)
    pdf.multi_cell(0, 5.5, f"• {text}")


def build_report(generated_at: datetime) -> FPDF:
    pdf = ReportPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_font("DejaVu", "", FONT_REG)
    pdf.add_font("DejaVu", "B", FONT_BOLD)

    pdf.add_page()
    pdf.set_font("DejaVu", "B", 18)
    pdf.cell(0, 10, "Raport due diligence pracodawcy", ln=1)
    pdf.set_font("DejaVu", "B", 14)
    pdf.cell(0, 8, "ABTM Sp. z o.o., Leszno", ln=1)
    pdf.set_font("DejaVu", "", 10)
    pdf.set_text_color(80, 80, 80)
    pdf.multi_cell(
        0,
        6,
        f"Kontekst: aplikacja na stanowisko spedytora\n"
        f"Data raportu: {generated_at.strftime('%Y-%m-%d %H:%M')} (Europe/Warsaw)\n"
        f"Źródła: KRS/RDF, ALEO.com, agregatory (firmy.ai, BizRaport), ogłoszenia Pracuj.pl",
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    _section(pdf, "1. Podsumowanie wykonawcze")
    _body(
        pdf,
        "ABTM Sp. z o.o. (KRS 0000870567, NIP 6972379473) to aktywny przewoźnik drogowy "
        "z siedzibą rejestrową Rynek 33/3, 64-100 Leszno. Spółka rośnie finansowo "
        "(przychody ok. 2,9 → 5,1 → 6,9 mln zł w latach 2023–2025 według ALEO/KRS), "
        "utrzymuje zysk netto i dobrą płynność bieżącą. Brak wpisu w Krajowym Rejestrze "
        "Zadłużonych (KRZ) w publicznych agregatorach.",
    )
    _body(
        pdf,
        "Werdykt dla kandydata na spedytora: rozmowa kwalifikacyjna jest uzasadniona — "
        "firma wygląda na realnego, wiarygodnego pracodawcę transportowo-spedycyjnego. "
        "Warunki zatrudnienia należy potwierdzić na umowie (forma, wynagrodzenie, zakres, "
        "podmiot pracodawcy = ABTM sp. z o.o.).",
    )

    _section(pdf, "2. Dane rejestrowe ABTM")
    for line in [
        "Pełna nazwa: ABTM Spółka z ograniczoną odpowiedzialnością",
        "KRS: 0000870567 | NIP: 6972379473 | REGON: 387557501",
        "Adres KRS: ul. Rynek 33/3, 64-100 Leszno",
        "Adres operacyjny (www): ul. Geodetów 1, 64-100 Leszno (abtm.pl)",
        "Rejestracja KRS: 2020-11-23 | Kapitał zakładowy: 5 000 zł",
        "VAT: czynny (publiczne rejestry)",
        "PKD (wybrane): 49.41.Z transport drogowy towarów; 52 magazynowanie i usługi transportowe; "
        "52.31 pośrednictwo w transporcie; 53.2 kurierskie; 69.20 księgowość (szeroki zakres PKD).",
    ]:
        _bullet(pdf, line)

    _section(pdf, "3. Władze i właściciele")
    _bullet(pdf, "Adrian Balcerzak — prezes zarządu, 50 udziałów (2 500 zł)")
    _bullet(pdf, "Tomasz Maćkowiak — członek zarządu, 50 udziałów (2 500 zł)")
    _body(
        pdf,
        "Reprezentacja: każdy członek zarządu samodzielnie (KRS).",
    )

    _section(pdf, "4. Kondycja finansowa ABTM (ALEO / KRS)")
    pdf.set_font("DejaVu", "B", 9)
    col_w = (pdf.w - pdf.l_margin - pdf.r_margin) / 4
    headers = ["Rok", "Przychody", "Zysk netto", "Aktywa"]
    for i, h in enumerate(headers):
        pdf.cell(col_w, 7, h, border=1)
    pdf.ln()
    pdf.set_font("DejaVu", "", 9)
    rows = [
        ("2023", "~2,9 mln zł", "~0,3 mln zł", "~0,7 mln zł"),
        ("2024", "~5,1 mln zł", "~0,6 mln zł", "~1,4 mln zł"),
        ("2025", "~6,9 mln zł", "~0,5 mln zł", "~1,3 mln zł"),
    ]
    for row in rows:
        for cell in row:
            pdf.cell(col_w, 7, cell, border=1)
        pdf.ln()
    pdf.ln(2)
    _body(
        pdf,
        "Wskaźniki (ALEO, 2025): kapitał własny do aktywów ok. 62%; wskaźnik bieżącej płynności "
        "ok. 2,97; zobowiązania krótkoterminowe spadają r/r. Środki pieniężne spadły "
        "(ok. 0,4 → 0,1 mln zł) — typowe dla firm operacyjnych, nie jest to samo co ryzyko upadłości.",
    )

    _section(pdf, "5. Powiązane podmioty")
    _body(pdf, "5.1 Adrian Balcerzak Tomasz Maćkowiak sp.j. (KRS 0000870382)")
    for line in [
        "Wspólnicy: Balcerzak + Maćkowiak (jak w ABTM)",
        "Adres: Rynek 33/3, Leszno | PKD: 77.12.Z wynajem ciężarówek",
        "Rola: typowy układ flota (sp.j.) + operacje transportowe (sp. z o.o.)",
        "Finanse: brak publicznych kwot przychodu/zysku w agregatorach (ograniczone ujawnianie sp.j.)",
        "KRZ: brak wpisu (BizRaport)",
    ]:
        _bullet(pdf, line)

    _body(pdf, "5.2 Holdex sp. z o.o. (KRS 0000388246) — powiązanie przez Adriana Balcerzaka")
    for line in [
        "Branża: gastronomia (PKD 56.10.A), Leszno, od 2011 r.",
        "Właściciel: Małgorzata Balcerzak 75%; Adrian Balcerzak — prezes (bez udziałów w KRS jako wspólnik)",
        "Przychody: ~2,85 mln (2023) → ~2,95 mln (2024) → ~3,36 mln (2025)",
        "Zysk netto: ~53 tys. (2023) → ~286 tys. (2024) → ~160 tys. (2025)",
        "Osobny biznes rodzinny — nie współwłaściciel Maćkowiak",
    ]:
        _bullet(pdf, line)

    _body(pdf, "5.3 Car Service Garage sp. z o.o. (KRS 0001157036)")
    for line in [
        "Założona 2025-02-20, Strzyżewice; serwis pojazdów + PKD transport",
        "Wspólnicy: Adrian Balcerzak 50%, Serhii Kush 50%",
        "2025 (skrócony rok): przychody ~0,58–0,72 mln zł, strata netto ~149 tys. zł, słaba płynność",
        "Nie dyskwalikuje ABTM, o ile umowa jest z ABTM sp. z o.o.",
    ]:
        _bullet(pdf, line)

    _section(pdf, "6. Sygnały rynkowe i HR")
    _bullet(
        pdf,
        "GoWork: średnia ~4,3/5; były kierowca (3+ lata): wypłaty na czas; także ostra negatywna opinia "
        "(umowy, nadgodziny — nieweryfikowane, dotyczy głównie kierowców).",
    )
    _bullet(
        pdf,
        "Pracuj.pl: dominują ogłoszenia kierowca kat. C; firma deklaruje transport/spedycję/logistykę.",
    )
    _bullet(pdf, "Opinie klientów transportu (Google): przeważnie pozytywne.")
    _body(
        pdf,
        "Dla spedytora: mało opinii biurowych; rola ma sens operacyjny (planowanie, kierowcy, palety/Gdrive w ogłoszeniach).",
    )

    _section(pdf, "7. Werdykt — stanowisko spedytor")
    pdf.set_font("DejaVu", "B", 10)
    pdf.multi_cell(
        0,
        6,
        "Wiarygodność pracodawcy (ABTM sp. z o.o.): umiarkowanie wysoka — realna firma, "
        "rosnące finanse, brak sygnałów upadłości w KRZ.",
    )
    pdf.set_font("DejaVu", "", 10)
    _bullet(pdf, "Idź na rozmowę — zaproszenie jest spójne z profilem firmy.")
    _bullet(pdf, "Umowa wyłącznie: ABTM Sp. z o.o., KRS 0000870567.")
    _bullet(pdf, "Ustal: własna flota vs spedycja obca, TMS/narzędzia, wynagrodzenie stałe vs prowizja, wielkość zespołu.")
    _bullet(pdf, "Miejsce pracy: Geodetów 1 vs Rynek 33/3.")

    _section(pdf, "8. Zastrzeżenia")
    _body(
        pdf,
        "Raport oparty o dane publiczne; nie stanowi porady prawnej, podatkowej ani inwestycyjnej. "
        "Przed podpisaniem umowy zaleca się weryfikację odpisu KRS, statusu VAT oraz treści umowy.",
    )

    return pdf


def main() -> None:
    parser = argparse.ArgumentParser(description="Generuj raport PDF ABTM due diligence")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("/opt/cursor/artifacts/Raport_ABTM_spedytor_due_diligence.pdf"),
        help="Ścieżka pliku PDF",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(WARSAW)
    pdf = build_report(now)
    pdf.output(str(args.output))
    print(args.output.resolve())


if __name__ == "__main__":
    main()
