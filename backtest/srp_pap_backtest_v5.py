"""
SRP + PAP Backtest v5 — SPY Early Recovery Hypothesis
======================================================
Hypothesis: SPY PAP is Rejected (market down) BUT SPY SRP fires a bullish
reversal signal = early buy opportunity before the market recovers.

Three Scenarios tested on SPY and 7 individual USA stocks:

  Scenario A — SPY Rejected + SPY SRP bullish:
    SPY PAP state == "Rejected" AND SPY SRP direction == "bullish"

  Scenario B — SPY PAP acceptance score rising while Rejected:
    SPY PAP acceptance_score < 60 AND score has risen >= 5 pts vs 5 bars ago

  Scenario C — Combined (most selective):
    Scenario A AND Scenario B (Rejected + bullish SRP + rising score)

For each scenario:
  1. SPY itself: hold 10, 20, 40 days → hit rate and avg return
  2. Individual stocks (AAPL, MSFT, NVDA, AMZN, META, GOOGL, JPM):
     enter when SPY scenario fires AND individual stock PAP is Accepted or Edge
  3. Baseline comparison: individual stock PAP Accepted/Edge with NO SPY condition

Also:
  - Days until SPY recovers to Accepted after each scenario signal
  - Avg return when entered "early" (during SPY Rejected) vs "normal" (SPY Accepted/Edge)

Usage:
    /Users/Elifcik/Desktop/apps/investment-radar/.venv/bin/python3 backtest/srp_pap_backtest_v5.py
"""

import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
from datetime import date, timedelta
import numpy as np
import pandas as pd
import yfinance as yf

BACKTEST_DIR = Path(__file__).parent
CACHE_DIR    = BACKTEST_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# ── Universe ──────────────────────────────────────────────────────────────────
SPY_TICKER   = "SPY"
USA_TICKERS  = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "JPM"]

START_DATE = (date.today() - timedelta(days=2 * 365 + 10)).isoformat()
END_DATE   = date.today().isoformat()

FIXED_HOLDS = [10, 20, 40]

# Scenario B parameters
SCORE_THRESHOLD  = 60   # acceptance_score must be below this
SCORE_RISE_MIN   = 5    # score must have risen by at least this vs 5 bars ago
SCORE_LOOKBACK   = 5    # bars to look back for score comparison


# ── Data fetching ──────────────────────────────────────────────────────────────

