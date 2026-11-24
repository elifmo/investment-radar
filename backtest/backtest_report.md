# Backtest Report
**Period:** 2023-01-01 → 2026-06-15
**Universe:** 175 US tickers (watchlist at backtest time; production pipeline now scans **521**)
**Method:** Weekly walk-forward, first trading day of each week
**Note:** volume_ratio set to 1.0 (neutral proxy — event filter not applied in backtest)

---

## Decision Outcome (Base: RS ≥ 70, Drop ≤ −20%)

| Decision  | Count | 1mo Ret | 1mo Alpha | 3mo Ret | 3mo Alpha | Win% |
|-----------|-------|---------|-----------|---------|-----------|------|
| BUY       |  3816 |   +3.0% |   +1.3% |   +6.0% |   +1.5% |   51% |
| BUY_SMALL |   128 |   +5.4% |   +3.3% |  +33.6% |  +24.7% |   52% |
| WATCH     | 21287 |   +1.6% |   +0.1% |   +5.6% |   +0.9% |   47% |
| SKIP      |   660 |   +4.7% |   +2.7% |  +12.1% |   +5.5% |   56% |

> Alpha = ticker return − SPY return over same window.
> Win% = % of signals where 1mo alpha > 0.

---

## Threshold Sensitivity (9 combinations)

| RS ≥ | Drop ≤ | BUY # | BUY Alpha 1mo | BUY Win% | BUY_SMALL # | BUY_SMALL Alpha 1mo |
|------|--------|-------|---------------|----------|-------------|---------------------|
| 60 | -15% | 5105 | +1.0% | 50% | 276 | +2.7% |
| 60 | -20% | 5105 | +1.0% | 50% | 128 | +3.3% |
| 60 | -25% | 5105 | +1.0% | 50% | 66 | +2.0% |
| 70 | -15% | 3816 | +1.3% | 51% | 276 | +2.7% |
| 70 | -20% | 3816 | +1.3% | 51% | 128 | +3.3% |
| 70 | -25% | 3816 | +1.3% | 51% | 66 | +2.0% |
| 80 | -15% | 2536 | +1.8% | 52% | 276 | +2.7% |
| 80 | -20% | 2536 | +1.8% | 52% | 128 | +3.3% |
| 80 | -25% | 2536 | +1.8% | 52% | 66 | +2.0% |

---

## Recommendation

Best BUY alpha: **RS ≥ 80, Drop ≤ -15%**

Update `config/factors.yaml` → `decision.rs_threshold` and `decision.drop_threshold`
if these differ from the current defaults (70 / −20%).

---

## RS Acceleration — Delta Threshold Sweep

_(Does raising the RS-delta cutoff improve signal quality?)_

| Scenario | BUY total | Accel-only BUY | Accel alpha 3mo | Accel Win% | All-BUY alpha 3mo |
|----------|-----------|----------------|-----------------|------------|-------------------|
| Base (RS=70, no accel)       |      3567 |              0 |               — |          — |              +1.5% |
| RS Accel Δ≥20                |      4892 |           2898 |           +0.9% |        48% |              +1.2% |
| RS Accel Δ≥30                |      4279 |           1892 |           +0.9% |        47% |              +1.3% |
| RS Accel Δ≥35                |      4066 |           1505 |           +1.0% |        46% |              +1.3% |
| RS Accel Δ≥40                |      3889 |           1176 |           +1.2% |        45% |              +1.4% |
| RS Accel Δ≥50                |      3683 |            711 |           +1.8% |        45% |              +1.4% |

### Accel-only BUY trades — top performers per threshold

#### RS Accel Δ≥20  (n=2898, avg=+0.9%, win=48%)

Top 5:
| Date       | Ticker | Sector                  | RS | Δ RS | Grade | Alpha |
|------------|--------|-------------------------|----|------|-------|-------|
| 2026-03-09 | MRVL   | Technology              | 95 |  +70 | C     | +214.2% |
| 2024-01-16 | SMCI   | Technology              | 96 |  +24 | B     | +177.8% |
| 2026-03-09 | DELL   | Technology              | 99 |  +71 | B     | +176.8% |
| 2026-03-16 | MRVL   | Technology              | 95 |  +65 | C     | +167.2% |
| 2026-03-16 | ARM    | Technology              | 95 |  +31 | C     | +143.9% |

Bottom 5:
| Date       | Ticker | Sector                  | RS | Δ RS | Grade | Alpha |
|------------|--------|-------------------------|----|------|-------|-------|
| 2024-04-08 | OKLO   | Utilities               | 98 |  +85 | B     |  -55.3% |
| 2024-06-17 | SMCI   | Technology              | 84 |  +49 | B     |  -52.7% |
| 2026-01-12 | OKLO   | Utilities               | 89 |  +87 | C     |  -51.5% |
| 2025-10-13 | SMCI   | Technology              | 93 |  +30 | C     |  -49.7% |
| 2025-10-06 | SMCI   | Technology              | 92 |  +90 | C     |  -48.2% |

#### RS Accel Δ≥30  (n=1892, avg=+0.9%, win=47%)

Top 5:
| Date       | Ticker | Sector                  | RS | Δ RS | Grade | Alpha |
|------------|--------|-------------------------|----|------|-------|-------|
| 2026-03-09 | MRVL   | Technology              | 95 |  +70 | C     | +214.2% |
| 2026-03-09 | DELL   | Technology              | 99 |  +71 | B     | +176.8% |
| 2026-03-16 | MRVL   | Technology              | 95 |  +65 | C     | +167.2% |
| 2026-03-16 | ARM    | Technology              | 95 |  +31 | C     | +143.9% |
| 2025-05-12 | LEU    | Energy                  | 99 |  +90 | C     | +139.3% |

Bottom 5:
| Date       | Ticker | Sector                  | RS | Δ RS | Grade | Alpha |
|------------|--------|-------------------------|----|------|-------|-------|
| 2024-04-08 | OKLO   | Utilities               | 98 |  +85 | B     |  -55.3% |
| 2024-06-17 | SMCI   | Technology              | 84 |  +49 | B     |  -52.7% |
| 2026-01-12 | OKLO   | Utilities               | 89 |  +87 | C     |  -51.5% |
| 2025-10-13 | SMCI   | Technology              | 93 |  +30 | C     |  -49.7% |
| 2025-10-06 | SMCI   | Technology              | 92 |  +90 | C     |  -48.2% |

