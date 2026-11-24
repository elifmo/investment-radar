# Pending Iterations

**Last updated:** July 2026

> **Partially addressed:** ITER-01 quality-dip use case is partially covered by
> `oversold_watch` (Stoch + RSI, no bounce required) and Opportunities → Contrarian.
> Full two-collection split is still pending.

---

## ITER-01: Two-Pipeline Architecture (Momentum + Quality Dip)

**Status:** Pending — implement when user says "yap"

### Problem
Current pipeline mixes short-term momentum signals (volume spike, EMA crossover)
with long-term quality filters (Grade A/B, sector long-term) in a single candidates list.
This creates conflicting logic and unclear signals.

### Solution: two separate pipelines, two separate Firestore collections

---

**Pipeline 1 — Momentum**
*"Has movement today, fast entry"*

Filter order:
1. Volume spike + price move (existing event filter — keep as-is)
2. RS Rating ≥ 70
3. Sector short-term: LEADING or IMPROVING
4. Quality ≥ C (just exclude D)

Position sizing: Small-medium, tight stop-loss
Hold time: 2–8 weeks
Firestore: `momentum_candidates`

---

**Pipeline 2 — Quality Dip**
*"Solid company, waiting for the right price"*

Filter order:
1. Quality Grade A or B (scan full universe, no event filter needed)
2. 30-day drop ≥ 15%
3. Sector long-term: LEADING or IMPROVING
4. Enter when Macro = RISK_ON

Position sizing: Larger, wider stop-loss
Hold time: 3–12 months
Firestore: `quality_dip_candidates`

---

### Files to change
- `src/pipeline.py` — split run_market() into run_momentum() + run_quality_dip()
- `src/firebase_writer.py` — add write functions for new collections
- `frontend/index.html` — USA tab: two sub-lists or two sub-tabs

### Files unchanged
- All layer files (quality_grade, rs_rating, sector_rotation, macro_regime, earnings_calendar)
- Decision engine (reuse with different thresholds per pipeline)

---

## ITER-02: PAP Filtresi + SPY Regime Entegrasyonu

**Status:** Pending — implement when user says "yap"  
**Backtest:** backtest/BACKTEST_OZET.md (v1–v5, 2 yıl günlük data)

### Problem
Mevcut filtre mantığı hacim spike ve EMA sinyallerine dayanıyor. Fiyatın "değer alanında" olup olmadığını (Price Acceptance Profile) ve piyasa toparlanma süreçlerindeki erken fırsatları görmüyor.

### Backtest Bulguları

**BIST:** PAP Accepted/Edge filtresi ile 80.9% hit rate, +5.64% ort. getiri (sinyal bazlı çıkış).  
Getiri 90 güne kadar artıyor (+19.50%) → BIST'te trend başlangıcı sinyali.  
SRP indikatörü BIST'te ek filtre değeri taşımıyor — kaldırıldı.

**USA:** PAP Accepted/Edge ile 61.9% hit rate, +2.27% ort. getiri.  
20 günde tepe (+5.12%), sonra geri dönüyor → kısa bounce sinyali.  
SPY Rejected + PAP skoru yükseliyorken bireysel hisseler baseline'dan +2.6% fazla getiri → erken alım fırsatı.

### Çözüm

**Yeni modül: `src/pap_indicator.py`**
- 320 bar lookback, 26 satır histogram, %70 value area
- Çıktı: poc, vah, val, acceptance_state (Accepted/Edge/Rejected), acceptance_score, rotation (up/down/stable)

**BIST değişiklikleri:**
- Filtre: PAP Accepted veya Edge (hard gate, SRP yok)
- Hisse listesi: ARCLK ve SASA çıkar; VAKBN, AKBNK, FROTO, GARAN, ISCTR, EREGL, KCHOL, THYAO, PETKM, TTKOM, BIMAS, MGROS, PETKM, TCELL kalır (20 hisse)
- Tutma: 60-90 gün (trend)
- Çıkış sinyali: PAP Rejected'a döndüğünde

**USA değişiklikleri:**
- Filtre: bireysel PAP Accepted veya Edge
- SRP: kaldır
- SPY PAP state → macro_regime katmanına ekle, 3 durum:
  - SPY Accepted/Edge → skor +5
  - SPY Rejected + skor düşüyor → skor -10 (giriş yapma)
  - SPY Rejected + skor yükseliyor → "erken fırsat" flag'i, 10 günlük tutma
- Tutma: 20 gün (bounce)
- Çıkış sinyali: PAP Rejected'a döndüğünde

**Dashboard değişiklikleri:**
- Candidate kartına PAP state göster (Accepted / Edge / Rejected)
- SPY PAP durumunu macro banner'a ekle

### Dosyalar

| Dosya | Değişiklik |
|-------|------------|
| `src/pap_indicator.py` | Yeni — PAP hesaplama |
| `src/event_filter.py` | PAP state kontrolü ekle |
| `src/detailed_scorer.py` | PAP state'e göre skor ayarı |
| `src/layers/macro_regime.py` | SPY PAP state ekle |
| `src/decision_engine.py` | SPY Rejected+rising = erken sinyal |
| `src/firebase_writer.py` | pap_state, pap_score, pap_poc/vah/val alanları |
| `config/bist_tickers.yaml` | ARCLK/SASA çıkar |
| `frontend/bist/index.html` | PAP state badge'i |
| `frontend/usa/index.html` | PAP state badge'i + SPY regime |

### Notlar
- PAP 320 bar lookback gerektiriyor → ~15 aylık günlük data şart (tüm mevcut BIST hisseleri için geçerli)
- SRP indikatörü backtest sonuçlarına göre eklenmeyecek (BIST'te değer katmıyor, USA'da zararlı)
- Backtest detayları: backtest/srp_pap_backtest_v1..v5.py + .md
