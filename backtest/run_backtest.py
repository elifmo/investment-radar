"""
Task 0 — Backtest / Threshold Validation

Simulates the decision engine weekly on 3+ years of historical US data.
All prices from yfinance, cached locally so re-runs are fast.

Usage:
  cd backtest
  python run_backtest.py

Output:
  backtest/backtest_report.md
"""

import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
import yfinance as yf

# ── Path setup ────────────────────────────────────────────────────────────────
BACKTEST_DIR = Path(__file__).parent
sys.path.insert(0, str(BACKTEST_DIR.parent / "src"))
from decision_engine import decide  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
CACHE_DIR   = BACKTEST_DIR / "cache"
REPORT_PATH = BACKTEST_DIR / "backtest_report.md"
CONFIG_DIR  = BACKTEST_DIR.parent / "config"

START_DATE = "2023-01-01"
END_DATE   = date.today().isoformat()

SECTOR_ETFS = {
    "Technology":             "XLK",
    "Financials":             "XLF",
    "Health Care":            "XLV",
    "Consumer Discretionary": "XLY",
    "Consumer Staples":       "XLP",
    "Industrials":            "XLI",
    "Energy":                 "XLE",
    "Materials":              "XLB",
    "Utilities":              "XLU",
    "Real Estate":            "XLRE",
    "Communication Services": "XLC",
}

RS_THRESHOLDS   = [60, 70, 80]
DROP_THRESHOLDS = [-0.15, -0.20, -0.25]


# ── Universe ──────────────────────────────────────────────────────────────────

def load_usa_universe() -> tuple[list[str], dict[str, str]]:
    universe   = yaml.safe_load((CONFIG_DIR / "universe.yaml").read_text())
    entries    = [e for e in universe.get("usa", []) if isinstance(e, dict)]
    tickers    = [e["ticker"] for e in entries]
    sector_map = {e["ticker"]: e.get("sector", "Unknown") for e in entries}
    return tickers, sector_map


# ── Data: prices ──────────────────────────────────────────────────────────────