#### RS Accel Δ≥35  (n=1505, avg=+1.0%, win=46%)

Top 5:
| Date       | Ticker | Sector                  | RS | Δ RS | Grade | Alpha |
|------------|--------|-------------------------|----|------|-------|-------|
| 2026-03-09 | MRVL   | Technology              | 95 |  +70 | C     | +214.2% |
| 2026-03-09 | DELL   | Technology              | 99 |  +71 | B     | +176.8% |
| 2026-03-16 | MRVL   | Technology              | 95 |  +65 | C     | +167.2% |
| 2025-05-12 | LEU    | Energy                  | 99 |  +90 | C     | +139.3% |
| 2026-03-16 | DELL   | Technology              | 99 |  +55 | B     | +128.3% |

Bottom 5:
| Date       | Ticker | Sector                  | RS | Δ RS | Grade | Alpha |
|------------|--------|-------------------------|----|------|-------|-------|
| 2024-04-08 | OKLO   | Utilities               | 98 |  +85 | B     |  -55.3% |
| 2024-06-17 | SMCI   | Technology              | 84 |  +49 | B     |  -52.7% |
| 2026-01-12 | OKLO   | Utilities               | 89 |  +87 | C     |  -51.5% |
| 2025-10-06 | SMCI   | Technology              | 92 |  +90 | C     |  -48.2% |
| 2025-04-21 | CPRT   | Industrials             | 98 |  +52 | B     |  -44.4% |

#### RS Accel Δ≥40  (n=1176, avg=+1.2%, win=45%)

Top 5:
| Date       | Ticker | Sector                  | RS | Δ RS | Grade | Alpha |
|------------|--------|-------------------------|----|------|-------|-------|
| 2026-03-09 | MRVL   | Technology              | 95 |  +70 | C     | +214.2% |
| 2026-03-09 | DELL   | Technology              | 99 |  +71 | B     | +176.8% |
| 2026-03-16 | MRVL   | Technology              | 95 |  +65 | C     | +167.2% |
| 2025-05-12 | LEU    | Energy                  | 99 |  +90 | C     | +139.3% |
| 2026-03-16 | DELL   | Technology              | 99 |  +55 | B     | +128.3% |

Bottom 5:
| Date       | Ticker | Sector                  | RS | Δ RS | Grade | Alpha |
|------------|--------|-------------------------|----|------|-------|-------|
| 2024-04-08 | OKLO   | Utilities               | 98 |  +85 | B     |  -55.3% |
| 2024-06-17 | SMCI   | Technology              | 84 |  +49 | B     |  -52.7% |
| 2026-01-12 | OKLO   | Utilities               | 89 |  +87 | C     |  -51.5% |
| 2025-10-06 | SMCI   | Technology              | 92 |  +90 | C     |  -48.2% |
| 2025-04-21 | CPRT   | Industrials             | 98 |  +52 | B     |  -44.4% |

#### RS Accel Δ≥50  (n=711, avg=+1.8%, win=45%)

Top 5:
| Date       | Ticker | Sector                  | RS | Δ RS | Grade | Alpha |
|------------|--------|-------------------------|----|------|-------|-------|
| 2026-03-09 | MRVL   | Technology              | 95 |  +70 | C     | +214.2% |
| 2026-03-09 | DELL   | Technology              | 99 |  +71 | B     | +176.8% |
| 2026-03-16 | MRVL   | Technology              | 95 |  +65 | C     | +167.2% |
| 2025-05-12 | LEU    | Energy                  | 99 |  +90 | C     | +139.3% |
| 2026-03-16 | DELL   | Technology              | 99 |  +55 | B     | +128.3% |

Bottom 5:
| Date       | Ticker | Sector                  | RS | Δ RS | Grade | Alpha |
|------------|--------|-------------------------|----|------|-------|-------|
| 2024-04-08 | OKLO   | Utilities               | 98 |  +85 | B     |  -55.3% |
| 2026-01-12 | OKLO   | Utilities               | 89 |  +87 | C     |  -51.5% |
| 2025-10-06 | SMCI   | Technology              | 92 |  +90 | C     |  -48.2% |
| 2025-04-21 | CPRT   | Industrials             | 98 |  +52 | B     |  -44.4% |
| 2025-09-22 | ORCL   | Technology              | 95 |  +82 | C     |  -44.2% |


---

## Year-by-Year Signal Quality (3mo Alpha)

| Year | Decision  | Signals | Avg 3mo Alpha | Win% |
|------|-----------|---------|---------------|------|
| 2023 | BUY       |     511 |          +2.2% |   53% |
| 2023 | BUY_SMALL |       6 |         +14.3% |   67% |
| 2024 | BUY       |    1377 |          +0.0% |   43% |
| 2024 | BUY_SMALL |      46 |         +19.8% |   52% |
| 2025 | BUY       |    1358 |          +1.5% |   48% |
| 2025 | BUY_SMALL |      70 |         +28.7% |   66% |
| 2026 | BUY       |     321 |          +6.3% |   47% |
| 2026 | BUY_SMALL |       5 |         +26.7% |   40% |


---

## Per-Sector Breakdown (BUY + BUY_SMALL signals)

| Sector | Signals | BUY | BUY_SMALL | 3mo Ret | 3mo Alpha | Win% |
|--------|---------|-----|-----------|---------|-----------|------|
| Utilities                  |     198 | 174 |        24 |   +19.2% |     +13.5% |   46% |
| Technology                 |    1063 | 1030 |        33 |   +10.1% |      +6.3% |   56% |
| Financials                 |     464 | 448 |        16 |    +8.9% |      +4.2% |   51% |
| Communication Services     |     144 | 144 |         0 |    +8.3% |      +3.4% |   53% |
| Energy                     |     187 | 181 |         6 |    +5.3% |      +1.3% |   43% |
| Real Estate                |     112 | 110 |         2 |    +5.5% |      -0.3% |   41% |
| Health Care                |     493 | 466 |        27 |    +1.9% |      -1.8% |   41% |
| Industrials                |     436 | 426 |        10 |    +3.6% |      -2.0% |   41% |
| Consumer Discretionary     |     312 | 304 |         8 |    +2.6% |      -2.3% |   38% |
| Materials                  |      67 |  67 |         0 |    +1.9% |      -3.9% |   33% |
| Consumer Staples           |     218 | 217 |         1 |    +3.4% |      -4.2% |   38% |


