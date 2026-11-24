# SRP + PAP Backtest v5 — SPY Early Recovery Hypothesis

**Date generated:** 2026-06-18
**Period:** 2024-06-08 → 2026-06-18 (2-year daily)
**SPY ticker:** SPY
**Individual stocks:** AAPL, MSFT, NVDA, AMZN, META, GOOGL, JPM
**Fixed hold periods:** 10d, 20d, 40d

## Hypothesis

When SPY PAP is **Rejected** (market down) but SPY SRP fires a **bullish
reversal signal**, this may represent an early recovery buy opportunity
before the market turns. Three scenarios test different filters to identify
this accumulation phase.

## Scenario Definitions

| Scenario | Condition |
|----------|-----------|
| **A** | SPY PAP state = Rejected AND SPY SRP direction = bullish |
| **B** | SPY PAP state = Rejected AND acceptance_score < 60 AND score rose ≥ 5 pts vs 5 bars ago |
| **C** | Scenario A AND Scenario B (most selective) |

**Baseline:** Individual stock PAP Accepted or Edge with NO SPY condition.

---

## Signal Counts

| Scenario | SPY Signals |
|----------|-------------|
| A | 2 |
| B | 9 |
| C | 1 |

---

## Part 1 — SPY Itself: Does SPY Recover After Each Scenario?

Entry at open of signal+1. Exit at fixed hold period close.

#### SPY — Scenario A

| Hold | # Signals | Hit Rate | Avg Return | Median Return |
|------|-----------|----------|------------|---------------|
| 10d |         2 |  +100.0% |      +1.6% |         +1.6% |
| 20d |         2 |   +50.0% |      +0.4% |         +0.4% |
| 40d |         2 |  +100.0% |      +3.6% |         +3.6% |

#### SPY — Scenario B

| Hold | # Signals | Hit Rate | Avg Return | Median Return |
|------|-----------|----------|------------|---------------|
| 10d |         9 |   +88.9% |      +2.3% |         +3.1% |
| 20d |         9 |  +100.0% |      +2.2% |         +1.4% |
| 40d |         9 |   +88.9% |      +2.6% |         +2.8% |

#### SPY — Scenario C

| Hold | # Signals | Hit Rate | Avg Return | Median Return |
|------|-----------|----------|------------|---------------|
| 10d |         1 |  +100.0% |      +3.1% |         +3.1% |
| 20d |         1 |  +100.0% |      +4.1% |         +4.1% |
| 40d |         1 |  +100.0% |      +4.3% |         +4.3% |

---

## Part 2 — Days Until SPY Recovers to Accepted/Edge

From each scenario signal bar, how many trading days until SPY PAP
acceptance_state reaches 'Accepted' or 'Edge'?

| Scenario | Signals | Recovered | Not Recovered | % Recovered | Avg Days | Median Days |
|----------|---------|-----------|---------------|-------------|----------|-------------|
| A | 2 | 2 | 0 | 100.0% | 25.5 | 25.5 |
| B | 9 | 9 | 0 | 100.0% | 49.8 | 52.0 |
| C | 1 | 1 | 0 | 100.0% | 50.0 | 50.0 |

---

## Part 3 — Individual Stock Results When SPY Scenario Fires

Entry condition: SPY scenario fires AND individual stock PAP = Accepted or Edge.
Entry at stock open of signal+1, exit at close of entry+hold.

### Scenario A

##### Hold 10d — Scenario A

| Ticker | # Trades | Hit Rate | Avg Return | Median Return |
|--------|----------|----------|------------|---------------|
| AAPL   |        0 |        — |          — |             — |
| MSFT   |        1 |  +100.0% |      +3.6% |         +3.6% |
| NVDA   |        1 |    +0.0% |      -3.0% |         -3.0% |
| AMZN   |        2 |  +100.0% |      +4.9% |         +4.9% |
| META   |        2 |  +100.0% |      +7.5% |         +7.5% |
| GOOGL  |        0 |        — |          — |             — |
| JPM    |        1 |    +0.0% |      -2.9% |         -2.9% |
| **All** |        7 |   +71.4% |      +3.2% |         +3.6% |

