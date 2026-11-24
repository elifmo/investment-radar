# SRP + PAP Backtest — Kapsamlı Özet Rapor

**Analiz Tarihi:** 18 Haziran 2026  
**Test Periyodu:** 8 Haziran 2024 → 18 Haziran 2026 (2 yıl, günlük data)  
**Kullanılan Data:** yfinance günlük OHLCV  
**Test Edilen İndikatörler:** Stop Run Reversal Planner (SRP) + Price Acceptance Profile (PAP)

---

## İNDİKATÖRLER

### Stop Run Reversal Planner (SRP)
Son N bar'ın high/low seviyesinin dışına wick atan ama oraya kapanmayan mumları tespit eder. "Stop avı" olarak adlandırılan bu hareket — piyasa, stop emirlerini tetikleyip geri döner. 0-100 arası puan üretir.

- **Parametreler:** Lookback=34, ATR=14, Volume baseline=34
- **Bullish sinyal:** Fiyat 34 günlük düşüğün altına wick attı, geri kapandı
- **Bearish sinyal:** Fiyat 34 günlük yükseğin üstüne wick attı, geri kapandı
- **Score formülü:** sweepScore×0.22 + closeBackScore×0.22 + confirmScore×0.22 + volumeScore×0.12 + targetRoomScore×0.14 + trendTurnScore×0.08

### Price Acceptance Profile (PAP)
Son 320 günde fiyatın zamanını nerede geçirdiğini ölçer (hacim değil, zaman bazlı). Histogram oluşturur, değer alanını hesaplar.

- **Parametreler:** Lookback=320 bar, 26 satır, %70 value area
- **POC:** En çok zaman geçirilen fiyat seviyesi
- **VAH/VAL:** %70'lik değer alanı üst/alt sınırı
- **Durumlar:**
  - **Accepted** → Fiyat değer alanı içinde (normal, dengeli)
  - **Edge** → Değer alanı sınırında (kritik bölge)
  - **Rejected** → Değer alanı dışında (uzak, riskli)
- **Skor:** 0-100 (acceptance strength + revisit density + rotation alignment)

---

## TEST EDİLEN SENARYOLAR

### V1 — İlk Backtest (5 günlük sabit tutma)
**BIST Hisseleri:** EREGL, TOASO, TUPRS, THYAO, KCHOL  
**USA Hisseleri:** SPY, AAPL, MSFT, NVDA, AMZN, META

| Filtre | Piyasa | Sinyal | Hit Rate | Ort. Getiri |
|--------|--------|--------|----------|-------------|
| Baseline (herhangi SRP) | BIST | 90 | 58.9% | +0.95% |
| PAP Accepted/Edge | BIST | 29 | **75.9%** | **+2.22%** |
| SRP ≥ 66 | BIST | 6 | 66.7% | +3.98% |
| SRP ≥ 70 | BIST | 3 | 66.7% | +4.43% |
| Baseline (herhangi SRP) | USA | 90 | 47.8% | -0.02% |
| SRP ≥ 66 | USA | 6 | 16.7% | **-0.92%** |
| PAP Accepted/Edge | USA | 34 | 52.9% | +0.88% |

**V1 Bulgusu:**
- BIST'te stop avı sinyalleri anlamlı (baseline bile coin-flip'i geçiyor)
- PAP Accepted/Edge en güçlü BIST filtresi
- USA'da SRP işe **yaramıyor** — büyük likit hissede wick sweep devam sinyali

---

### V2 — Sinyal Bazlı Çıkış (PAP Rejected veya ters SRP)
**Çıkış mantığı:** PAP Rejected'a dönünce çık veya ters yönde SRP sinyali gelince çık (max 40 gün)

| Piyasa | Sinyal | Hit Rate | Ort. Getiri | Ort. Tutma |
|--------|--------|----------|-------------|------------|
| BIST | 8 | **87.5%** | **+5.51%** | 14 gün |
| USA | 25 | 68.0% | +3.40% | 25-27 gün |

**Sabit tutma karşılaştırması:**

| Süre | Hit Rate | Ort. Getiri |
|------|----------|-------------|
| 5 gün | 57.6% | +1.29% |
| 10 gün | 66.7% | +3.01% |
| **20 gün** | **75.8%** | **+5.06%** |
| 40 gün | 66.7% | +4.47% |

**V2 Bulgusu:** 20 gün sayısal olarak en verimli. Sinyal bazlı çıkış biraz daha az getiri ama risk yönetimi açısından daha sağlıklı.

---

### V3 — Bounce mu Trend mi? (5-120 günlük getiri eğrisi)

| Tutma | BIST Ort. | USA Ort. |
|-------|-----------|----------|
| 5 gün | +1.25% | +1.14% |
| 20 gün | -1.90% | **+5.12%** ← USA tepesi |
| 40 gün | +3.05% | -0.23% |
| 60 gün | +10.87% | -2.30% |
| **90 gün** | **+22.61%** ← BIST tepesi | -11.96% |
| 120 gün | +21.64% | -5.55% |

