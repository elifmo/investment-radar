# SRP + PAP Backtest v4 — BIST 20 Tickers & USA SPY Regime

**Date generated:** 2026-06-18
**Period:** 2024-06-08 → 2026-06-18 (2 years daily)

## Entry & Exit Configs

| Universe | Entry Logic | SRP Gate | Hold Periods |
|----------|-------------|----------|--------------|
| BIST     | PAP Accepted or Edge | None (SRP recorded as booster score) | 20, 40, 60, 90d fixed + signal-based (max 90d) |
| USA      | PAP Accepted or Edge | None (SPY PAP regime gate instead) | 10, 20d fixed + signal-based (max 20d) |

---

## BIST Results

### 1. Overall — Signal-Based Exit

| Metric | Value |
|--------|-------|
| Total trades | 89 |
| Hit rate | 80.9% |
| Avg return | +5.64% |
| Median return | +5.38% |
| Avg days held | 19.1d |
| Median days held | 16d |

**Exit reason breakdown:**

- PAP_Rejected: 62 (69.7%)
- Opposite_SRP: 27 (30.3%)

### 1b. Fixed Hold Periods — BIST

| Hold (days) | # Trades | Hit Rate | Avg Return | Median Return |
|-------------|----------|----------|------------|---------------|
|          20 |       89 |    71.9% |     +5.35% |        +5.70% |
|          40 |       89 |    65.2% |     +8.43% |        +6.86% |
|          60 |       89 |    82.0% |    +12.61% |       +10.54% |
|          90 |       89 |    73.0% |    +19.50% |       +12.46% |

### 2. SRP Booster Analysis — Signal-Based Exit

Entry condition: PAP Accepted or Edge (same for both groups). SRP score only used to split results.

| Subgroup      | # Trades | Hit Rate | Avg Return | Median Return | Avg Days |
|---------------|----------|----------|------------|---------------|----------|
| SRP >= 60     |       14 |    71.4% |     +4.06% |        +3.68% |     17.5 |
| SRP < 60      |       75 |    82.7% |     +5.93% |        +5.39% |     19.4 |

#### SRP Booster — Fixed Hold Comparison

| Hold | SRP>=60 n | SRP>=60 Hit | SRP>=60 Avg | SRP<60 n | SRP<60 Hit | SRP<60 Avg |
|------|-----------|-------------|-------------|----------|------------|------------|
|   20 |        14 |       71.4% |      +6.54% |       75 |      72.0% |     +5.12% |
|   40 |        14 |       57.1% |      +3.54% |       75 |      66.7% |     +9.34% |
|   60 |        14 |       57.1% |      +5.70% |       75 |      86.7% |    +13.90% |
|   90 |        14 |       57.1% |     +14.18% |       75 |      76.0% |    +20.49% |

### 3. Per-Ticker Breakdown — BIST Signal-Based Exit

| Ticker | # Trades | Hit Rate | Avg Return | Avg Days | Median Days |
|--------|----------|----------|------------|----------|-------------|
| VAKBN.IS     |        4 |   100.0% |    +14.85% |     17.2 |          20 |
| AKBNK.IS     |       13 |   100.0% |     +9.18% |     18.2 |          20 |
| FROTO.IS     |        7 |   100.0% |     +9.06% |     43.9 |          43 |
| GARAN.IS     |        3 |   100.0% |     +8.97% |      9.0 |           8 |
| KCHOL.IS     |        6 |    83.3% |     +8.16% |     31.3 |          35 |
| TTKOM.IS     |        3 |   100.0% |     +8.11% |      9.3 |          11 |
| ISCTR.IS     |       10 |    90.0% |     +7.96% |     28.0 |          34 |
| EREGL.IS     |        7 |   100.0% |     +5.74% |     10.7 |           8 |
| BIMAS.IS     |        1 |   100.0% |     +5.39% |      5.0 |           5 |
| MGROS.IS     |        3 |   100.0% |     +4.90% |     13.0 |          16 |
| PETKM.IS     |        4 |   100.0% |     +4.83% |      9.5 |           8 |
| ASELS.IS     |        1 |   100.0% |     +4.44% |      2.0 |           2 |
| THYAO.IS     |        9 |    77.8% |     +3.59% |      9.2 |          10 |
| EKGYO.IS     |        1 |   100.0% |     +3.22% |      1.0 |           1 |
| TCELL.IS     |        2 |   100.0% |     +2.45% |     14.5 |          14 |
| ARCLK.IS     |       10 |    20.0% |     -1.71% |     25.7 |          31 |
| SASA.IS      |        5 |     0.0% |     -5.49% |      6.6 |           6 |