##### Hold 20d — Scenario A

| Ticker | # Trades | Hit Rate | Avg Return | Median Return |
|--------|----------|----------|------------|---------------|
| AAPL   |        0 |        — |          — |             — |
| MSFT   |        1 |  +100.0% |      +2.5% |         +2.5% |
| NVDA   |        1 |    +0.0% |      -4.4% |         -4.4% |
| AMZN   |        2 |  +100.0% |      +4.1% |         +4.1% |
| META   |        2 |   +50.0% |      +4.2% |         +4.2% |
| GOOGL  |        0 |        — |          — |             — |
| JPM    |        1 |    +0.0% |      -6.7% |         -6.7% |
| **All** |        7 |   +57.1% |      +1.1% |         +2.5% |

##### Hold 40d — Scenario A

| Ticker | # Trades | Hit Rate | Avg Return | Median Return |
|--------|----------|----------|------------|---------------|
| AAPL   |        0 |        — |          — |             — |
| MSFT   |        1 |    +0.0% |      -1.9% |         -1.9% |
| NVDA   |        1 |  +100.0% |      +5.1% |         +5.1% |
| AMZN   |        2 |  +100.0% |     +15.5% |        +15.5% |
| META   |        2 |  +100.0% |      +8.5% |         +8.5% |
| GOOGL  |        0 |        — |          — |             — |
| JPM    |        1 |  +100.0% |      +1.0% |         +1.0% |
| **All** |        7 |   +85.7% |      +7.5% |         +6.9% |

### Scenario B

##### Hold 10d — Scenario B

| Ticker | # Trades | Hit Rate | Avg Return | Median Return |
|--------|----------|----------|------------|---------------|
| AAPL   |        2 |  +100.0% |      +9.5% |         +9.5% |
| MSFT   |        6 |   +33.3% |      -1.2% |         -1.4% |
| NVDA   |        2 |   +50.0% |      +2.5% |         +2.5% |
| AMZN   |        8 |  +100.0% |      +2.6% |         +2.4% |
| META   |        9 |   +88.9% |      +7.0% |         +9.7% |
| GOOGL  |        0 |        — |          — |             — |
| JPM    |        1 |  +100.0% |      +4.6% |         +4.6% |
| **All** |       28 |   +78.6% |      +3.8% |         +3.4% |

##### Hold 20d — Scenario B

| Ticker | # Trades | Hit Rate | Avg Return | Median Return |
|--------|----------|----------|------------|---------------|
| AAPL   |        2 |  +100.0% |      +6.5% |         +6.5% |
| MSFT   |        6 |   +33.3% |      -2.6% |         -1.2% |
| NVDA   |        2 |  +100.0% |      +3.5% |         +3.5% |
| AMZN   |        8 |   +75.0% |      +1.7% |         +1.8% |
| META   |        9 |   +77.8% |      +5.1% |         +9.2% |
| GOOGL  |        0 |        — |          — |             — |
| JPM    |        1 |  +100.0% |      +1.5% |         +1.5% |
| **All** |       28 |   +71.4% |      +2.4% |         +2.4% |

##### Hold 40d — Scenario B

| Ticker | # Trades | Hit Rate | Avg Return | Median Return |
|--------|----------|----------|------------|---------------|
| AAPL   |        2 |  +100.0% |      +5.7% |         +5.7% |
| MSFT   |        6 |    +0.0% |      -9.1% |         -8.5% |
| NVDA   |        2 |   +50.0% |      +3.7% |         +3.7% |
| AMZN   |        8 |   +75.0% |      +1.4% |         +4.0% |
| META   |        9 |   +77.8% |      +2.6% |         +1.8% |
| GOOGL  |        0 |        — |          — |             — |
| JPM    |        1 |    +0.0% |      -5.1% |         -5.1% |
| **All** |       28 |   +57.1% |      -0.2% |         +0.9% |

