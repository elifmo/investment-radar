"""
SRP + PAP Backtest v4 — Updated Configs (BIST 20 tickers, USA SPY regime filter)
==================================================================================

BIST Config:
  - Entry: PAP state Accepted or Edge (NO hard SRP gate)
  - SRP tracked as score booster — recorded but never used to exclude signals
  - 20 BIST tickers
  - Hold periods: 20, 40, 60, 90 days (fixed) + signal-based exit (PAP→Rejected or max 90d)
  - SRP booster analysis: SRP>=60 vs SRP<60 subgroups

USA Config:
  - Entry: PAP state Accepted or Edge (NO SRP filter)
  - SPY PAP computed separately; individual stock signals only entered when SPY PAP is Accepted or Edge
  - 10 stocks + SPY for regime
  - Hold periods: 10, 20 days (fixed) + signal-based exit (PAP→Rejected or max 20d)
  - Reports % of signals filtered by SPY Rejected state

Usage:
    /Users/Elifcik/Desktop/apps/investment-radar/.venv/bin/python3 backtest/srp_pap_backtest_v4.py
"""

import warnings
warnings.filterwarnings("ignore")

import sys
from pathlib import Path
from datetime import date, timedelta
import numpy as np
import pandas as pd
import yfinance as yf

BACKTEST_DIR = Path(__file__).parent
CACHE_DIR    = BACKTEST_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# ── Universe ──────────────────────────────────────────────────────────────────
BIST_TICKERS = [
    "EREGL.IS", "TOASO.IS", "TUPRS.IS", "THYAO.IS", "KCHOL.IS",
    "AKBNK.IS", "GARAN.IS", "ISCTR.IS", "HALKB.IS", "VAKBN.IS",
    "BIMAS.IS", "MGROS.IS", "ARCLK.IS", "FROTO.IS", "TTKOM.IS",
    "PETKM.IS", "ASELS.IS", "TCELL.IS", "SASA.IS",  "EKGYO.IS",
]

USA_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META",
    "GOOGL", "JPM", "V", "UNH", "XOM",
]

SPY_TICKER = "SPY"

START_DATE = (date.today() - timedelta(days=2 * 365 + 10)).isoformat()
END_DATE   = date.today().isoformat()

BIST_MAX_HOLD   = 90   # safety cap for BIST signal-based exit
BIST_FIXED_HOLDS = [20, 40, 60, 90]

USA_MAX_HOLD    = 20   # safety cap for USA signal-based exit
USA_FIXED_HOLDS = [10, 20]

SRP_BOOSTER_THRESHOLD = 60  # split into SRP >= 60 vs SRP < 60 subgroups

# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch_ohlcv(tickers: list[str], cache_key: str) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV for a list of tickers, with per-group cache."""
    cache_path = CACHE_DIR / f"srp_pap_v4_{cache_key}.pkl"
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
      score     : reversalScore (0-100) per bar
      direction : 'bullish' | 'bearish' | '' (only non-empty on sweep bars)
    """
    n = len(df)
    if n < max(lookback, atr_period, vol_baseline) + 5:
        return pd.DataFrame({
            "score":     pd.Series(np.nan, index=df.index),
            "direction": pd.Series("",    index=df.index),
        })

    hi  = df["High"]
    lo  = df["Low"]
    cl  = df["Close"]
    op  = df["Open"]
    vol = df["Volume"] if "Volume" in df.columns else pd.Series(1, index=df.index)

    tr = pd.concat([
        hi - lo,
        (hi - cl.shift(1)).abs(),
        (lo - cl.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(atr_period).mean()

    roll_hi  = hi.rolling(lookback).max().shift(1)
    roll_lo  = lo.rolling(lookback).min().shift(1)

    vol_ma    = vol.rolling(vol_baseline).mean()
    vol_ratio = (vol / vol_ma.replace(0, np.nan)).clip(0.1, 5.0)

    scores     = pd.Series(0.0, index=df.index)
    directions = pd.Series("",  index=df.index, dtype=object)

    for i in range(max(lookback, atr_period, vol_baseline) + 1, n):
        bar_hi  = hi.iloc[i]
        bar_lo  = lo.iloc[i]
        bar_cl  = cl.iloc[i]
        bar_op  = op.iloc[i]
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

        wick_size  = (wick_lower if bull_sweep else wick_upper)
        wick_score = min(100.0, (wick_size / bar_atr) * 50)
        pen_score  = min(100.0, (sweep_depth / bar_atr) * 40)

        vr        = vol_ratio.iloc[i]
        vol_score = min(100.0, (vr - 1.0) * 50 + 50) if not pd.isna(vr) else 50.0
        vol_score = max(0.0, vol_score)

        sweep_score      = wick_score * 0.56 + pen_score * 0.34 + vol_score * 0.10
        close_back_score = min(100.0, close_pct * 100)
        confirm_score    = 80.0 if confirm_bull else 30.0

        body              = abs(bar_cl - bar_op)
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

        bins          = np.linspace(w_min, w_max, n_rows + 1)
        counts, edges = np.histogram(window, bins=bins)
        row_mids      = (edges[:-1] + edges[1:]) / 2

        poc_idx = counts.argmax()
        poc     = row_mids[poc_idx]

        total    = counts.sum()
        target   = int(total * value_area_pct)
        included = set([poc_idx])
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
            rotation   = "Up" if cog_second > cog_first * 1.001 else \
                         "Down" if cog_second < cog_first * 0.999 else "Neutral"
        else:
            rotation = "Neutral"

        row_height = (w_max - w_min) / n_rows
        edge_band  = row_height * 1.5
        if cur_price < val - edge_band or cur_price > vah + edge_band:
            state = "Rejected"
        elif (cur_price < val + edge_band and cur_price >= val - edge_band) or \
             (cur_price > vah - edge_band and cur_price <= vah + edge_band):
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


# ── BIST Entry signal detection ───────────────────────────────────────────────

def detect_entries_bist(df: pd.DataFrame, srp: pd.DataFrame,
                         pap: pd.DataFrame, max_hold_buffer: int) -> list[dict]:
    """
    BIST entry: PAP state Accepted or Edge (no hard SRP gate).
    SRP score is recorded but does NOT exclude signals.
    """
    n  = len(df)
    op = df["Open"] if "Open" in df.columns else df["Close"]
    entries = []

    for i in range(1, n - max_hold_buffer - 2):
        srp_score = srp["score"].iloc[i]
        srp_dir   = srp["direction"].iloc[i]
        pap_state = pap["acceptance_state"].iloc[i]

        # Must have an SRP event (direction non-empty and score > 0)
        if srp_dir == "" or pd.isna(srp_score) or srp_score == 0.0:
            continue
        if pap_state == "" or pd.isna(pap_state):
            continue

        # PAP gate (no SRP gate)
        if pap_state not in ("Accepted", "Edge"):
            continue

        entry_price = float(op.iloc[i + 1])
        if entry_price <= 0:
            continue

        entries.append({
            "signal_bar":  i,
            "entry_bar":   i + 1,
            "entry_price": entry_price,
            "srp_score":   float(srp_score),
            "srp_dir":     srp_dir,
            "pap_state":   pap_state,
        })

    return entries


# ── USA Entry signal detection ────────────────────────────────────────────────

def detect_entries_usa(df: pd.DataFrame, srp: pd.DataFrame,
                        pap: pd.DataFrame, spy_pap: pd.DataFrame,
                        max_hold_buffer: int) -> tuple[list[dict], int]:
    """
    USA entry: PAP state Accepted or Edge (no SRP filter).
    SPY PAP state must be Accepted or Edge to enter.
    Returns (entries, n_filtered_by_spy).
    """
    n  = len(df)
    op = df["Open"] if "Open" in df.columns else df["Close"]
    entries          = []
    filtered_by_spy  = 0

    for i in range(1, n - max_hold_buffer - 2):
        srp_score = srp["score"].iloc[i]
        srp_dir   = srp["direction"].iloc[i]
        pap_state = pap["acceptance_state"].iloc[i]

        if srp_dir == "" or pd.isna(srp_score) or srp_score == 0.0:
            continue
        if pap_state == "" or pd.isna(pap_state):
            continue

        if pap_state not in ("Accepted", "Edge"):
            continue

        entry_price = float(op.iloc[i + 1])
        if entry_price <= 0:
            continue

        # SPY macro regime gate
        if i < len(spy_pap):
            spy_state = spy_pap["acceptance_state"].iloc[i]
            if spy_state == "Rejected" or spy_state == "":
                filtered_by_spy += 1
                continue
        else:
            filtered_by_spy += 1
            continue

        entries.append({
            "signal_bar":  i,
            "entry_bar":   i + 1,
            "entry_price": entry_price,
            "srp_score":   float(srp_score),
            "srp_dir":     srp_dir,
            "pap_state":   pap_state,
        })

    return entries, filtered_by_spy


# ── Signal-based exit simulation ──────────────────────────────────────────────

def simulate_signal_exit(df: pd.DataFrame, srp: pd.DataFrame, pap: pd.DataFrame,
                          entries: list[dict], ticker: str, universe: str,
                          max_hold: int) -> list[dict]:
    """
    For each entry, walk forward bar-by-bar until:
      1. PAP state shifts to Rejected
      2. SRP fires a signal in the OPPOSITE direction
      3. max_hold days reached

    Exit price = close of the exit bar.
    """
    cl     = df["Close"]
    n      = len(df)
    trades = []

    for e in entries:
        entry_bar   = e["entry_bar"]
        entry_price = e["entry_price"]
        srp_dir     = e["srp_dir"]
        opposite    = "bearish" if srp_dir == "bullish" else "bullish"

        exit_bar    = None
        exit_reason = None

        for j in range(entry_bar + 1, min(entry_bar + max_hold + 1, n)):
            pap_state_j = pap["acceptance_state"].iloc[j]
            srp_dir_j   = srp["direction"].iloc[j]

            if pap_state_j == "Rejected":
                exit_bar    = j
                exit_reason = "PAP_Rejected"
                break

            if srp_dir_j == opposite:
                exit_bar    = j
                exit_reason = "Opposite_SRP"
                break

        if exit_bar is None:
            exit_bar    = min(entry_bar + max_hold, n - 1)
            exit_reason = "MaxHold"

        exit_price = float(cl.iloc[exit_bar])
        days_held  = exit_bar - entry_bar
        ret        = (exit_price - entry_price) / entry_price

        trades.append({
            "ticker":      ticker,
            "universe":    universe,
            "signal_date": df.index[e["signal_bar"]],
            "entry_date":  df.index[entry_bar],
            "exit_date":   df.index[exit_bar],
            "srp_score":   e["srp_score"],
            "srp_dir":     srp_dir,
            "pap_state":   e["pap_state"],
            "entry_price": entry_price,
            "exit_price":  exit_price,
            "days_held":   days_held,
            "ret":         ret,
            "hit":         int(ret > 0),
            "exit_reason": exit_reason,
        })

    return trades


# ── Fixed hold period simulation ──────────────────────────────────────────────

def simulate_fixed_hold(df: pd.DataFrame, entries: list[dict],
                         ticker: str, universe: str, hold: int) -> list[dict]:
    """
    For each entry, exit at close of (entry_bar + hold) bar.
    Skip if not enough data.
    """
    cl     = df["Close"]
    n      = len(df)
    trades = []

    for e in entries:
        entry_bar = e["entry_bar"]
        exit_bar  = entry_bar + hold

        if exit_bar >= n:
            continue

        exit_price = float(cl.iloc[exit_bar])
        ret        = (exit_price - e["entry_price"]) / e["entry_price"]

        trades.append({
            "ticker":      ticker,
            "universe":    universe,
            "hold":        hold,
            "srp_score":   e["srp_score"],
            "pap_state":   e["pap_state"],
            "entry_price": e["entry_price"],
            "exit_price":  exit_price,
            "ret":         ret,
            "hit":         int(ret > 0),
        })

    return trades


# ── Statistics helpers ────────────────────────────────────────────────────────

def trade_stats(trades: list[dict], label: str = "") -> dict:
    """Compute summary stats for a list of signal-exit trades."""
    if not trades:
        return {
            "label": label, "n": 0,
            "hit_rate": np.nan, "avg_ret": np.nan,
            "median_ret": np.nan, "avg_days": np.nan, "median_days": np.nan,
        }
    df = pd.DataFrame(trades)
    return {
        "label":       label,
        "n":           len(df),
        "hit_rate":    df["hit"].mean() * 100,
        "avg_ret":     df["ret"].mean() * 100,
        "median_ret":  df["ret"].median() * 100,
        "avg_days":    df["days_held"].mean(),
        "median_days": df["days_held"].median(),
    }


def fixed_hold_stats(trades: list[dict], holds: list[int], universe: str) -> list[dict]:
    """Compute stats per fixed hold period for a given universe."""
    results = []
    df = pd.DataFrame(trades) if trades else pd.DataFrame()

    for hold in holds:
        sub = df[df["hold"] == hold] if not df.empty else pd.DataFrame()
        if sub.empty:
            results.append({
                "hold": hold, "universe": universe, "n": 0,
                "hit_rate": np.nan, "avg_ret": np.nan, "median_ret": np.nan,
            })
        else:
            results.append({
                "hold":       hold,
                "universe":   universe,
                "n":          len(sub),
                "hit_rate":   sub["hit"].mean() * 100,
                "avg_ret":    sub["ret"].mean() * 100,
                "median_ret": sub["ret"].median() * 100,
            })
    return results


def srp_booster_stats(trades: list[dict], threshold: float = 60.0) -> dict:
    """Split signal-exit trades into SRP >= threshold and SRP < threshold."""
    if not trades:
        return {"high_srp": {}, "low_srp": {}}
    df       = pd.DataFrame(trades)
    high_srp = df[df["srp_score"] >= threshold].to_dict("records")
    low_srp  = df[df["srp_score"] <  threshold].to_dict("records")
    return {
        "high_srp": trade_stats(high_srp, f"SRP >= {threshold:.0f}"),
        "low_srp":  trade_stats(low_srp,  f"SRP < {threshold:.0f}"),
    }


def srp_booster_fixed_stats(trades: list[dict], holds: list[int],
                              threshold: float = 60.0) -> dict:
    """SRP booster split for fixed hold trades."""
    if not trades:
        return {"high": [], "low": []}
    df       = pd.DataFrame(trades)
    high_trades = df[df["srp_score"] >= threshold].to_dict("records")
    low_trades  = df[df["srp_score"] <  threshold].to_dict("records")
    return {
        "high": fixed_hold_stats(high_trades, holds, "BIST SRP>=60"),
        "low":  fixed_hold_stats(low_trades,  holds, "BIST SRP<60"),
    }


def exit_reason_breakdown(trades: list[dict]) -> dict:
    if not trades:
        return {}
    df = pd.DataFrame(trades)
    return df["exit_reason"].value_counts().to_dict()


def per_ticker_signal_stats(trades: list[dict]) -> pd.DataFrame:
    """Per-ticker stats for signal-based exits."""
    if not trades:
        return pd.DataFrame()
    df      = pd.DataFrame(trades)
    grouped = df.groupby("ticker").agg(
        n           = ("hit",       "count"),
        hit_rate    = ("hit",       "mean"),
        avg_ret     = ("ret",       "mean"),
        avg_days    = ("days_held", "mean"),
        median_days = ("days_held", "median"),
    ).reset_index()
    grouped["hit_rate"] = grouped["hit_rate"] * 100
    grouped["avg_ret"]  = grouped["avg_ret"]  * 100
    return grouped.sort_values("avg_ret", ascending=False)


# ── Markdown formatting helpers ───────────────────────────────────────────────

def _f(val, fmt=".2f", suffix="", fallback="—"):
    if pd.isna(val):
        return fallback
    return f"{val:{fmt}}{suffix}"


def fmt_fixed_hold_table(fixed_rows: list[dict]) -> str:
    lines = [
        "| Hold (days) | # Trades | Hit Rate | Avg Return | Median Return |",
        "|-------------|----------|----------|------------|---------------|",
    ]
    for r in fixed_rows:
        n  = r["n"]
        hr = _f(r.get("hit_rate"), ".1f", "%")
        ar = _f(r.get("avg_ret"),  "+.2f", "%")
        mr = _f(r.get("median_ret"), "+.2f", "%")
        lines.append(f"| {r['hold']:>11} | {n:>8} | {hr:>8} | {ar:>10} | {mr:>13} |")
    return "\n".join(lines)


def fmt_ticker_signal_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No data_"
    lines = [
        "| Ticker | # Trades | Hit Rate | Avg Return | Avg Days | Median Days |",
        "|--------|----------|----------|------------|----------|-------------|",
    ]
    for row in df.itertuples():
        lines.append(
            f"| {row.ticker:<12} | {row.n:>8} | {row.hit_rate:>7.1f}% | "
            f"{row.avg_ret:>+9.2f}% | {row.avg_days:>8.1f} | {row.median_days:>11.0f} |"
        )
    return "\n".join(lines)


def fmt_srp_booster_table(high: dict, low: dict) -> str:
    lines = [
        "| Subgroup      | # Trades | Hit Rate | Avg Return | Median Return | Avg Days |",
        "|---------------|----------|----------|------------|---------------|----------|",
    ]
    for s in [high, low]:
        if not s or s.get("n", 0) == 0:
            lines.append(f"| {s.get('label', '—'):<13} |        0 |        — |          — |             — |        — |")
        else:
            lines.append(
                f"| {s['label']:<13} | {s['n']:>8} | {_f(s.get('hit_rate'), '.1f', '%'):>8} | "
                f"{_f(s.get('avg_ret'), '+.2f', '%'):>10} | {_f(s.get('median_ret'), '+.2f', '%'):>13} | "
                f"{_f(s.get('avg_days'), '.1f'):>8} |"
            )
    return "\n".join(lines)


def fmt_srp_booster_fixed_table(booster_fixed: dict, holds: list[int]) -> str:
    """Side-by-side fixed hold comparison for high vs low SRP subgroups."""
    high_rows = {r["hold"]: r for r in booster_fixed["high"]}
    low_rows  = {r["hold"]: r for r in booster_fixed["low"]}

    lines = [
        "| Hold | SRP>=60 n | SRP>=60 Hit | SRP>=60 Avg | SRP<60 n | SRP<60 Hit | SRP<60 Avg |",
        "|------|-----------|-------------|-------------|----------|------------|------------|",
    ]
    for h in holds:
        hi = high_rows.get(h, {})
        lo = low_rows.get(h, {})
        lines.append(
            f"| {h:>4} | {hi.get('n', 0):>9} | {_f(hi.get('hit_rate'), '.1f', '%'):>11} | "
            f"{_f(hi.get('avg_ret'), '+.2f', '%'):>11} | {lo.get('n', 0):>8} | "
            f"{_f(lo.get('hit_rate'), '.1f', '%'):>10} | {_f(lo.get('avg_ret'), '+.2f', '%'):>10} |"
        )
    return "\n".join(lines)


# ── Report generation ─────────────────────────────────────────────────────────

def generate_report(
    bist_sig_trades: list[dict],
    bist_fix_trades: list[dict],
    usa_sig_trades_no_spy: list[dict],
    usa_fix_trades_no_spy: list[dict],
    usa_sig_trades_spy:    list[dict],
    usa_fix_trades_spy:    list[dict],
    spy_filtered_count:    int,
    spy_total_pre_filter:  int,
    today: str,
) -> str:

    # ── BIST stats ────────────────────────────────────────────────────────
    bist_overall      = trade_stats(bist_sig_trades, "BIST (all PAP)")
    bist_fixed        = fixed_hold_stats(bist_fix_trades, BIST_FIXED_HOLDS, "BIST")
    bist_exit_reasons = exit_reason_breakdown(bist_sig_trades)
    bist_ticker_df    = per_ticker_signal_stats(bist_sig_trades)

    srp_split      = srp_booster_stats(bist_sig_trades, SRP_BOOSTER_THRESHOLD)
    srp_fixed_split = srp_booster_fixed_stats(bist_fix_trades, BIST_FIXED_HOLDS, SRP_BOOSTER_THRESHOLD)

    # ── USA stats ─────────────────────────────────────────────────────────
    usa_no_spy_overall = trade_stats(usa_sig_trades_no_spy, "USA (no SPY filter)")
    usa_spy_overall    = trade_stats(usa_sig_trades_spy,    "USA (SPY regime)")
    usa_no_spy_fixed   = fixed_hold_stats(usa_fix_trades_no_spy, USA_FIXED_HOLDS, "USA no-filter")
    usa_spy_fixed      = fixed_hold_stats(usa_fix_trades_spy,    USA_FIXED_HOLDS, "USA SPY-filter")
    usa_exit_reasons   = exit_reason_breakdown(usa_sig_trades_spy)
    usa_ticker_df      = per_ticker_signal_stats(usa_sig_trades_spy)

    spy_filter_pct = (spy_filtered_count / spy_total_pre_filter * 100) if spy_total_pre_filter > 0 else 0.0

    # ── Final recommendation table ────────────────────────────────────────
    def _row(label, stats):
        if stats.get("n", 0) == 0:
            return f"| {label:<28} | {'—':>8} | {'—':>8} | {'—':>10} | {'—':>13} | {'—':>9} |"
        return (
            f"| {label:<28} | {stats['n']:>8} | {_f(stats.get('hit_rate'), '.1f', '%'):>8} | "
            f"{_f(stats.get('avg_ret'), '+.2f', '%'):>10} | {_f(stats.get('median_ret'), '+.2f', '%'):>13} | "
            f"{_f(stats.get('avg_days'), '.1f'):>9} |"
        )

    rec_header = (
        "| Strategy                     | # Trades | Hit Rate | Avg Return | Median Return | Avg Days |\n"
        "|------------------------------|----------|----------|------------|---------------|----------|"
    )

    # ── BIST verdict ──────────────────────────────────────────────────────
    hi_srp = srp_split["high_srp"]
    lo_srp = srp_split["low_srp"]

    def srp_booster_verdict():
        if hi_srp.get("n", 0) == 0 or lo_srp.get("n", 0) == 0:
            return "Insufficient data to compare SRP subgroups."
        diff = (hi_srp.get("avg_ret", 0) or 0) - (lo_srp.get("avg_ret", 0) or 0)
        hr_diff = (hi_srp.get("hit_rate", 0) or 0) - (lo_srp.get("hit_rate", 0) or 0)
        if diff > 0.5 or hr_diff > 3:
            return (
                f"SRP booster adds value even without a hard gate: SRP>=60 signals yield "
                f"{_f(hi_srp.get('avg_ret'), '+.2f', '%')} avg return and "
                f"{_f(hi_srp.get('hit_rate'), '.1f', '%')} hit rate vs "
                f"{_f(lo_srp.get('avg_ret'), '+.2f', '%')} / "
                f"{_f(lo_srp.get('hit_rate'), '.1f', '%')} for SRP<60. "
                f"Soft SRP threshold of 60 recommended as a confidence booster."
            )
        elif diff < -0.5:
            return (
                f"Surprisingly, SRP<60 signals perform similarly or better in this period "
                f"({_f(lo_srp.get('avg_ret'), '+.2f', '%')} vs {_f(hi_srp.get('avg_ret'), '+.2f', '%')}). "
                f"The PAP entry gate appears sufficient; SRP scoring provides limited additional filtering."
            )
        else:
            return (
                f"SRP score subgroups show minimal difference in this period "
                f"(SRP>=60: {_f(hi_srp.get('avg_ret'), '+.2f', '%')}, "
                f"SRP<60: {_f(lo_srp.get('avg_ret'), '+.2f', '%')}). "
                f"PAP state alone appears to be the primary driver."
            )

    # ── USA verdict ───────────────────────────────────────────────────────
    def spy_filter_verdict():
        if usa_no_spy_overall.get("n", 0) == 0:
            return "Insufficient data for USA analysis."
        diff = (usa_spy_overall.get("avg_ret", 0) or 0) - (usa_no_spy_overall.get("avg_ret", 0) or 0)
        hr_diff = (usa_spy_overall.get("hit_rate", 0) or 0) - (usa_no_spy_overall.get("hit_rate", 0) or 0)
        if diff > 0.3 or hr_diff > 3:
            return (
                f"SPY PAP regime filter improves signal quality: filtered signals avg "
                f"{_f(usa_spy_overall.get('avg_ret'), '+.2f', '%')} return vs "
                f"{_f(usa_no_spy_overall.get('avg_ret'), '+.2f', '%')} without filter. "
                f"{spy_filtered_count} signals ({spy_filter_pct:.1f}%) were filtered out by SPY Rejected state. "
                f"Recommend keeping SPY regime gate."
            )
        else:
            return (
                f"SPY PAP regime filter shows marginal improvement "
                f"({_f(usa_spy_overall.get('avg_ret'), '+.2f', '%')} vs "
                f"{_f(usa_no_spy_overall.get('avg_ret'), '+.2f', '%')}). "
                f"{spy_filtered_count} signals ({spy_filter_pct:.1f}%) were filtered. "
                f"Individual stock PAP state is the primary driver."
            )

    # ── Build markdown ─────────────────────────────────────────────────────
    lines = [
        "# SRP + PAP Backtest v4 — BIST 20 Tickers & USA SPY Regime",
        "",
        f"**Date generated:** {today}",
        f"**Period:** {START_DATE} → {END_DATE} (2 years daily)",
        "",
        "## Entry & Exit Configs",
        "",
        "| Universe | Entry Logic | SRP Gate | Hold Periods |",
        "|----------|-------------|----------|--------------|",
        f"| BIST     | PAP Accepted or Edge | None (SRP recorded as booster score) | 20, 40, 60, 90d fixed + signal-based (max 90d) |",
        f"| USA      | PAP Accepted or Edge | None (SPY PAP regime gate instead) | 10, 20d fixed + signal-based (max 20d) |",
        "",
        "---",
        "",
        "## BIST Results",
        "",
        "### 1. Overall — Signal-Based Exit",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total trades | {bist_overall['n']} |",
        f"| Hit rate | {_f(bist_overall.get('hit_rate'), '.1f', '%')} |",
        f"| Avg return | {_f(bist_overall.get('avg_ret'), '+.2f', '%')} |",
        f"| Median return | {_f(bist_overall.get('median_ret'), '+.2f', '%')} |",
        f"| Avg days held | {_f(bist_overall.get('avg_days'), '.1f', 'd')} |",
        f"| Median days held | {_f(bist_overall.get('median_days'), '.0f', 'd')} |",
        "",
        "**Exit reason breakdown:**",
        "",
    ]

    for reason, cnt in sorted(bist_exit_reasons.items(), key=lambda x: -x[1]):
        total = bist_overall["n"] or 1
        lines.append(f"- {reason}: {cnt} ({cnt/total*100:.1f}%)")

    lines += [
        "",
        "### 1b. Fixed Hold Periods — BIST",
        "",
        fmt_fixed_hold_table(bist_fixed),
        "",
        "### 2. SRP Booster Analysis — Signal-Based Exit",
        "",
        "Entry condition: PAP Accepted or Edge (same for both groups). SRP score only used to split results.",
        "",
        fmt_srp_booster_table(hi_srp, lo_srp),
        "",
        "#### SRP Booster — Fixed Hold Comparison",
        "",
        fmt_srp_booster_fixed_table(srp_fixed_split, BIST_FIXED_HOLDS),
        "",
        "### 3. Per-Ticker Breakdown — BIST Signal-Based Exit",
        "",
        fmt_ticker_signal_table(bist_ticker_df),
        "",
        "### 4. BIST Verdict",
        "",
        srp_booster_verdict(),
        "",
        "---",
        "",
        "## USA Results",
        "",
        f"**SPY Regime Filter:** {spy_filtered_count} signals filtered out of {spy_total_pre_filter} "
        f"total pre-filter signals ({spy_filter_pct:.1f}% filtered).",
        "",
        "### 1. Without SPY Filter vs With SPY Filter — Signal-Based Exit",
        "",
        "| Config | # Trades | Hit Rate | Avg Return | Median Return | Avg Days |",
        "|--------|----------|----------|------------|---------------|----------|",
        _row("USA (no SPY filter)", usa_no_spy_overall),
        _row("USA (SPY regime gate)", usa_spy_overall),
        "",
        "### 2. Fixed Hold Periods",
        "",
        "#### Without SPY Filter",
        "",
        fmt_fixed_hold_table(usa_no_spy_fixed),
        "",
        "#### With SPY Regime Gate",
        "",
        fmt_fixed_hold_table(usa_spy_fixed),
        "",
        "### 3. Signals Filtered by SPY Rejected State",
        "",
        f"- Pre-filter signals (individual PAP ok): **{spy_total_pre_filter}**",
        f"- Filtered by SPY Rejected: **{spy_filtered_count}** ({spy_filter_pct:.1f}%)",
        f"- Signals that passed SPY gate: **{spy_total_pre_filter - spy_filtered_count}** ({100 - spy_filter_pct:.1f}%)",
        "",
        "### 4. Per-Ticker Breakdown — USA Signal-Based Exit (SPY regime applied)",
        "",
        fmt_ticker_signal_table(usa_ticker_df),
        "",
        "**Exit reason breakdown (SPY-filtered):**",
        "",
    ]

    for reason, cnt in sorted(usa_exit_reasons.items(), key=lambda x: -x[1]):
        total = usa_spy_overall["n"] or 1
        lines.append(f"- {reason}: {cnt} ({cnt/total*100:.1f}%)")

    lines += [
        "",
        "### 5. USA Verdict",
        "",
        spy_filter_verdict(),
        "",
        "---",
        "",
        "## Final Recommendation Table",
        "",
        rec_header,
        _row("BIST signal-based (no SRP gate)", bist_overall),
        _row(f"BIST SRP>=60 signal-based", hi_srp),
        _row(f"BIST SRP<60 signal-based", lo_srp),
        _row("USA signal-based (no SPY)", usa_no_spy_overall),
        _row("USA signal-based (SPY regime)", usa_spy_overall),
        "",
        "#### Fixed Hold Summary",
        "",
        "| Universe | Hold | # Trades | Hit Rate | Avg Return |",
        "|----------|------|----------|----------|------------|",
    ]

    for r in bist_fixed:
        lines.append(
            f"| BIST | {r['hold']:>4}d | {r['n']:>8} | "
            f"{_f(r.get('hit_rate'), '.1f', '%'):>8} | {_f(r.get('avg_ret'), '+.2f', '%'):>10} |"
        )
    for r in usa_spy_fixed:
        lines.append(
            f"| USA (SPY gate) | {r['hold']:>4}d | {r['n']:>8} | "
            f"{_f(r.get('hit_rate'), '.1f', '%'):>8} | {_f(r.get('avg_ret'), '+.2f', '%'):>10} |"
        )

    lines += [
        "",
        "---",
        "",
        "_Generated by backtest/srp_pap_backtest_v4.py_",
    ]

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("SRP + PAP Backtest v4 — BIST 20 tickers + USA SPY regime")
    print(f"Period: {START_DATE} → {END_DATE}")
    print("=" * 65)

    # ── 1. Fetch data ──────────────────────────────────────────────────
    print("\n[1] Fetching BIST data …")
    bist_data = fetch_ohlcv(BIST_TICKERS, "bist_v4")

    print("\n[2] Fetching USA data …")
    usa_data  = fetch_ohlcv(USA_TICKERS, "usa_v4")

    print("\n[3] Fetching SPY data for regime …")
    spy_data  = fetch_ohlcv([SPY_TICKER], "spy_v4")
    spy_df    = spy_data.get(SPY_TICKER)

    if spy_df is None:
        print("  WARNING: SPY data not available — USA SPY filter will pass all signals.")
        spy_pap = pd.DataFrame({"acceptance_state": pd.Series("Accepted", index=range(10000))})
    else:
        print(f"  SPY: {len(spy_df)} bars — computing PAP …")
        spy_pap = compute_pap(spy_df)

    # ── 2. BIST backtest ───────────────────────────────────────────────
    print("\n[4] Running BIST backtest (20 tickers, no hard SRP gate) …")
    bist_sig_trades = []
    bist_fix_trades = []

    for ticker, df in bist_data.items():
        print(f"  [BIST] {ticker} ({len(df)} bars) …")
        srp     = compute_srp(df)
        pap     = compute_pap(df)
        entries = detect_entries_bist(df, srp, pap, BIST_MAX_HOLD)
        print(f"    Entries: {len(entries)}")

        if not entries:
            continue

        sig_trades = simulate_signal_exit(df, srp, pap, entries, ticker, "BIST", BIST_MAX_HOLD)
        bist_sig_trades.extend(sig_trades)

        for hold in BIST_FIXED_HOLDS:
            fx_trades = simulate_fixed_hold(df, entries, ticker, "BIST", hold)
            bist_fix_trades.extend(fx_trades)

    print(f"  BIST signal trades: {len(bist_sig_trades)}")
    print(f"  BIST fixed-hold records: {len(bist_fix_trades)}")

    # ── 3. USA backtest — no SPY filter (baseline) ─────────────────────
    print("\n[5] Running USA backtest without SPY filter (baseline) …")
    usa_sig_no_spy = []
    usa_fix_no_spy = []

    for ticker, df in usa_data.items():
        print(f"  [USA-baseline] {ticker} ({len(df)} bars) …")
        srp     = compute_srp(df)
        pap     = compute_pap(df)
        # No SPY filter: pass a dummy all-accepted spy_pap
        dummy_spy = pd.DataFrame({
            "acceptance_state": pd.Series(["Accepted"] * len(df), index=df.index)
        })
        entries, _ = detect_entries_usa(df, srp, pap, dummy_spy, USA_MAX_HOLD)
        print(f"    Entries (no SPY gate): {len(entries)}")

        if not entries:
            continue

        sig_trades = simulate_signal_exit(df, srp, pap, entries, ticker, "USA", USA_MAX_HOLD)
        usa_sig_no_spy.extend(sig_trades)

        for hold in USA_FIXED_HOLDS:
            fx_trades = simulate_fixed_hold(df, entries, ticker, "USA", hold)
            usa_fix_no_spy.extend(fx_trades)

    print(f"  USA no-filter signal trades: {len(usa_sig_no_spy)}")

    # ── 4. USA backtest — with SPY regime filter ───────────────────────
    print("\n[6] Running USA backtest with SPY regime filter …")
    usa_sig_spy     = []
    usa_fix_spy     = []
    spy_total_pre   = 0
    spy_total_filt  = 0

    for ticker, df in usa_data.items():
        print(f"  [USA-SPY] {ticker} ({len(df)} bars) …")
        srp     = compute_srp(df)
        pap     = compute_pap(df)

        # Align spy_pap to the stock's date index
        aligned_spy = spy_pap.reindex(df.index, method="ffill")

        entries, n_filt = detect_entries_usa(df, srp, pap, aligned_spy, USA_MAX_HOLD)
        # baseline count for this ticker (no SPY filter)
        ticker_no_spy = [t for t in usa_sig_no_spy if t["ticker"] == ticker]
        spy_total_pre  += len(entries) + n_filt
        spy_total_filt += n_filt
        print(f"    Entries with SPY gate: {len(entries)}  (filtered: {n_filt})")

        if not entries:
            continue

        sig_trades = simulate_signal_exit(df, srp, pap, entries, ticker, "USA", USA_MAX_HOLD)
        usa_sig_spy.extend(sig_trades)

        for hold in USA_FIXED_HOLDS:
            fx_trades = simulate_fixed_hold(df, entries, ticker, "USA", hold)
            usa_fix_spy.extend(fx_trades)

    print(f"  USA SPY-filtered signal trades: {len(usa_sig_spy)}")
    print(f"  Signals filtered by SPY Rejected: {spy_total_filt} / {spy_total_pre}")

    # ── 5. Console summary ─────────────────────────────────────────────
    print("\n=== BIST Signal-Based Summary ===")
    bist_s = trade_stats(bist_sig_trades, "BIST")
    if bist_s["n"] > 0:
        print(
            f"  n={bist_s['n']}  hit={bist_s['hit_rate']:.1f}%  "
            f"avg={bist_s['avg_ret']:+.2f}%  median={bist_s['median_ret']:+.2f}%  "
            f"avg_days={bist_s['avg_days']:.1f}"
        )
    else:
        print("  No trades.")

    srp_split = srp_booster_stats(bist_sig_trades, SRP_BOOSTER_THRESHOLD)
    hi = srp_split["high_srp"]
    lo = srp_split["low_srp"]
    if hi.get("n", 0) > 0:
        print(f"  SRP>=60: n={hi['n']}  hit={_f(hi.get('hit_rate'), '.1f', '%')}  avg={_f(hi.get('avg_ret'), '+.2f', '%')}")
    if lo.get("n", 0) > 0:
        print(f"  SRP<60:  n={lo['n']}  hit={_f(lo.get('hit_rate'), '.1f', '%')}  avg={_f(lo.get('avg_ret'), '+.2f', '%')}")

    print("\n=== USA Signal-Based Summary ===")
    for s, label in [(trade_stats(usa_sig_no_spy, "USA no-filter"), "No SPY filter"),
                     (trade_stats(usa_sig_spy,    "USA SPY gate"),   "SPY regime")]:
        if s["n"] > 0:
            print(
                f"  [{label}] n={s['n']}  hit={s['hit_rate']:.1f}%  "
                f"avg={s['avg_ret']:+.2f}%  median={s['median_ret']:+.2f}%"
            )
        else:
            print(f"  [{label}] No trades.")

    print(f"\n  SPY filtered: {spy_total_filt}/{spy_total_pre} "
          f"({spy_total_filt/spy_total_pre*100:.1f}% filtered)" if spy_total_pre > 0 else "")

    # ── 6. Write report ────────────────────────────────────────────────
    print("\n[7] Writing report …")
    report = generate_report(
        bist_sig_trades      = bist_sig_trades,
        bist_fix_trades      = bist_fix_trades,
        usa_sig_trades_no_spy = usa_sig_no_spy,
        usa_fix_trades_no_spy = usa_fix_no_spy,
        usa_sig_trades_spy   = usa_sig_spy,
        usa_fix_trades_spy   = usa_fix_spy,
        spy_filtered_count   = spy_total_filt,
        spy_total_pre_filter = spy_total_pre,
        today                = date.today().isoformat(),
    )
    report_path = BACKTEST_DIR / "srp_pap_backtest_v4.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"  Report saved → {report_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