def load_prices(all_symbols: list[str]) -> pd.DataFrame:
    """Load from cache or download. Returns DataFrame of adjusted closes."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache = CACHE_DIR / "prices.pkl"

    if cache.exists():
        df = pd.read_pickle(cache)
        cached_end = df.index[-1].date()
        if cached_end >= date.today() - timedelta(days=2):
            logger.info("Prices loaded from cache (%s rows, last=%s)", len(df), cached_end)
            return df
        logger.info("Cache stale (%s), refreshing...", cached_end)

    logger.info("Downloading %d symbols %s → %s ...", len(all_symbols), START_DATE, END_DATE)
    raw = yf.download(
        tickers=" ".join(all_symbols),
        start=START_DATE, end=END_DATE,
        interval="1d", auto_adjust=True,
        progress=True,
    )
    df = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    df.to_pickle(cache)
    logger.info("Prices cached (%d rows, %d cols)", len(df), len(df.columns))
    return df


# ── Data: quality grades (quarterly financials, cached once) ──────────────────

def load_quality_raw(tickers: list[str], sector_map: dict) -> dict:
    """
    Fetch quarterly NI and balance sheet for every ticker.
    Cached to disk — slow first run (~5 min), instant after.
    Returns {ticker: {sector, ni: Series, debt: Series, equity: Series}}
    """
    cache = CACHE_DIR / "quality_raw.pkl"
    if cache.exists():
        logger.info("Quality data loaded from cache.")
        return pd.read_pickle(cache)

    logger.info("Fetching quarterly financials for %d tickers (first run, ~5 min)...", len(tickers))
    result = {}
    for i, ticker in enumerate(tickers):
        if i % 25 == 0:
            logger.info("  %d / %d", i, len(tickers))
        try:
            t   = yf.Ticker(ticker)
            fin = t.quarterly_financials
            bs  = t.quarterly_balance_sheet

            ni = None
            for key in ["Net Income", "Net Income From Continuing Operations",
                        "Net Income Common Stockholders"]:
                if fin is not None and not fin.empty and key in fin.index:
                    ni = fin.loc[key].dropna().sort_index()
                    break

            debt = equity = None
            if bs is not None and not bs.empty:
                for key in ["Total Debt", "Long Term Debt"]:
                    if key in bs.index:
                        debt = bs.loc[key].dropna().sort_index()
                        break
                for key in ["Stockholders Equity", "Total Stockholders Equity",
                            "Common Stock Equity"]:
                    if key in bs.index:
                        equity = bs.loc[key].dropna().sort_index()
                        break

            result[ticker] = {"sector": sector_map.get(ticker, "Unknown"),
                              "ni": ni, "debt": debt, "equity": equity}
        except Exception as exc:
            logger.debug("Quality fetch failed %s: %s", ticker, exc)
            result[ticker] = {"sector": sector_map.get(ticker, "Unknown"),
                              "ni": None, "debt": None, "equity": None}

    pd.to_pickle(result, cache)
    logger.info("Quality data cached.")
    return result


# ── Layer computations on historical slices ───────────────────────────────────

def _classify(rs: float, mom: float) -> str:
    if rs > 0 and mom > 0: return "LEADING"
    if rs < 0 and mom > 0: return "IMPROVING"
    if rs > 0 and mom < 0: return "WEAKENING"
    return "LAGGING"


def compute_rs(prices: pd.DataFrame, tickers: list[str],
               sim_date: pd.Timestamp, window: int = 30,
               accel_lag: int = 15) -> dict:
    """
    RS ratings for all tickers as of sim_date.
    Also computes rs_delta = current RS rating minus RS rating `accel_lag` trading days ago.
    """
    sl  = prices.loc[:sim_date]
    spy = sl.get("SPY")
    if spy is None or spy.dropna().shape[0] < window + accel_lag + 2:
        return {}

    def _rank_snapshot(sl_snap):
        spy_s = sl_snap.get("SPY")
        if spy_s is None: return {}
        spy_s = spy_s.dropna()
        if len(spy_s) < window + 1: return {}
        spy_r = float(spy_s.iloc[-1] / spy_s.iloc[-(window + 1)] - 1)
        perf = {}
        for t in tickers:
            col = sl_snap.get(t)
            if col is None: continue
            col = col.dropna()
            if len(col) < window + 1: continue
            ret = float(col.iloc[-1] / col.iloc[-(window + 1)] - 1)
            perf[t] = ret - spy_r
        if len(perf) < 2: return {}
        ranks = pd.Series(perf).rank(pct=True, na_option="keep")
        out = {}
        for t, r in ranks.items():
            out[t] = 50 if pd.isna(r) else int(max(1, min(99, round(r * 98 + 1))))
        return out

    # Current RS ratings
    now_ranks = _rank_snapshot(sl)

    # RS ratings `accel_lag` trading days ago
    past_idx   = sl.index
    if len(past_idx) > accel_lag:
        past_date  = past_idx[-accel_lag - 1]
        past_ranks = _rank_snapshot(prices.loc[:past_date])
    else:
        past_ranks = {}

    spy_full = sl.get("SPY").dropna()
    spy_ret  = float(spy_full.iloc[-1] / spy_full.iloc[-(window + 1)] - 1)

    result = {}
    for t in tickers:
        col = sl.get(t)
        if col is None: continue
        col = col.dropna()
        if len(col) < window + 1: continue
        ret = float(col.iloc[-1] / col.iloc[-(window + 1)] - 1)
        rs_now  = now_ranks.get(t, 50)
        rs_past = past_ranks.get(t, rs_now)   # default to no change if past unavailable
        result[t] = {
            "rel":            ret - spy_ret,
            "return_30d":     ret,
            "spy_return_30d": spy_ret,
            "rs_rating":      rs_now,
            "rs_delta":       rs_now - rs_past,  # positive = accelerating
        }
    return result


def compute_sector(prices: pd.DataFrame, sim_date: pd.Timestamp,
                   sw=20, sm=10, lw=126, lm=20) -> dict:
    """Sector short/long status as of sim_date."""
    sl  = prices.loc[:sim_date]
    spy = sl.get("SPY")
    if spy is None or spy.dropna().shape[0] < lw + lm + 5:
        return {}

    out = {}
    for sector, etf in SECTOR_ETFS.items():
        col = sl.get(etf)
        if col is None: continue
        both = pd.DataFrame({"e": col, "s": spy}).dropna()
        if len(both) < lw + lm + 5: continue

        def rs_at(end, w):
            if end < w: return 0.0
            return (float(both["e"].iloc[end] / both["e"].iloc[end - w] - 1) -
                    float(both["s"].iloc[end] / both["s"].iloc[end - w] - 1))

        n = len(both) - 1
        rs_sn = rs_at(n, sw);  rs_sp = rs_at(n - sm, sw)
        rs_ln = rs_at(n, lw);  rs_lp = rs_at(n - lm, lw)
        out[sector] = {
            "short_status": _classify(rs_sn, rs_sn - rs_sp),
            "long_status":  _classify(rs_ln, rs_ln - rs_lp),
        }
    return out


def compute_macro(prices: pd.DataFrame, sim_date: pd.Timestamp,
                  tw=20, sw=5) -> str:
    """Macro regime as of sim_date."""
    sl = prices.loc[:sim_date]

    def smoothed(col_name):
        col = sl.get(col_name)
        if col is None or col.dropna().shape[0] < tw + sw + 5: return 0.0
        col = col.dropna()
        return float((col - col.shift(tw)).rolling(sw).mean().dropna().iloc[-1])

    score = (-1 if smoothed("TNX") > 0 else 1) + (-1 if smoothed("DXY") > 0 else 1)
    return "RISK_ON" if score >= 1 else "RISK_OFF" if score <= -1 else "NEUTRAL"


def sector_medians_at(quality_raw: dict, sim_date: pd.Timestamp) -> dict:
    """Sector-median D/E using only data available as of sim_date."""
    sec_de: dict[str, list] = {}
    for raw in quality_raw.values():
        debt, eq, sec = raw["debt"], raw["equity"], raw["sector"]
        if debt is None or eq is None or debt.empty or eq.empty: continue
        d = debt[debt.index <= sim_date]
        e = eq[eq.index <= sim_date]
        if d.empty or e.empty: continue
        e0 = float(e.iloc[-1])
        if e0 > 0:
            sec_de.setdefault(sec, []).append(float(d.iloc[-1]) / e0)
    return {s: float(pd.Series(v).median()) for s, v in sec_de.items()}


def grade_at(raw: dict, sim_date: pd.Timestamp, sec_medians: dict) -> str:
    """Point-in-time quality grade for one ticker."""
    def avail(s):
        if s is None or s.empty: return None
        m = s[s.index <= sim_date]
        return m if not m.empty else None

    ni   = avail(raw.get("ni"))
    debt = avail(raw.get("debt"))
    eq   = avail(raw.get("equity"))
    sec  = raw.get("sector", "Unknown")

    ni_trend = "flat"
    if ni is not None and len(ni) >= 2:
        q0, q1 = float(ni.iloc[-1]), float(ni.iloc[-2])
        if q1 != 0:
            chg = (q0 - q1) / abs(q1)
            ni_trend = "growing" if chg > 0.03 else "declining" if chg < -0.03 else "flat"

    consec_decline = False
    if ni is not None and len(ni) >= 3:
        consec_decline = float(ni.iloc[-1]) < float(ni.iloc[-2]) < float(ni.iloc[-3])

    de_ratio = None
    de_rising = False
    if debt is not None and eq is not None:
        e0 = float(eq.iloc[-1])
        if e0 > 0:
            de_ratio = float(debt.iloc[-1]) / e0
            if len(debt) >= 2 and len(eq) >= 2:
                e1 = float(eq.iloc[-2])
                if e1 > 0:
                    de_rising = de_ratio > float(debt.iloc[-2]) / e1

    median = sec_medians.get(sec, 1.0)
    if de_ratio is None: de_ratio = median

    if consec_decline and de_rising:            return "D"
    if ni_trend == "declining" or de_ratio > median * 1.5: return "C"
    if ni_trend == "growing"   and de_ratio < median * 1.0: return "A"
    if ni_trend in ("growing", "flat") and de_ratio < median * 1.5: return "B"
    return "C"


# ── Simulation ────────────────────────────────────────────────────────────────

def run_simulation(prices: pd.DataFrame, tickers: list[str],
                   sector_map: dict, quality_raw: dict,
                   rs_threshold: float = 70,
                   drop_threshold: float = -0.20,
                   macro_rs_adjust: bool = False,
                   rs_accel_min: int | None = None) -> list[dict]:
    """
    Weekly walk-forward simulation.

    macro_rs_adjust: if True, use 65/70/75 based on RISK_ON/NEUTRAL/RISK_OFF.
    rs_accel_min:    if set (e.g. 20), a ticker whose RS jumped >= this many points
                     in the last 15 trading days qualifies as if RS met the threshold
                     (overrides the RS gate only — sector + grade gates still apply).
    """
    # First trading day of each week, after we have 200 days of history
    all_dates = prices.index
    start_cutoff = pd.Timestamp(START_DATE) + pd.Timedelta(days=200)
    seen, sim_dates = set(), []
    for dt in all_dates:
        if dt < start_cutoff: continue
        wk = (dt.year, dt.isocalendar()[1])
        if wk not in seen:
            seen.add(wk)
            sim_dates.append(dt)

    logger.info("Simulating %d weeks (%s → %s), RS≥%d, drop≤%.0f%%...",
                len(sim_dates), sim_dates[0].date(), sim_dates[-1].date(),
                rs_threshold, drop_threshold * 100)

    signals = []
    for i, sim_date in enumerate(sim_dates):
        if i % 26 == 0:
            logger.info("  Week %d / %d  (%s)", i + 1, len(sim_dates), sim_date.date())

        sec_meds   = sector_medians_at(quality_raw, sim_date)
        rs_data    = compute_rs(prices, tickers, sim_date)
        sec_data   = compute_sector(prices, sim_date)
        macro      = compute_macro(prices, sim_date)

        # Macro-aware RS threshold
        if macro_rs_adjust:
            eff_threshold = 65 if macro == "RISK_ON" else 75 if macro == "RISK_OFF" else 70
        else:
            eff_threshold = rs_threshold

        for ticker in tickers:
            rs_info     = rs_data.get(ticker, {})
            sector_name = sector_map.get(ticker)
            sec_info    = sec_data.get(sector_name, {})
            grade       = grade_at(quality_raw.get(ticker, {}), sim_date, sec_meds)

            col = prices.get(ticker)
            if col is None: continue
            price_slice = col.dropna().loc[:sim_date]
            if price_slice.empty: continue

            rs_now   = rs_info.get("rs_rating", 0)
            rs_delta = rs_info.get("rs_delta", 0)

            # RS acceleration override: if RS jumped enough, treat as if RS met threshold
            # but only if grade != D (quality gate still applies)
            accel_boost = (
                rs_accel_min is not None
                and rs_delta >= rs_accel_min
                and grade != "D"
            )
            effective_rs = max(rs_now, eff_threshold) if accel_boost else rs_now

            candidate = {
                "rs_rating":           effective_rs,
                "return_30d":          rs_info.get("return_30d", 0.0),
                "sector_short_status": sec_info.get("short_status", "LAGGING"),
                "sector_long_status":  sec_info.get("long_status",  "LAGGING"),
                "quality_grade":       grade,
                "macro_regime":        macro,
                "volume_ratio":        1.0,
                "days_to_earnings":    None,
            }

            result = decide(candidate, rs_threshold=eff_threshold,
                            drop_threshold=drop_threshold)
            signals.append({
                "date":         sim_date,
                "ticker":       ticker,
                "decision":     result.decision,
                "entry_price":  float(price_slice.iloc[-1]),
                "rs_rating":    rs_now,
                "rs_delta":     rs_delta,
                "accel_boost":  accel_boost,
                "grade":        grade,
                "sector":       sector_name,
                "sector_short": sec_info.get("short_status", "LAGGING"),
                "macro":        macro,
            })

    return signals


# ── Forward returns ───────────────────────────────────────────────────────────

def attach_forward_returns(signals: list[dict], prices: pd.DataFrame) -> pd.DataFrame:
    df  = pd.DataFrame(signals)
    spy = prices.get("SPY")

    def fwd(col, dt, w):
        if col is None: return None
        fut = col.dropna().loc[dt:]
        return float(fut.iloc[w] / fut.iloc[0] - 1) if len(fut) > w else None

    df["ret_20"]   = [fwd(prices.get(r.ticker), r.date, 20) for r in df.itertuples()]
    df["ret_60"]   = [fwd(prices.get(r.ticker), r.date, 60) for r in df.itertuples()]
    df["spy_20"]   = [fwd(spy, r.date, 20) for r in df.itertuples()]
    df["spy_60"]   = [fwd(spy, r.date, 60) for r in df.itertuples()]
    df["alpha_20"] = df["ret_20"] - df["spy_20"]
    df["alpha_60"] = df["ret_60"] - df["spy_60"]
    return df


# ── Journey analysis ─────────────────────────────────────────────────────────

def _trail_exit(fut_vals: np.ndarray, entry: float, trail_pct: float):
    """Return (exit_ret, exit_day) for a trailing stop, or (final_ret, None) if never triggered."""
    running_peak = entry
    for i, price in enumerate(fut_vals[1:], start=1):
        running_peak = max(running_peak, price)
        if price <= running_peak * (1 - trail_pct):
            return float(price / entry - 1), i
    return float(fut_vals[-1] / entry - 1), None


def analyze_journey(df: pd.DataFrame, prices: pd.DataFrame,
                    stop_loss_pct: float = 0.05,
                    max_days: int = 90,
                    spx_rel_window: int = 10,
                    spx_rel_threshold: float = -0.05) -> pd.DataFrame:
    """
    For each BUY/BUY_SMALL signal, track the daily price path for up to max_days.

    Compares four exit strategies:
      - Hold 60 days (baseline)
      - Trail 8%  — trailing stop 8% from running peak
      - Trail 15% — trailing stop 15% from running peak
      - Combo (C) — exit when EITHER: trail 15% OR last-10d underperform SPY by 5%+
    """
    spy = prices.get("SPY")
    signals = df[df["decision"].isin(["BUY", "BUY_SMALL"])].copy()

    peak_rets, peak_days = [], []
    first_loss_days      = []
    trail8_rets,  trail8_days  = [], []
    trail15_rets, trail15_days = [], []
    combo_rets,   combo_days   = [], []
    combo_reasons              = []

    for row in signals.itertuples():
        col = prices.get(row.ticker)
        if col is None:
            for lst in (peak_rets, peak_days, first_loss_days,
                        trail8_rets, trail8_days, trail15_rets, trail15_days,
                        combo_rets, combo_days, combo_reasons):
                lst.append(None)
            continue

        fut = col.dropna().loc[row.date:]
        if len(fut) < 2:
            for lst in (peak_rets, peak_days, first_loss_days,
                        trail8_rets, trail8_days, trail15_rets, trail15_days,
                        combo_rets, combo_days, combo_reasons):
                lst.append(None)
            continue

        fut  = fut.iloc[:max_days + 1]
        entry = fut.iloc[0]
        rets  = (fut / entry - 1).values

        # Peak
        peak_idx = int(rets.argmax())
        peak_rets.append(float(rets[peak_idx]))
        peak_days.append(peak_idx)

        # First loss day (return < -stop_loss_pct)
        loss_days = [i for i, r in enumerate(rets) if r < -stop_loss_pct]
        first_loss_days.append(loss_days[0] if loss_days else None)

        # Trailing stop 8%
        r8, d8 = _trail_exit(fut.values, entry, 0.08)
        trail8_rets.append(r8); trail8_days.append(d8)

        # Trailing stop 15%
        r15, d15 = _trail_exit(fut.values, entry, 0.15)
        trail15_rets.append(r15); trail15_days.append(d15)

        # Combo C: trail 15% OR 10-day SPX-relative underperformance < spx_rel_threshold
        spy_fut = None
        if spy is not None:
            spy_slice = spy.dropna().loc[row.date:]
            if len(spy_slice) >= 2:
                spy_fut = spy_slice.iloc[:max_days + 1]

        combo_exit_ret  = None
        combo_exit_day  = None
        combo_reason    = None
        running_peak    = entry
        for i, price in enumerate(fut.values[1:], start=1):
            running_peak = max(running_peak, price)
            # Condition 1: trailing stop 15%
            if price <= running_peak * (1 - 0.15):
                combo_exit_ret = float(price / entry - 1)
                combo_exit_day = i
                combo_reason   = "trail15"
                break
            # Condition 2: last-10d ticker vs SPY < spx_rel_threshold
            if i >= spx_rel_window and spy_fut is not None and len(spy_fut) > i:
                look_back = i - spx_rel_window
                tkr_10d   = fut.values[i] / fut.values[look_back] - 1
                spy_entry = spy_fut.iloc[0]
                spy_10d   = spy_fut.values[i] / spy_fut.values[look_back] - 1 if look_back < len(spy_fut) else 0
                if tkr_10d - spy_10d < spx_rel_threshold:
                    combo_exit_ret = float(price / entry - 1)
                    combo_exit_day = i
                    combo_reason   = "spx_rel"
                    break

        combo_rets.append(combo_exit_ret if combo_exit_ret is not None else float(rets[-1]))
        combo_days.append(combo_exit_day)
        combo_reasons.append(combo_reason if combo_reason else "held")

    signals = signals.copy()
    signals["peak_ret"]       = peak_rets
    signals["peak_day"]       = peak_days
    signals["first_loss_day"] = first_loss_days
    signals["trail8_ret"]     = trail8_rets
    signals["trail8_day"]     = trail8_days
    signals["trail15_ret"]    = trail15_rets
    signals["trail15_day"]    = trail15_days
    signals["combo_ret"]      = combo_rets
    signals["combo_day"]      = combo_days
    signals["combo_reason"]   = combo_reasons
    # Keep trail_ret alias so other code doesn't break
    signals["trail_ret"]      = signals["trail8_ret"]
    signals["trail_day"]      = signals["trail8_day"]
    signals["trail_vs_hold"]  = signals["trail8_ret"] - signals["ret_60"].fillna(0)
    return signals


def _journey_section(journey: pd.DataFrame) -> list[str]:
    """Format the journey analysis section for the report — 4-strategy comparison."""
    lines = [
        "## Journey Analysis — Exit Strategy Comparison",
        "",
        "_(Seçenek C: Combo = trail 15% OR last-10d underperform SPY by 5%+)_",
        "_(max tracking = 90 days, stop-loss proxy = −5%)_",
        "",
    ]

    for decision in ["BUY", "BUY_SMALL"]:
        sub = journey[journey["decision"] == decision].dropna(subset=["peak_ret"])
        if sub.empty:
            continue

        n            = len(sub)
        avg_peak     = sub["peak_ret"].mean() * 100
        avg_peak_day = sub["peak_day"].mean()
        pct_hit_loss = (sub["first_loss_day"].notna()).mean() * 100
        avg_loss_day = sub.loc[sub["first_loss_day"].notna(), "first_loss_day"].mean()

        hold_avg   = sub["ret_60"].mean() * 100

        t8_sub     = sub.dropna(subset=["trail8_ret"])
        t8_avg     = t8_sub["trail8_ret"].mean() * 100
        t8_day     = t8_sub["trail8_day"].dropna().mean()
        t8_better  = (t8_sub["trail8_ret"] > t8_sub["ret_60"].fillna(0)).mean() * 100

        t15_sub    = sub.dropna(subset=["trail15_ret"])
        t15_avg    = t15_sub["trail15_ret"].mean() * 100
        t15_day    = t15_sub["trail15_day"].dropna().mean()
        t15_better = (t15_sub["trail15_ret"] > t15_sub["ret_60"].fillna(0)).mean() * 100

        combo_sub    = sub.dropna(subset=["combo_ret"])
        combo_avg    = combo_sub["combo_ret"].mean() * 100
        combo_day    = combo_sub["combo_day"].dropna().mean()
        combo_better = (combo_sub["combo_ret"] > combo_sub["ret_60"].fillna(0)).mean() * 100

        # Combo exit reason breakdown
        if "combo_reason" in combo_sub.columns:
            reason_counts = combo_sub["combo_reason"].value_counts()
            trail_triggered = reason_counts.get("trail15", 0)
            spx_triggered   = reason_counts.get("spx_rel", 0)
            held_full       = reason_counts.get("held", 0)
        else:
            trail_triggered = spx_triggered = held_full = 0

        def pct_peak_in(lo, hi):
            return (sub["peak_day"].between(lo, hi)).mean() * 100

        lines += [
            f"### {decision} ({n} signals)",
            "",
            f"- Avg peak: **+{avg_peak:.1f}%** at day **{avg_peak_day:.0f}** (≈{avg_peak_day/4:.1f} weeks)",
            f"- {pct_hit_loss:.0f}% of signals hit −5% at some point"
            + (f" (avg on day {avg_loss_day:.0f})" if not pd.isna(avg_loss_day) else ""),
            "",
            "**Peak timing:**",
            "",
            "| Window | % of signals |",
            "|--------|-------------|",
            f"| Days 1–10  (week 1-2)  | {pct_peak_in(1,10):.0f}% |",
            f"| Days 11–20 (week 3-4)  | {pct_peak_in(11,20):.0f}% |",
            f"| Days 21–45 (month 2)   | {pct_peak_in(21,45):.0f}% |",
            f"| Days 46–90 (month 2-3) | {pct_peak_in(46,90):.0f}% |",
            "",
            "**Exit strategy comparison:**",
            "",
            "| Strategy | Avg return | Exits avg day | Better than hold |",
            "|----------|-----------|--------------|-----------------|",
            f"| Hold 60 days             | {hold_avg:>+.1f}%  | 60  | —    |",
            f"| Trail 8%                 | {t8_avg:>+.1f}%  | {int(t8_day) if not pd.isna(t8_day) else '—':<4} | {t8_better:.0f}%  |",
            f"| Trail 15%                | {t15_avg:>+.1f}%  | {int(t15_day) if not pd.isna(t15_day) else '—':<4} | {t15_better:.0f}%  |",
            f"| **Combo C** (trail15+SPX) | **{combo_avg:>+.1f}%** | {int(combo_day) if not pd.isna(combo_day) else '—':<4} | {combo_better:.0f}%  |",
            "",
        ]

        if trail_triggered + spx_triggered + held_full > 0:
            total_combo = trail_triggered + spx_triggered + held_full
            lines += [
                "**Combo C — exit reason breakdown:**",
                "",
                f"- Trail 15% triggered: {trail_triggered} ({trail_triggered/total_combo*100:.0f}%)",
                f"- SPX-relative triggered: {spx_triggered} ({spx_triggered/total_combo*100:.0f}%)",
                f"- Held full period: {held_full} ({held_full/total_combo*100:.0f}%)",
                "",
            ]

    return lines


# ── Report ────────────────────────────────────────────────────────────────────

def _why_decision(row) -> str:
    """Human-readable explanation of why the decision was made."""
    rs   = getattr(row, "rs_rating", 0) or 0
    grade = getattr(row, "grade", "?") or "?"
    ss   = getattr(row, "sector_short", "?") or "?"
    d    = getattr(row, "decision", "?")
    if d == "BUY":
        return f"RS={rs} ✓  Grade={grade} ✓  Sector={ss} ✓"
    if d == "BUY_SMALL":
        return f"RS={rs} low (dip)  Grade={grade} ✓  Sector_long={ss}"
    if d == "WATCH":
        if rs >= 70:
            return f"RS={rs} ✓  but Sector={ss} ✗ (not LEADING/IMPROVING)"
        return f"RS={rs} ✗ (weak, no big drop)"
    if d == "SKIP":
        if grade == "D":
            return f"Grade=D ✗ (quality gate rejected)"
        return f"RS={rs} low + Sector={ss} weak"
    return "?"


def _individual_trades_section(df: pd.DataFrame) -> list[str]:
    """Top 30 BUY winners, top 30 BUY losers, top 40 missed opportunities."""
    buy = df[df["decision"].isin(["BUY", "BUY_SMALL"])].dropna(subset=["alpha_60"])
    all_df = df.dropna(subset=["alpha_60"])

    def fmt_row(row, show_decision=False):
        dt   = str(row.date)[:10]
        dec  = f" [{row.decision}]" if show_decision else ""
        why  = _why_decision(row)
        return (
            f"| {dt} | {row.ticker:<6} | {row.sector or '—':<26} "
            f"| {row.ret_60*100:>+7.1f}% | {row.alpha_60*100:>+7.1f}% "
            f"| {why}{dec} |"
        )

    header = (
        "| Date       | Ticker | Sector                     "
        "| 3mo Ret  | 3mo Alpha | Why / Signals |"
    )
    sep = (
        "|------------|--------|----------------------------|"
        "----------|-----------|---------------|"
    )

    lines = [
        "## Individual Trade Analysis",
        "",
    ]

    # ── Top 30 BUY winners ────────────────────────────────────────────────────
    winners = buy.sort_values("alpha_60", ascending=False).head(30)
    lines += [
        "### Best 30 BUY Trades (by 3mo Alpha)",
        "",
        "_These are the clearest proof the system works: all 3 conditions aligned._",
        "",
        header, sep,
    ]
    for row in winners.itertuples():
        lines.append(fmt_row(row))
    lines.append("")

    # ── Top 30 BUY losers ─────────────────────────────────────────────────────
    losers = buy.sort_values("alpha_60").head(30)
    lines += [
        "### Worst 30 BUY Trades (by 3mo Alpha)",
        "",
        "_These are signals where all conditions passed but return was still negative._",
        "",
        header, sep,
    ]
    for row in losers.itertuples():
        lines.append(fmt_row(row))
    lines.append("")

    # ── Missed opportunities: WATCH/SKIP that had great returns ───────────────
    missed = (
        all_df[all_df["decision"].isin(["WATCH", "SKIP"])]
        .sort_values("alpha_60", ascending=False)
        .head(40)
    )
    lines += [
        "### Top 40 Missed Opportunities (WATCH/SKIP that performed well)",
        "",
        "_Stocks that would have been big winners — but the system held back. Column 'Why' shows which condition blocked the BUY._",
        "",
        header, sep,
    ]
    for row in missed.itertuples():
        lines.append(fmt_row(row, show_decision=True))
    lines.append("")

    return lines


def _per_ticker_section(df: pd.DataFrame) -> list[str]:
    """Per-ticker breakdown for BUY signals: signal count, avg 3mo return, alpha, win rate."""
    buy = df[df["decision"].isin(["BUY", "BUY_SMALL"])].dropna(subset=["alpha_60"])
    if buy.empty:
        return []

    grouped = buy.groupby("ticker").agg(
        signals   =("alpha_60", "count"),
        avg_ret60 =("ret_60",   "mean"),
        avg_alpha =("alpha_60", "mean"),
        win_rate  =("alpha_60", lambda x: (x > 0).mean()),
        decisions =("decision", lambda x: ", ".join(sorted(x.unique()))),
    ).reset_index()
    grouped = grouped[grouped["signals"] >= 2].sort_values("avg_alpha", ascending=False)

    lines = [
        "## Per-Ticker Breakdown (BUY + BUY_SMALL, ≥2 signals)",
        "",
        "### Top 25 — highest 3mo alpha",
        "",
        "| Ticker | Signals | 3mo Ret | 3mo Alpha | Win% | Decision types |",
        "|--------|---------|---------|-----------|------|----------------|",
    ]
    for row in grouped.head(25).itertuples():
        lines.append(
            f"| {row.ticker:<6} | {row.signals:>7} | {row.avg_ret60*100:>+7.1f}% "
            f"| {row.avg_alpha*100:>+9.1f}% | {row.win_rate*100:>4.0f}% | {row.decisions} |"
        )

    lines += [
        "",
        "### Bottom 25 — lowest 3mo alpha",
        "",
        "| Ticker | Signals | 3mo Ret | 3mo Alpha | Win% | Decision types |",
        "|--------|---------|---------|-----------|------|----------------|",
    ]
    for row in grouped.tail(25).sort_values("avg_alpha").itertuples():
        lines.append(
            f"| {row.ticker:<6} | {row.signals:>7} | {row.avg_ret60*100:>+7.1f}% "
            f"| {row.avg_alpha*100:>+9.1f}% | {row.win_rate*100:>4.0f}% | {row.decisions} |"
        )

    lines += [
        "",
        "### Full ticker list (sorted by alpha)",
        "",
        "| Ticker | Signals | 3mo Ret | 3mo Alpha | Win% |",
        "|--------|---------|---------|-----------|------|",
    ]
    for row in grouped.itertuples():
        lines.append(
            f"| {row.ticker:<6} | {row.signals:>7} | {row.avg_ret60*100:>+7.1f}% "
            f"| {row.avg_alpha*100:>+9.1f}% | {row.win_rate*100:>4.0f}% |"
        )

    lines.append("")
    return lines


def _per_sector_section(df: pd.DataFrame) -> list[str]:
    """Per-sector breakdown: BUY signal count, avg return, alpha, win rate."""
    buy = df[df["decision"].isin(["BUY", "BUY_SMALL"])].dropna(subset=["alpha_60", "sector"])
    if buy.empty:
        return []

    grouped = buy.groupby("sector").agg(
        signals   =("alpha_60", "count"),
        avg_ret60 =("ret_60",   "mean"),
        avg_alpha =("alpha_60", "mean"),
        win_rate  =("alpha_60", lambda x: (x > 0).mean()),
        buy_count =("decision", lambda x: (x == "BUY").sum()),
        bs_count  =("decision", lambda x: (x == "BUY_SMALL").sum()),
    ).reset_index().sort_values("avg_alpha", ascending=False)

    lines = [
        "## Per-Sector Breakdown (BUY + BUY_SMALL signals)",
        "",
        "| Sector | Signals | BUY | BUY_SMALL | 3mo Ret | 3mo Alpha | Win% |",
        "|--------|---------|-----|-----------|---------|-----------|------|",
    ]
    for row in grouped.itertuples():
        lines.append(
            f"| {row.sector:<26} | {row.signals:>7} | {row.buy_count:>3} | {row.bs_count:>9} "
            f"| {row.avg_ret60*100:>+7.1f}% | {row.avg_alpha*100:>+9.1f}% | {row.win_rate*100:>4.0f}% |"
        )

    lines.append("")
    return lines


def _per_decision_by_year(df: pd.DataFrame) -> list[str]:
    """Year-by-year BUY alpha to see if signal quality was consistent."""
    buy = df[df["decision"].isin(["BUY", "BUY_SMALL"])].dropna(subset=["alpha_60"]).copy()
    if buy.empty:
        return []
    buy["year"] = pd.to_datetime(buy["date"]).dt.year

    grouped = buy.groupby(["year", "decision"]).agg(
        signals  =("alpha_60", "count"),
        avg_alpha=("alpha_60", "mean"),
        win_rate =("alpha_60", lambda x: (x > 0).mean()),
    ).reset_index()

    lines = [
        "## Year-by-Year Signal Quality (3mo Alpha)",
        "",
        "| Year | Decision  | Signals | Avg 3mo Alpha | Win% |",
        "|------|-----------|---------|---------------|------|",
    ]
    for row in grouped.sort_values(["year", "decision"]).itertuples():
        lines.append(
            f"| {row.year} | {row.decision:<9} | {row.signals:>7} "
            f"| {row.avg_alpha*100:>+13.1f}% | {row.win_rate*100:>4.0f}% |"
        )

    lines.append("")
    return lines


def _outcome_table(df: pd.DataFrame) -> str:
    rows = []
    for d in ["BUY", "BUY_SMALL", "WATCH", "SKIP"]:
        sub = df[df["decision"] == d].dropna(subset=["alpha_20"])
        if sub.empty: continue
        win = (sub["alpha_20"] > 0).mean() * 100
        rows.append(
            f"| {d:<9} | {len(sub):>5} | "
            f"{sub['ret_20'].mean()*100:>+6.1f}% | {sub['alpha_20'].mean()*100:>+6.1f}% | "
            f"{sub['ret_60'].mean()*100:>+6.1f}% | {sub['alpha_60'].mean()*100:>+6.1f}% | "
            f"{win:>4.0f}% |"
        )
    return "\n".join(rows)


def _scenario_comparison(scenarios: list[dict]) -> list[str]:
    """RS Acceleration delta sweep: how does alpha change as we raise the delta threshold?"""
    lines = [
        "## RS Acceleration — Delta Threshold Sweep",
        "",
        "_(Does raising the RS-delta cutoff improve signal quality?)_",
        "",
        "| Scenario | BUY total | Accel-only BUY | Accel alpha 3mo | Accel Win% | All-BUY alpha 3mo |",
        "|----------|-----------|----------------|-----------------|------------|-------------------|",
    ]

    for s in scenarios:
        df   = s["df"]
        name = s["name"]
        buy  = df[df["decision"] == "BUY"].dropna(subset=["alpha_60"])
        ba   = buy["alpha_60"].mean() * 100 if not buy.empty else float("nan")

        if "accel_boost" in df.columns and df["accel_boost"].any():
            accel = buy[buy["accel_boost"] == True]
            accel_n   = len(accel)
            accel_a   = accel["alpha_60"].mean() * 100 if not accel.empty else float("nan")
            accel_w   = (accel["alpha_60"] > 0).mean() * 100 if not accel.empty else float("nan")
        else:
            accel_n, accel_a, accel_w = 0, float("nan"), float("nan")

        accel_a_str = f"{accel_a:>+.1f}%" if not pd.isna(accel_a) else "—"
        accel_w_str = f"{accel_w:.0f}%"   if not pd.isna(accel_w) else "—"
        lines.append(
            f"| {name:<28} | {len(buy):>9} | {accel_n:>14} "
            f"| {accel_a_str:>15} | {accel_w_str:>10} | {ba:>+17.1f}% |"
        )

    # Accel signal detail for each threshold (top-5 per scenario, sorted by alpha)
    accel_scenarios = [
        s for s in scenarios
        if "accel_boost" in s["df"].columns and s["df"]["accel_boost"].any()
    ]

    if accel_scenarios:
        lines += [
            "",
            "### Accel-only BUY trades — top performers per threshold",
            "",
        ]
        for s in accel_scenarios:
            df_a = s["df"]
            accel_buys = df_a[
                (df_a["decision"] == "BUY") & (df_a["accel_boost"] == True)
            ].dropna(subset=["alpha_60"])
            if accel_buys.empty:
                continue
            avg_a  = accel_buys["alpha_60"].mean() * 100
            win_a  = (accel_buys["alpha_60"] > 0).mean() * 100
            top5   = accel_buys.sort_values("alpha_60", ascending=False).head(5)
            bottom5 = accel_buys.sort_values("alpha_60").head(5)

            lines += [
                f"#### {s['name']}  (n={len(accel_buys)}, avg={avg_a:+.1f}%, win={win_a:.0f}%)",
                "",
                "Top 5:",
                "| Date       | Ticker | Sector                  | RS | Δ RS | Grade | Alpha |",
                "|------------|--------|-------------------------|----|------|-------|-------|",
            ]
            for row in top5.itertuples():
                lines.append(
                    f"| {str(row.date)[:10]} | {row.ticker:<6} | {(row.sector or '—'):<23} "
                    f"| {row.rs_rating:>2} | {row.rs_delta:>+4} | {row.grade:<5} "
                    f"| {row.alpha_60*100:>+6.1f}% |"
                )
            lines += [
                "",
                "Bottom 5:",
                "| Date       | Ticker | Sector                  | RS | Δ RS | Grade | Alpha |",
                "|------------|--------|-------------------------|----|------|-------|-------|",
            ]
            for row in bottom5.itertuples():
                lines.append(
                    f"| {str(row.date)[:10]} | {row.ticker:<6} | {(row.sector or '—'):<23} "
                    f"| {row.rs_rating:>2} | {row.rs_delta:>+4} | {row.grade:<5} "
                    f"| {row.alpha_60*100:>+6.1f}% |"
                )
            lines.append("")

    return lines


def generate_report(base_df: pd.DataFrame, sweep: list[dict],
                    journey: pd.DataFrame | None = None,
                    scenarios: list[dict] | None = None) -> str:
    lines = [
        "# Backtest Report",
        f"**Period:** {START_DATE} → {END_DATE}",
        f"**Universe:** {base_df['ticker'].nunique()} US tickers",
        "**Method:** Weekly walk-forward, first trading day of each week",
        "**Note:** volume_ratio set to 1.0 (neutral proxy — event filter not applied in backtest)",
        "",
        "---",
        "",
        "## Decision Outcome (Base: RS ≥ 70, Drop ≤ −20%)",
        "",
        "| Decision  | Count | 1mo Ret | 1mo Alpha | 3mo Ret | 3mo Alpha | Win% |",
        "|-----------|-------|---------|-----------|---------|-----------|------|",
        _outcome_table(base_df),
        "",
        "> Alpha = ticker return − SPY return over same window.",
        "> Win% = % of signals where 1mo alpha > 0.",
        "",
        "---",
        "",
        "## Threshold Sensitivity (9 combinations)",
        "",
        "| RS ≥ | Drop ≤ | BUY # | BUY Alpha 1mo | BUY Win% | BUY_SMALL # | BUY_SMALL Alpha 1mo |",
        "|------|--------|-------|---------------|----------|-------------|---------------------|",
    ]

    for r in sweep:
        df  = r["df"]
        rs  = r["rs"]
        dr  = r["drop"]
        buy = df[df["decision"] == "BUY"].dropna(subset=["alpha_20"])
        bs  = df[df["decision"] == "BUY_SMALL"].dropna(subset=["alpha_20"])
        ba  = buy["alpha_20"].mean() * 100 if not buy.empty else float("nan")
        bw  = (buy["alpha_20"] > 0).mean() * 100 if not buy.empty else float("nan")
        bsa = bs["alpha_20"].mean() * 100 if not bs.empty else float("nan")
        lines.append(
            f"| {rs} | {dr*100:.0f}% | {len(buy)} | {ba:>+.1f}% | {bw:.0f}% | {len(bs)} | {bsa:>+.1f}% |"
        )

    # Best combo by BUY alpha
    valid = [r for r in sweep
             if not r["df"][r["df"]["decision"] == "BUY"].dropna(subset=["alpha_20"]).empty]
    if valid:
        best = max(valid,
                   key=lambda r: r["df"][r["df"]["decision"] == "BUY"]["alpha_20"].mean())
        lines += [
            "",
            "---",
            "",
            "## Recommendation",
            "",
            f"Best BUY alpha: **RS ≥ {best['rs']}, Drop ≤ {best['drop']*100:.0f}%**",
            "",
            "Update `config/factors.yaml` → `decision.rs_threshold` and `decision.drop_threshold`",
            "if these differ from the current defaults (70 / −20%).",
        ]

    if scenarios:
        lines += ["", "---", ""]
        lines += _scenario_comparison(scenarios)

    lines += ["", "---", ""]
    lines += _per_decision_by_year(base_df)

    lines += ["", "---", ""]
    lines += _per_sector_section(base_df)

    lines += ["", "---", ""]
    lines += _individual_trades_section(base_df)

    lines += ["", "---", ""]
    lines += _per_ticker_section(base_df)

    if journey is not None and not journey.empty:
        lines += ["", "---", ""]
        lines += _journey_section(journey)

    lines += ["", "---", "", "*Generated by backtest/run_backtest.py*"]
    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    tickers, sector_map = load_usa_universe()

    all_symbols = (tickers
                   + list(SECTOR_ETFS.values())
                   + ["SPY", "^TNX", "DX-Y.NYB"])

    prices_raw = load_prices(all_symbols)
    prices = prices_raw.rename(columns={"^TNX": "TNX", "DX-Y.NYB": "DXY"})

    quality_raw = load_quality_raw(tickers, sector_map)

    # Base simulation
    logger.info("=== Base simulation (RS=70, drop=-20%) ===")
    base_sigs = run_simulation(prices, tickers, sector_map, quality_raw,
                               rs_threshold=70, drop_threshold=-0.20)
    base_df = attach_forward_returns(base_sigs, prices)

    buy_count = len(base_df[base_df["decision"] == "BUY"])
    bs_count  = len(base_df[base_df["decision"] == "BUY_SMALL"])
    logger.info("Base: %d BUY + %d BUY_SMALL signals", buy_count, bs_count)

    if buy_count + bs_count < 50:
        logger.warning("Only %d BUY/BUY_SMALL signals — consider lowering RS threshold.",
                       buy_count + bs_count)

    # Threshold sweep
    sweep = []
    for rs in RS_THRESHOLDS:
        for drop in DROP_THRESHOLDS:
            if rs == 70 and drop == -0.20:
                sweep.append({"rs": rs, "drop": drop, "df": base_df})
                continue
            logger.info("=== Sweep RS=%d, drop=%.0f%% ===", rs, drop * 100)
            sigs = run_simulation(prices, tickers, sector_map, quality_raw,
                                  rs_threshold=rs, drop_threshold=drop)
            sweep.append({"rs": rs, "drop": drop,
                          "df": attach_forward_returns(sigs, prices)})

    # Scenario comparison: RS Acceleration delta sweep
    ACCEL_THRESHOLDS = [20, 30, 35, 40, 50]
    scenarios = [{"name": "Base (RS=70, no accel)", "df": base_df}]

    for delta in ACCEL_THRESHOLDS:
        logger.info("=== RS Accel sweep: delta ≥ %d ===", delta)
        sigs = run_simulation(prices, tickers, sector_map, quality_raw,
                              rs_threshold=70, drop_threshold=-0.20,
                              rs_accel_min=delta)
        scenarios.append({
            "name": f"RS Accel Δ≥{delta}",
            "df":   attach_forward_returns(sigs, prices),
        })

    logger.info("=== Journey analysis (BUY/BUY_SMALL signals) ===")
    journey = analyze_journey(base_df, prices)

    report = generate_report(base_df, sweep, journey, scenarios)
    REPORT_PATH.write_text(report, encoding="utf-8")
    logger.info("Report saved → %s", REPORT_PATH)
    print("\n" + "=" * 60)
    print(report)


if __name__ == "__main__":
    main()