**MFE (Maximum Favorable Excursion) Analizi:**

| Piyasa | Ort. MFE | MFE Günü | Bounce Oranı |
|--------|----------|----------|--------------|
| BIST | **+30.17%** | ~50. gün | %50 |
| USA | +11.94% | ~22. gün | **%86** |

**V3 Bulgusu:**
- **BIST = Trend Başlangıcı** → Getiri 90 güne kadar artıyor, MFE ortalama +30%
- **USA = Kısa Bounce** → 20 günde tepe, sonra çöküyor, sinyallerin %86'sı kazancı geri veriyor

---

### V4 — BIST 20 Hisse + USA SPY Regime Filtresi

**BIST — 20 hisseye genişletildi, SRP gate kaldırıldı:**

| Tutma | Hit Rate | Ort. Getiri |
|-------|----------|-------------|
| Sinyal bazlı | **80.9%** | **+5.64%** (ort. 19 gün) |
| 20 gün | 71.9% | +5.35% |
| 40 gün | 65.2% | +8.43% |
| 60 gün | 82.0% | +12.61% |
| 90 gün | 73.0% | +19.50% |

**SRP Booster Analizi — Beklenmedik Sonuç:**

| Grup | Sinyal | Hit Rate | Ort. Getiri |
|------|--------|----------|-------------|
| SRP < 60 | 75 | **82.7%** | **+5.93%** |
| SRP ≥ 60 | 14 | 71.4% | +4.06% |

→ SRP düşük olan sinyaller daha iyi performans gösterdi. **SRP BIST'te filtre olarak işe yaramıyor.**

**USA — SPY PAP Regime Filtresi:**
- SPY Rejected durumunda 63 sinyalin **%77.8'i** elendi
- Kalan 14 sinyal: %42.9 hit rate, +2.78% (çok az örnekle güvenilmez)
- SPY hard gate çok kısıtlayıcı → soft modifier kullanılmalı

---

### V5 — SPY Düşerken Erken Sinyal Testi

**Hipotez:** SPY Rejected ama toparlanma başlıyor → bireysel hisseler için erken alım fırsatı

**Üç senaryo:**

| Senaryo | Tanım | Sinyal Sayısı |
|---------|-------|---------------|
| A | SPY Rejected + SPY üzerinde SRP bullish | 2 |
| **B** | **SPY Rejected + PAP skoru yükseliyor** | **9** |
| C | A + B beraber | 1 |

**SPY her sinyalden sonra toparlandı (2 yılda %100):**
- Senaryo A: ortalama 25 gün sonra Accepted'a döndü
- Senaryo B: ortalama 50 gün sonra Accepted'a döndü

**Erken giriş vs Normal giriş (bireysel hisseler):**

| Senaryo | Tutma | Erken Giriş | Normal Giriş | Fark |
|---------|-------|-------------|--------------|------|
| A | 40 gün | +7.5% | +3.0% | **+4.5%** |
| **B** | **10 gün** | **+3.8%** | **+1.2%** | **+2.6%** |
| C | 10 gün | +5.2% | +1.2% | +4.0% |
| C | 20 gün | +6.0% | +2.2% | +3.8% |

**V5 Bulgusu:** Senaryo B en pratik — 9 sinyal, baseline'dan +2.6% fazla, %78.6 hit rate. SPY henüz kötü görünürken birikim başlıyorsa erken giriş mantıklı.

---

## HİSSE BAZINDA SONUÇLAR

### BIST — Ticker Performansı (Sinyal Bazlı Çıkış, v4)

| Ticker | Sinyal | Hit Rate | Ort. Getiri | Ort. Tutma | Değerlendirme |
|--------|--------|----------|-------------|------------|---------------|
| VAKBN.IS | 4 | **100%** | **+14.85%** | 17 gün | ✅ Çok güçlü |
| AKBNK.IS | 13 | **100%** | **+9.18%** | 18 gün | ✅ Güvenilir + yeterli sinyal |
| FROTO.IS | 7 | **100%** | **+9.06%** | 44 gün | ✅ Trend takip ediyor |
| GARAN.IS | 3 | **100%** | **+8.97%** | 9 gün | ✅ Hızlı dönüşler |
| KCHOL.IS | 6 | 83.3% | +8.16% | 31 gün | ✅ İyi |
| TTKOM.IS | 3 | **100%** | +8.11% | 9 gün | ✅ İyi |
| ISCTR.IS | 10 | 90.0% | +7.96% | 28 gün | ✅ Güvenilir |
| EREGL.IS | 7 | **100%** | +5.74% | 11 gün | ✅ İyi |
| BIMAS.IS | 1 | 100% | +5.39% | 5 gün | ⚠️ Çok az sinyal |
| MGROS.IS | 3 | 100% | +4.90% | 13 gün | ✅ İyi |
| PETKM.IS | 4 | 100% | +4.83% | 9 gün | ✅ İyi |
| ASELS.IS | 1 | 100% | +4.44% | 2 gün | ⚠️ Çok az sinyal |
| THYAO.IS | 9 | 77.8% | +3.59% | 9 gün | ✅ Kabul edilebilir |
| EKGYO.IS | 1 | 100% | +3.22% | 1 gün | ⚠️ Çok az sinyal |
| TCELL.IS | 2 | 100% | +2.45% | 14 gün | ⚠️ Az sinyal |
| TOASO.IS | — | — | — | — | Sinyal üretmedi |
| TUPRS.IS | — | — | — | — | Sinyal üretmedi |
| HALKB.IS | — | — | — | — | Sinyal üretmedi |
| **ARCLK.IS** | 10 | **20%** | **-1.71%** | 26 gün | ❌ Çıkar |
| **SASA.IS** | 5 | **0%** | **-5.49%** | 7 gün | ❌ Çıkar |

