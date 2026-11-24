# Stochastic Candidates Backtest
**Period:** 2024-06-14 → 2026-07-14
**Universe:** USA watchlist — 175 tickers at backtest time (production pipeline: **521** since July 2026)
**Method:** Daily walk-forward, entry next-day open, top 10 @ score ≥ 55

---

## Scenario Comparison

| Scenario | Picks | Days w/ picks | Hit% 5d | Avg 5d | Hit% 20d | Avg 20d | Alpha 20d | Hit% 60d | Avg 60d |
|----------|-------|---------------|---------|--------|----------|---------|-----------|----------|---------|
| Baseline (RSI-only, current weights) | 3407 | 378 | 53.6% | 0.83% | 55.1% | 3.16% | 1.87% | 57.5% | 8.38% |
| Stoch health weight (rsi 10 + stoch 10) | 3487 | 377 | 53.3% | 0.86% | 54.4% | 3.1% | 1.77% | 55.8% | 7.76% |
| Stoch triggers added (bounce + cross) | 3599 | 378 | 53.3% | 0.77% | 53.7% | 2.82% | 1.47% | 54.4% | 7.28% |
| Dual gate (RSI bounce AND stoch bounce) | 284 | 150 | 53.7% | 0.17% | 56.7% | 2.02% | 0.98% | 57.4% | 3.36% |
| Stoch health + contrarian zone tag | 3487 | 377 | 53.3% | 0.86% | 54.4% | 3.1% | 1.77% | 55.8% | 7.76% |

---

## S0_baseline: Baseline (RSI-only, current weights)

- Total top-10 picks: **3407**
- Trading days with ≥1 pick: **378**
- Avg picks per active day: **9.0**
- 20d hit rate: **55.1%** | avg return: **3.16%** | alpha: **1.87%**

**Stoch zone breakdown (20d):**

| Zone | Picks | Hit% | Avg Ret | Avg Alpha |
|------|-------|------|---------|-----------|
| oversold | 14 | 71% | +5.69% | +3.91% |
| neutral | 1814 | 51% | +1.85% | +0.60% |
| overbought | 1386 | 61% | +4.86% | +3.51% |

**Top 5 picks (20d return):**

| Date | Ticker | Score | Stoch K | RSI | 20d Ret | Alpha |
|------|--------|-------|---------|-----|---------|-------|
| 2026-04-01 | INTC | 70 | 44.7 | 56.5 | +116.3% | +104.8% |
| 2025-01-02 | OKLO | 60 | 65.0 | 52.1 | +113.5% | +111.1% |
| 2026-04-07 | INTC | 75 | 94.1 | 64.7 | +104.1% | +95.6% |
| 2026-04-09 | INTC | 75 | 98.1 | 74.8 | +103.1% | +94.8% |
| 2025-09-12 | OKLO | 65 | 84.2 | 64.6 | +103.0% | +102.2% |

## S2_stoch_health: Stoch health weight (rsi 10 + stoch 10)

- Total top-10 picks: **3487**
- Trading days with ≥1 pick: **377**
- Avg picks per active day: **9.2**
- 20d hit rate: **54.4%** | avg return: **3.1%** | alpha: **1.77%**

**Stoch zone breakdown (20d):**

| Zone | Picks | Hit% | Avg Ret | Avg Alpha |
|------|-------|------|---------|-----------|
| oversold | 6 | 83% | +10.72% | +6.19% |
| neutral | 2387 | 51% | +2.04% | +0.78% |
| overbought | 898 | 62% | +5.86% | +4.39% |

**Top 5 picks (20d return):**

| Date | Ticker | Score | Stoch K | RSI | 20d Ret | Alpha |
|------|--------|-------|---------|-----|---------|-------|
| 2026-04-01 | INTC | 75 | 44.7 | 56.5 | +116.3% | +104.8% |
| 2025-01-02 | OKLO | 65 | 65.0 | 52.1 | +113.5% | +111.1% |
| 2026-04-07 | INTC | 65 | 94.1 | 64.7 | +104.1% | +95.6% |
| 2026-04-09 | INTC | 75 | 98.1 | 74.8 | +103.1% | +94.8% |
| 2026-05-18 | ARM | 65 | 51.9 | 56.9 | +99.7% | +98.9% |

