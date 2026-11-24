# SRP + PAP Backtest Report

**Date generated:** 2026-06-18
**Period:** 2024-06-08 → 2026-06-18 (2 years daily)
**Hold period:** 5 trading days (buy next open, exit on close)
**BIST tickers:** EREGL.IS, TOASO.IS, TUPRS.IS, THYAO.IS, KCHOL.IS
**USA tickers:** SPY, AAPL, MSFT, NVDA, AMZN, META

---

## Indicator Implementation Notes

### Stop Run Reversal Planner (SRP)
- Lookback = 34 bars, ATR = 14, Volume baseline = 34
- Detects bars that sweep below recent N-bar low (bullish) or above recent N-bar high (bearish)
  then close back inside the range
- sweepScore = wickScore×0.56 + penScore×0.34 + volumeScore×0.10
- reversalScore = sweepScore×0.22 + closeBackScore×0.22 + confirmScore×0.22
  + volumeScore×0.12 + targetRoomScore×0.14 + trendTurnScore×0.08
- Score range: 0–100 (only non-zero on sweep bars)

### Price Acceptance Profile (PAP)
- Lookback = 320 bars, 26 histogram rows, value area = 70%
- Builds time-at-price histogram; finds POC, VAH, VAL
- Acceptance state: Accepted (inside VA), Edge (within 1.5 rows of boundary), Rejected (outside VA)
- Rotation: COG shift from first half to second half of lookback window
- acceptanceScore = POC proximity (0-40) + VA width bonus (0-20) + rotation alignment (0-20) + state bonus (0-20)

---

## BIST Results
(Tickers: EREGL.IS, TOASO.IS, TUPRS.IS, THYAO.IS, KCHOL.IS)

### PAP State Distribution (all BIST bars with SRP activity)

- Rejected: 61 (67.8%)
- Accepted: 16 (17.8%)
- Edge: 13 (14.4%)

### SRP Score Distribution (BIST)

- Score >= 50: 36 signals (40.0%)
- Score >= 60: 16 signals (17.8%)
- Score >= 66: 6 signals (6.7%)
- Score >= 70: 3 signals (3.3%)
- Score >= 75: 1 signals (1.1%)

### Filter Performance — BIST

| Filter | # Signals | Hit Rate | Avg 5d Ret | Median 5d Ret |
|--------|-----------|----------|------------|---------------|
| Baseline (all SRP signals)               |        90 |    58.9% |     +0.95% |        +0.59% |
| SRP >= 66                                |         6 |    66.7% |     +3.98% |        +5.68% |
| SRP >= 70                                |         3 |    66.7% |     +4.43% |        +8.23% |
| SRP >= 75                                |         1 |   100.0% |    +10.84% |       +10.84% |
| PAP: Accepted or Edge                    |        29 |    75.9% |     +2.22% |        +1.92% |
| PAP: Accepted only                       |        16 |    75.0% |     +1.28% |        +0.88% |
| Combined: SRP>=66 + PAP Acc/Edge         |         4 |    75.0% |     +4.71% |        +5.68% |
| Combined: SRP>=70 + PAP Acc/Edge         |         1 |   100.0% |     +8.23% |        +8.23% |

### Per-Ticker Breakdown — BIST (Baseline / all SRP signals)

| Ticker | # Signals | Hit Rate | Avg 5d Ret | Max | Min |
|--------|-----------|----------|------------|-----|-----|
| EREGL.IS   |        20 |    85.0% |     +2.64% | +13.63% | -9.86% |
| KCHOL.IS   |        22 |    59.1% |     +1.27% | +8.24% | -5.87% |
| TOASO.IS   |        10 |    50.0% |     +0.58% | +12.25% | -8.31% |
| THYAO.IS   |        17 |    58.8% |     +0.14% | +7.41% | -8.81% |
| TUPRS.IS   |        21 |    38.1% |     -0.16% | +10.84% | -6.82% |

### Per-Ticker Breakdown — BIST (SRP >= 66 filter)

| Ticker | # Signals | Hit Rate | Avg 5d Ret | Max | Min |
|--------|-----------|----------|------------|-----|-----|
| TUPRS.IS   |         1 |   100.0% |    +10.84% | +10.84% | +10.84% |
| KCHOL.IS   |         1 |   100.0% |     +8.23% | +8.23% | +8.23% |
| EREGL.IS   |         3 |    66.7% |     +1.86% | +6.69% | -5.77% |
| THYAO.IS   |         1 |     0.0% |     -0.75% | -0.75% | -0.75% |

---

## USA Results
(Tickers: SPY, AAPL, MSFT, NVDA, AMZN, META)

