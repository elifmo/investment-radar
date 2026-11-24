# Documentation index

**Updated:** November 2026

Start at **[README.md](README.md)** for product overview and setup. This file maps the rest.

| Goal | Document |
|------|----------|
| What the system is | [README.md](README.md) |
| Pipeline, Firestore, cron | [CLAUDE_EN.md](CLAUDE_EN.md) |
| Local run + deploy | [QUICK_START_DEPLOYMENT_EN.md](QUICK_START_DEPLOYMENT_EN.md) |
| UI layout (may lag the live site) | [DASHBOARD_DESIGN_EN.md](DASHBOARD_DESIGN_EN.md) |
| Auth console steps | [docs/FAZ0_AUTH_SETUP.md](docs/FAZ0_AUTH_SETUP.md) |
| Product roadmap (TR, internal) | [docs/YAPILACAKLAR_PLANI.md](docs/YAPILACAKLAR_PLANI.md) |
| Backtest summaries | [backtest/BACKTEST_OZET.md](backtest/BACKTEST_OZET.md) |
| Cursor prompt history | [CURSOR_QUICK_START_EN.md](CURSOR_QUICK_START_EN.md) |

---

## Live USA dashboard (Nov 2026)

Visible tabs: **Momentum · Oversold · Sector Heatmap · ETF Scan · Deep Dive**

Pipeline still computes opportunities, radar items, news, and stats; several of those tabs are hidden in the current USA UI.

Oversold tab reads `fib_ema_radar` (4h EMA5×EMA20 after a Fib 61.8/78.6 pullback, 5-day max age, daily confirm within 1 day) plus `oversold_watch`.

---

## Snapshot

```
fetch (4h or daily) → event_filter → score_all → top Momentum names
  └─ USA universe: S&P 500 + Nasdaq-100 extras + watchlist (~523)
  └─ RS + sector + macro + quality + earnings + decision_engine
  └─ oversold_scan → oversold_watch
  └─ fib_ema_radar → Oversold tab
  └─ daily close: sector_heatmap + etf_scans
```

**Public Firestore (examples):** `daily_candidates` · `scan_meta` · `oversold_watch` · `fib_ema_radar` · `macro_regime` · `quality_grades` · `sector_status` · `sector_heatmap` · `etf_scans`

**Private (Auth):** `radar_items` · `trade_entries` · related logs

**Hosting:** `frontend/usa` → investment-radar-usa.web.app · `frontend/bist` → investment-radar-bist.web.app

---

## Layout

```
config/          factors.yaml, universes, ETFs, themes
src/             pipeline + TA + layers + firebase_writer
frontend/        usa + bist dashboards
functions/       deep_dive
backtest/        scripts + markdown reports
docs/            auth + roadmap
```

Removed long ago: `backend/`, GitHub Pages as the dashboard host.

---

## When you change the system

1. `config/factors.yaml` is source of truth for thresholds  
2. Update **CLAUDE_EN.md** if collections, cron, or pipeline steps change  
3. Update **README.md** if tabs or setup change  
4. Treat **DASHBOARD_DESIGN_EN.md** as a design note, not always the live UI  