## S4_stoch_trig: Stoch triggers added (bounce + cross)

- Total top-10 picks: **3599**
- Trading days with ≥1 pick: **378**
- Avg picks per active day: **9.5**
- 20d hit rate: **53.7%** | avg return: **2.82%** | alpha: **1.47%**

**Stoch zone breakdown (20d):**

| Zone | Picks | Hit% | Avg Ret | Avg Alpha |
|------|-------|------|---------|-----------|
| oversold | 5 | 80% | +10.47% | +5.06% |
| neutral | 2564 | 51% | +1.81% | +0.53% |
| overbought | 834 | 62% | +5.87% | +4.34% |

**Top 5 picks (20d return):**

| Date | Ticker | Score | Stoch K | RSI | 20d Ret | Alpha |
|------|--------|-------|---------|-----|---------|-------|
| 2026-04-01 | INTC | 75 | 44.7 | 56.5 | +116.3% | +104.8% |
| 2025-01-02 | OKLO | 65 | 65.0 | 52.1 | +113.5% | +111.1% |
| 2026-04-07 | INTC | 65 | 94.1 | 64.7 | +104.1% | +95.6% |
| 2026-04-09 | INTC | 75 | 98.1 | 74.8 | +103.1% | +94.8% |
| 2026-05-18 | ARM | 65 | 51.9 | 56.9 | +99.7% | +98.9% |

## S6_dual_gate: Dual gate (RSI bounce AND stoch bounce)

- Total top-10 picks: **284**
- Trading days with ≥1 pick: **150**
- Avg picks per active day: **1.9**
- 20d hit rate: **56.7%** | avg return: **2.02%** | alpha: **0.98%**

**Stoch zone breakdown (20d):**

| Zone | Picks | Hit% | Avg Ret | Avg Alpha |
|------|-------|------|---------|-----------|
| oversold | 7 | 29% | -1.40% | -0.18% |
| neutral | 254 | 57% | +2.14% | +1.02% |
| overbought | 9 | 56% | +1.40% | +0.87% |

**Top 5 picks (20d return):**

| Date | Ticker | Score | Stoch K | RSI | 20d Ret | Alpha |
|------|--------|-------|---------|-----|---------|-------|
| 2026-04-16 | DDOG | 55 | 64.6 | 55.5 | +64.2% | +59.5% |
| 2026-03-31 | MCHP | 55 | 26.0 | 45.1 | +43.3% | +33.4% |
| 2025-04-09 | HOOD | 65 | 37.6 | 50.1 | +35.6% | +29.6% |
| 2025-09-09 | SMCI | 55 | 25.9 | 44.9 | +33.4% | +30.1% |
| 2025-04-11 | MPWR | 55 | 44.3 | 46.3 | +31.6% | +23.7% |

## S7_contrarian: Stoch health + contrarian zone tag

- Total top-10 picks: **3487**
- Trading days with ≥1 pick: **377**
- Avg picks per active day: **9.2**
- 20d hit rate: **54.4%** | avg return: **3.1%** | alpha: **1.77%**

**Stoch zone breakdown (20d):**

| Zone | Picks | Hit% | Avg Ret | Avg Alpha |
|------|-------|------|---------|-----------|
| oversold | 6 | 83% | +10.72% | +6.19% |
| neutral | 2387 | 51% | +2.04% | +0.78% |
| overbought | 898 | 62% | +5.86% | +4.39% |

**Top 5 picks (20d return):**

| Date | Ticker | Score | Stoch K | RSI | 20d Ret | Alpha |
|------|--------|-------|---------|-----|---------|-------|
| 2026-04-01 | INTC | 75 | 44.7 | 56.5 | +116.3% | +104.8% |
| 2025-01-02 | OKLO | 65 | 65.0 | 52.1 | +113.5% | +111.1% |
| 2026-04-07 | INTC | 65 | 94.1 | 64.7 | +104.1% | +95.6% |
| 2026-04-09 | INTC | 75 | 98.1 | 74.8 | +103.1% | +94.8% |
| 2026-05-18 | ARM | 65 | 51.9 | 56.9 | +99.7% | +98.9% |

---

_Generated by backtest/stoch_candidates_backtest.py_