### PAP State Distribution (all USA bars with SRP activity)

- Rejected: 56 (62.2%)
- Edge: 18 (20.0%)
- Accepted: 16 (17.8%)

### SRP Score Distribution (USA)

- Score >= 50: 35 signals (38.9%)
- Score >= 60: 10 signals (11.1%)
- Score >= 66: 6 signals (6.7%)
- Score >= 70: 4 signals (4.4%)
- Score >= 75: 1 signals (1.1%)

### Filter Performance — USA

| Filter | # Signals | Hit Rate | Avg 5d Ret | Median 5d Ret |
|--------|-----------|----------|------------|---------------|
| Baseline (all SRP signals)               |        90 |    47.8% |     -0.02% |        -0.16% |
| SRP >= 66                                |         6 |    16.7% |     -0.92% |        -1.00% |
| SRP >= 70                                |         4 |    25.0% |     -0.88% |        -0.78% |
| SRP >= 75                                |         1 |   100.0% |     +0.57% |        +0.57% |
| PAP: Accepted or Edge                    |        34 |    52.9% |     +0.88% |        +0.13% |
| PAP: Accepted only                       |        16 |    50.0% |     +0.52% |        +0.03% |
| Combined: SRP>=66 + PAP Acc/Edge         |         1 |     0.0% |     -1.28% |        -1.28% |
| Combined: SRP>=70 + PAP Acc/Edge         |         0 |        — |          — |             — |

### Per-Ticker Breakdown — USA (Baseline / all SRP signals)

| Ticker | # Signals | Hit Rate | Avg 5d Ret | Max | Min |
|--------|-----------|----------|------------|-----|-----|
| META       |        10 |    50.0% |     +0.77% | +7.16% | -4.23% |
| AMZN       |        16 |    56.2% |     +0.48% | +5.94% | -6.30% |
| NVDA       |        10 |    30.0% |     +0.45% | +6.06% | -2.53% |
| MSFT       |         9 |    55.6% |     +0.14% | +3.43% | -7.07% |
| SPY        |        20 |    50.0% |     -0.43% | +2.65% | -2.78% |
| AAPL       |        25 |    44.0% |     -0.57% | +3.08% | -7.96% |

### Per-Ticker Breakdown — USA (SRP >= 66 filter)

| Ticker | # Signals | Hit Rate | Avg 5d Ret | Max | Min |
|--------|-----------|----------|------------|-----|-----|
| META       |         1 |     0.0% |     -0.28% | -0.28% | -0.28% |
| SPY        |         2 |    50.0% |     -0.36% | +0.57% | -1.28% |
| AAPL       |         2 |     0.0% |     -1.00% | -0.72% | -1.29% |
| NVDA       |         1 |     0.0% |     -2.53% | -2.53% | -2.53% |

---

## SPY PAP as Market Regime Indicator

When SPY is in a given PAP acceptance state, how do individual USA stocks perform (5d)?

| SPY State | # Observations | Hit Rate | Avg 5d Ret |
|-----------|----------------|----------|------------|
| Accepted   |              5 |    60.0% |     -0.69% |
| Edge       |              5 |    40.0% |     -0.13% |
| Rejected   |             60 |    46.7% |     +0.18% |

---

## Recommendations

> **Statistical caveat:** Total dataset spans 5 tickers × ~507 bars. SRP fires only on wick-sweep bars (rare events), so high-threshold subsets (SRP >= 66, Combined) have n < 10. All conclusions at high thresholds are directionally suggestive only and need more data (more tickers, longer history, or intraday bars) before production use.

---

### BIST Recommendations

| Approach | n | Avg 5d Ret | Hit Rate | Practical? |
|----------|---|-----------|----------|------------|
| Baseline (any SRP) | 90 | +0.95% | 58.9% | Yes — adequate volume |
| PAP Accepted/Edge | 29 | +2.22% | 75.9% | **Best tradeoff** |
| SRP >= 66 | 6 | +3.98% | 66.7% | Low volume — confirm before use |
| Combined SRP>=66 + PAP | 4 | +4.71% | 75.0% | Very low volume — directional only |

**Key finding for BIST:**
- The **PAP Accepted/Edge filter** is the strongest signal on BIST with an adequate sample (n=29). It improves both hit rate (58.9% → 75.9%) and avg return (+0.95% → +2.22%) versus baseline, without relying on very sparse SRP score thresholds.
- BIST baseline (any SRP activity) already beats coin-flip (58.9%), suggesting that stop-run wick sweeps are a valid signal type on these tickers even without filtering.
- SRP >= 66 improves returns further (+3.98%) but with only 6 signals over 2 years — too sparse for reliable inference.
- **Recommended threshold for BIST:** Apply **PAP Accepted/Edge** as the primary gate. Use SRP >= 60 as a supporting confirmation (n=16, between baseline and high-threshold). Do not use SRP >= 70 as a standalone gate in production yet.
- EREGL.IS stands out as the best BIST ticker for SRP-based signals (85% hit rate, +2.64% avg at baseline).

