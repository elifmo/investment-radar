#!/usr/bin/env python3
"""Generate weekly portfolio action summary PDF."""

import sys
from datetime import date
from pathlib import Path

import yaml
from fpdf import FPDF

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from sync_portfolio import build_trade_list, compute_position, load_portfolio

OUTPUT = ROOT / "reports" / "Portfoy_Haftalik_Aksiyon_Ozeti.pdf"
PORTFOLIO_CONFIG = ROOT / "config" / "portfolio.yaml"

# macOS Arial supports Turkish chars
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


class PortfolioPDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 11)
        self.set_text_color(40, 40, 40)
        self.cell(0, 8, "Investment Radar - Haftalik Portfoy Aksiyon Ozeti", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Arial", "", 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, f"Olusturulma: {date.today().strftime('%d %B %Y')}  |  Yatirim tavsiyesi degildir", align="C", new_x="LMARGIN", new_y="NEXT")
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
        self.set_font("Arial", "", 8)
        self.set_text_color(50, 50, 50)
        self.multi_cell(0, 4.5, text)
        self.ln(1)

    def table_header(self, cols, widths):
        self.set_font("Arial", "B", 7)
        self.set_fill_color(50, 80, 120)
        self.set_text_color(255, 255, 255)
        for i, col in enumerate(cols):
            self.cell(widths[i], 6, col, border=1, fill=True)
        self.ln()

    def table_row(self, cols, widths, fill=False):
        self.set_font("Arial", "", 6.5)
        self.set_text_color(40, 40, 40)
        if fill:
            self.set_fill_color(248, 249, 250)
        else:
            self.set_fill_color(255, 255, 255)
        max_h = 6
        x0, y0 = self.get_x(), self.get_y()
        lines_per_cell = []
        for i, col in enumerate(cols):
            self.set_xy(x0 + sum(widths[:i]), y0)
            lines = self.multi_cell(widths[i], 4, str(col), border=0, dry_run=True, output="LINES")
            lines_per_cell.append(lines)
            max_h = max(max_h, len(lines) * 4)
        for i, col in enumerate(cols):
            x = x0 + sum(widths[:i])
            self.rect(x, y0, widths[i], max_h)
            self.set_xy(x, y0)
            self.multi_cell(widths[i], 4, str(col), border=0, fill=fill)
            self.set_xy(x + widths[i], y0)
        self.set_xy(x0, y0 + max_h)


def _fmt_price(ticker: str, price: float) -> str:
    if ticker == "DSFIR":
        return f"EUR {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"${price:,.2f}"


def load_holdings_from_yaml() -> list[dict]:
    """Return holdings with computed qty, avg_cost, exit from portfolio.yaml."""
    holdings, trades_map = load_portfolio(PORTFOLIO_CONFIG)
    rows = []
    for h in holdings:
        ticker = h["ticker"]
        trades = build_trade_list(ticker, trades_map)
        pos = compute_position(trades)
        if pos["remaining_qty"] <= 0:
            continue
        rows.append({
            "ticker": ticker,
            "name": h.get("name", ticker),
            "qty": int(pos["remaining_qty"]),
            "avg_cost": pos["avg_cost"],
            "exit": h.get("exit_condition", "—"),
            "platform": h.get("platform", "DeGiro"),
        })
    return rows


def build_pdf():
    pdf = PortfolioPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("Arial", "", FONT_PATH)
    pdf.add_font("Arial", "B", FONT_BOLD)
    pdf.add_page()

    # --- OVERVIEW ---
    pdf.section_title("OZET")
    pdf.body_text(
        "Hafta: 14-18 Temmuz 2026\n"
        "Yeni para (Hibrit model): EUR 3.000 - LIMIT emir, market buy yok\n"
        "Makro: SPY zirvede (Stoch ~99) - bu hafta sadece limit koy, dolmayanlari gelecek haftaya birak\n"
        "Hibrit dagilim: VHYL (EUR 850) + DFEN + 4GLD + ORCL + ISRG + NUKL + EUR 200 nakit\n"
        "Guncelleme: DUK kaldirildi — EUR 250 VHYL'ye aktarildi, EUR 200 nakit tutuluyor"
    )

    # --- EXISTING POSITIONS (from config/portfolio.yaml) ---
    pdf.section_title("MEVCUT POZISYONLAR - BU HAFTA NE YAP?")
    w = [22, 48, 12, 18, 16, 14, 60]
    pdf.table_header(["Ticker", "Tam Isim", "Lot", "Giris", "Simdi", "P/L", "Aksiyon / Stop"], w)
    holdings = load_holdings_from_yaml()
    rows = []
    for h in holdings:
        entry = _fmt_price(h["ticker"], h["avg_cost"])
        rows.append([
            h["ticker"],
            h["name"],
            str(h["qty"]),
            entry,
            "—",
            "—",
            h["exit"][:55] if h.get("exit") else "—",
        ])
    if not rows:
        rows = [["—", "portfolio.yaml bos", "—", "—", "—", "—", "sync_portfolio.py calistir"]]
    for i, r in enumerate(rows):
        pdf.table_row(r, w, fill=i % 2 == 0)
    pdf.ln(3)

    # --- CALENDAR ---
    pdf.section_title("HAFTALIK TAKVIM")
    w2 = [28, 40, 122]
    pdf.table_header(["Tarih", "Olay", "Aksiyon"], w2)
    cal = [
        ["14 Tem Paz", "Hafta basi", "6 yeni limit emir koy + DSFIR satis limiti"],
        ["15-18 Tem", "RKLB $80 testi", "$78,50 stop aktif tut"],
        ["23 Tem Car", "INTC Q2 earnings", "Oncesi satis yok; sonrasi planla"],
        ["6 Agu", "RKLB Q2", "Bilanco sonrasi karar"],
        ["10 Agu", "ASTS Q2", "Bilanco sonrasi karar"],
    ]
    for i, r in enumerate(cal):
        pdf.table_row(r, w2, fill=i % 2 == 0)
    pdf.ln(3)

    # --- NEW BUYS ---
    pdf.add_page()
    pdf.section_title("YENI ALIMLAR - HIBRIT MODEL (EUR 3.000)")
    w3 = [16, 42, 28, 10, 14, 18, 10, 18, 14]
    pdf.table_header(["Ticker", "Tam Isim", "ISIN", "Vade", "Tutar", "Limit", "Lot", "Platform", "Durum"], w3)
    buys = [
        ["VHYL", "Vanguard FTSE High Div Yield ETF", "IE00B8GKDB10", "3 ay", "EUR 850", "EUR 78,10", "10", "Bux", "Limit koy"],
        ["DFEN", "VanEck Defense UCITS ETF", "IE000YYE6WK5", "3 ay", "EUR 350", "EUR 48,50", "7", "Bux", "Limit koy"],
        ["4GLD", "Xetra-Gold ETC", "DE000A0S9GB0", "3 ay", "EUR 300", "EUR 113,20", "2", "DeGiro", "Limit koy"],
        ["ORCL", "Oracle Corporation", "US67066G1040", "1 ay", "EUR 450", "$137,00", "3", "DeGiro", "Limit koy"],
        ["ISRG", "Intuitive Surgical, Inc.", "US46120E6023", "1 ay", "EUR 400", "$400,00", "1", "DeGiro", "Limit koy"],
        ["NUKL", "VanEck Uranium UCITS ETF", "IE000M7V94E1", "1 ay", "EUR 450", "EUR 43,90", "10", "Bux", "Limit koy"],
        ["NAKIT", "—", "—", "—", "EUR 200", "—", "—", "—", "Simdilik tut"],
    ]
    for i, r in enumerate(buys):
        pdf.table_row(r, w3, fill=i % 2 == 0)
    pdf.ln(3)

    pdf.section_title("LOT HESABI")
    pdf.body_text(
        "VHYL:  EUR 850 / EUR 78,10  = 10 stuk  (EUR 781,00)  [DUK'tan +EUR 250 aktarildi]\n"
        "DFEN:  EUR 350 / EUR 48,50  = 7 stuk   (EUR 339,50)\n"
        "4GLD:  EUR 300 / EUR 113,20 = 2 stuk   (EUR 226,40)\n"
        "ORCL:  EUR 450 / $137       = 3 adet   (~EUR 374)\n"
        "ISRG:  EUR 400 / $400       = 1 adet   (~EUR 364)\n"
        "NUKL:  EUR 450 / EUR 43,90  = 10 stuk  (EUR 439,00)\n"
        "NAKIT: EUR 200 simdilik tutuluyor (DUK kaldirildi — kalan miktar)\n"
        "Toplam: EUR 2.800 limit emir + EUR 200 nakit = EUR 3.000"
    )

    # --- SELLS ---
    pdf.section_title("KISALTMA / SATIS PLANI")
    w4 = [16, 38, 10, 22, 12, 20, 72]
    pdf.table_header(["Ticker", "Tam Isim", "Lot", "Ne Zaman", "Kac Lot", "Limit", "Neden"], w4)
    sells = [
        ["DSFIR", "DSM-Firmenich AG", "?", "Bu hafta", "%30", "EUR 85-86", "+%15 karda realizasyon"],
        ["DSFIR", "DSM-Firmenich AG", "?", "Sonraki hafta", "%25", "EUR 87-89", "Kademeli kar alma"],
        ["INTC", "Intel Corporation", str(next((h["qty"] for h in holdings if h["ticker"] == "INTC"), "—")), "23 Tem sonrasi (iyi)", "2 lot", "$125-128", "Zarari kis"],
        ["INTC", "Intel Corporation", str(next((h["qty"] for h in holdings if h["ticker"] == "INTC"), "—")), "23 Tem sonrasi (kotu)", "tumu", "$105", "Stop mantigi"],
        ["RKLB", "Rocket Lab Corporation", str(next((h["qty"] for h in holdings if h["ticker"] == "RKLB"), "—")), "Stop tetiklenirse", "tumu", "$78,50", "Destek kirilimi"],
        ["SIFG", "Sif Holding N.V.", "?", "Stop tetiklenirse", "Tumu", "EUR 3,75", "Zarar kontrolu"],
        ["SIFG", "Sif Holding N.V.", "?", "Toparlanirsa", "%30", "EUR 5,50", "Kismi cikis"],
    ]
    for i, r in enumerate(sells):
        pdf.table_row(r, w4, fill=i % 2 == 0)
    pdf.ln(3)

    # --- FULL PORTFOLIO ---
    pdf.add_page()
    pdf.section_title("TUM PORTFOY - MEVCUT + YENI")
    w5 = [14, 16, 42, 10, 16, 92]
    pdf.table_header(["Durum", "Ticker", "Tam Isim", "Lot", "Platform", "Aksiyon Bu Hafta"], w5)
    all_pos = []
    for h in holdings:
        all_pos.append([
            "Mevcut", h["ticker"], h["name"], str(h["qty"]), h["platform"],
            (h.get("exit") or "—")[:40],
        ])
    all_pos.extend([
        ["Yeni", "VHYL", "Vanguard FTSE High Div Yield ETF", "10", "Bux", "AL limit EUR 78,10"],
        ["Yeni", "DFEN", "VanEck Defense UCITS ETF", "7", "Bux", "AL limit EUR 48,50"],
        ["Yeni", "4GLD", "Xetra-Gold ETC", "2", "DeGiro", "AL limit EUR 113,20"],
        ["Yeni", "ORCL", "Oracle Corporation", "3", "DeGiro", "AL limit $137"],
        ["Yeni", "ISRG", "Intuitive Surgical", "1", "DeGiro", "AL limit $400"],
        ["Yeni", "NUKL", "VanEck Uranium UCITS ETF", "10", "Bux", "AL limit EUR 43,90"],
        ["Nakit", "—", "Bekleyen nakit", "—", "—", "EUR 200 simdilik tut"],
    ])
    for i, r in enumerate(all_pos):
        pdf.table_row(r, w5, fill=i % 2 == 0)
    pdf.ln(3)

    # --- CHECKLIST ---
    pdf.section_title("HAFTALIK CHECKLIST")
    pdf.body_text(
        "PAZARTESI 14 TEMMUZ\n"
        "  [ ] Bux: VHYL 10 @ EUR 78,10 | DFEN 7 @ EUR 48,50 | NUKL 10 @ EUR 43,90\n"
        "  [ ] DeGiro: 4GLD 2 @ EUR 113,20 | ORCL 3 @ $137 | ISRG 1 @ $400\n"
        "  [ ] DeGiro: DSFIR satis limiti EUR 85-86 (%30 lot)\n"
        "  [ ] EUR 200 nakit — simdilik yatirim disi tut\n\n"
        "SALI - CUMA\n"
        "  [ ] RKLB $80 destek - $78,50 stop aktif mi kontrol\n"
        "  [ ] Limit dolanlari onayla, dolmayanlari degistirme (sabirli kal)\n"
        "  [ ] INTC 23 Tem earnings plani hazirla\n\n"
        "GELECEK HAFTA\n"
        "  [ ] EUR 200 nakit -> piyasa duzeltmesinde VHYL veya yeni limit\n"
        "  [ ] DSFIR 2. satis limiti EUR 87-89 (1. satis dolmussa)"
    )

    # --- BALANCE ---
    pdf.section_title("PORTFOY DENGESI - HEDEF")
    w6 = [50, 40, 40, 60]
    pdf.table_header(["Kova", "Su An (Mevcut)", "Hibrit Sonrasi", "Aciklama"], w6)
    bal = [
        ["Spekulatif (INTC/ASTS/RKLB)", "~%60+", "~%40", "Yeni para ile seyrelir"],
        ["Cekirdek (VHYL)", "%0", "~%28", "Temettu + stabilite (DUK payi eklendi)"],
        ["Defansif (4GLD/VHYL)", "%0", "~%18", "ASTS/RKLB hedge"],
        ["Nakit (beklemede)", "%0", "~%7", "EUR 200 — DUK yerine"],
        ["Tema (DFEN/NUKL)", "%0", "~%15", "Savunma + uranyum"],
        ["Bounce 1ay (ORCL/ISRG)", "%0", "~%15", "Stokastik oversold"],
        ["Karda (DSFIR)", "Var", "Kuculur", "Satisla realizasyon"],
        ["Zararda (SIFG)", "Var", "Stop veya bekle", "Yeni alim yok"],
    ]
    for i, r in enumerate(bal):
        pdf.table_row(r, w6, fill=i % 2 == 0)
    pdf.ln(3)

    pdf.section_title("TEK CUMLE")
    pdf.body_text(
        "Bu hafta: 6 yeni limit emir koy (DUK yok, VHYL 10 stuk @ EUR 78,10), EUR 200 nakit tut, "
        "DSFIR'de %30 kar satisi limiti koy; RKLB stop kontrol; INTC earnings 23 Tem'e kadar bekle."
    )

    pdf.section_title("UYARI")
    pdf.body_text(
        "Bu belge yatirim tavsiyesi degildir. Tum kararlar size aittir.\n"
        "Fiyatlar portfolio.yaml ortalama maliyetine dayanir; guncel fiyat icin dashboard kullanin.\n"
        "Kaynak: config/portfolio.yaml — My Radar ile sync_portfolio.py ile senkronize edilir."
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUTPUT))
    return OUTPUT


if __name__ == "__main__":
    path = build_pdf()
    print(f"PDF olusturuldu: {path}")