### USA — Ticker Performansı (SPY Regime, Sinyal Bazlı Çıkış, v4)

| Ticker | Sinyal | Hit Rate | Ort. Getiri | Değerlendirme |
|--------|--------|----------|-------------|---------------|
| UNH | 1 | 100% | +20.90% | ⚠️ Çok az sinyal |
| AAPL | 3 | **100%** | **+7.82%** | ✅ İyi |
| AMZN | 6 | 66.7% | +7.80% | ✅ İyi (erken girişte daha iyi) |
| SPY | 3 | 100% | +5.98% | ✅ Regime test olarak çalışıyor |
| META | 7 | 85.7% | +2.15% | ✅ Yeterli sinyal, tutarlı |
| JPM | 7 | 28.6% | +1.01% | ⚠️ Zayıf |
| MSFT | 6 | 16.7% | -3.73% | ❌ Çalışmıyor |

---

## TREND ANALİZİ

### BIST Trend Karakteri
BIST'te PAP Accepted/Edge sinyali gerçek bir **orta-uzun vadeli trend başlangıcını** işaret ediyor:
- Getiri 20. günde düşüp 90. günde +19.50% ile tepe yapıyor
- MFE ortalama +30%, zirveye ~50. günde ulaşılıyor
- Bankacılık hisseleri (AKBNK, GARAN, VAKBN, ISCTR) en güçlü ve en güvenilir
- Sanayi (FROTO) trend en uzun sürenler arasında (ort. 44 gün tutma)
- Emtia/kimya (SASA, ARCLK) filtreden geçse de çalışmıyor → hisse seçimi kritik

### USA Trend Karakteri
USA'da PAP sinyali **kısa vadeli momentum bounce**:
- Getiri 20. günde tepe yapıp sonra geri döner
- Sinyallerin %86'sı kazancın yarısından fazlasını 120. güne kadar geri verir
- SPY düşerken (Rejected + skor yükseliyorsa) bireysel hisseler daha erken alınabilir
- MSFT bu filtrelerle çalışmıyor, JPM zayıf

---

## NİHAİ ÖNERİLER

### BIST
| Konu | Karar |
|------|-------|
| Filtre | PAP Accepted veya Edge |
| SRP | Kaldır — veri desteklemiyor |
| Tutma | 60-90 gün (trend takip) |
| Çıkış | PAP Rejected'a dönünce veya 90 gün |
| İzleme listesi | AKBNK, VAKBN, FROTO, GARAN, ISCTR, EREGL, KCHOL, THYAO, PETKM |
| Listeden çıkar | ARCLK, SASA |

### USA
| Konu | Karar |
|------|-------|
| Filtre | Bireysel PAP Accepted veya Edge |
| SRP | Kaldır |
| SPY durumu | Soft modifier (hard gate değil): |
| | SPY Accepted → +5 puan |
| | SPY Rejected düşüyor → -10 puan (giriş yapma) |
| | SPY Rejected yükseliyor → Erken giriş fırsatı |
| Tutma | 20 gün (bounce) |
| Çıkış | PAP Rejected'a dönünce veya 20 gün |
| İzleme listesi | AAPL, AMZN, META, SPY |
| Dikkat | MSFT, JPM bu sistemde çalışmıyor |

---

## PIPELINE ENTEGRASYONU — SIRALAMA

1. `src/pap_indicator.py` — PAP hesaplama modülü (öncelik: yüksek)
2. BIST hisse listesini güncelle (ARCLK/SASA çıkar, 20 hisse)
3. `src/layers/macro_regime.py` — SPY PAP state ekle (Accepted/Rejected/Rising)
4. `src/detailed_scorer.py` — PAP state'e göre skor ayarı
5. `src/decision_engine.py` — SPY Rejected+rising = erken sinyal flag'i
6. Dashboard'a PAP state göster (Accepted/Edge/Rejected)

---

*Backtest dosyaları: backtest/srp_pap_backtest_v1..v5.py + .md*  
*Tüm backtest sonuçları 2 yıllık günlük data üzerinden, 5-20 hisse ile üretilmiştir. Yüksek eşik altgrupları (n<10) istatistiksel olarak yönlendirici olup kesin değildir.*
