# Investment Radar — System Architecture

**Last updated:** November 2026  
**Status:** Production (Firebase Hosting + Firestore + GitHub Actions)

Public overview: **[README.md](README.md)**

---

## Project Overview

Personal investment **decision support** system for two markets:

| Market | Universe | Dashboard |
|--------|----------|-------------|
| **USA** | ~523 tickers (S&P 500 + Nasdaq-100 extras + watchlist) | https://investment-radar-usa.web.app |
| **BIST** | ~93 tickers | https://investment-radar-bist.web.app |

**Purpose:** Surface setups with reasoning. The user decides. Not financial advice.

**Golden rules:**
- Do not treat dashboard labels as trade orders
- Do not predict prices
- Always show reasoning (triggers, scores, layers), not just numbers

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  GitHub Actions (.github/workflows/pipeline.yml)            │
│  BIST: 10:15 / 14:15 / 18:15 TR  ·  USA: 16:30 / 20:30 / 23:15 TR │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│  pipeline.py (src/)                                         │
│  ├─ Core: event_filter → detailed_scorer → top 10           │
│  ├─ USA enrichment: RS, sector, macro, quality, earnings  │
│  ├─ decision_engine → BUY / BUY_SMALL / WATCH / SKIP        │
│  ├─ oversold_scan (full universe, separate from top 10)     │
│  └─ Daily close (~23:15 TR): sector heatmap + ETF scan      │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│  Firestore (investment-radar-2c19d)                         │
│  Public read: daily_candidates, oversold_watch, heatmap…    │
│  Private (Auth): radar_items, signal_log, trade_entries     │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│  Firebase Hosting — frontend/usa/index.html (SPA)           │
└─────────────────────────────────────────────────────────────┘
```

**No Flask/API server.** Dashboard reads Firestore directly via Firebase JS SDK.

**Cost:** $0/month (GitHub Actions free tier + Firebase Spark plan).

---

## Pipeline — Core Funnel (all markets)

Configured in `config/factors.yaml`. USA tickers resolved by `usa_universe.py` (default: `sp500_nasdaq` ≈ 523 stocks). BIST uses `config/universe.yaml`.

**USA scan universe (default `sp500_nasdaq`):**

| Source | Count | Config |
|--------|-------|--------|
| S&P 500 | ~503 | `config/sp500.yaml` |
| Nasdaq-100 (not in S&P 500) | ~13 | `config/nasdaq100.yaml` |
| Watchlist extras | ~7 | `config/universe.yaml` |
| **Merged total** | **~523** | `src/usa_universe.py` |

Modes in `factors.yaml` → `scan.universe`: `watchlist` · `sp500` · `sp500_nasdaq` (default).

**Scan timeframe:** `4h` (default) — intraday 4-hour bars; daily OHLCV used for USA enrichment layers.

### Step 1 — Event filter (`event_filter.py`)

OR logic — any trigger passes the ticker forward:

| Trigger | Description |
|---------|-------------|
| `volume_spike` | Volume > 1.5× 20-bar average |
| `ema_crossover` | EMA5 crossed above EMA20 (last 2 bars) |
| `rsi_bounce` | RSI was < 35 in lookback, now rising |
| `price_move` | Bar change ≥ threshold (2% daily / 1% 4h) |
| `support_proximity` | Price within 2% of nearest support |
| `52w_high_break` | Close above prior 52-week high |

### Step 2 — Detailed scorer (`detailed_scorer.py`)

Weighted TA score 0–100 (`ta_engine.py`):

| Weight | Signal |
|--------|--------|
| 20 | EMA alignment (5>20>50) |
| 15 | RSI health (40–70) |
| 20 | Volume spike |
| 15 | Price momentum |
| 10 | Bollinger position |
| 10 | Support proximity |
| 10 | Breakout (volume-confirmed) |

**min_score:** from `config/factors.yaml` (currently 45; below → filtered out)  
**Output:** Top 10 candidates per market per run

Exported fields include: `score`, `rsi`, `stoch_k`, `stoch_d`, `support`, `resistance`, `volume_ratio`, `triggers`, `why_today`.

### Step 3 — USA enrichment + decision (USA only)

| Layer | Module | Output |
|-------|--------|--------|
| RS Rating | `layers/relative_strength.py` | `rs_rating`, `return_30d` |
| Sector rotation | `layers/sector_rotation.py` | `sector_short_status`, `sector_long_status` |
| Macro regime | `layers/macro_regime.py` | `RISK_ON` / `RISK_OFF` / `NEUTRAL` |
| Quality grade | `layers/quality_grade.py` | A / B / C / D |
| Earnings | `layers/earnings_calendar.py` | `days_to_earnings` |
| Decision | `decision_engine.py` | `BUY`, `BUY_SMALL`, `WATCH`, `SKIP` |

### Step 4 — Oversold Watch (USA only, parallel path)

`layers/oversold_scan.py` — scans the **full USA pipeline universe**, not just triggered stocks.

### Step 4b — Fib EMA radar (USA, Oversold tab)

`layers/fib_ema_radar.py` — Fib 61.8 / 78.6 pullback, then EMA5 above EMA20 on 4h; daily confirm must land within 1 day. Max age 5 days. Writes `fib_ema_radar/{market}_current`.

| Tier | Condition |
|------|-----------|
| `deep` | Stoch %K < 20 **and** RSI < 35 |
| `stoch` | Stoch %K < 20 only |
| `rsi` | RSI < 35 only |

Writes to `oversold_watch/current`. Used for limit-order zone (e.g. ORCL with Stoch 10) — **no bounce required**.

Thresholds in `config/factors.yaml` → `oversold:` block.

### Step 5 — Daily close reports (USA, ~23:15 TR)

On cron `15 20 * * 1-5` (or `--daily` / `RUN_DAILY_REPORTS=true`):

- **Sector heatmap** — pipeline universe + S&P 500 index map → `sector_heatmap/`
- **ETF scan** — VHYL, VUSA, SEMI, HEAL, DFEN, NUKL → `etf_scans/`
- Macro + sector status refresh even when no candidates pass filter

---

## Technical Indicators (`ta_engine.py`)

| Indicator | Used in |
|-----------|---------|
| EMA 5/20/50 | Scorer, event filter |
| RSI 14 | Scorer, event filter, oversold |
| **Stochastic** (%K 14, smooth 3, %D 3) | Oversold watch, candidate export |
| ATR, Bollinger | Scorer |
| Support/Resistance | Scorer, detail panel |
| Stop run detection | Signals (not in main funnel) |

---

## Firestore Collections

### Public (read-only from dashboard)

| Collection | Document pattern | Content |
|------------|------------------|---------|
| `daily_candidates` | `{date}_{ticker}` | Top candidates + USA enrichment |
| `scan_meta` | `{date}_{MARKET}` | Run timestamp, timeframe, session |
| `oversold_watch` | `current`, `{date}` | 15 deepest oversold tickers |
| `macro_regime` | `current` | RISK_ON / RISK_OFF / NEUTRAL |
| `quality_grades` | `{ticker}` | A/B/C/D per ticker |
| `sector_status` | `{etf}` | 11 GICS sectors short/long status |
| `sector_status_history` | `{week}_{etf}` | Weekly sector snapshots |
| `sector_heatmap` | `current`, `{date}`, `_index` | Full market heatmap |
| `etf_scans` | `current`, `{date}` | EUR ETF technical scan |
| `fib_ema_radar` | `{market}_current` | 4h Fib + EMA bounce radar |

### Private (Firebase Auth required)

| Collection | Owner field | Purpose |
|------------|-------------|---------|
| `radar_items` | `user_id` | Personal watchlist + thesis |
| `signal_log` | `user_id` | Future: signal audit |
| `recommendation_log` | `user_id` | Future: recommendation audit |
| `trade_entries` | `user_id` | Future: trade journal |

Rules: `firestore.rules`

---

## GitHub Actions Schedule

| Cron (UTC) | Turkey | Market | Notes |
|------------|--------|--------|-------|
| `15 7 * * 1-5` | 10:15 | BIST | Intraday scan |
| `15 11 * * 1-5` | 14:15 | BIST | Intraday scan |
| `15 15 * * 1-5` | 18:15 | BIST | Intraday scan |
| `30 13 * * 1-5` | 16:30 | USA | Intraday scan |
| `30 17 * * 1-5` | 20:30 | USA | Intraday scan |
| `15 20 * * 1-5` | 23:15 | USA | Intraday + **heatmap + ETF** (`--daily`) |

Manual run: Actions → workflow_dispatch → choose market + optional `daily_reports`.

---

## Dashboard tabs (frontend/usa/index.html)

**Visible (Nov 2026):**

| Tab | Data source | Purpose |
|-----|-------------|---------|
| **Momentum** | `daily_candidates` | Ranked setups + detail (S/R, decision) |
| **Oversold** | `fib_ema_radar` + `oversold_watch` | Fib/EMA bounce radar + today’s oversold chips |
| **Sector Heatmap** | `sector_heatmap` | S&P 500 map + GICS / regime |
| **ETF Scan** | `etf_scans` | EUR ETFs; S/R in ticker detail |
| **Deep Dive** | Cloud Function | Per-ticker AI analysis |

Still computed / present in code, currently hidden in the USA chrome: Opportunities, My Radar, News, Statistics.

---

## Key Config Files

| File | Controls |
|------|----------|
| `config/factors.yaml` | min_score, weights, thresholds, decision, oversold, `scan.universe` |
| `config/sp500.yaml` | S&P 500 constituents (503) — heatmap + pipeline base |
| `config/nasdaq100.yaml` | Nasdaq-100 constituents (101) — pipeline merge |
| `config/universe.yaml` | Curated USA extras (175) + 93 BIST tickers |
| `config/etfs.yaml` | ETF scan universe |
| `config/themes.yaml` | Heatmap theme groupings |

---

## Backtests (`backtest/`)

| Script | Purpose |
|--------|---------|
| `run_backtest.py` | Decision engine threshold validation |
| `srp_pap_backtest_v1..v5.py` | Stop Run + Price Acceptance Profile |
| `stoch_candidates_backtest.py` | Stochastic layer vs baseline candidates funnel |

Summary: `backtest/BACKTEST_OZET.md`, `backtest/stoch_candidates_backtest.md`

**Finding:** Stochastic adds value in **oversold zone** (separate list), not as a general score weight.

---

## Local Development

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# Place serviceAccountKey.json in project root (from Firebase Console)

# Run pipeline
cd src
python pipeline.py usa              # intraday scan
python pipeline.py usa --daily      # + heatmap + ETF
python pipeline.py bist
python pipeline.py all

# Deploy
firebase deploy --only hosting:investment-radar-usa
firebase deploy --only firestore:rules
```