---

## Individual Trade Analysis

### Best 30 BUY Trades (by 3mo Alpha)

_These are the clearest proof the system works: all 3 conditions aligned._

| Date       | Ticker | Sector                     | 3mo Ret  | 3mo Alpha | Why / Signals |
|------------|--------|----------------------------|----------|-----------|---------------|
| 2024-09-03 | OKLO   | Utilities                  |  +294.3% |  +285.1% | RS=3 low (dip)  Grade=B ✓  Sector_long=LAGGING |
| 2026-03-09 | MRVL   | Technology                 |  +225.7% |  +214.2% | RS=95 ✓  Grade=C ✓  Sector=LEADING ✓ |
| 2024-08-26 | OKLO   | Utilities                  |  +213.7% |  +208.1% | RS=8 low (dip)  Grade=B ✓  Sector_long=WEAKENING |
| 2025-04-21 | OKLO   | Utilities                  |  +229.4% |  +206.8% | RS=9 low (dip)  Grade=B ✓  Sector_long=WEAKENING |
| 2024-09-16 | OKLO   | Utilities                  |  +196.6% |  +189.2% | RS=2 low (dip)  Grade=B ✓  Sector_long=LEADING |
| 2024-01-16 | SMCI   | Technology                 |  +187.2% |  +177.8% | RS=96 ✓  Grade=B ✓  Sector=LEADING ✓ |
| 2026-03-09 | DELL   | Technology                 |  +188.3% |  +176.8% | RS=99 ✓  Grade=B ✓  Sector=LEADING ✓ |
| 2025-07-21 | OKLO   | Utilities                  |  +178.6% |  +173.0% | RS=96 ✓  Grade=C ✓  Sector=IMPROVING ✓ |
| 2026-03-16 | MRVL   | Technology                 |  +176.0% |  +167.2% | RS=95 ✓  Grade=C ✓  Sector=LEADING ✓ |
| 2026-03-09 | AMD    | Technology                 |  +167.7% |  +156.2% | RS=5 low (dip)  Grade=A ✓  Sector_long=LEADING |
| 2025-03-31 | OKLO   | Utilities                  |  +158.2% |  +148.5% | RS=2 low (dip)  Grade=B ✓  Sector_long=WEAKENING |
| 2026-03-16 | ARM    | Technology                 |  +152.6% |  +143.9% | RS=95 ✓  Grade=C ✓  Sector=LEADING ✓ |
| 2025-04-07 | HOOD   | Financials                 |  +166.6% |  +142.2% | RS=11 low (dip)  Grade=B ✓  Sector_long=WEAKENING |
| 2026-03-09 | STX    | Technology                 |  +151.7% |  +140.2% | RS=78 ✓  Grade=C ✓  Sector=LEADING ✓ |
| 2025-05-12 | LEU    | Energy                     |  +148.1% |  +139.3% | RS=99 ✓  Grade=C ✓  Sector=IMPROVING ✓ |
| 2024-11-18 | OKLO   | Utilities                  |  +142.8% |  +138.5% | RS=99 ✓  Grade=B ✓  Sector=IMPROVING ✓ |
| 2025-03-17 | OKLO   | Utilities                  |  +143.0% |  +136.6% | RS=3 low (dip)  Grade=B ✓  Sector_long=LEADING |
| 2026-03-02 | ARM    | Technology                 |  +143.4% |  +133.8% | RS=91 ✓  Grade=C ✓  Sector=IMPROVING ✓ |
| 2025-04-14 | OKLO   | Utilities                  |  +148.7% |  +132.7% | RS=5 low (dip)  Grade=B ✓  Sector_long=WEAKENING |
| 2025-03-24 | LEU    | Energy                     |  +135.4% |  +131.3% | RS=3 low (dip)  Grade=B ✓  Sector_long=LEADING |
| 2026-03-16 | DELL   | Technology                 |  +137.0% |  +128.3% | RS=99 ✓  Grade=B ✓  Sector=LEADING ✓ |
| 2024-09-23 | OKLO   | Utilities                  |  +129.8% |  +123.8% | RS=71 ✓  Grade=B ✓  Sector=LEADING ✓ |
| 2025-04-07 | OKLO   | Utilities                  |  +145.0% |  +120.6% | RS=4 low (dip)  Grade=B ✓  Sector_long=LEADING |
| 2026-03-02 | STX    | Technology                 |  +129.8% |  +120.2% | RS=91 ✓  Grade=C ✓  Sector=IMPROVING ✓ |
| 2024-09-30 | PLTR   | Technology                 |  +121.5% |  +116.3% | RS=94 ✓  Grade=B ✓  Sector=LEADING ✓ |
| 2024-01-22 | SMCI   | Technology                 |  +120.1% |  +116.2% | RS=99 ✓  Grade=B ✓  Sector=LEADING ✓ |
| 2026-03-02 | MU     | Technology                 |  +125.1% |  +115.4% | RS=97 ✓  Grade=A ✓  Sector=IMPROVING ✓ |
| 2026-03-09 | WDC    | Technology                 |  +126.7% |  +115.2% | RS=83 ✓  Grade=B ✓  Sector=LEADING ✓ |
| 2024-11-04 | HOOD   | Financials                 |  +113.4% |  +108.1% | RS=88 ✓  Grade=B ✓  Sector=LEADING ✓ |
| 2025-03-31 | COIN   | Financials                 |  +117.8% |  +108.1% | RS=3 low (dip)  Grade=B ✓  Sector_long=WEAKENING |

### Worst 30 BUY Trades (by 3mo Alpha)

_These are signals where all conditions passed but return was still negative._