### 4. BIST Verdict

Surprisingly, SRP<60 signals perform similarly or better in this period (+5.93% vs +4.06%). The PAP entry gate appears sufficient; SRP scoring provides limited additional filtering.

---

## USA Results

**SPY Regime Filter:** 49 signals filtered out of 63 total pre-filter signals (77.8% filtered).

### 1. Without SPY Filter vs With SPY Filter — Signal-Based Exit

| Config | # Trades | Hit Rate | Avg Return | Median Return | Avg Days |
|--------|----------|----------|------------|---------------|----------|
| USA (no SPY filter)          |       63 |    61.9% |     +2.27% |        +2.25% |      14.2 |
| USA (SPY regime gate)        |       14 |    42.9% |     +2.78% |        -0.65% |      18.4 |

### 2. Fixed Hold Periods

#### Without SPY Filter

| Hold (days) | # Trades | Hit Rate | Avg Return | Median Return |
|-------------|----------|----------|------------|---------------|
|          10 |       63 |    52.4% |     +1.41% |        +0.38% |
|          20 |       63 |    54.0% |     +1.63% |        +1.17% |

#### With SPY Regime Gate

| Hold (days) | # Trades | Hit Rate | Avg Return | Median Return |
|-------------|----------|----------|------------|---------------|
|          10 |       14 |    42.9% |     +0.34% |        -0.41% |
|          20 |       14 |    50.0% |     +3.32% |        +2.29% |

### 3. Signals Filtered by SPY Rejected State

- Pre-filter signals (individual PAP ok): **63**
- Filtered by SPY Rejected: **49** (77.8%)
- Signals that passed SPY gate: **14** (22.2%)

### 4. Per-Ticker Breakdown — USA Signal-Based Exit (SPY regime applied)

| Ticker | # Trades | Hit Rate | Avg Return | Avg Days | Median Days |
|--------|----------|----------|------------|----------|-------------|
| UNH          |        1 |   100.0% |    +20.90% |     20.0 |          20 |
| AAPL         |        3 |   100.0% |     +7.82% |     18.7 |          20 |
| JPM          |        7 |    28.6% |     +1.01% |     19.6 |          20 |
| AMZN         |        1 |     0.0% |     -1.53% |      4.0 |           4 |
| MSFT         |        1 |     0.0% |     -2.48% |     20.0 |          20 |
| META         |        1 |     0.0% |     -8.51% |     20.0 |          20 |

**Exit reason breakdown (SPY-filtered):**

- MaxHold: 10 (71.4%)
- Opposite_SRP: 3 (21.4%)
- PAP_Rejected: 1 (7.1%)

### 5. USA Verdict

SPY PAP regime filter improves signal quality: filtered signals avg +2.78% return vs +2.27% without filter. 49 signals (77.8%) were filtered out by SPY Rejected state. Recommend keeping SPY regime gate.

---

## Final Recommendation Table

| Strategy                     | # Trades | Hit Rate | Avg Return | Median Return | Avg Days |
|------------------------------|----------|----------|------------|---------------|----------|
| BIST signal-based (no SRP gate) |       89 |    80.9% |     +5.64% |        +5.38% |      19.1 |
| BIST SRP>=60 signal-based    |       14 |    71.4% |     +4.06% |        +3.68% |      17.5 |
| BIST SRP<60 signal-based     |       75 |    82.7% |     +5.93% |        +5.39% |      19.4 |
| USA signal-based (no SPY)    |       63 |    61.9% |     +2.27% |        +2.25% |      14.2 |
| USA signal-based (SPY regime) |       14 |    42.9% |     +2.78% |        -0.65% |      18.4 |

#### Fixed Hold Summary

| Universe | Hold | # Trades | Hit Rate | Avg Return |
|----------|------|----------|----------|------------|
| BIST |   20d |       89 |    71.9% |     +5.35% |
| BIST |   40d |       89 |    65.2% |     +8.43% |
| BIST |   60d |       89 |    82.0% |    +12.61% |
| BIST |   90d |       89 |    73.0% |    +19.50% |
| USA (SPY gate) |   10d |       14 |    42.9% |     +0.34% |
| USA (SPY gate) |   20d |       14 |    50.0% |     +3.32% |

---

_Generated by backtest/srp_pap_backtest_v4.py_