### Scenario C

##### Hold 10d — Scenario C

| Ticker | # Trades | Hit Rate | Avg Return | Median Return |
|--------|----------|----------|------------|---------------|
| AAPL   |        0 |        — |          — |             — |
| MSFT   |        1 |  +100.0% |      +3.6% |         +3.6% |
| NVDA   |        0 |        — |          — |             — |
| AMZN   |        1 |  +100.0% |      +2.4% |         +2.4% |
| META   |        1 |  +100.0% |      +9.7% |         +9.7% |
| GOOGL  |        0 |        — |          — |             — |
| JPM    |        0 |        — |          — |             — |
| **All** |        3 |  +100.0% |      +5.2% |         +3.6% |

##### Hold 20d — Scenario C

| Ticker | # Trades | Hit Rate | Avg Return | Median Return |
|--------|----------|----------|------------|---------------|
| AAPL   |        0 |        — |          — |             — |
| MSFT   |        1 |  +100.0% |      +2.5% |         +2.5% |
| NVDA   |        0 |        — |          — |             — |
| AMZN   |        1 |  +100.0% |      +4.3% |         +4.3% |
| META   |        1 |  +100.0% |     +11.2% |        +11.2% |
| GOOGL  |        0 |        — |          — |             — |
| JPM    |        0 |        — |          — |             — |
| **All** |        3 |  +100.0% |      +6.0% |         +4.3% |

##### Hold 40d — Scenario C

| Ticker | # Trades | Hit Rate | Avg Return | Median Return |
|--------|----------|----------|------------|---------------|
| AAPL   |        0 |        — |          — |             — |
| MSFT   |        1 |    +0.0% |      -1.9% |         -1.9% |
| NVDA   |        0 |        — |          — |             — |
| AMZN   |        1 |  +100.0% |      +7.5% |         +7.5% |
| META   |        1 |  +100.0% |     +10.1% |        +10.1% |
| GOOGL  |        0 |        — |          — |             — |
| JPM    |        0 |        — |          — |             — |
| **All** |        3 |   +66.7% |      +5.2% |         +7.5% |

---

## Part 4 — Baseline: Individual Stock PAP Accepted/Edge (No SPY Condition)

##### Baseline Hold 10d (no SPY condition)

| Ticker | # Trades | Hit Rate | Avg Return | Median Return |
|--------|----------|----------|------------|---------------|
| AAPL   |       54 |   +68.5% |      +2.9% |         +3.4% |
| MSFT   |       63 |   +20.6% |      -3.4% |         -2.3% |
| NVDA   |       64 |   +51.6% |      +2.4% |         +0.8% |
| AMZN   |      118 |   +62.7% |      +2.6% |         +1.6% |
| META   |      121 |   +49.6% |      +0.0% |         -0.6% |
| GOOGL  |        5 |  +100.0% |     +17.4% |        +15.9% |
| JPM    |       52 |   +61.5% |      +1.5% |         +1.5% |
| **All** |      477 |   +53.2% |      +1.2% |         +0.8% |

##### Baseline Hold 20d (no SPY condition)

| Ticker | # Trades | Hit Rate | Avg Return | Median Return |
|--------|----------|----------|------------|---------------|
| AAPL   |       54 |   +88.9% |      +6.5% |         +7.2% |
| MSFT   |       63 |   +12.7% |      -5.9% |         -3.6% |
| NVDA   |       64 |   +68.8% |      +5.3% |         +2.8% |
| AMZN   |      118 |   +75.4% |      +5.0% |         +2.7% |
| META   |      121 |   +46.3% |      -0.9% |         -1.4% |
| GOOGL  |        5 |  +100.0% |     +28.1% |        +26.5% |
| JPM    |       52 |   +53.8% |      +1.9% |         +1.1% |
| **All** |      477 |   +58.3% |      +2.2% |         +1.5% |

##### Baseline Hold 40d (no SPY condition)

