# SRP + PAP Backtest v3 — Bounce vs Trend Analysis

**Date generated:** 2026-06-18
**Period:** 2024-06-08 → 2026-06-18 (2 years daily)
**Fixed hold periods:** 5, 10, 20, 40, 60, 90, 120 days
**MFE look-forward window:** 120 days

## Entry Criteria (identical to v2)

| Universe | PAP State | SRP Threshold |
|----------|-----------|---------------|
| BIST     | Accepted or Edge | SRP score >= 60 |
| USA      | Accepted or Edge | Any SRP signal (score > 0) |

---

## 1. Full Return Curve Table

Same entry signals, exit at each fixed number of days after entry.

### BIST

| Hold (days) | # Trades | Avg Return | Median Return | Hit Rate |
|-------------|----------|------------|---------------|----------|
|           5 |        2 |     +1.25% |        +1.25% |    50.0% |
|          10 |        2 |     +1.67% |        +1.67% |    50.0% |
|          20 |        2 |     -1.90% |        -1.90% |    50.0% |
|          40 |        2 |     +3.05% |        +3.05% |    50.0% |
|          60 |        2 |    +10.87% |       +10.87% |    50.0% |
|          90 |        2 |    +22.61% |       +22.61% |   100.0% |
|         120 |        2 |    +21.64% |       +21.64% |   100.0% |

### USA

| Hold (days) | # Trades | Avg Return | Median Return | Hit Rate |
|-------------|----------|------------|---------------|----------|
|           5 |       14 |     +1.14% |        +0.64% |    57.1% |
|          10 |       14 |     +3.70% |        +2.39% |    64.3% |
|          20 |       14 |     +5.12% |        +6.04% |    71.4% |
|          40 |       14 |     -0.23% |        +1.74% |    57.1% |
|          60 |       14 |     -2.30% |        +3.72% |    57.1% |
|          90 |       14 |    -11.96% |        -9.07% |     0.0% |
|         120 |       14 |     -5.55% |        -4.84% |    28.6% |

### Combined (BIST + USA)

| Hold (days) | # Trades | Avg Return | Median Return | Hit Rate |
|-------------|----------|------------|---------------|----------|
|           5 |       16 |     +1.16% |        +0.64% |    56.2% |
|          10 |       16 |     +3.44% |        +2.39% |    62.5% |
|          20 |       16 |     +4.25% |        +6.04% |    68.8% |
|          40 |       16 |     +0.18% |        +1.74% |    56.2% |
|          60 |       16 |     -0.65% |        +3.72% |    56.2% |
|          90 |       16 |     -7.64% |        -7.32% |    12.5% |
|         120 |       16 |     -2.15% |        -2.89% |    37.5% |

---

## 2. Maximum Favorable Excursion (MFE) Analysis

For each trade, we look forward **120 trading days** from entry and record:
- **MFE**: the peak gain (for bullish signals) or peak gain-equivalent (for bearish) at any bar
- **MFE day**: how many days after entry the peak was reached
- **Return @120d**: the actual return at day 120
- **DD from MFE**: MFE minus Return@120d (how much was given back)
- **Bounce Rate**: % of trades where >50% of MFE was given back by day 120

### MFE Summary by Universe

| Universe | # Trades | Avg MFE | Avg Day MFE | Avg Return @120d | Avg DD from MFE | Bounce Rate |
|----------|----------|---------|-------------|------------------|-----------------|-------------|
| BIST     |        2 | +30.17% |          50 |          +14.46% |          15.71% |         50% |
| USA      |       14 | +11.94% |          22 |           -5.55% |          16.49% |         86% |

### MFE by Ticker

| Universe | Ticker | # | Avg MFE | Avg Day | Ret @120d | Avg DD | Bounce % |
|----------|--------|---|---------|---------|-----------|--------|----------|
| BIST     | KCHOL.IS   |   2 |  +30.17% |      50 |    +14.46% | +15.71% |       50% |
| USA      | META       |   5 |  +18.38% |      43 |     -4.47% | +22.85% |      100% |
| USA      | AMZN       |   4 |  +16.92% |      14 |     +4.19% | +12.73% |       75% |
| USA      | MSFT       |   5 |   +1.52% |       9 |    -14.42% | +13.14% |       80% |

---

## 3. Verdict: Bounce or Trend Starter?

### BIST

The return curve is **rising**: avg return improves from +3.05% at 40d to +21.64% at 120d — consistent with a TREND starter, not a short-term bounce. Peak average return of +22.61% is achieved at the 90-day hold. The signal's true potential (MFE) averages +30.17%, typically reached around day 50. 50% of trades give back >50% of their MFE by day 120 — **MIXED** behaviour: some trades sustain gains while others fade. 
**Verdict for BIST: TREND STARTER**

### USA

The return curve is **declining** after 40d: return drops from -0.23% (40d) to -5.55% (120d) — typical bounce behaviour where early gains fade. Peak average return of +5.12% is achieved at the 20-day hold. The signal's true potential (MFE) averages +11.94%, typically reached around day 22. 86% of trades give back >50% of their MFE by day 120 — strong evidence these are **SHORT-TERM BOUNCES**, not persistent trends. 
**Verdict for USA: SHORT-TERM BOUNCE**

---

## 4. Key Highlights

### BIST
- Best hold period: **90 days** → avg return +22.61%  (hit rate 100.0%)
- Worst hold period: **20 days** → avg return -1.90%

### USA
- Best hold period: **20 days** → avg return +5.12%  (hit rate 71.4%)
- Worst hold period: **90 days** → avg return -11.96%

### MFE Highlights
- BIST signals reach their peak gain (MFE avg 30.17%) around day 50 on average.
- USA signals reach their peak gain (MFE avg 11.94%) around day 22 on average.
- BIST bounce rate (>50% MFE given back by d120): **50%**
- USA  bounce rate (>50% MFE given back by d120): **86%**

---

_Generated by backtest/srp_pap_backtest_v3.py_