| Date       | Ticker | Sector                     | 3mo Ret  | 3mo Alpha | Why / Signals |
|------------|--------|----------------------------|----------|-----------|---------------|
| 2024-08-19 | SMCI   | Technology                 |   -65.2% |   -72.2% | RS=3 low (dip)  Grade=B ✓  Sector_long=IMPROVING |
| 2024-08-26 | SMCI   | Technology                 |   -49.7% |   -55.3% | RS=2 low (dip)  Grade=B ✓  Sector_long=IMPROVING |
| 2024-04-08 | OKLO   | Utilities                  |   -48.6% |   -55.3% | RS=98 ✓  Grade=B ✓  Sector=LEADING ✓ |
| 2024-06-17 | SMCI   | Technology                 |   -50.2% |   -52.7% | RS=84 ✓  Grade=B ✓  Sector=LEADING ✓ |
| 2026-01-12 | OKLO   | Utilities                  |   -53.4% |   -51.5% | RS=89 ✓  Grade=C ✓  Sector=IMPROVING ✓ |
| 2025-10-06 | OKLO   | Utilities                  |   -48.2% |   -50.0% | RS=99 ✓  Grade=C ✓  Sector=LEADING ✓ |
| 2025-10-13 | SMCI   | Technology                 |   -45.4% |   -49.7% | RS=93 ✓  Grade=C ✓  Sector=LEADING ✓ |
| 2025-10-06 | SMCI   | Technology                 |   -46.4% |   -48.2% | RS=92 ✓  Grade=C ✓  Sector=LEADING ✓ |
| 2024-04-29 | OKLO   | Utilities                  |   -41.7% |   -47.6% | RS=99 ✓  Grade=B ✓  Sector=LEADING ✓ |
| 2025-10-13 | OKLO   | Utilities                  |   -42.9% |   -47.2% | RS=99 ✓  Grade=C ✓  Sector=LEADING ✓ |
| 2025-10-20 | OKLO   | Utilities                  |   -42.5% |   -45.9% | RS=99 ✓  Grade=C ✓  Sector=LEADING ✓ |
| 2025-04-21 | CPRT   | Industrials                |   -21.9% |   -44.4% | RS=98 ✓  Grade=B ✓  Sector=LEADING ✓ |
| 2025-09-22 | ORCL   | Technology                 |   -42.4% |   -44.2% | RS=95 ✓  Grade=C ✓  Sector=LEADING ✓ |
| 2025-11-03 | SMCI   | Technology                 |   -42.6% |   -44.2% | RS=71 ✓  Grade=C ✓  Sector=LEADING ✓ |
| 2024-04-22 | OKLO   | Utilities                  |   -32.7% |   -43.6% | RS=98 ✓  Grade=B ✓  Sector=LEADING ✓ |
| 2024-06-17 | MU     | Technology                 |   -41.0% |   -43.5% | RS=97 ✓  Grade=B ✓  Sector=LEADING ✓ |
| 2025-10-06 | COIN   | Financials                 |   -41.4% |   -43.3% | RS=88 ✓  Grade=C ✓  Sector=IMPROVING ✓ |
| 2025-10-13 | ORCL   | Technology                 |   -38.4% |   -42.7% | RS=95 ✓  Grade=C ✓  Sector=LEADING ✓ |
| 2024-12-16 | TSLA   | Consumer Discretionary     |   -48.6% |   -42.4% | RS=99 ✓  Grade=B ✓  Sector=LEADING ✓ |
| 2025-09-22 | OKLO   | Utilities                  |   -40.5% |   -42.3% | RS=99 ✓  Grade=C ✓  Sector=IMPROVING ✓ |
| 2024-10-07 | SMCI   | Technology                 |   -37.1% |   -40.4% | RS=2 low (dip)  Grade=B ✓  Sector_long=LEADING |
| 2026-01-20 | LEU    | Energy                     |   -36.1% |   -39.9% | RS=92 ✓  Grade=C ✓  Sector=LEADING ✓ |
| 2026-01-12 | LEU    | Energy                     |   -41.7% |   -39.8% | RS=93 ✓  Grade=C ✓  Sector=LEADING ✓ |
| 2024-05-28 | DELL   | Technology                 |   -34.2% |   -39.5% | RS=98 ✓  Grade=B ✓  Sector=LEADING ✓ |
| 2025-11-03 | ARM    | Technology                 |   -37.5% |   -39.1% | RS=90 ✓  Grade=A ✓  Sector=LEADING ✓ |
| 2025-10-13 | ARM    | Technology                 |   -34.2% |   -38.5% | RS=90 ✓  Grade=A ✓  Sector=LEADING ✓ |
| 2025-05-05 | CPRT   | Industrials                |   -25.7% |   -38.2% | RS=94 ✓  Grade=B ✓  Sector=LEADING ✓ |
| 2025-04-07 | PCG    | Utilities                  |   -13.3% |   -37.7% | RS=92 ✓  Grade=B ✓  Sector=LEADING ✓ |
| 2024-06-03 | OKLO   | Utilities                  |   -31.2% |   -37.3% | RS=2 low (dip)  Grade=B ✓  Sector_long=WEAKENING |
| 2024-12-16 | MRVL   | Technology                 |   -43.6% |   -37.3% | RS=96 ✓  Grade=B ✓  Sector=LEADING ✓ |

### Top 40 Missed Opportunities (WATCH/SKIP that performed well)

_Stocks that would have been big winners — but the system held back. Column 'Why' shows which condition blocked the BUY._