| Ticker | # Trades | Hit Rate | Avg Return | Median Return |
|--------|----------|----------|------------|---------------|
| AAPL   |       53 |   +83.0% |     +10.9% |        +11.5% |
| MSFT   |       62 |    +1.6% |     -12.9% |        -14.3% |
| NVDA   |       63 |   +84.1% |     +11.2% |         +9.4% |
| AMZN   |      118 |   +69.5% |      +6.6% |         +3.8% |
| META   |      120 |   +50.0% |      -1.6% |         -0.0% |
| GOOGL  |        5 |  +100.0% |     +34.9% |        +40.2% |
| JPM    |       51 |   +82.4% |      +3.0% |         +3.5% |
| **All** |      472 |   +60.8% |      +3.0% |         +2.2% |

---

## Part 5 — Scenario vs Baseline Comparison

Delta = Scenario avg return minus Baseline avg return.
Positive delta = scenario entries outperformed baseline.

### Scenario A

##### Avg Return Comparison — Scenario A vs Baseline — Hold 10d

| Ticker | Scenario Avg Ret | Baseline Avg Ret | Delta |
|--------|-----------------|-----------------|-------|
| AAPL   |               — |           +2.9% |     — |
| MSFT   |           +3.6% |           -3.4% | +7.0% |
| NVDA   |           -3.0% |           +2.4% | -5.5% |
| AMZN   |           +4.9% |           +2.6% | +2.2% |
| META   |           +7.5% |           +0.0% | +7.5% |
| GOOGL  |               — |          +17.4% |     — |
| JPM    |           -2.9% |           +1.5% | -4.4% |

##### Avg Return Comparison — Scenario A vs Baseline — Hold 20d

| Ticker | Scenario Avg Ret | Baseline Avg Ret | Delta |
|--------|-----------------|-----------------|-------|
| AAPL   |               — |           +6.5% |     — |
| MSFT   |           +2.5% |           -5.9% | +8.4% |
| NVDA   |           -4.4% |           +5.3% | -9.7% |
| AMZN   |           +4.1% |           +5.0% | -1.0% |
| META   |           +4.2% |           -0.9% | +5.1% |
| GOOGL  |               — |          +28.1% |     — |
| JPM    |           -6.7% |           +1.9% | -8.6% |

##### Avg Return Comparison — Scenario A vs Baseline — Hold 40d

| Ticker | Scenario Avg Ret | Baseline Avg Ret | Delta |
|--------|-----------------|-----------------|-------|
| AAPL   |               — |          +10.9% |     — |
| MSFT   |           -1.9% |          -12.9% | +10.9% |
| NVDA   |           +5.1% |          +11.2% | -6.1% |
| AMZN   |          +15.5% |           +6.6% | +9.0% |
| META   |           +8.5% |           -1.6% | +10.1% |
| GOOGL  |               — |          +34.9% |     — |
| JPM    |           +1.0% |           +3.0% | -2.0% |

### Scenario B

##### Avg Return Comparison — Scenario B vs Baseline — Hold 10d

| Ticker | Scenario Avg Ret | Baseline Avg Ret | Delta |
|--------|-----------------|-----------------|-------|
| AAPL   |           +9.5% |           +2.9% | +6.6% |
| MSFT   |           -1.2% |           -3.4% | +2.2% |
| NVDA   |           +2.5% |           +2.4% | +0.1% |
| AMZN   |           +2.6% |           +2.6% | +0.0% |
| META   |           +7.0% |           +0.0% | +7.0% |
| GOOGL  |               — |          +17.4% |     — |
| JPM    |           +4.6% |           +1.5% | +3.1% |

##### Avg Return Comparison — Scenario B vs Baseline — Hold 20d

| Ticker | Scenario Avg Ret | Baseline Avg Ret | Delta |
|--------|-----------------|-----------------|-------|
| AAPL   |           +6.5% |           +6.5% | -0.0% |
| MSFT   |           -2.6% |           -5.9% | +3.4% |
| NVDA   |           +3.5% |           +5.3% | -1.8% |
| AMZN   |           +1.7% |           +5.0% | -3.4% |
| META   |           +5.1% |           -0.9% | +6.1% |
| GOOGL  |               — |          +28.1% |     — |
| JPM    |           +1.5% |           +1.9% | -0.4% |

