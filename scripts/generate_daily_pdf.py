#!/usr/bin/env python3
"""Generate daily portfolio evaluation PDF."""

import shutil
from datetime import date
from pathlib import Path

from fpdf import FPDF

REPORTS = Path(__file__).resolve().parent.parent / "reports"
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

DATA_US = "13 Temmuz 2026"
DATA_EU = "10 Temmuz 2026"


class DailyPDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 11)
        self.set_text_color(40, 40, 40)
        self.cell(0, 8, "Investment Radar - Gunluk Portfoy Degerlendirmesi", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Arial", "", 8)
        self.set_text_color(100, 100, 100)
        self.cell(
            0, 5,
            f"Tarih: 14 Temmuz 2026  |  US veri: {DATA_US}  |  EU veri: {DATA_EU}  |  Yatirim tavsiyesi degildir",
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
        self.set_fill_color(248, 249, 250) if fill else self.set_fill_color(255, 255, 255)
        max_h = 6
        x0, y0 = self.get_x(), self.get_y()
        for i, col in enumerate(cols):
            self.set_xy(x0 + sum(widths[:i]), y0)
            lines = self.multi_cell(widths[i], 4, str(col), border=0, dry_run=True, output="LINES")
            max_h = max(max_h, len(lines) * 4)
        for i, col in enumerate(cols):
            x = x0 + sum(widths[:i])
            self.rect(x, y0, widths[i], max_h)
            self.set_xy(x, y0)
            self.multi_cell(widths[i], 4, str(col), border=0, fill=fill)
            self.set_xy(x + widths[i], y0)
        self.set_xy(x0, y0 + max_h)


def build_pdf():
    pdf = DailyPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("Arial", "", FONT_PATH)
    pdf.add_font("Arial", "B", FONT_BOLD)
    pdf.add_page()

    pdf.section_title("BUGUNUN OZETI")
    pdf.body_text(
        "Gunun hikayesi: RISK-OFF — SPY -%0,8, QQQ -%1,9. Spekülatif portfoy sert satis yedi.\n"
        "ACIL: RKLB stop $78,50 kirildi ($76,73) -> 6 lot SAT\n"
        "KRITIK: ASTS $67,58 — $66 stop'a $1,58 kaldi\n"
        "FIRSAT: ORCL $131,54 — limit $137 ALTINDA, Stoch 0 -> bugun limit koy/dolar"
    )

    pdf.section_title("MAKRO")
    w = [18, 22, 16, 14, 14, 14, 96]
    pdf.table_header(["Sembol", "Fiyat", "Gun", "RSI", "Stoch", "21g", "Yorum"], w)
    for r in [
        ["SPY", "$749,17", "-%0,8", "55", "84", "+%4", "Piyasa yuksek ama bugun satis"],
        ["QQQ", "$711,74", "-%1,9", "48", "30", "+%3", "Tech/growth daha cok ezildi"],
        ["UUP", "$28,50", "+%0,4", "66", "79", "+%2", "Dolar gucleniyor — risk-off"],
    ]:
        pdf.table_row(r, w)
    pdf.ln(3)

    pdf.section_title("MEVCUT POZISYONLAR")
    w2 = [16, 40, 10, 16, 16, 12, 14, 66]
    pdf.table_header(["Ticker", "Tam Isim", "Lot", "Giris", "Simdi", "P/L", "Stoch", "Bugun Aksiyon"], w2)
    holdings = [
        ["RKLB", "Rocket Lab Corporation", "6", "$92,66", "$76,73", "-%17", "4", "ACIL SAT — stop $78,50 kirildi"],
        ["ASTS", "AST SpaceMobile, Inc.", "7", "$73,83", "$67,58", "-%8,5", "14", "DIKKAT — stop $66 ($1,58 kaldi)"],
        ["INTC", "Intel Corporation", "5", "$137,80", "$103,12", "-%25", "3", "TUT — stop $98, earnings 23 Tem"],
        ["DSFIR", "DSM-Firmenich AG", "?", "EUR 72,50", "EUR 83,48*", "+%15", "—", "SAT limit EUR 85-86 (%30)"],
        ["SIFG", "Sif Holding N.V.", "?", "EUR 8,20", "EUR 4,28*", "-%48", "—", "TUT — stop EUR 3,75"],
    ]
    for i, r in enumerate(holdings):
        pdf.table_row(r, w2, fill=i % 2 == 0)
    pdf.body_text("* EU fiyatlari 10 Temmuz kapanisi")
    pdf.ln(2)

    pdf.section_title("BUGUN AKSİYON ONCELIKLERI")
    w3 = [12, 16, 40, 12, 22, 88]
    pdf.table_header(["#", "Tip", "Ticker", "Lot", "Limit/Stop", "Neden"], w3)
    actions = [
        ["1", "SAT", "RKLB", "6", "~$76,73", "Stop $78,50 kirildi — plana gore sat"],
        ["2", "AL-limit", "ORCL", "3", "$137", "Stoch 0, RSI 27 — limit altinda, bugun dolar"],
        ["3", "KONTROL", "ASTS", "7", "Stop $66", "Sadece $1,58 mesafe — stop aktif tut"],
        ["4", "KONTROL", "INTC", "5", "Stop $98", "Earnings oncesi panik satis yok"],
        ["5", "KAR AL", "DSFIR", "%30", "EUR 85-86", "+%15 karda realizasyon limiti"],
        ["6", "BEKLE", "VHYL/NUKL/4GLD/DFEN", "—", "Limitler", "Henuz dolmadi — sabir"],
        ["7", "BEKLE", "ISRG", "1", "$400", "Simdi $407 — %1,8 uzakta"],
    ]
    for i, r in enumerate(actions):
        pdf.table_row(r, w3, fill=i % 2 == 0)
    pdf.ln(3)

    pdf.add_page()
    pdf.section_title("LIMIT EMIRLERI — BUGUN DURUM (HIBRIT EUR 3.000)")
    w4 = [14, 38, 18, 18, 18, 14, 70]
    pdf.table_header(["Ticker", "Tam Isim", "Limit", "Son Fiyat", "Durum", "Stoch", "Bugun"], w4)
    limits = [
        ["ORCL", "Oracle Corporation", "$137,00", "$131,54", "LIMIT ALTI", "0", "BUGUN KOY — dolabilir"],
        ["ISRG", "Intuitive Surgical", "$400,00", "$407,12", "+%1,8 uzak", "21", "Limit $400'de bekle"],
        ["VHYL", "Vanguard FTSE High Div Yield", "EUR 78,10", "EUR 79,88*", "+%2,3 uzak", "—", "Bekle"],
        ["NUKL", "VanEck Uranium UCITS ETF", "EUR 43,90", "EUR 45,92*", "+%4,6 uzak", "—", "Bekle"],
        ["4GLD", "Xetra-Gold ETC", "EUR 113,20", "EUR 115,43*", "+%2,0 uzak", "—", "Bekle"],
        ["DFEN", "VanEck Defense UCITS ETF", "EUR 48,50", "EUR 51,13*", "+%5,4 uzak", "—", "Bekle"],
        ["NAKIT", "Bekleyen nakit", "—", "EUR 200", "Tutuluyor", "—", "Yatirim disi"],
    ]
    for i, r in enumerate(limits):
        pdf.table_row(r, w4, fill=i % 2 == 0)
    pdf.body_text("* EU fiyatlari 10 Temmuz kapanisi\nDUK kaldirildi — EUR 250 VHYL'ye aktarildi")
    pdf.ln(2)

    pdf.section_title("HIBRIT MODEL — LOT TABLOSU")
    w5 = [14, 42, 28, 14, 16, 10, 16, 50]
    pdf.table_header(["Ticker", "Tam Isim", "ISIN", "Tutar", "Limit", "Lot", "Platform", "Not"], w5)
    buys = [
        ["VHYL", "Vanguard FTSE High Div Yield ETF", "IE00B8GKDB10", "EUR 850", "EUR 78,10", "10", "Bux", "DUK payi eklendi"],
        ["DFEN", "VanEck Defense UCITS ETF", "IE000YYE6WK5", "EUR 350", "EUR 48,50", "7", "Bux", "Bekle"],
        ["4GLD", "Xetra-Gold ETC", "DE000A0S9GB0", "EUR 300", "EUR 113,20", "2", "DeGiro", "Bekle"],
        ["ORCL", "Oracle Corporation", "US67066G1040", "EUR 450", "$137,00", "3", "DeGiro", "BUGUN"],
        ["ISRG", "Intuitive Surgical, Inc.", "US46120E6023", "EUR 400", "$400,00", "1", "DeGiro", "Bekle"],
        ["NUKL", "VanEck Uranium UCITS ETF", "IE000M7V94E1", "EUR 450", "EUR 43,90", "10", "Bux", "Bekle"],
    ]
    for i, r in enumerate(buys):
        pdf.table_row(r, w5, fill=i % 2 == 0)
    pdf.ln(3)

    pdf.section_title("STOKASTIK ONE CIKANLAR — YENI FIKIRLER (1 AY BOUNCE)")
    w6 = [12, 36, 14, 12, 12, 12, 12, 74]
    pdf.table_header(["Skor", "Ticker", "Tam Isim", "Fiyat", "Stoch", "RSI", "21g", "Limit / Not"], w6)
    picks = [
        ["80", "ORCL", "Oracle Corporation", "$131,54", "0", "27", "-%34", "$137 limit — planda var"],
        ["72", "CCJ", "Cameco Corporation", "$90,20", "4", "31", "-%5", "$87-90 — NUKL alternatifi"],
        ["47", "LRCX", "Lam Research Corporation", "$329,92", "13", "45", "+%3", "$318-325 — INTC overlap"],
        ["43", "TSM", "Taiwan Semiconductor", "$421,58", "4", "46", "+%3", "$405-415 — foundry"],
        ["43", "DIS", "The Walt Disney Company", "$96,00", "14", "41", "-%2", "$93-96 — tech disi"],
        ["43", "BA", "The Boeing Company", "$215,51", "7", "44", "+%3", "$207-212 — tech disi"],
    ]
    for i, r in enumerate(picks):
        pdf.table_row(r, w6, fill=i % 2 == 0)
    pdf.ln(3)

    pdf.section_title("SATIS / KISALTMA PLANI")
    w7 = [14, 36, 10, 22, 14, 18, 76]
    pdf.table_header(["Ticker", "Tam Isim", "Lot", "Ne Zaman", "Miktar", "Limit", "Neden"], w7)
    sells = [
        ["RKLB", "Rocket Lab Corporation", "6", "BUGUN", "6 lot", "$78,50 stop", "Kirildi — sat"],
        ["DSFIR", "DSM-Firmenich AG", "?", "Bu hafta", "%30", "EUR 85-86", "Kar realizasyonu"],
        ["DSFIR", "DSM-Firmenich AG", "?", "Sonraki", "%25", "EUR 87-89", "Kademeli kar"],
        ["INTC", "Intel Corporation", "5", "23 Tem sonra", "2-5 lot", "$125 / $105", "Earnings sonrasi"],
        ["ASTS", "AST SpaceMobile", "7", "Stop $66", "7 lot", "$66", "Kirilirsa sat"],
        ["SIFG", "Sif Holding N.V.", "?", "Stop", "Tumu", "EUR 3,75", "Zarar kontrolu"],
    ]
    for i, r in enumerate(sells):
        pdf.table_row(r, w7, fill=i % 2 == 0)
    pdf.ln(3)

    pdf.section_title("TAKVIM")
    w8 = [28, 50, 112]
    pdf.table_header(["Tarih", "Olay", "Etkilenen"], w8)
    for r in [
        ["14 Tem Sal", "RKLB stop / ORCL limit", "RKLB sat, ORCL al"],
        ["15-18 Tem", "ASTS $66 stop testi", "ASTS"],
        ["23 Tem", "INTC Q2 earnings", "INTC — en buyuk katalizor"],
        ["6 Agu", "RKLB Q2", "Satildiysa gecersiz"],
        ["10 Agu", "ASTS Q2", "ASTS"],
    ]:
        pdf.table_row(r, w8)
    pdf.ln(3)

    pdf.section_title("BUGUN CHECKLIST")
    pdf.body_text(
        "[ ] RKLB 6 lot SAT (stop $78,50 kirildi)\n"
        "[ ] DeGiro: ORCL 3 adet limit $137 koy\n"
        "[ ] ASTS stop $66 aktif mi kontrol et\n"
        "[ ] INTC stop $98 (haftalik) kontrol et\n"
        "[ ] DSFIR satis limiti EUR 85-86 koy\n"
        "[ ] Bux: VHYL 10 @ EUR 78,10 | DFEN 7 @ EUR 48,50 | NUKL 10 @ EUR 43,90\n"
        "[ ] DeGiro: 4GLD 2 @ EUR 113,20 | ISRG 1 @ $400\n"
        "[ ] EUR 200 nakit — tut\n"
        "[ ] Limit dolanlari onayla, dolmayanlari degistirme"
    )

    pdf.section_title("TEK CUMLE")
    pdf.body_text(
        "Bugun: RKLB SAT (stop kirildi), ORCL $137 limit koy (Stoch 0), "
        "ASTS $66 stop kontrol; diger limitlere dokunma."
    )

    pdf.section_title("UYARI")
    pdf.body_text(
        "Bu belge yatirim tavsiyesi degildir. Tum kararlar size aittir.\n"
        f"US fiyatlar: {DATA_US} | EU fiyatlar: {DATA_EU} Yahoo Finance.\n"
        "DSFIR ve SIFG lot sayilari bilinmediginden '?' isaretlidir."
    )

    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"Portfoy_Gunluk_{date.today().isoformat()}.pdf"
    stable = REPORTS / "Portfoy_Gunluk_Degerlendirme.pdf"
    pdf.output(str(out))
    shutil.copy(out, stable)
    return out, stable


if __name__ == "__main__":
    path, stable = build_pdf()
    print(f"PDF olusturuldu: {path}")
    print(f"PDF kopya: {stable}")