| Date       | Ticker | Sector                     | 3mo Ret  | 3mo Alpha | Why / Signals |
|------------|--------|----------------------------|----------|-----------|---------------|
| 2023-12-11 | SMCI   | Technology                 |  +334.7% |  +323.5% | RS=31 ✗ (weak, no big drop) [WATCH] |
| 2025-04-21 | LEU    | Energy                     |  +273.4% |  +250.9% | RS=9 low + Sector=LAGGING weak [SKIP] |
| 2024-09-09 | OKLO   | Utilities                  |  +256.3% |  +245.4% | RS=3 low + Sector=WEAKENING weak [SKIP] |
| 2024-01-02 | SMCI   | Technology                 |  +253.8% |  +242.8% | RS=16 ✗ (weak, no big drop) [WATCH] |
| 2026-03-09 | ARM    | Technology                 |  +250.1% |  +238.6% | RS=55 ✗ (weak, no big drop) [WATCH] |
| 2025-04-28 | LEU    | Energy                     |  +244.4% |  +228.9% | RS=19 ✗ (weak, no big drop) [WATCH] |
| 2023-12-04 | SMCI   | Technology                 |  +240.0% |  +227.2% | RS=34 ✗ (weak, no big drop) [WATCH] |
| 2023-12-18 | SMCI   | Technology                 |  +231.7% |  +223.4% | RS=92 ✓  but Sector=WEAKENING ✗ (not LEADING/IMPROVING) [WATCH] |
| 2023-12-26 | SMCI   | Technology                 |  +230.5% |  +220.6% | RS=53 ✗ (weak, no big drop) [WATCH] |
| 2024-08-05 | OKLO   | Utilities                  |  +225.1% |  +212.3% | RS=18 ✗ (weak, no big drop) [WATCH] |
| 2024-08-19 | OKLO   | Utilities                  |  +210.7% |  +203.7% | RS=32 ✗ (weak, no big drop) [WATCH] |
| 2025-04-14 | LEU    | Energy                     |  +218.2% |  +202.2% | RS=5 low + Sector=LAGGING weak [SKIP] |
| 2024-01-08 | SMCI   | Technology                 |  +199.1% |  +190.7% | RS=77 ✓  but Sector=LAGGING ✗ (not LEADING/IMPROVING) [WATCH] |
| 2025-04-28 | OKLO   | Utilities                  |  +204.6% |  +189.1% | RS=8 ✗ (weak, no big drop) [WATCH] |
| 2025-05-05 | OKLO   | Utilities                  |  +200.7% |  +188.2% | RS=20 ✗ (weak, no big drop) [WATCH] |
| 2025-05-05 | LEU    | Energy                     |  +200.6% |  +188.1% | RS=30 ✗ (weak, no big drop) [WATCH] |
| 2024-09-30 | OKLO   | Utilities                  |  +191.8% |  +186.7% | RS=71 ✓  but Sector=WEAKENING ✗ (not LEADING/IMPROVING) [WATCH] |
| 2023-11-27 | SMCI   | Technology                 |  +196.2% |  +184.0% | RS=28 ✗ (weak, no big drop) [WATCH] |
| 2024-08-12 | OKLO   | Utilities                  |  +191.9% |  +183.4% | RS=11 ✗ (weak, no big drop) [WATCH] |
| 2025-04-07 | LEU    | Energy                     |  +199.9% |  +175.6% | RS=5 low + Sector=LAGGING weak [SKIP] |
| 2023-11-13 | SMCI   | Technology                 |  +189.4% |  +175.1% | RS=6 ✗ (weak, no big drop) [WATCH] |
| 2024-08-05 | LEU    | Energy                     |  +187.7% |  +174.9% | RS=15 ✗ (weak, no big drop) [WATCH] |
| 2025-03-31 | LEU    | Energy                     |  +181.2% |  +171.5% | RS=2 low + Sector=LEADING weak [SKIP] |
| 2025-05-12 | OKLO   | Utilities                  |  +174.9% |  +166.2% | RS=96 ✓  but Sector=LAGGING ✗ (not LEADING/IMPROVING) [WATCH] |
| 2026-03-09 | MU     | Technology                 |  +177.4% |  +165.9% | RS=44 ✗ (weak, no big drop) [WATCH] |
| 2026-03-02 | INTC   | Technology                 |  +167.6% |  +158.0% | RS=31 ✗ (weak, no big drop) [WATCH] |
| 2024-11-18 | SMCI   | Technology                 |  +159.1% |  +154.7% | RS=2 low + Sector=LAGGING weak [SKIP] |
| 2023-11-20 | SMCI   | Technology                 |  +163.7% |  +153.3% | RS=45 ✗ (weak, no big drop) [WATCH] |
| 2024-10-14 | OKLO   | Utilities                  |  +151.4% |  +151.7% | RS=99 ✓  but Sector=LAGGING ✗ (not LEADING/IMPROVING) [WATCH] |
| 2026-02-17 | INTC   | Technology                 |  +160.5% |  +151.5% | RS=83 ✓  but Sector=LAGGING ✗ (not LEADING/IMPROVING) [WATCH] |
| 2026-02-23 | INTC   | Technology                 |  +154.0% |  +146.1% | RS=54 ✗ (weak, no big drop) [WATCH] |
| 2025-04-21 | HOOD   | Financials                 |  +164.6% |  +142.0% | RS=50 ✗ (weak, no big drop) [WATCH] |
| 2026-03-02 | AMD    | Technology                 |  +149.5% |  +139.9% | RS=18 ✗ (weak, no big drop) [WATCH] |
| 2026-03-02 | MRVL   | Technology                 |  +145.9% |  +136.2% | RS=45 ✗ (weak, no big drop) [WATCH] |
| 2026-03-09 | INTC   | Technology                 |  +147.3% |  +135.8% | RS=55 ✗ (weak, no big drop) [WATCH] |
| 2023-10-02 | COIN   | Financials                 |  +146.0% |  +134.0% | RS=79 ✓  but Sector=WEAKENING ✗ (not LEADING/IMPROVING) [WATCH] |
| 2024-07-29 | OKLO   | Utilities                  |  +137.0% |  +129.6% | RS=9 ✗ (weak, no big drop) [WATCH] |
| 2024-08-19 | LEU    | Energy                     |  +134.3% |  +127.3% | RS=37 ✗ (weak, no big drop) [WATCH] |
| 2025-06-30 | OKLO   | Utilities                  |  +134.3% |  +127.0% | RS=98 ✓  but Sector=LAGGING ✗ (not LEADING/IMPROVING) [WATCH] |
| 2026-03-16 | INTC   | Technology                 |  +133.9% |  +125.2% | RS=52 ✗ (weak, no big drop) [WATCH] |


---

## Per-Ticker Breakdown (BUY + BUY_SMALL, ≥2 signals)

### Top 25 — highest 3mo alpha