##### Avg Return Comparison — Scenario B vs Baseline — Hold 40d

| Ticker | Scenario Avg Ret | Baseline Avg Ret | Delta |
|--------|-----------------|-----------------|-------|
| AAPL   |           +5.7% |          +10.9% | -5.2% |
| MSFT   |           -9.1% |          -12.9% | +3.7% |
| NVDA   |           +3.7% |          +11.2% | -7.5% |
| AMZN   |           +1.4% |           +6.6% | -5.1% |
| META   |           +2.6% |           -1.6% | +4.1% |
| GOOGL  |               — |          +34.9% |     — |
| JPM    |           -5.1% |           +3.0% | -8.1% |

### Scenario C

##### Avg Return Comparison — Scenario C vs Baseline — Hold 10d

| Ticker | Scenario Avg Ret | Baseline Avg Ret | Delta |
|--------|-----------------|-----------------|-------|
| AAPL   |               — |           +2.9% |     — |
| MSFT   |           +3.6% |           -3.4% | +7.0% |
| NVDA   |               — |           +2.4% |     — |
| AMZN   |           +2.4% |           +2.6% | -0.2% |
| META   |           +9.7% |           +0.0% | +9.7% |
| GOOGL  |               — |          +17.4% |     — |
| JPM    |               — |           +1.5% |     — |

##### Avg Return Comparison — Scenario C vs Baseline — Hold 20d

| Ticker | Scenario Avg Ret | Baseline Avg Ret | Delta |
|--------|-----------------|-----------------|-------|
| AAPL   |               — |           +6.5% |     — |
| MSFT   |           +2.5% |           -5.9% | +8.4% |
| NVDA   |               — |           +5.3% |     — |
| AMZN   |           +4.3% |           +5.0% | -0.7% |
| META   |          +11.2% |           -0.9% | +12.1% |
| GOOGL  |               — |          +28.1% |     — |
| JPM    |               — |           +1.9% |     — |

##### Avg Return Comparison — Scenario C vs Baseline — Hold 40d

| Ticker | Scenario Avg Ret | Baseline Avg Ret | Delta |
|--------|-----------------|-----------------|-------|
| AAPL   |               — |          +10.9% |     — |
| MSFT   |           -1.9% |          -12.9% | +10.9% |
| NVDA   |               — |          +11.2% |     — |
| AMZN   |           +7.5% |           +6.6% | +0.9% |
| META   |          +10.1% |           -1.6% | +11.7% |
| GOOGL  |               — |          +34.9% |     — |
| JPM    |               — |           +3.0% |     — |

---

## Summary & Interpretation

### Scenario A — Rejected + SRP Bullish

- Signals fired: **2**
- Recovery: SPY recovered in 25.5d avg (100.0% of the time within 80 bars).
- Best SPY hold: 40d (avg +3.6%, hit +100.0%).
- Best stock hold: 40d (avg +7.5%, hit +85.7%, delta vs baseline +4.5%).

### Scenario B — Rejected + Rising Score

- Signals fired: **9**
- Recovery: SPY recovered in 49.8d avg (100.0% of the time within 80 bars).
- Best SPY hold: 40d (avg +2.6%, hit +88.9%).
- Best stock hold: 10d (avg +3.8%, hit +78.6%, delta vs baseline +2.6%).

### Scenario C — Combined (A & B)

- Signals fired: **1**
- Recovery: SPY recovered in 50.0d avg (100.0% of the time within 80 bars).
- Best SPY hold: 40d (avg +4.3%, hit +100.0%).
- Best stock hold: 20d (avg +6.0%, hit +100.0%, delta vs baseline +3.8%).

---

_Generated by backtest/srp_pap_backtest_v5.py_