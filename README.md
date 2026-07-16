# Investment Radar

Günlük hisse tarama ve sinyal sistemi. Pipeline her gün BIST ve USA hisselerini analiz edip skorlar, dashboard'da gösterir.

---

## Hisse Evreni

**Son güncelleme: Temmuz 2026** — Toplam **616 hisse** (USA pipeline: **523** · BIST: **93**)

---

### 🇺🇸 USA — Pipeline tarama evreni (523 hisse)

Varsayılan mod: `config/factors.yaml` → `scan.universe: sp500_nasdaq`

| Kaynak | Adet | Dosya |
|--------|------|-------|
| S&P 500 | 503 | `config/sp500.yaml` |
| Nasdaq-100 (SP500 dışı) | 13 | `config/nasdaq100.yaml` |
| Ekstra izleme listesi | 7 | `config/universe.yaml` |
| **Toplam (dedupe)** | **523** | `src/usa_universe.py` |

**Nasdaq-100 (SP500’de olmayanlar):** ALNY, ARM, ASML, CCEP, FER, INSM, MELI, MSTR, PDD, SHOP, TEAM, TRI, ZS

**Ekstra izleme (uranium / ADR / space):** CCJ, LEU, OKLO, SNOW, TSM, RKLB, ASTS

Candidates, Oversold Watch ve RS hesapları bu **523 hisseyi** tarar. Sector heatmap ayrıca tam S&P 500 (503) kullanır.

`scan.universe` modları: `watchlist` (177) · `sp500` (503) · `sp500_nasdaq` (523, varsayılan)

Listeleri güncellemek:
```bash
python3 scripts/refresh_sp500_universe.py
python3 scripts/refresh_nasdaq100_universe.py
```

---

### 🇺🇸 USA — Öncelikli izleme listesi (177 hisse)

`config/universe.yaml` içindeki el ile seçilmiş liste. Pipeline’da `sp500_nasdaq` modunda bunların çoğu zaten S&P 500’de; yalnızca yukarıdaki **7 ekstra** ticker birleşik evrene eklenir.

| Sektör | Hisseler |
|--------|----------|
| **Popular & Fintech** (5) | COIN, HOOD, CRWD, SNOW, DDOG |
| **AI Altyapı & Ağ** (13) | ARM, MRVL, SMCI, TSM, MPWR, ON, WDC, STX, ANET, CSCO, DELL, DLR, PLTR |
| **Tech** (30) | AAPL, MSFT, NVDA, GOOGL, GOOG, META, AMZN, TSLA, AVGO, AMD, ORCL, CRM, ADBE, INTC, QCOM, TXN, AMAT, LRCX, KLAC, MCHP, NXPI, ADI, SNPS, CDNS, MU, FTNT, PANW, NOW, WDAY, INTU |
| **Finance** (19) | JPM, BAC, GS, MS, V, MA, AXP, BLK, SPGI, MCO, CME, ICE, CB, PGR, AIG, AON, USB, C, KKR |
| **Healthcare** (22) | UNH, JNJ, LLY, ABBV, MRK, TMO, DHR, ABT, BMY, AMGN, GILD, VRTX, ISRG, SYK, BSX, BDX, ELV, CI, HCA, DXCM, IDXX, EW |
| **Consumer** (24) | WMT, COST, HD, MCD, SBUX, PG, PEP, KO, PM, MO, MDLZ, KMB, CL, KR, TJX, ORLY, AZO, MAR, BKNG, ABNB, UBER, LOW, MNST, STZ |
| **Industrial** (21) | CAT, HON, RTX, GE, DE, ETN, EMR, ITW, PH, CARR, TDG, GD, NSC, CSX, UNP, PCAR, CTAS, FAST, MSI, ROP, TT |
| **Enerji & Nükleer** (12) | XOM, CVX, SLB, EOG, VLO, OKE, FCX, CEG, VST, CCJ, OKLO, LEU |
| **Gayrimenkul & Utilities** (10) | NEE, DUK, SO, EXC, PCG, PLD, EQIX, SPG, PSA, WELL |
| **İletişim** (4) | T, NFLX, APH, TEL |
| **Diğer** (15) | LIN, ACN, IBM, CPRT, WM, ECL, SHW, ZTS, CTVA, F, GM, GEHC, PAYX, A, BRK-B |

---

### 🇹🇷 BIST — 93 hisse

| Grup | Hisseler |
|------|----------|
| **Bankacılık** | AKBNK, GARAN, HALKB, ISCTR, SKBNK, VAKBN, YKBNK |
| **Holding & Yatırım** | DOHOL, KCHOL, SAHOL, TKFEN, AGHOL, GLYHO, NTHOL |
| **Sanayi & Üretim** | ARCLK, ASELS, EREGL, FROTO, KRDMD, OTKAR, TOASO, TTRAK, VESTL, BRISA, JANTS, EGEEN |
| **Enerji & Doğal Kaynaklar** | AKSEN, ASTOR, CWENE, ENJSA, ENKAI, ODAS, PETKM, TUPRS, AYDEM, IPEKE, SMRTG, EUPWR |
| **Madencilik** | KOZAL, KOZAA, ISDMR, OYAKC |
| **Telekomünikasyon & Teknoloji** | KAREL, LOGO, TCELL, TTKOM, NETAS, PENTA, REEDR, TKNSA, KONTR |
| **Perakende & Tüketici** | BIMAS, MGROS, SOKM, ULKER, CCOLA, AEFES, FRIGO, INDES, MAVI, YATAS |
| **Sigorta & Finans** | AKGRT, RAYSG, TURSG |
| **Sağlık** | MPARK |
| **Kimya & Malzeme** | GUBRF, HEKTS, SASA, SISE, AKSA, ALKIM, BAGFS, BUCIM, CEMTS, QUAGR, GESAN |
| **GYO & İnşaat** | EKGYO, ISGYO |
| **Ulaşım & Lojistik** | PGSUS, TAVHL, THYAO, ALARK, DOAS, LIDER, ULUFA |
| **Diğer** | BERA, CIMSA, FENER, FRIGO, KORDS, PARSN, SELEC, TMSN, VESBE |

> **Not:** BIST 100 kompozisyonu 3 ayda bir güncellenir. Güncel resmi liste: [borsaistanbul.com](https://www.borsaistanbul.com) → Endeksler → BIST 100 Bileşenleri

---

## Dokümantasyon

| Dosya | İçerik | Güncellik |
|-------|--------|-----------|
| `README_DOCUMENTATION.md` | Tüm dokümanların indeksi — **buradan başla** | ✅ Tem 2026 |
| `CLAUDE_EN.md` | Sistem mimarisi, pipeline, Firestore, cron | ✅ Tem 2026 |
| `DASHBOARD_DESIGN_EN.md` | Dashboard UI (7 tab) | ✅ Tem 2026 |
| `QUICK_START_DEPLOYMENT_EN.md` | Kurulum, deploy, troubleshooting | ✅ Tem 2026 |
| `CURSOR_QUICK_START_EN.md` | Cursor komut rehberi | 🟡 Kısmen |
| `docs/YAPILACAKLAR_PLANI.md` | Türkçe yol haritası | ✅ Güncel |
| `backtest/BACKTEST_OZET.md` | SRP/PAP backtest özeti | ✅ Güncel |
| `backtest/stoch_candidates_backtest.md` | Stochastic backtest | ✅ Tem 2026 |