| Ticker | Signals | 3mo Ret | 3mo Alpha | Win% | Decision types |
|--------|---------|---------|-----------|------|----------------|
| OKLO   |      44 |   +55.1% |     +50.1% |   64% | BUY, BUY_SMALL |
| WDC    |      42 |   +35.0% |     +31.3% |   79% | BUY, BUY_SMALL |
| HOOD   |      41 |   +34.9% |     +30.8% |   83% | BUY, BUY_SMALL |
| STX    |      40 |   +29.3% |     +25.0% |   82% | BUY |
| MU     |      39 |   +28.4% |     +24.3% |   77% | BUY, BUY_SMALL |
| PLTR   |      37 |   +28.8% |     +24.1% |   73% | BUY |
| COIN   |      38 |   +25.1% |     +18.2% |   58% | BUY, BUY_SMALL |
| NVDA   |      24 |   +21.1% |     +15.6% |   71% | BUY |
| DELL   |      31 |   +19.5% |     +14.1% |   61% | BUY, BUY_SMALL |
| VST    |      39 |   +17.2% |     +12.7% |   64% | BUY, BUY_SMALL |
| AMAT   |      28 |   +13.7% |     +11.3% |   75% | BUY |
| LEU    |      35 |   +13.8% |     +10.9% |   57% | BUY, BUY_SMALL |
| MPWR   |      27 |   +15.1% |     +10.6% |   81% | BUY |
| LRCX   |      32 |   +11.9% |      +9.2% |   75% | BUY, BUY_SMALL |
| CEG    |      42 |   +13.9% |      +8.9% |   50% | BUY, BUY_SMALL |
| CAT    |      27 |   +12.8% |      +8.8% |   70% | BUY |
| TSM    |      31 |   +13.1% |      +8.7% |   84% | BUY |
| AVGO   |      30 |   +13.8% |      +8.5% |   70% | BUY |
| KLAC   |      29 |   +11.3% |      +8.0% |   79% | BUY |
| GOOG   |      30 |   +12.8% |      +7.9% |   53% | BUY |
| GOOGL  |      30 |   +12.8% |      +7.9% |   57% | BUY |
| AMD    |      23 |   +13.4% |      +7.8% |   52% | BUY, BUY_SMALL |
| MRVL   |      26 |   +10.5% |      +7.8% |   27% | BUY, BUY_SMALL |
| ADI    |      19 |    +9.9% |      +7.2% |   68% | BUY |
| BMY    |      19 |    +8.5% |      +7.2% |   79% | BUY |

### Bottom 25 — lowest 3mo alpha

| Ticker | Signals | 3mo Ret | 3mo Alpha | Win% | Decision types |
|--------|---------|---------|-----------|------|----------------|
| ITW    |       4 |   -11.5% |     -19.3% |    0% | BUY |
| CPRT   |      19 |    -6.6% |     -14.5% |    5% | BUY, BUY_SMALL |
| PG     |       6 |    -0.9% |     -13.3% |   17% | BUY |
| ACN    |      14 |   -10.7% |     -11.3% |   21% | BUY, BUY_SMALL |
| ZTS    |      13 |    -4.8% |     -11.3% |   15% | BUY |
| PEP    |      13 |    -3.2% |     -10.7% |    8% | BUY |
| CRM    |      14 |   -11.5% |     -10.2% |   14% | BUY |
| MCD    |      18 |    -2.1% |     -10.1% |   11% | BUY |
| DDOG   |      23 |    -6.4% |      -9.9% |   26% | BUY, BUY_SMALL |
| STZ    |      11 |    -3.0% |      -9.9% |   18% | BUY, BUY_SMALL |
| PCG    |      12 |    -2.6% |      -9.6% |   17% | BUY, BUY_SMALL |
| CARR   |      15 |    -3.1% |      -9.6% |   13% | BUY |
| EOG    |      13 |    -7.5% |      -9.2% |    0% | BUY |
| CL     |      14 |    +2.6% |      -9.1% |   21% | BUY |
| LOW    |      10 |    -4.6% |      -8.9% |   10% | BUY |
| KMB    |      10 |    +0.3% |      -8.9% |   30% | BUY |
| MDLZ   |      13 |    +0.1% |      -8.8% |   23% | BUY |
| AZO    |      16 |    -2.4% |      -8.8% |   12% | BUY |
| BRK-B  |      10 |    -0.6% |      -8.1% |    0% | BUY |
| FCX    |      12 |    -2.1% |      -8.1% |   33% | BUY |
| EMR    |      24 |    -4.2% |      -8.1% |   12% | BUY |
| VRTX   |      15 |    -2.5% |      -7.9% |   13% | BUY |
| A      |      25 |    -4.4% |      -7.8% |   16% | BUY, BUY_SMALL |
| SHW    |      11 |    -0.2% |      -7.6% |   18% | BUY |
| NXPI   |      15 |    -5.5% |      -7.4% |   20% | BUY |

### Full ticker list (sorted by alpha)