---

## Code Organization

```
config/           YAML config (factors, sp500, nasdaq100, universe, etfs, themes)
src/
  usa_universe.py Merge S&P 500 + Nasdaq-100 + watchlist extras
  pipeline.py     Main orchestrator
  event_filter.py Step 1 triggers
  detailed_scorer.py  Step 2 scoring
  ta_engine.py    Indicator calculations (RSI, Stoch, EMA, BB, S/R)
  decision_engine.py  BUY/WATCH/SKIP tree
  etf_scanner.py  EUR ETF scan
  firebase_writer.py  All Firestore writes
  data_fetcher.py yfinance batch fetch (daily + 4h)
  layers/         RS, sector, macro, quality, earnings, heatmap, oversold, fib_ema_radar
frontend/
  usa/index.html  USA dashboard (Firebase Hosting)
  bist/index.html BIST dashboard
backtest/         Historical validation scripts
.github/workflows/pipeline.yml  Scheduled runs
```

**No `backend/` folder.** No `trigger_detector.py`.

---

## What NOT To Do

- Add a persistent API server (Firestore is the API)
- Add real-time price feeds (scheduled scans are sufficient)
- Change min_score or weights without backtest consideration
- Put oversold tickers into the main top-10 funnel (separate collection by design)
- Skip `firestore.rules` update when adding new public collections

---

## Pending / Roadmap

See `ITERATIONS.md` (two-pipeline architecture) and `docs/YAPILACAKLAR_PLANI.md` (Turkish long-term plan).

---

## Cursor Prompt Examples

Good:
> "Add `stoch_oversold_bounce` trigger to event_filter.py + factors.yaml thresholds_4h."

> "Oversold watch shows stale data — check pipeline writes and Firestore rules."

Bad:
> "Improve the system." / "Make it work."
