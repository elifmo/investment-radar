#!/usr/bin/env python3
"""Generate USA pre-market report PDF from pipeline output."""

from pathlib import Path

from fpdf import FPDF

REPORTS = Path(__file__).resolve().parent.parent / "reports"
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

DATA_DATE_USA = "15 Temmuz 2026"
DATA_DATE_EU = "16 Temmuz 2026"
REPORT_DATE = "16 Temmuz 2026"

TOP10 = [
    ("GL", "Globe Life Inc.", "Financials", "90", "$181.60", "WATCH", "RS 96, hacim 2.2x"),
    ("NSC", "Norfolk Southern Corp.", "Industrials", "90", "$328.52", "WATCH", "Fiyat sicramasi + hacim"),
    ("BNY", "Bank of New York Mellon", "Financials", "75", "$162.40", "WATCH", "52w high break"),
    ("EA", "Electronic Arts Inc.", "Comm. Services", "75", "$207.23", "WATCH", "Destek yakini, grade A"),
    ("FE", "FirstEnergy Corp.", "Utilities", "75", "$48.62", "WATCH", "Utilities momentum"),
    ("STT", "State Street Corp.", "Financials", "75", "$186.73", "WATCH", "Finans, RS 95"),
    ("BKNG", "Booking Holdings Inc.", "Cons. Discretionary", "70", "$182.81", "WATCH", "EMA kesisimi"),
    ("IEX", "IDEX Corporation", "Industrials", "70", "$223.51", "WATCH", "EMA kesisimi"),
    ("VLO", "Valero Energy Corp.", "Energy", "70", "$292.77", "BUY", "Energy LEADING, RS 93"),
    ("WFC", "Wells Fargo & Co.", "Financials", "70", "$87.52", "SKIP", "Grade D — elendi"),
]

OVERSOLD = [
    ("IBM", "International Business Machines", "Technology"),
    ("ALNY", "Alnylam Pharmaceuticals", "Health Care"),
    ("MAA", "Mid-America Apartment Comm.", "Real Estate"),
    ("ARM", "Arm Holdings plc", "Technology"),
    ("MRVL", "Marvell Technology", "Technology"),
]

PORTFOLIO = [
    ("ORCL", "Oracle Corporation", "Technology", "$132.49",
     "Deep oversold. RS 17, 30g -46%. Limit $127-130; acele alim degil."),
    ("INTC", "Intel Corporation", "Technology", "$102.99",
     "Hafif bounce, skor 25. Destek $99 — limit dusunulebilir."),
    ("RKLB", "Rocket Lab Corporation", "Industrials", "$76.20",
     "PORTFOYDE. Spekulatif, deep oversold. Destek $74.84 kritik — stop aktif."),
    ("ASTS", "AST SpaceMobile Inc.", "Comm. Services", "$66.31",
     "PORTFOYDE. RKLB ile ayni profil, destek $64.59. Stop $66 yakin."),
    ("PLTR", "Palantir Technologies", "Technology", "$133.76",
     "Sakin profil, grade A. Acil bir sey yok."),
    ("ISRG", "Intuitive Surgical Inc.", "Health Care", "$388.97",
     "En temiz aday. RS 99, grade B. Limit $378-390."),
]

EU_PORTFOLIO = [
    ("DSFIR", "DSM-Firmenich AG", "Materials", "EUR 85.62",
     "PORTFOYDE. +18% kar. Stoch 86 overbought, direnc EUR 86.40. Satis limiti EUR 85-86; yeni alim yok."),
    ("SIFG", "Sif Holding N.V.", "Industrials", "EUR 4.39",
     "PORTFOYDE. -46% zarar. RSI 32, destek EUR 3.91, stop EUR 3.75 aktif. Yeni alim yok."),
]


class ReportPDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 11)
        self.set_text_color(40, 40, 40)
        self.cell(0, 8, "Investment Radar — Pre-Market Raporu (USA + EU)", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Arial", "", 8)
        self.set_text_color(100, 100, 100)
        self.cell(
            0, 5,
            f"Rapor: {REPORT_DATE}  |  USA: {DATA_DATE_USA}  |  EU: {DATA_DATE_EU}  |  523 hisse  |  Yatirim tavsiyesi degildir",
            align="C", new_x="LMARGIN", new_y="NEXT",
        )
        self.ln(3)
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-12)
        self.set_font("Arial", "", 7)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8, f"Sayfa {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title: str):
        self.set_font("Arial", "B", 10)
        self.set_fill_color(240, 244, 248)
        self.set_text_color(30, 60, 100)
        self.cell(0, 7, title, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def body_text(self, text: str):
        self.set_font("Arial", "", 8.5)
        self.set_text_color(50, 50, 50)
        self.multi_cell(0, 4.8, text)
        self.ln(1)

    def bullet(self, text: str):
        self.set_font("Arial", "", 8.5)
        self.set_text_color(50, 50, 50)
        self.multi_cell(0, 4.8, f"  •  {text}")
        self.ln(0.5)

    def stock_block(self, ticker: str, name: str, sector: str, price: str, text: str):
        self.set_font("Arial", "B", 9)
        self.set_text_color(30, 60, 100)
        self.cell(0, 5, f"{ticker} — {name}", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Arial", "", 7.5)
        self.set_text_color(100, 100, 100)
        self.cell(0, 4, f"Sektor: {sector}  |  Kapanis: {price}", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Arial", "", 8.5)
        self.set_text_color(50, 50, 50)
        self.multi_cell(0, 4.8, text)
        self.ln(2)

    def table_header(self, cols, widths):
        self.set_font("Arial", "B", 6.5)
        self.set_fill_color(50, 80, 120)
        self.set_text_color(255, 255, 255)
        for i, col in enumerate(cols):
            self.cell(widths[i], 6, col, border=1, fill=True)
        self.ln()

    def table_row(self, cols, widths, fill=False, bold_cols=None):
        bold_cols = bold_cols or set()
        self.set_text_color(40, 40, 40)
        self.set_fill_color(248, 249, 250) if fill else self.set_fill_color(255, 255, 255)
        x0, y0 = self.get_x(), self.get_y()
        row_h = 7
        for i, col in enumerate(cols):
            x = x0 + sum(widths[:i])
            self.rect(x, y0, widths[i], row_h)
            self.set_font("Arial", "B" if i in bold_cols else "", 6)
            self.set_xy(x + 1, y0 + 1)
            self.cell(widths[i] - 2, row_h - 2, str(col))
        self.set_xy(x0, y0 + row_h)


def build_pdf() -> Path:
    pdf = ReportPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("Arial", "", FONT_PATH)
    pdf.add_font("Arial", "B", FONT_BOLD)
    pdf.add_page()

    pdf.section_title("GENEL TABLO")
    pdf.body_text(
        "Dunku kapanisa gore ortam RISK_OFF. SPY 30g -0.2%. Para Energy ve Communication tarafina kaymis; "
        "Tech, Consumer ve Materials geride.\n\n"
        "Momentum adaylarinin cogu WATCH. Tek net BUY: VLO (Valero Energy, Energy sektoru)."
    )

    pdf.section_title("SISTEMIN ONE CIKARDIKLARI (TOP 10)")
    w = [11, 38, 22, 10, 16, 12, 81]
    pdf.table_header(["Ticker", "Tam ad", "Sektor", "Skor", "Kapanis", "Karar", "Not"], w)
    for i, row in enumerate(TOP10):
        bold = {5} if row[5] == "BUY" else set()
        pdf.table_row(list(row), w, fill=i % 2 == 0, bold_cols=bold)
    pdf.ln(3)

    pdf.section_title("OVERSOLD — EN DERIN 5")
    w2 = [12, 52, 28, 98]
    pdf.table_header(["Ticker", "Tam ad", "Sektor", "Not"], w2)
    for i, (t, n, s) in enumerate(OVERSOLD):
        pdf.table_row([t, n, s, "Limit emir bolgesi — bounce sarti yok"], w2, fill=i % 2 == 0)
    pdf.ln(2)
    pdf.body_text("Toplam 118 hisse oversold (523 icinden).")

    pdf.section_title("SENIN HISSELER — USA")
    for t, n, s, p, note in PORTFOLIO:
        pdf.stock_block(t, n, s, p, note)

    pdf.section_title("EU PORTFOY — DEGIRO (AMSTERDAM)")
    for t, n, s, p, note in EU_PORTFOLIO:
        pdf.stock_block(t, n, s, p, note)
    w3 = [14, 14, 14, 14, 144]
    pdf.table_header(["", "DSFIR", "SIFG", "", "Aksiyon"], w3)
    pdf.table_row(["Durum", "Karda", "Zararda", "", "—"], w3, fill=True)
    pdf.table_row(["Islem", "Satis limiti", "Stop bekle", "EUR 3,75", "Yeni alim yok"], w3)
    pdf.ln(2)

    pdf.section_title("BUGUN NEYE BAK")
    pdf.bullet("Acilis gap (USA) — portfolyodaki RKLB ve ASTS; stop seviyeleri aktif.")
    pdf.bullet("VLO / Valero Energy — sistemin tek BUY'su.")
    pdf.bullet("ISRG — kaliteli limit; ORCL daha riskli.")
    pdf.bullet("DSFIR — direnc bandinda kar realize et; SIFG — stop EUR 3,75, panik satis yok.")

    pdf.section_title("NOT")
    pdf.body_text(
        "RKLB ve ASTS portfolyode (USA pipeline 523). DSFIR ve SIFG DeGiro Amsterdam.\n"
        "Bu belge yatirim tavsiyesi degildir."
    )

    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"USA_PreMarket_{DATA_DATE_USA.replace(' ', '_')}.pdf"
    pdf.output(str(out))
    return out


if __name__ == "__main__":
    path = build_pdf()
    print(f"PDF olusturuldu: {path}")