| Ticker | Signals | 3mo Ret | 3mo Alpha | Win% |
|--------|---------|---------|-----------|------|
| OKLO   |      44 |   +55.1% |     +50.1% |   64% |
| WDC    |      42 |   +35.0% |     +31.3% |   79% |
| HOOD   |      41 |   +34.9% |     +30.8% |   83% |
| STX    |      40 |   +29.3% |     +25.0% |   82% |
| MU     |      39 |   +28.4% |     +24.3% |   77% |
| PLTR   |      37 |   +28.8% |     +24.1% |   73% |
| COIN   |      38 |   +25.1% |     +18.2% |   58% |
| NVDA   |      24 |   +21.1% |     +15.6% |   71% |
| DELL   |      31 |   +19.5% |     +14.1% |   61% |
| VST    |      39 |   +17.2% |     +12.7% |   64% |
| AMAT   |      28 |   +13.7% |     +11.3% |   75% |
| LEU    |      35 |   +13.8% |     +10.9% |   57% |
| MPWR   |      27 |   +15.1% |     +10.6% |   81% |
| LRCX   |      32 |   +11.9% |      +9.2% |   75% |
| CEG    |      42 |   +13.9% |      +8.9% |   50% |
| CAT    |      27 |   +12.8% |      +8.8% |   70% |
| TSM    |      31 |   +13.1% |      +8.7% |   84% |
| AVGO   |      30 |   +13.8% |      +8.5% |   70% |
| KLAC   |      29 |   +11.3% |      +8.0% |   79% |
| GOOG   |      30 |   +12.8% |      +7.9% |   53% |
| GOOGL  |      30 |   +12.8% |      +7.9% |   57% |
| AMD    |      23 |   +13.4% |      +7.8% |   52% |
| MRVL   |      26 |   +10.5% |      +7.8% |   27% |
| ADI    |      19 |    +9.9% |      +7.2% |   68% |
| BMY    |      19 |    +8.5% |      +7.2% |   79% |
| V      |      12 |    +5.8% |      +6.8% |   75% |
| ARM    |      26 |   +10.6% |      +6.1% |   27% |
| MRK    |      17 |    +8.4% |      +5.8% |   59% |
| APH    |      30 |   +10.6% |      +5.6% |   60% |
| INTC   |      25 |    +8.8% |      +5.4% |   60% |
| C      |      33 |    +8.9% |      +5.0% |   61% |
| CCJ    |      37 |   +10.0% |      +5.0% |   62% |
| GE     |      24 |    +8.1% |      +4.9% |   62% |
| NFLX   |      30 |    +9.3% |      +4.7% |   63% |
| ANET   |      35 |    +8.2% |      +4.7% |   63% |
| TSLA   |      30 |    +7.4% |      +4.5% |   43% |
| GILD   |      26 |    +6.6% |      +3.8% |   58% |
| WELL   |      27 |    +9.4% |      +3.8% |   59% |
| TXN    |      16 |    +6.2% |      +3.6% |   56% |
| AAPL   |      15 |    +5.7% |      +3.5% |   67% |
| TEL    |      10 |    +7.9% |      +3.5% |   60% |
| TT     |      24 |   +10.4% |      +3.4% |   67% |
| JPM    |      20 |    +5.9% |      +3.3% |   70% |
| CRWD   |      40 |    +7.7% |      +3.2% |   48% |
| GS     |      28 |    +6.4% |      +2.9% |   61% |
| PM     |      24 |    +9.8% |      +2.9% |   54% |
| FTNT   |      27 |    +5.7% |      +2.8% |   48% |
| MAR    |      19 |    +4.6% |      +2.8% |   58% |
| EQIX   |      15 |    +6.8% |      +2.4% |   47% |
| PH     |      24 |    +6.3% |      +2.3% |   54% |
| IBM    |      29 |    +4.7% |      +2.2% |   66% |
| RTX    |      23 |    +6.9% |      +1.8% |   57% |
| UBER   |      26 |    +8.3% |      +1.8% |   46% |
| JNJ    |      18 |    +6.7% |      +1.8% |   56% |
| DE     |      17 |    +3.0% |      +1.7% |   65% |
| BSX    |      18 |    +4.4% |      +1.5% |   67% |
| MS     |      30 |    +4.4% |      +1.5% |   60% |
| KKR    |      32 |    +5.1% |      +1.4% |   66% |
| EW     |      18 |    +5.6% |      +1.4% |   56% |
| ISRG   |      23 |    +5.8% |      +1.3% |   52% |
| INTU   |      13 |    +7.9% |      +1.2% |   69% |
| LLY    |      24 |    +4.6% |      +1.1% |   42% |
| GM     |      33 |    +5.3% |      +1.0% |   55% |
| SPG    |      16 |    +7.7% |      +0.9% |   50% |
| VLO    |      25 |    +4.3% |      +0.4% |   48% |
| ON     |      20 |    +3.5% |      +0.4% |   50% |
| COST   |      24 |    +6.2% |      +0.4% |   54% |
| HCA    |      22 |    +5.6% |      +0.4% |   64% |
| CSCO   |      16 |    +2.1% |      -0.1% |   62% |
| AXP    |      25 |    +3.5% |      -0.2% |   40% |
| QCOM   |      18 |    +5.8% |      -0.2% |   61% |
| SLB    |      23 |    +1.9% |      -0.2% |   43% |
| CTAS   |      13 |   +10.7% |      -0.3% |   69% |
| ICE    |      11 |    +4.5% |      -0.3% |   55% |
| BAC    |      27 |    +5.1% |      -0.3% |   48% |
| CTVA   |      22 |    +3.7% |      -0.4% |   36% |
| GD     |      14 |    +6.9% |      -0.5% |   43% |
| TJX    |      23 |    +3.1% |      -0.6% |   61% |
| ETN    |      31 |    +4.5% |      -0.8% |   42% |
| CME    |      15 |    +5.0% |      -0.8% |   47% |
| BLK    |      21 |    +5.4% |      -0.9% |   43% |
| AMZN   |      29 |    +3.0% |      -1.1% |   45% |
| SMCI   |      31 |    +1.7% |      -1.3% |   35% |
| PSA    |      12 |    +6.1% |      -1.3% |   42% |
| IDXX   |      21 |    +4.1% |      -1.4% |   43% |
| MSFT   |      15 |    +5.2% |      -1.4% |   40% |
| TDG    |      22 |    +3.9% |      -1.5% |   45% |
| BKNG   |      25 |    +1.4% |      -1.6% |   32% |
| META   |      26 |    +2.3% |      -1.8% |   42% |
| ABBV   |      28 |    +2.2% |      -1.9% |   39% |
| DXCM   |      39 |    +2.0% |      -1.9% |   33% |
| WMT    |      25 |    +3.6% |      -1.9% |   44% |
| AON    |      16 |    +2.6% |      -2.0% |   38% |
| PAYX   |      10 |    +1.7% |      -2.1% |   30% |
| CSX    |       6 |    +5.1% |      -2.1% |   33% |
| MO     |      25 |    +5.1% |      -2.2% |   52% |
| SYK    |      10 |    -0.6% |      -2.2% |   40% |
| USB    |      23 |    +3.2% |      -2.3% |   35% |
| CB     |      17 |    +4.6% |      -2.4% |   35% |
| XOM    |      22 |    +3.0% |      -2.6% |   27% |
| CI     |       9 |    +3.8% |      -2.6% |   22% |
| PGR    |      18 |    +5.1% |      -2.7% |   39% |
| T      |      28 |    +3.3% |      -2.8% |   46% |
| PCAR   |      24 |    +2.1% |      -2.9% |   50% |
| LIN    |      13 |    +3.8% |      -3.0% |   31% |
| PANW   |      27 |    +1.7% |      -3.0% |   41% |
| NOW    |      24 |    +1.0% |      -3.2% |   46% |
| SNOW   |      23 |    -0.7% |      -3.3% |   30% |
| MNST   |      16 |    +4.0% |      -3.4% |   44% |
| MCO    |      15 |    +3.3% |      -3.4% |   33% |
| TMO    |      26 |    -0.6% |      -3.6% |   35% |
| MA     |      10 |    -0.5% |      -3.6% |   30% |
| NEE    |      18 |    +3.9% |      -3.6% |   33% |
| ECL    |       9 |    +2.4% |      -3.6% |   44% |
| OKE    |      17 |    +1.0% |      -3.7% |   29% |
| WM     |      16 |    +2.8% |      -3.8% |   25% |
| PLD    |      22 |    +0.5% |      -3.8% |   27% |
| UNH    |      19 |    +1.5% |      -3.8% |   37% |
| EXC    |      16 |    +0.8% |      -3.8% |   25% |
| UNP    |      12 |    +0.1% |      -3.9% |   17% |
| ABT    |      12 |    +0.7% |      -3.9% |   33% |
| ORCL   |      21 |    -0.3% |      -4.1% |   38% |
| MSI    |      26 |    +3.6% |      -4.2% |   50% |
| ELV    |      15 |    -3.7% |      -4.2% |   27% |
| DLR    |      20 |    +2.9% |      -4.2% |   20% |
| KR     |      18 |    +3.0% |      -4.2% |   33% |
| AIG    |      13 |    -0.7% |      -4.3% |    8% |
| ROP    |      11 |    +2.4% |      -4.8% |    9% |
| MCHP   |      17 |    -2.0% |      -5.0% |   47% |
| BDX    |      12 |    -7.3% |      -5.0% |   17% |
| SNPS   |      19 |    -0.4% |      -5.2% |   26% |
| AMGN   |      26 |    -0.1% |      -5.4% |   42% |
| SPGI   |       9 |    +2.9% |      -5.5% |   22% |
| CVX    |      15 |    -0.0% |      -5.5% |   27% |
| KO     |      19 |    +3.3% |      -5.6% |   32% |
| DUK    |      14 |    +2.6% |      -5.6% |   21% |
| NSC    |      15 |    -0.1% |      -5.7% |   13% |
| ABNB   |      14 |    -1.1% |      -5.7% |   29% |
| F      |      20 |    +0.5% |      -5.7% |   35% |
| HD     |      12 |    -1.2% |      -5.7% |   25% |
| SO     |      13 |    +2.4% |      -5.8% |   23% |
| ORLY   |      18 |    +1.0% |      -5.9% |   33% |
| FAST   |      23 |    +1.3% |      -6.0% |   30% |
| HON    |      12 |    -1.3% |      -6.0% |   25% |
| ADBE   |      10 |    -3.1% |      -6.0% |   40% |
| CDNS   |      19 |    -0.3% |      -6.2% |   37% |
| GEHC   |      19 |    -2.3% |      -6.6% |   37% |
| SBUX   |      19 |    +1.8% |      -6.8% |   16% |
| DHR    |      19 |    -5.1% |      -6.8% |   16% |
| WDAY   |      13 |    -5.2% |      -6.8% |   15% |
| NXPI   |      15 |    -5.5% |      -7.4% |   20% |
| SHW    |      11 |    -0.2% |      -7.6% |   18% |
| A      |      25 |    -4.4% |      -7.8% |   16% |
| VRTX   |      15 |    -2.5% |      -7.9% |   13% |
| EMR    |      24 |    -4.2% |      -8.1% |   12% |
| FCX    |      12 |    -2.1% |      -8.1% |   33% |
| BRK-B  |      10 |    -0.6% |      -8.1% |    0% |
| AZO    |      16 |    -2.4% |      -8.8% |   12% |
| MDLZ   |      13 |    +0.1% |      -8.8% |   23% |
| KMB    |      10 |    +0.3% |      -8.9% |   30% |
| LOW    |      10 |    -4.6% |      -8.9% |   10% |
| CL     |      14 |    +2.6% |      -9.1% |   21% |
| EOG    |      13 |    -7.5% |      -9.2% |    0% |
| CARR   |      15 |    -3.1% |      -9.6% |   13% |
| PCG    |      12 |    -2.6% |      -9.6% |   17% |
| STZ    |      11 |    -3.0% |      -9.9% |   18% |
| DDOG   |      23 |    -6.4% |      -9.9% |   26% |
| MCD    |      18 |    -2.1% |     -10.1% |   11% |
| CRM    |      14 |   -11.5% |     -10.2% |   14% |
| PEP    |      13 |    -3.2% |     -10.7% |    8% |
| ZTS    |      13 |    -4.8% |     -11.3% |   15% |
| ACN    |      14 |   -10.7% |     -11.3% |   21% |
| PG     |       6 |    -0.9% |     -13.3% |   17% |
| CPRT   |      19 |    -6.6% |     -14.5% |    5% |
| ITW    |       4 |   -11.5% |     -19.3% |    0% |