def fetch_ohlcv(tickers: list[str], cache_key: str) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV for a list of tickers, with per-group cache."""
    cache_path = CACHE_DIR / f"srp_pap_v5_{cache_key}.pkl"
    if cache_path.exists():
        cached = pd.read_pickle(cache_path)
        keys = list(cached.keys())
        if keys:
            last = cached[keys[0]].index[-1].date()
            if last >= date.today() - timedelta(days=2):
                print(f"  [{cache_key}] loaded from cache (last={last})")
                return cached

    print(f"  [{cache_key}] downloading {len(tickers)} tickers …")
    result = {}
    for ticker in tickers:
        try:
            raw = yf.download(
                ticker, start=START_DATE, end=END_DATE,
                interval="1d", auto_adjust=True, progress=False
            )
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.droplevel(1)
            if len(raw) > 60:
                result[ticker] = raw
                print(f"    {ticker}: {len(raw)} bars")
        except Exception as e:
            print(f"    {ticker}: FAILED - {e}")

    pd.to_pickle(result, cache_path)
    return result


# ── SRP — Stop Run Reversal Planner ──────────────────────────────────────────
# Reused verbatim from srp_pap_backtest_v2.py

def compute_srp(df: pd.DataFrame,
                lookback: int = 34,
                atr_period: int = 14,
                vol_baseline: int = 34) -> pd.DataFrame:
    """
    Simplified SRP indicator. Returns DataFrame with columns:
      score       : reversalScore (0-100) per bar
      direction   : 'bullish' | 'bearish' | '' (only non-empty on sweep bars)
    """
    n = len(df)
    if n < max(lookback, atr_period, vol_baseline) + 5:
        return pd.DataFrame({
            "score":     pd.Series(np.nan, index=df.index),
            "direction": pd.Series("", index=df.index),
        })

    hi  = df["High"]
    lo  = df["Low"]
    cl  = df["Close"]
    op  = df["Open"]
    vol = df["Volume"] if "Volume" in df.columns else pd.Series(1, index=df.index)

    # ATR
    tr = pd.concat([
        hi - lo,
        (hi - cl.shift(1)).abs(),
        (lo - cl.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(atr_period).mean()

    roll_hi = hi.rolling(lookback).max().shift(1)
    roll_lo = lo.rolling(lookback).min().shift(1)

    vol_ma    = vol.rolling(vol_baseline).mean()
    vol_ratio = (vol / vol_ma.replace(0, np.nan)).clip(0.1, 5.0)

    scores     = pd.Series(0.0, index=df.index)
    directions = pd.Series("", index=df.index, dtype=object)

    for i in range(max(lookback, atr_period, vol_baseline) + 1, n):
        bar_hi = hi.iloc[i]
        bar_lo = lo.iloc[i]
        bar_cl = cl.iloc[i]
        bar_op = op.iloc[i]
        bar_atr = atr.iloc[i]
        if pd.isna(bar_atr) or bar_atr == 0:
            continue

        rhi = roll_hi.iloc[i]
        rlo = roll_lo.iloc[i]
        if pd.isna(rhi) or pd.isna(rlo):
            continue

        bar_range = bar_hi - bar_lo
        if bar_range == 0:
            continue

        bull_sweep = (bar_lo < rlo) and (bar_cl > rlo)
        bear_sweep = (bar_hi > rhi) and (bar_cl < rhi)

        if not (bull_sweep or bear_sweep):
            continue

        if bull_sweep:
            sweep_depth  = max(0, rlo - bar_lo)
            wick_upper   = bar_hi - max(bar_cl, bar_op)
            wick_lower   = min(bar_cl, bar_op) - bar_lo
            close_pct    = (bar_cl - bar_lo) / bar_range
            confirm_bull = bar_cl > bar_op
        else:
            sweep_depth  = max(0, bar_hi - rhi)
            wick_upper   = bar_hi - max(bar_cl, bar_op)
            wick_lower   = min(bar_cl, bar_op) - bar_lo
            close_pct    = (bar_hi - bar_cl) / bar_range
            confirm_bull = bar_cl < bar_op

        wick_size  = wick_lower if bull_sweep else wick_upper
        wick_score = min(100.0, (wick_size / bar_atr) * 50)
        pen_score  = min(100.0, (sweep_depth / bar_atr) * 40)

        vr        = vol_ratio.iloc[i]
        vol_score = min(100.0, (vr - 1.0) * 50 + 50) if not pd.isna(vr) else 50.0
        vol_score = max(0.0, vol_score)

        sweep_score      = wick_score * 0.56 + pen_score * 0.34 + vol_score * 0.10
        close_back_score = min(100.0, close_pct * 100)
        confirm_score    = 80.0 if confirm_bull else 30.0

        body             = abs(bar_cl - bar_op)
        target_room_score = min(100.0, (body / bar_atr) * 60)

        if i >= 6:
            prior_change = cl.iloc[i - 1] - cl.iloc[i - 6]
            if bull_sweep:
                trend_turn_score = 80.0 if prior_change < 0 else 30.0
            else:
                trend_turn_score = 80.0 if prior_change > 0 else 30.0
        else:
            trend_turn_score = 50.0

        reversal_score = (
            sweep_score       * 0.22 +
            close_back_score  * 0.22 +
            confirm_score     * 0.22 +
            vol_score         * 0.12 +
            target_room_score * 0.14 +
            trend_turn_score  * 0.08
        )

        scores.iloc[i]     = reversal_score
        directions.iloc[i] = "bullish" if bull_sweep else "bearish"

    return pd.DataFrame({"score": scores, "direction": directions})


# ── PAP — Price Acceptance Profile ───────────────────────────────────────────
# Reused verbatim from srp_pap_backtest_v2.py

def compute_pap(df: pd.DataFrame,
                lookback: int = 320,
                n_rows: int = 26,
                value_area_pct: float = 0.70) -> pd.DataFrame:
    """
    Simplified PAP indicator. Returns DataFrame with columns:
      poc, vah, val, acceptance_state, rotation, acceptance_score, cog
    """
    cl = df["Close"]
    n  = len(df)

    poc_arr   = np.full(n, np.nan)
    vah_arr   = np.full(n, np.nan)
    val_arr   = np.full(n, np.nan)
    state_arr = np.full(n, "", dtype=object)
    rot_arr   = np.full(n, "", dtype=object)
    score_arr = np.full(n, np.nan)
    cog_arr   = np.full(n, np.nan)

    for i in range(lookback, n):
        window    = cl.iloc[i - lookback + 1: i + 1].values
        cur_price = window[-1]

        w_min = window.min()
        w_max = window.max()
        if w_max == w_min:
            continue

        bins              = np.linspace(w_min, w_max, n_rows + 1)
        counts, edges     = np.histogram(window, bins=bins)
        row_mids          = (edges[:-1] + edges[1:]) / 2

        poc_idx = counts.argmax()
        poc     = row_mids[poc_idx]

        total   = counts.sum()
        target  = int(total * value_area_pct)
        included       = {poc_idx}
        included_count = counts[poc_idx]

        lo_idx = poc_idx
        hi_idx = poc_idx

        while included_count < target:
            can_lo = lo_idx - 1 >= 0
            can_hi = hi_idx + 1 < n_rows

            if not can_lo and not can_hi:
                break

            add_lo = counts[lo_idx - 1] if can_lo else -1
            add_hi = counts[hi_idx + 1] if can_hi else -1

            if add_lo >= add_hi and can_lo:
                lo_idx -= 1
                included.add(lo_idx)
                included_count += counts[lo_idx]
            elif can_hi:
                hi_idx += 1
                included.add(hi_idx)
                included_count += counts[hi_idx]
            else:
                lo_idx -= 1
                included.add(lo_idx)
                included_count += counts[lo_idx]

        vah = row_mids[hi_idx]
        val = row_mids[lo_idx]

        total_weighted = (counts * row_mids).sum()
        cog = total_weighted / total if total > 0 else poc

        half     = lookback // 2
        w_first  = cl.iloc[i - lookback + 1: i - half + 1].values
        w_second = cl.iloc[i - half + 1: i + 1].values
        if len(w_first) > 0 and len(w_second) > 0:
            cog_first  = w_first.mean()
            cog_second = w_second.mean()
            rotation = ("Up"   if cog_second > cog_first * 1.001 else
                        "Down" if cog_second < cog_first * 0.999 else "Neutral")
        else:
            rotation = "Neutral"

        row_height = (w_max - w_min) / n_rows
        edge_band  = row_height * 1.5
        if cur_price < val - edge_band or cur_price > vah + edge_band:
            state = "Rejected"
        elif ((cur_price < val + edge_band and cur_price >= val - edge_band) or
              (cur_price > vah - edge_band and cur_price <= vah + edge_band)):
            state = "Edge"
        else:
            state = "Accepted"

        poc_dist  = abs(cur_price - poc) / (w_max - w_min + 1e-10)
        poc_score = max(0.0, 40.0 * (1 - poc_dist * 2))

        va_width  = (vah - val) / (w_max - w_min + 1e-10)
        va_score  = max(0.0, 20.0 * (1 - va_width))

        toward_poc_up = cur_price < poc
        if (rotation == "Up" and toward_poc_up) or (rotation == "Down" and not toward_poc_up):
            rot_score = 20.0
        elif rotation == "Neutral":
            rot_score = 10.0
        else:
            rot_score = 5.0

        state_score      = 20.0 if state == "Accepted" else (10.0 if state == "Edge" else 0.0)
        acceptance_score = poc_score + va_score + rot_score + state_score

        poc_arr[i]   = poc
        vah_arr[i]   = vah
        val_arr[i]   = val
        state_arr[i] = state
        rot_arr[i]   = rotation
        score_arr[i] = acceptance_score
        cog_arr[i]   = cog

    return pd.DataFrame({
        "poc":              poc_arr,
        "vah":              vah_arr,
        "val":              val_arr,
        "acceptance_state": state_arr,
        "rotation":         rot_arr,
        "acceptance_score": score_arr,
        "cog":              cog_arr,
    }, index=df.index)


# ── Scenario detection ────────────────────────────────────────────────────────

def detect_spy_scenarios(spy_srp: pd.DataFrame, spy_pap: pd.DataFrame,
                          max_signal_bar: int) -> dict[str, list[int]]:
    """
    Detect bar indices where each SPY scenario fires.
    Returns dict: {'A': [...], 'B': [...], 'C': [...]}
    """
    scenarios = {"A": [], "B": [], "C": []}
    n = len(spy_pap)

    for i in range(SCORE_LOOKBACK + 1, min(n, max_signal_bar + 1)):
        pap_state = spy_pap["acceptance_state"].iloc[i]
        pap_score = spy_pap["acceptance_score"].iloc[i]
        srp_dir   = spy_srp["direction"].iloc[i]
        srp_score = spy_srp["score"].iloc[i]

        if pap_state == "" or pd.isna(pap_state):
            continue

        rejected = pap_state == "Rejected"

        # Scenario A: Rejected + SRP bullish
        spy_srp_bullish = (srp_dir == "bullish" and
                           not pd.isna(srp_score) and srp_score > 0)
        scenario_a = rejected and spy_srp_bullish

        # Scenario B: score < threshold but rising
        score_prev = spy_pap["acceptance_score"].iloc[i - SCORE_LOOKBACK]
        score_rising = (not pd.isna(pap_score) and
                        not pd.isna(score_prev) and
                        pap_score < SCORE_THRESHOLD and
                        (pap_score - score_prev) >= SCORE_RISE_MIN)
        scenario_b = rejected and score_rising

        # Scenario C: both A and B
        scenario_c = scenario_a and scenario_b

        if scenario_a:
            scenarios["A"].append(i)
        if scenario_b:
            scenarios["B"].append(i)
        if scenario_c:
            scenarios["C"].append(i)

    return scenarios


def days_until_spy_recovered(spy_pap: pd.DataFrame,
                              signal_bar: int,
                              max_search: int = 80) -> int | None:
    """
    From signal_bar+1, count how many trading days until SPY PAP
    acceptance_state is 'Accepted' or 'Edge'.
    Returns None if not recovered within max_search bars.
    """
    n = len(spy_pap)
    for j in range(signal_bar + 1, min(signal_bar + max_search + 1, n)):
        state = spy_pap["acceptance_state"].iloc[j]
        if state in ("Accepted", "Edge"):
            return j - signal_bar
    return None


# ── Simulation helpers ────────────────────────────────────────────────────────

def simulate_spy_fixed_hold(spy_df: pd.DataFrame,
                             signal_bars: list[int],
                             hold: int) -> list[dict]:
    """Entry at open of signal_bar+1, exit at close of entry+hold."""
    cl  = spy_df["Close"]
    op  = spy_df["Open"]
    n   = len(spy_df)
    trades = []

    for sig in signal_bars:
        entry_bar = sig + 1
        exit_bar  = entry_bar + hold
        if entry_bar >= n or exit_bar >= n:
            continue
        entry_price = float(op.iloc[entry_bar])
        exit_price  = float(cl.iloc[exit_bar])
        if entry_price <= 0:
            continue
        ret = (exit_price - entry_price) / entry_price
        trades.append({
            "signal_bar":  sig,
            "entry_bar":   entry_bar,
            "exit_bar":    exit_bar,
            "hold":        hold,
            "signal_date": spy_df.index[sig],
            "entry_date":  spy_df.index[entry_bar],
            "exit_date":   spy_df.index[exit_bar],
            "entry_price": entry_price,
            "exit_price":  exit_price,
            "ret":         ret,
            "hit":         int(ret > 0),
        })
    return trades


def simulate_stock_fixed_hold(stock_df: pd.DataFrame,
                               stock_pap: pd.DataFrame,
                               signal_bars: list[int],
                               ticker: str,
                               hold: int) -> list[dict]:
    """
    For each SPY signal bar, check if stock PAP is Accepted or Edge on the
    same bar. If so, enter at stock open of signal+1.
    """
    cl  = stock_df["Close"]
    op  = stock_df["Open"]
    n   = len(stock_df)
    # Build a date-indexed lookup from the stock's pap
    trades = []

    for sig in signal_bars:
        if sig + 1 >= n or sig + 1 + hold >= n:
            continue

        # Match by bar index (both aligned to same calendar after merge)
        stock_state = stock_pap["acceptance_state"].iloc[sig]
        if stock_state not in ("Accepted", "Edge"):
            continue

        entry_bar   = sig + 1
        exit_bar    = entry_bar + hold
        entry_price = float(op.iloc[entry_bar])
        exit_price  = float(cl.iloc[exit_bar])
        if entry_price <= 0:
            continue
        ret = (exit_price - entry_price) / entry_price
        trades.append({
            "ticker":       ticker,
            "signal_bar":   sig,
            "entry_bar":    entry_bar,
            "exit_bar":     exit_bar,
            "hold":         hold,
            "signal_date":  stock_df.index[sig],
            "entry_date":   stock_df.index[entry_bar],
            "exit_date":    stock_df.index[exit_bar],
            "stock_state":  stock_state,
            "entry_price":  entry_price,
            "exit_price":   exit_price,
            "ret":          ret,
            "hit":          int(ret > 0),
        })
    return trades


def simulate_baseline(stock_df: pd.DataFrame,
                       stock_pap: pd.DataFrame,
                       ticker: str,
                       hold: int,
                       max_bar: int) -> list[dict]:
    """
    Baseline: enter whenever stock PAP is Accepted or Edge, regardless of SPY.
    Entry = next open, exit at close of entry+hold.
    """
    cl  = stock_df["Close"]
    op  = stock_df["Open"]
    n   = len(stock_df)
    trades = []

    for i in range(1, min(n - hold - 2, max_bar + 1)):
        state = stock_pap["acceptance_state"].iloc[i]
        if state not in ("Accepted", "Edge"):
            continue
        entry_bar   = i + 1
        exit_bar    = entry_bar + hold
        if exit_bar >= n:
            continue
        entry_price = float(op.iloc[entry_bar])
        exit_price  = float(cl.iloc[exit_bar])
        if entry_price <= 0:
            continue
        ret = (exit_price - entry_price) / entry_price
        trades.append({
            "ticker":       ticker,
            "signal_bar":   i,
            "hold":         hold,
            "stock_state":  state,
            "ret":          ret,
            "hit":          int(ret > 0),
        })
    return trades


# ── Statistics helpers ────────────────────────────────────────────────────────

def stats(trades: list[dict], label: str = "") -> dict:
    if not trades:
        return {"label": label, "n": 0,
                "hit_rate": np.nan, "avg_ret": np.nan, "median_ret": np.nan}
    df = pd.DataFrame(trades)
    return {
        "label":      label,
        "n":          len(df),
        "hit_rate":   df["hit"].mean() * 100,
        "avg_ret":    df["ret"].mean() * 100,
        "median_ret": df["ret"].median() * 100,
    }


def recovery_stats(recovery_days: list[int | None]) -> dict:
    valid = [d for d in recovery_days if d is not None]
    not_recovered = len(recovery_days) - len(valid)
    if not valid:
        return {"n_signals": len(recovery_days), "n_recovered": 0,
                "not_recovered": not_recovered,
                "avg_days": np.nan, "median_days": np.nan,
                "pct_recovered": 0.0}
    return {
        "n_signals":     len(recovery_days),
        "n_recovered":   len(valid),
        "not_recovered": not_recovered,
        "avg_days":      float(np.mean(valid)),
        "median_days":   float(np.median(valid)),
        "pct_recovered": len(valid) / len(recovery_days) * 100,
    }


def fmt_pct(v, decimals=1):
    return f"{v:+.{decimals}f}%" if not (v is None or (isinstance(v, float) and np.isnan(v))) else "—"


def fmt_f(v, decimals=1):
    return f"{v:.{decimals}f}" if not (v is None or (isinstance(v, float) and np.isnan(v))) else "—"


# ── Report generation ────────────────────────────────────────────────────────

def build_spy_hold_table(scenario_label: str,
                          spy_hold_results: dict[int, list[dict]]) -> list[str]:
    lines = [
        f"#### SPY — Scenario {scenario_label}",
        "",
        "| Hold | # Signals | Hit Rate | Avg Return | Median Return |",
        "|------|-----------|----------|------------|---------------|",
    ]
    for hold in FIXED_HOLDS:
        s = stats(spy_hold_results.get(hold, []))
        lines.append(
            f"| {hold}d | {s['n']:>9} | "
            f"{fmt_pct(s['hit_rate']):>8} | "
            f"{fmt_pct(s['avg_ret']):>10} | "
            f"{fmt_pct(s['median_ret']):>13} |"
        )
    return lines


def build_stock_table(scenario_label: str, hold: int,
                       stock_results: dict[str, list[dict]]) -> list[str]:
    lines = [
        f"##### Hold {hold}d — Scenario {scenario_label}",
        "",
        "| Ticker | # Trades | Hit Rate | Avg Return | Median Return |",
        "|--------|----------|----------|------------|---------------|",
    ]
    all_trades = []
    for ticker in USA_TICKERS:
        t = stock_results.get(ticker, [])
        all_trades.extend(t)
        s = stats(t)
        lines.append(
            f"| {ticker:<6} | {s['n']:>8} | "
            f"{fmt_pct(s['hit_rate']):>8} | "
            f"{fmt_pct(s['avg_ret']):>10} | "
            f"{fmt_pct(s['median_ret']):>13} |"
        )
    # combined row
    s_all = stats(all_trades, "All")
    lines.append(
        f"| {'**All**':<6} | {s_all['n']:>8} | "
        f"{fmt_pct(s_all['hit_rate']):>8} | "
        f"{fmt_pct(s_all['avg_ret']):>10} | "
        f"{fmt_pct(s_all['median_ret']):>13} |"
    )
    return lines


def build_baseline_table(hold: int, baseline_results: dict[str, list[dict]]) -> list[str]:
    lines = [
        f"##### Baseline Hold {hold}d (no SPY condition)",
        "",
        "| Ticker | # Trades | Hit Rate | Avg Return | Median Return |",
        "|--------|----------|----------|------------|---------------|",
    ]
    all_trades = []
    for ticker in USA_TICKERS:
        t = baseline_results.get(ticker, [])
        all_trades.extend(t)
        s = stats(t)
        lines.append(
            f"| {ticker:<6} | {s['n']:>8} | "
            f"{fmt_pct(s['hit_rate']):>8} | "
            f"{fmt_pct(s['avg_ret']):>10} | "
            f"{fmt_pct(s['median_ret']):>13} |"
        )
    s_all = stats(all_trades)
    lines.append(
        f"| {'**All**':<6} | {s_all['n']:>8} | "
        f"{fmt_pct(s_all['hit_rate']):>8} | "
        f"{fmt_pct(s_all['avg_ret']):>10} | "
        f"{fmt_pct(s_all['median_ret']):>13} |"
    )
    return lines


def build_comparison_table(scenario_label: str, hold: int,
                            scenario_stock: dict[str, list[dict]],
                            baseline_stock: dict[str, list[dict]]) -> list[str]:
    """Side-by-side avg return: scenario vs baseline for each ticker."""
    lines = [
        f"##### Avg Return Comparison — Scenario {scenario_label} vs Baseline — Hold {hold}d",
        "",
        "| Ticker | Scenario Avg Ret | Baseline Avg Ret | Delta |",
        "|--------|-----------------|-----------------|-------|",
    ]
    for ticker in USA_TICKERS:
        s_scen = stats(scenario_stock.get(ticker, []))
        s_base = stats(baseline_stock.get(ticker, []))
        delta = (s_scen["avg_ret"] - s_base["avg_ret"]
                 if not np.isnan(s_scen["avg_ret"]) and not np.isnan(s_base["avg_ret"])
                 else np.nan)
        delta_str = fmt_pct(delta) if not np.isnan(delta) else "—"
        lines.append(
            f"| {ticker:<6} | {fmt_pct(s_scen['avg_ret']):>15} | "
            f"{fmt_pct(s_base['avg_ret']):>15} | {delta_str:>5} |"
        )
    return lines


def generate_report(
    spy_df: pd.DataFrame,
    spy_scenarios: dict[str, list[int]],
    spy_hold_results: dict[str, dict[int, list[dict]]],
    recovery_by_scenario: dict[str, list[int | None]],
    stock_hold_results: dict[str, dict[str, dict[str, list[dict]]]],
    baseline_hold_results: dict[str, dict[str, list[dict]]],
    today: str,
) -> str:
    """Build the full markdown report."""

    lines = [
        "# SRP + PAP Backtest v5 — SPY Early Recovery Hypothesis",
        "",
        f"**Date generated:** {today}",
        f"**Period:** {START_DATE} → {END_DATE} (2-year daily)",
        f"**SPY ticker:** {SPY_TICKER}",
        f"**Individual stocks:** {', '.join(USA_TICKERS)}",
        f"**Fixed hold periods:** {', '.join(str(h)+'d' for h in FIXED_HOLDS)}",
        "",
        "## Hypothesis",
        "",
        "When SPY PAP is **Rejected** (market down) but SPY SRP fires a **bullish",
        "reversal signal**, this may represent an early recovery buy opportunity",
        "before the market turns. Three scenarios test different filters to identify",
        "this accumulation phase.",
        "",
        "## Scenario Definitions",
        "",
        "| Scenario | Condition |",
        "|----------|-----------|",
        "| **A** | SPY PAP state = Rejected AND SPY SRP direction = bullish |",
        f"| **B** | SPY PAP state = Rejected AND acceptance_score < {SCORE_THRESHOLD} "
        f"AND score rose ≥ {SCORE_RISE_MIN} pts vs {SCORE_LOOKBACK} bars ago |",
        "| **C** | Scenario A AND Scenario B (most selective) |",
        "",
        "**Baseline:** Individual stock PAP Accepted or Edge with NO SPY condition.",
        "",
        "---",
        "",
        "## Signal Counts",
        "",
        "| Scenario | SPY Signals |",
        "|----------|-------------|",
    ]
    for sc in ("A", "B", "C"):
        lines.append(f"| {sc} | {len(spy_scenarios[sc])} |")

    lines += [
        "",
        "---",
        "",
        "## Part 1 — SPY Itself: Does SPY Recover After Each Scenario?",
        "",
        "Entry at open of signal+1. Exit at fixed hold period close.",
        "",
    ]

    for sc in ("A", "B", "C"):
        lines += build_spy_hold_table(sc, spy_hold_results[sc])
        lines.append("")

    lines += [
        "---",
        "",
        "## Part 2 — Days Until SPY Recovers to Accepted/Edge",
        "",
        "From each scenario signal bar, how many trading days until SPY PAP",
        "acceptance_state reaches 'Accepted' or 'Edge'?",
        "",
        "| Scenario | Signals | Recovered | Not Recovered | % Recovered | Avg Days | Median Days |",
        "|----------|---------|-----------|---------------|-------------|----------|-------------|",
    ]

    for sc in ("A", "B", "C"):
        rs = recovery_stats(recovery_by_scenario[sc])
        lines.append(
            f"| {sc} | {rs['n_signals']} | {rs['n_recovered']} | "
            f"{rs['not_recovered']} | "
            f"{fmt_f(rs['pct_recovered'])}% | "
            f"{fmt_f(rs['avg_days'])} | "
            f"{fmt_f(rs['median_days'])} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Part 3 — Individual Stock Results When SPY Scenario Fires",
        "",
        "Entry condition: SPY scenario fires AND individual stock PAP = Accepted or Edge.",
        "Entry at stock open of signal+1, exit at close of entry+hold.",
        "",
    ]

    for sc in ("A", "B", "C"):
        lines += [f"### Scenario {sc}", ""]
        for hold in FIXED_HOLDS:
            lines += build_stock_table(sc, hold, stock_hold_results[sc][hold])
            lines.append("")

    lines += [
        "---",
        "",
        "## Part 4 — Baseline: Individual Stock PAP Accepted/Edge (No SPY Condition)",
        "",
    ]
    for hold in FIXED_HOLDS:
        lines += build_baseline_table(hold, baseline_hold_results[hold])
        lines.append("")

    lines += [
        "---",
        "",
        "## Part 5 — Scenario vs Baseline Comparison",
        "",
        "Delta = Scenario avg return minus Baseline avg return.",
        "Positive delta = scenario entries outperformed baseline.",
        "",
    ]
    for sc in ("A", "B", "C"):
        lines += [f"### Scenario {sc}", ""]
        for hold in FIXED_HOLDS:
            lines += build_comparison_table(
                sc, hold,
                stock_hold_results[sc][hold],
                baseline_hold_results[hold],
            )
            lines.append("")

    lines += [
        "---",
        "",
        "## Summary & Interpretation",
        "",
    ]

    # Auto-generate brief interpretation
    for sc in ("A", "B", "C"):
        sc_name = {
            "A": "Rejected + SRP Bullish",
            "B": "Rejected + Rising Score",
            "C": "Combined (A & B)",
        }[sc]
        lines.append(f"### Scenario {sc} — {sc_name}")
        lines.append("")

        n_sig = len(spy_scenarios[sc])
        if n_sig == 0:
            lines.append("_No signals fired in the test period._")
            lines.append("")
            continue

        rs = recovery_stats(recovery_by_scenario[sc])
        rec_str = (
            f"SPY recovered in {fmt_f(rs['avg_days'])}d avg "
            f"({fmt_f(rs['pct_recovered'])}% of the time within 80 bars)."
            if rs["n_recovered"] > 0 else "SPY did not recover within 80 bars in any case."
        )

        # best hold for SPY
        spy_hold_stats = {hold: stats(spy_hold_results[sc].get(hold, [])) for hold in FIXED_HOLDS}
        valid_spy = [(hold, s) for hold, s in spy_hold_stats.items() if s["n"] > 0 and not np.isnan(s["avg_ret"])]
        if valid_spy:
            best_spy_hold, best_spy_s = max(valid_spy, key=lambda x: x[1]["avg_ret"])
            spy_str = (
                f"Best SPY hold: {best_spy_hold}d "
                f"(avg {fmt_pct(best_spy_s['avg_ret'])}, "
                f"hit {fmt_pct(best_spy_s['hit_rate'])})."
            )
        else:
            spy_str = "Insufficient SPY trade data."

        # best hold for stocks: combined across all tickers
        stock_hold_summary = {}
        for hold in FIXED_HOLDS:
            all_t = []
            for ticker in USA_TICKERS:
                all_t.extend(stock_hold_results[sc][hold].get(ticker, []))
            stock_hold_summary[hold] = stats(all_t)
        valid_stock = [(h, s) for h, s in stock_hold_summary.items() if s["n"] > 0 and not np.isnan(s["avg_ret"])]
        if valid_stock:
            best_stock_hold, best_stock_s = max(valid_stock, key=lambda x: x[1]["avg_ret"])
            # compare to baseline
            base_combined = []
            for ticker in USA_TICKERS:
                base_combined.extend(baseline_hold_results[best_stock_hold].get(ticker, []))
            base_s = stats(base_combined)
            delta = best_stock_s["avg_ret"] - base_s["avg_ret"] if not np.isnan(base_s["avg_ret"]) else np.nan
            delta_str = fmt_pct(delta) if not np.isnan(delta) else "unknown"
            stock_str = (
                f"Best stock hold: {best_stock_hold}d "
                f"(avg {fmt_pct(best_stock_s['avg_ret'])}, "
                f"hit {fmt_pct(best_stock_s['hit_rate'])}, "
                f"delta vs baseline {delta_str})."
            )
        else:
            stock_str = "No valid stock trades under this scenario."

        lines += [
            f"- Signals fired: **{n_sig}**",
            f"- Recovery: {rec_str}",
            f"- {spy_str}",
            f"- {stock_str}",
            "",
        ]

    lines += [
        "---",
        "",
        "_Generated by backtest/srp_pap_backtest_v5.py_",
    ]

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("SRP + PAP Backtest v5 — SPY Early Recovery Hypothesis")
    print(f"Period: {START_DATE} → {END_DATE}")
    print("=" * 60)

    # ── 1. Fetch data ─────────────────────────────────────────────────────────
    print("\n[1] Fetching SPY data …")
    spy_data = fetch_ohlcv([SPY_TICKER], "spy_v5")
    spy_df   = spy_data.get(SPY_TICKER)
    if spy_df is None:
        print("ERROR: Could not fetch SPY data.")
        return

    print("\n[2] Fetching individual stock data …")
    stock_data = fetch_ohlcv(USA_TICKERS, "usa_v5")

    # ── 2. Compute indicators for SPY ─────────────────────────────────────────
    print("\n[3] Computing SPY SRP and PAP …")
    spy_srp = compute_srp(spy_df)
    spy_pap = compute_pap(spy_df)
    print(f"  SPY bars: {len(spy_df)}")
    print(f"  SPY SRP bullish signals: {(spy_srp['direction'] == 'bullish').sum()}")
    print(f"  SPY PAP Rejected bars:   {(spy_pap['acceptance_state'] == 'Rejected').sum()}")

    # ── 3. Align all stocks to SPY dates ──────────────────────────────────────
    # We run PAP on the stock's own data, then reindex to SPY dates
    spy_dates = spy_df.index
    max_n     = len(spy_df)

    print("\n[4] Computing PAP for individual stocks …")
    stock_pafs: dict[str, pd.DataFrame] = {}
    stock_dfs:  dict[str, pd.DataFrame] = {}

    for ticker in USA_TICKERS:
        df = stock_data.get(ticker)
        if df is None:
            print(f"  {ticker}: missing, skipping")
            continue
        # Reindex to SPY trading dates
        df_aligned = df.reindex(spy_dates, method=None)
        df_aligned = df_aligned.ffill().bfill()
        pap = compute_pap(df_aligned)
        stock_pafs[ticker] = pap
        stock_dfs[ticker]  = df_aligned
        print(f"  {ticker}: {len(df_aligned)} bars aligned")

    # ── 4. Detect SPY scenarios ───────────────────────────────────────────────
    # Leave room: max signal bar = n - max_hold - 2
    max_sig_bar = max_n - max(FIXED_HOLDS) - 2
    print("\n[5] Detecting SPY scenarios …")
    spy_scenarios = detect_spy_scenarios(spy_srp, spy_pap, max_sig_bar)
    for sc, bars in spy_scenarios.items():
        print(f"  Scenario {sc}: {len(bars)} signals")

    # ── 5. SPY fixed-hold simulation ──────────────────────────────────────────
    print("\n[6] Simulating SPY fixed-hold trades …")
    spy_hold_results: dict[str, dict[int, list[dict]]] = {}
    for sc in ("A", "B", "C"):
        spy_hold_results[sc] = {}
        for hold in FIXED_HOLDS:
            trades = simulate_spy_fixed_hold(spy_df, spy_scenarios[sc], hold)
            spy_hold_results[sc][hold] = trades
            s = stats(trades)
            print(f"  SPY Scenario {sc} hold={hold}d: n={s['n']:>3}  "
                  f"hit={fmt_pct(s['hit_rate'])}  avg={fmt_pct(s['avg_ret'])}")

    # ── 6. Recovery analysis ──────────────────────────────────────────────────
    print("\n[7] Computing SPY recovery days …")
    recovery_by_scenario: dict[str, list[int | None]] = {}
    for sc in ("A", "B", "C"):
        days_list = [days_until_spy_recovered(spy_pap, sig) for sig in spy_scenarios[sc]]
        recovery_by_scenario[sc] = days_list
        rs = recovery_stats(days_list)
        print(f"  Scenario {sc}: recovered={rs['n_recovered']}/{rs['n_signals']} "
              f"({fmt_f(rs['pct_recovered'])}%)  avg={fmt_f(rs['avg_days'])}d")

    # ── 7. Stock fixed-hold simulation under each scenario ───────────────────
    print("\n[8] Simulating stock trades under SPY scenarios …")
    # stock_hold_results[scenario][hold][ticker] = list of trades
    stock_hold_results: dict[str, dict[int, dict[str, list[dict]]]] = {}
    for sc in ("A", "B", "C"):
        stock_hold_results[sc] = {}
        for hold in FIXED_HOLDS:
            stock_hold_results[sc][hold] = {}
            all_sc_hold = []
            for ticker in USA_TICKERS:
                if ticker not in stock_dfs:
                    stock_hold_results[sc][hold][ticker] = []
                    continue
                trades = simulate_stock_fixed_hold(
                    stock_dfs[ticker], stock_pafs[ticker],
                    spy_scenarios[sc], ticker, hold
                )
                stock_hold_results[sc][hold][ticker] = trades
                all_sc_hold.extend(trades)
            s = stats(all_sc_hold)
            print(f"  Scenario {sc} hold={hold}d: n={s['n']:>4}  "
                  f"hit={fmt_pct(s['hit_rate'])}  avg={fmt_pct(s['avg_ret'])}")

    # ── 8. Baseline simulation ─────────────────────────────────────────────────
    print("\n[9] Simulating baseline (no SPY condition) …")
    baseline_hold_results: dict[int, dict[str, list[dict]]] = {}
    for hold in FIXED_HOLDS:
        baseline_hold_results[hold] = {}
        all_base = []
        for ticker in USA_TICKERS:
            if ticker not in stock_dfs:
                baseline_hold_results[hold][ticker] = []
                continue
            trades = simulate_baseline(
                stock_dfs[ticker], stock_pafs[ticker],
                ticker, hold, max_sig_bar
            )
            baseline_hold_results[hold][ticker] = trades
            all_base.extend(trades)
        s = stats(all_base)
        print(f"  Baseline hold={hold}d: n={s['n']:>4}  "
              f"hit={fmt_pct(s['hit_rate'])}  avg={fmt_pct(s['avg_ret'])}")

    # ── 9. Generate report ────────────────────────────────────────────────────
    print("\n[10] Writing report …")
    today_str = date.today().isoformat()
    report = generate_report(
        spy_df               = spy_df,
        spy_scenarios        = spy_scenarios,
        spy_hold_results     = spy_hold_results,
        recovery_by_scenario = recovery_by_scenario,
        stock_hold_results   = stock_hold_results,
        baseline_hold_results= baseline_hold_results,
        today                = today_str,
    )
    report_path = BACKTEST_DIR / "srp_pap_backtest_v5.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"  Report saved → {report_path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