### USA Recommendations

| Approach | n | Avg 5d Ret | Hit Rate | Practical? |
|----------|---|-----------|----------|------------|
| Baseline (any SRP) | 90 | -0.02% | 47.8% | Below coin-flip |
| PAP Accepted/Edge | 34 | +0.88% | 52.9% | **Best for USA** |
| SRP >= 66 | 6 | -0.92% | 16.7% | Counter-productive |
| Combined SRP>=66 + PAP | 1 | -1.28% | 0.0% | Too sparse |

**Key finding for USA:**
- For large-cap US stocks, SRP alone is **not a positive signal** — the baseline is essentially flat (-0.02%). High SRP scores are actually associated with negative returns on this 2-year window (n=6, avg -0.92%), possibly because on liquid large-caps, wick sweeps are more likely continuation patterns than reversals on daily timeframe.
- The **PAP Accepted/Edge filter** is the only filter that consistently outperforms (+0.88%, 52.9% hit rate) on USA data. This makes intuitive sense: PAP identifies whether price is in an area of market acceptance, which has edge regardless of SRP signal presence.
- **Recommended threshold for USA:** Use PAP Accepted/Edge as a standalone regime filter for directional bias. Do not use SRP as a primary gate on daily large-cap data — SRP may be more effective on intraday timeframes for US stocks.
- SPY PAP regime analysis shows inconclusive results over this 2-year period (small sample of SRP-active dates where SPY PAP data is available). The SPY Rejected state dominates because most of the data captures trending periods.

### SRP Threshold Summary (BIST vs USA)

| Market | Recommended SRP Gate | Reason |
|--------|---------------------|--------|
| BIST | SRP >= 60 (with PAP) | BIST sweeps are real reversals; filter adds signal quality |
| USA daily | None / PAP only | Large-cap daily SRP has no edge; use PAP as regime filter |
| USA intraday | SRP >= 66 (to be tested) | Wick sweeps are more reliable on shorter timeframes |

---

## Pipeline Integration — Required Code Changes

To add SRP + PAP to the existing pipeline (`src/`), the following changes are needed:

### 1. New module: `src/srp_indicator.py`
```python
# Expose: compute_srp(df) -> pd.Series (score per bar)
# Parameters: lookback=34, atr_period=14, vol_baseline=34
# Call from pipeline after OHLCV fetch
```

### 2. New module: `src/pap_indicator.py`
```python
# Expose: compute_pap(df) -> pd.DataFrame (poc, vah, val, state, score per bar)
# Parameters: lookback=320, n_rows=26, value_area_pct=0.70
# Note: PAP lookback=320 requires at least 320 bars of history (~15 months daily)
```

### 3. Update `src/event_filter.py`
```python
# Add to run_event_filter():
#   srp_score = compute_srp(df)
#   pap_df    = compute_pap(df)
#   if srp_score.iloc[-1] >= 66:
#       triggers.append('srp_reversal')
#   pap_state = pap_df['acceptance_state'].iloc[-1]
#   if pap_state in ['Accepted', 'Edge']:
#       triggers.append('pap_accepted')
```

### 4. Update `src/detailed_scorer.py`
```python
# Add SRP and PAP components to score_ticker():
#   srp component: up to +15 pts (srp_score/100 * 15)
#   pap component: +10 pts if Accepted, +5 if Edge, 0 if Rejected
#   Adjust _DEFAULT_WEIGHTS to accommodate new components
```

### 5. Update `src/decision_engine.py`
```python
# Add optional srp_score and pap_state fields to candidate dict
# Gate: if srp_score is present and < 66, treat as WATCH even if RS passes
# Gate: if pap_state == 'Rejected', downgrade BUY -> WATCH
```

### 6. Update `src/firebase_writer.py`
```python
# Add srp_score, pap_state, pap_score fields to Firestore document
# Add pap_poc, pap_vah, pap_val for display in dashboard
```

### 7. Minimum data requirements
- SRP: needs max(34, 14, 34) + 5 = 39 bars minimum (easily met for daily data)
- PAP: needs 320 bars minimum (~15 months of daily data)
- For BIST tickers: verify data availability >= 320 bars before enabling PAP

---

_Generated by backtest/srp_pap_backtest.py_