---

## Journey Analysis — Exit Strategy Comparison

_(Seçenek C: Combo = trail 15% OR last-10d underperform SPY by 5%+)_
_(max tracking = 90 days, stop-loss proxy = −5%)_

### BUY (3905 signals)

- Avg peak: **+23.5%** at day **51** (≈12.8 weeks)
- 61% of signals hit −5% at some point (avg on day 23)

**Peak timing:**

| Window | % of signals |
|--------|-------------|
| Days 1–10  (week 1-2)  | 12% |
| Days 11–20 (week 3-4)  | 8% |
| Days 21–45 (month 2)   | 18% |
| Days 46–90 (month 2-3) | 57% |

**Exit strategy comparison:**

| Strategy | Avg return | Exits avg day | Better than hold |
|----------|-----------|--------------|-----------------|
| Hold 60 days             | +6.0%  | 60  | —    |
| Trail 8%                 | +3.0%  | 29   | 44%  |
| Trail 15%                | +5.7%  | 42   | 49%  |
| **Combo C** (trail15+SPX) | **+3.0%** | 27   | 43%  |

**Combo C — exit reason breakdown:**

- Trail 15% triggered: 427 (11%)
- SPX-relative triggered: 3191 (82%)
- Held full period: 287 (7%)

### BUY_SMALL (130 signals)

- Avg peak: **+61.6%** at day **63** (≈15.7 weeks)
- 65% of signals hit −5% at some point (avg on day 12)

**Peak timing:**

| Window | % of signals |
|--------|-------------|
| Days 1–10  (week 1-2)  | 5% |
| Days 11–20 (week 3-4)  | 5% |
| Days 21–45 (month 2)   | 12% |
| Days 46–90 (month 2-3) | 76% |

**Exit strategy comparison:**

| Strategy | Avg return | Exits avg day | Better than hold |
|----------|-----------|--------------|-----------------|
| Hold 60 days             | +33.6%  | 60  | —    |
| Trail 8%                 | +3.7%  | 20   | 21%  |
| Trail 15%                | +9.9%  | 34   | 30%  |
| **Combo C** (trail15+SPX) | **+7.5%** | 22   | 25%  |

**Combo C — exit reason breakdown:**

- Trail 15% triggered: 36 (28%)
- SPX-relative triggered: 90 (69%)
- Held full period: 4 (3%)


---

*Generated by backtest/run_backtest.py*