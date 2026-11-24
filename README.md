# Investment Radar

Daily stock scan and decision-support dashboard for **US** and **BIST** markets.

The pipeline scores a large universe, writes results to Firestore, and the dashboard reads them. You decide. The system does not place trades and is **not financial advice**.

| Market | Live dashboard |
|--------|----------------|
| USA | [investment-radar-usa.web.app](https://investment-radar-usa.web.app) |
| BIST | [investment-radar-bist.web.app](https://investment-radar-bist.web.app) |

---

## What it does

On a weekday schedule (GitHub Actions), `src/pipeline.py`:

1. Pulls prices (Yahoo Finance)
2. Filters for events (volume, EMA, RSI, support, 52-week high)
3. Scores technicals (0–100)
4. Enriches USA names (relative strength, sector, macro, quality, earnings)
5. Writes a short **Momentum** list, an **Oversold / Fib bounce** radar, a **sector heatmap**, and an **ETF scan**

The USA site currently shows:

- **Momentum** — ranked setups with score, streak, and ticker detail (support / resistance, decision)
- **Oversold** — Fib pullback + 4h EMA5/20 cross, daily confirm, 5-day window
- **Sector heatmap** — S&P 500 map + GICS / regime context
- **ETF scan** — EUR-listed ETFs with levels in the ticker panel
- **Deep Dive** — per-ticker AI brief (Cloud Function)

Auth is only required for private **My Radar** data (watchlist / thesis). Scan results are public reads.

---

## Architecture

```
GitHub Actions (weekdays)
        │
        ▼
src/pipeline.py  →  Firestore
        │
        ▼
Firebase Hosting  (frontend/usa, frontend/bist)
```

There is no app server. The dashboard talks to Firestore (and Deep Dive to a Cloud Function).

**Universe (config-driven):**

| Source | Typical size | File |
|--------|----------------|------|
| S&P 500 | ~503 | `config/sp500.yaml` |
| Nasdaq-100 extras | ~13 | `config/nasdaq100.yaml` |
| Extra watch names | ~7 | `config/universe.yaml` |
| **USA scan (default `sp500_nasdaq`)** | **~523** | `src/usa_universe.py` |
| BIST | ~93 | `config/universe.yaml` |

Thresholds live in `config/factors.yaml` (`min_score`, weights, oversold, Fib radar).

---

## Repository layout

```
config/                 scores, universes, ETFs, themes
src/                    pipeline, TA, layers, Firestore writers
src/layers/             RS, sector, macro, quality, oversold, Fib radar
frontend/usa/           USA dashboard (single HTML/JS app)
frontend/bist/          BIST dashboard
functions/              Deep Dive Cloud Function
backtest/               historical tests and reports
docs/                   extra notes (auth, roadmap)
.github/workflows/      scheduled pipeline
```

---

## Local setup

**Needs:** Python 3.11+, Firebase CLI, a Firebase project.

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

1. Firebase Console → Project settings → Service accounts → generate a private key  
2. Save it as `serviceAccountKey.json` in the repo root (**gitignored — never commit**)  
3. Optional: copy `.env.example` to `.env` for local extras

```bash
cd src
python pipeline.py usa           # USA 4h scan
python pipeline.py usa --daily   # + heatmap + ETF
python pipeline.py bist
```

Deploy dashboards:

```bash
firebase deploy --only hosting:investment-radar-usa
firebase deploy --only hosting:investment-radar-bist
firebase deploy --only firestore:rules
```

Full commands, cron times, and troubleshooting: **[QUICK_START_DEPLOYMENT_EN.md](QUICK_START_DEPLOYMENT_EN.md)**  
Architecture: **[CLAUDE_EN.md](CLAUDE_EN.md)**  
Doc index: **[README_DOCUMENTATION.md](README_DOCUMENTATION.md)**

---

## Security before you fork or open the repo

Do **not** commit:

- `serviceAccountKey.json`, `.env`, `.env.save`
- Anthropic / Alpha Vantage / other API keys
- personal `config/portfolio.yaml` trade history

Firebase **web** API keys in `frontend/*/index.html` are normal for client apps; lock them down with Firebase Auth, App Check, and hosting domains. Rotate any Admin private key that ever left your machine.

---

## Disclaimer

This is a personal research tool. Signals can be late, incomplete, or wrong. Nothing here is a recommendation to buy or sell any security.
