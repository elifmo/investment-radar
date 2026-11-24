# Quick Start & Deployment Guide

**Last updated:** November 2026

Product overview: **[README.md](README.md)**

---

## Prerequisites

- Python 3.11+
- Firebase CLI (`npm install -g firebase-tools`)
- Git + GitHub account
- Firebase project: `investment-radar-2c19d`

---

## 1. Local Setup

```bash
git clone https://github.com/elifmo/investment-radar.git
cd investment-radar

python -m venv venv
source venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
```

### Firebase service account

1. Firebase Console → Project Settings → Service accounts → Generate new private key
2. Save as `serviceAccountKey.json` in project root (gitignored)
3. Never commit this file

---

## 2. Run Pipeline Locally

```bash
cd src

# USA intraday scan (4h timeframe)
python pipeline.py usa

# USA + sector heatmap + ETF scan
python pipeline.py usa --daily

# BIST
python pipeline.py bist

# Both markets
python pipeline.py all
```

Verify in Firebase Console → Firestore:
- `daily_candidates` — top candidates
- `oversold_watch/current` — oversold list
- `scan_meta` — run metadata

---

## 3. Deploy Dashboard

```bash
firebase login
firebase use investment-radar-2c19d

# USA dashboard only
firebase deploy --only hosting:investment-radar-usa

# BIST dashboard
firebase deploy --only hosting:investment-radar-bist

# Firestore security rules (after adding new collections)
firebase deploy --only firestore:rules

# Both hosting targets + rules
firebase deploy --only hosting,firestore:rules
```

**Live URLs:**
- https://investment-radar-usa.web.app
- https://investment-radar-bist.web.app

Hard-refresh after deploy: Cmd+Shift+R

---

## 4. GitHub Actions (Scheduled Pipeline)

Workflow: `.github/workflows/pipeline.yml`

### Schedule (weekdays only)

| Turkey time | Market | Extra |
|-------------|--------|-------|
| 10:15, 14:15, 18:15 | BIST | — |
| 16:30, 20:30 | USA | — |
| **23:15** | USA | Heatmap + ETF (`--daily`) |

### Required GitHub secret

| Secret | Content |
|--------|---------|
| `FIREBASE_SERVICE_ACCOUNT` | Full JSON of service account key |

### Manual run

GitHub → Actions → Investment Radar Pipeline → Run workflow  
Options: `market` (usa/bist/all), `daily_reports` (true for heatmap+ETF)

---

## 5. Firebase Project Structure

| Service | Usage |
|---------|-------|
| **Firestore** | All pipeline + user data |
| **Hosting** | `frontend/usa`, `frontend/bist` |
| **Auth** | Google + email (My Radar) |
| **Cloud Functions** | Deep Dive analysis (optional) |

**Not used:** Realtime Database, GitHub Pages

---

## 6. Configuration

Edit YAML files — no code changes needed for threshold tuning:

| File | What to change |
|------|----------------|
| `config/factors.yaml` | min_score, weights, RSI/Stoch, Fib radar, `scan.universe` (~523 default) |
| `config/sp500.yaml` | S&P 500 list — refresh via `scripts/refresh_sp500_universe.py` |
| `config/nasdaq100.yaml` | Nasdaq-100 list — refresh via `scripts/refresh_nasdaq100_universe.py` |
| `config/universe.yaml` | USA priority extras + BIST tickers |
| `config/etfs.yaml` | ETF scan list |
| `config/portfolio.yaml` | Optional personal holdings (keep gitignored if it is private) |

After a config change: run the pipeline locally or wait for the next cron.

### My Radar portfolio sync (optional)

Sign in on the dashboard, copy your Firebase Auth UID, then:

```bash
python3 scripts/sync_portfolio.py --uid YOUR_FIREBASE_UID --dry-run
python3 scripts/sync_portfolio.py --uid YOUR_FIREBASE_UID
```

---

## 7. Troubleshooting

### Dashboard shows "Loading..." forever

- Open browser DevTools → Console → look for JavaScript errors
- Common cause: syntax error in `frontend/usa/index.html`
- Hard-refresh: Cmd+Shift+R

### Candidates empty but scan ran

- Check `scan_meta` in Firestore for latest date
- `min_score` in `config/factors.yaml` — quiet days may have few or zero candidates
- Oversold Watch is separate (`oversold_watch/current`)

### Heatmap / ETF stale

- Only updates on 23:15 TR cron (or manual `--daily`)
- Check GitHub Actions log for `RUN_DAILY_REPORTS=true`

### Pipeline fails on GitHub Actions

- Verify `FIREBASE_SERVICE_ACCOUNT` secret is valid JSON
- Check Actions log for yfinance fetch errors

### Firestore permission denied

- Deploy rules: `firebase deploy --only firestore:rules`
- New collections must be added to `firestore.rules` with `allow read: if true`

### Local pipeline: ModuleNotFoundError

```bash
cd src   # pipeline must run from src/ or use PYTHONPATH
python pipeline.py usa
```

---

## 8. Backtests

```bash
# Decision engine thresholds
python backtest/run_backtest.py

# Stochastic layer comparison
python backtest/stoch_candidates_backtest.py --all
```

Reports written to `backtest/*.md`

---

## 9. What changed since early docs

The live stack is Firebase Hosting + Firestore + GitHub Actions (six weekday runs). There is no `backend/` API. USA scan universe is S&P 500 + Nasdaq extras (~523). Live USA tabs (Nov 2026): Momentum, Oversold, Sector Heatmap, ETF Scan, Deep Dive.

See **CLAUDE_EN.md** for architecture.
