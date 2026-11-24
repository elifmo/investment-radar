"""
SRP + PAP Backtest v2 — Signal-Based Exit vs Fixed Hold Periods
===============================================================
Entry logic:
  BIST: PAP state is Accepted or Edge AND SRP score >= 60
  USA:  PAP state is Accepted or Edge (SRP fires a signal but no score threshold)

Exit logic (signal-based):
  Exit when: PAP state shifts to Rejected
          OR SRP fires a signal in the OPPOSITE direction
          OR max hold = 40 days

Also runs fixed hold periods (5, 10, 20, 40 days) on same entry signals for comparison.

Usage:
    /Users/Elifcik/Desktop/apps/investment-radar/.venv/bin/python3 backtest/srp_pap_backtest_v2.py
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
CACHE_DIR = BACKTEST_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# ── Universe ──────────────────────────────────────────────────────────────────
BIST_TICKERS = ["EREGL.IS", "TOASO.IS", "TUPRS.IS", "THYAO.IS", "KCHOL.IS"]
USA_TICKERS  = ["SPY", "AAPL", "MSFT", "NVDA", "AMZN", "META"]

START_DATE = (date.today() - timedelta(days=2*365+10)).isoformat()
END_DATE   = date.today().isoformat()

MAX_HOLD   = 40  # safety cap in trading days
FIXED_HOLDS = [5, 10, 20, 40]


# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch_ohlcv(tickers: list[str], cache_key: str) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV for a list of tickers, with per-group cache."""
    cache_path = CACHE_DIR / f"srp_pap_{cache_key}.pkl"
    if cache_path.exists():
        cached = pd.read_pickle(cache_path)
        last = cached[list(cached.keys())[0]].index[-1].date()
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

def compute_srp(df: pd.DataFrame,
                lookback: int = 34,
                atr_period: int = 14,
                vol_baseline: int = 34) -> pd.DataFrame:
    """
    Simplified SRP indicator. Returns DataFrame with columns:
      score       : reversalScore (0-100) per bar
      direction   : 'bullish' | 'bearish' | '' (only non-empty on sweep bars)

    Detection logic:
      - Bullish: bar sweeps below N-bar low (low < rolling_low.shift(1)),
                 then closes back above previous low
      - Bearish: bar sweeps above N-bar high (high > rolling_high.shift(1)),
                 then closes back below previous high
    """
    n = len(df)
    if n < max(lookback, atr_period, vol_baseline) + 5:
        return pd.DataFrame({
            "score": pd.Series(np.nan, index=df.index),
            "direction": pd.Series("", index=df.index),
        })

    hi = df["High"]
    lo = df["Low"]
    cl = df["Close"]
    op = df["Open"]
    vol = df["Volume"] if "Volume" in df.columns else pd.Series(1, index=df.index)

    # ATR
    tr = pd.concat([
        hi - lo,
        (hi - cl.shift(1)).abs(),
        (lo - cl.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(atr_period).mean()

    # Rolling highs/lows for sweep detection
    roll_hi = hi.rolling(lookback).max().shift(1)
    roll_lo = lo.rolling(lookback).min().shift(1)

    # Volume baseline
    vol_ma = vol.rolling(vol_baseline).mean()
    vol_ratio = (vol / vol_ma.replace(0, np.nan)).clip(0.1, 5.0)

    scores = pd.Series(0.0, index=df.index)
    directions = pd.Series("", index=df.index, dtype=object)

    for i in range(max(lookback, atr_period, vol_baseline) + 1, n):
        bar_hi = hi.iloc[i]
        bar_lo = lo.iloc[i]
        bar_cl = cl.iloc[i]
        bar_op = op.iloc[i]
        prev_cl = cl.iloc[i - 1]
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

        # ── Bullish sweep: pierces below recent low, closes back above ──
        bull_sweep = (bar_lo < rlo) and (bar_cl > rlo)
        # ── Bearish sweep: pierces above recent high, closes back below ──
        bear_sweep = (bar_hi > rhi) and (bar_cl < rhi)

        if not (bull_sweep or bear_sweep):
            continue

        # ── Score components ──────────────────────────────────────────
        if bull_sweep:
            sweep_depth = max(0, rlo - bar_lo)
            wick_upper  = bar_hi - max(bar_cl, bar_op)
            wick_lower  = min(bar_cl, bar_op) - bar_lo
            close_pct   = (bar_cl - bar_lo) / bar_range
            confirm_bull = bar_cl > bar_op
        else:
            sweep_depth = max(0, bar_hi - rhi)
            wick_upper  = bar_hi - max(bar_cl, bar_op)
            wick_lower  = min(bar_cl, bar_op) - bar_lo
            close_pct   = (bar_hi - bar_cl) / bar_range
            confirm_bull = bar_cl < bar_op

        wick_size = (wick_lower if bull_sweep else wick_upper)
        wick_score = min(100.0, (wick_size / bar_atr) * 50)
        pen_score  = min(100.0, (sweep_depth / bar_atr) * 40)

        vr = vol_ratio.iloc[i]
        vol_score = min(100.0, (vr - 1.0) * 50 + 50) if not pd.isna(vr) else 50.0
        vol_score = max(0.0, vol_score)

        sweep_score      = wick_score * 0.56 + pen_score * 0.34 + vol_score * 0.10
        close_back_score = min(100.0, close_pct * 100)
        confirm_score    = 80.0 if confirm_bull else 30.0

        body = abs(bar_cl - bar_op)
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

def compute_pap(df: pd.DataFrame,
                lookback: int = 320,
                n_rows: int = 26,
                value_area_pct: float = 0.70) -> pd.DataFrame:
    """
    Simplified PAP indicator. Returns DataFrame with columns:
      poc, vah, val, acceptance_state, rotation, acceptance_score, cog
    """
    cl = df["Close"]
    n = len(df)

    poc_arr   = np.full(n, np.nan)
    vah_arr   = np.full(n, np.nan)
    val_arr   = np.full(n, np.nan)
    state_arr = np.full(n, "", dtype=object)
    rot_arr   = np.full(n, "", dtype=object)
    score_arr = np.full(n, np.nan)
    cog_arr   = np.full(n, np.nan)

    for i in range(lookback, n):
        window = cl.iloc[i - lookback + 1: i + 1].values
        cur_price = window[-1]

        w_min = window.min()
        w_max = window.max()
        if w_max == w_min:
            continue

        bins = np.linspace(w_min, w_max, n_rows + 1)
        counts, edges = np.histogram(window, bins=bins)
        row_mids = (edges[:-1] + edges[1:]) / 2

        poc_idx = counts.argmax()
        poc = row_mids[poc_idx]

        total = counts.sum()
        target = int(total * value_area_pct)
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

        half = lookback // 2
        w_first  = cl.iloc[i - lookback + 1: i - half + 1].values
        w_second = cl.iloc[i - half + 1: i + 1].values
        if len(w_first) > 0 and len(w_second) > 0:
            cog_first  = w_first.mean()
            cog_second = w_second.mean()
            rotation = "Up" if cog_second > cog_first * 1.001 else \
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

        state_score = 20.0 if state == "Accepted" else (10.0 if state == "Edge" else 0.0)
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


# ── Entry signal detection ────────────────────────────────────────────────────

def detect_entries(df: pd.DataFrame, srp: pd.DataFrame, pap: pd.DataFrame,
                   universe: str) -> list[dict]:
    """
    Detect entry bars according to universe-specific rules.

    BIST: PAP state Accepted or Edge AND SRP score >= 60
    USA:  PAP state Accepted or Edge (any SRP signal, score > 0)

    Returns list of dicts with entry bar index, entry_price (next open),
    SRP direction, SRP score, PAP state.
    """
    n = len(df)
    op = df["Open"] if "Open" in df.columns else df["Close"]
    entries = []

    for i in range(1, n - MAX_HOLD - 2):
        srp_score = srp["score"].iloc[i]
        srp_dir   = srp["direction"].iloc[i]
        pap_state = pap["acceptance_state"].iloc[i]

        if srp_dir == "" or pd.isna(srp_score) or srp_score == 0.0:
            continue
        if pap_state == "" or pd.isna(pap_state):
            continue

        pap_ok = pap_state in ("Accepted", "Edge")
        if not pap_ok:
            continue

        if universe == "BIST" and srp_score < 60:
            continue

        entry_price = float(op.iloc[i + 1])
        if entry_price <= 0:
            continue

        entries.append({
            "signal_bar":  i,          # bar index where signal fires
            "entry_bar":   i + 1,      # bar where we enter (next open)
            "entry_price": entry_price,
            "srp_score":   float(srp_score),
            "srp_dir":     srp_dir,    # 'bullish' or 'bearish'
            "pap_state":   pap_state,
        })

    return entries


# ── Signal-based exit simulation ──────────────────────────────────────────────

def simulate_signal_exit(df: pd.DataFrame, srp: pd.DataFrame, pap: pd.DataFrame,
                          entries: list[dict], ticker: str, universe: str) -> list[dict]:
    """
    For each entry, walk forward bar-by-bar until:
      1. PAP state shifts to Rejected
      2. SRP fires a signal in the OPPOSITE direction
      3. MAX_HOLD days reached

    Exit price = close of the exit bar.
    """
    cl = df["Close"]
    n  = len(df)
    trades = []

    for e in entries:
        entry_bar   = e["entry_bar"]
        entry_price = e["entry_price"]
        srp_dir     = e["srp_dir"]
        opposite    = "bearish" if srp_dir == "bullish" else "bullish"

        exit_bar    = None
        exit_reason = None

        for j in range(entry_bar + 1, min(entry_bar + MAX_HOLD + 1, n)):
            pap_state_j = pap["acceptance_state"].iloc[j]
            srp_dir_j   = srp["direction"].iloc[j]

            # Exit condition 1: PAP flips to Rejected
            if pap_state_j == "Rejected":
                exit_bar    = j
                exit_reason = "PAP_Rejected"
                break

            # Exit condition 2: opposite SRP signal fires
            if srp_dir_j == opposite:
                exit_bar    = j
                exit_reason = "Opposite_SRP"
                break

        # Safety cap
        if exit_bar is None:
            exit_bar    = min(entry_bar + MAX_HOLD, n - 1)
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
    cl = df["Close"]
    n  = len(df)
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


# ── Per-universe runner ────────────────────────────────────────────────────────

def run_universe(data: dict[str, pd.DataFrame], universe: str) -> tuple[list[dict], list[dict]]:
    """
    Run signal detection + exits for all tickers.
    Returns (signal_exit_trades, fixed_hold_trades).
    """
    all_signal_trades = []
    all_fixed_trades  = []

    for ticker, df in data.items():
        print(f"  [{universe}] {ticker} ({len(df)} bars) …")
        srp = compute_srp(df)
        pap = compute_pap(df)

        entries = detect_entries(df, srp, pap, universe)
        print(f"    Entries: {len(entries)}")

        if not entries:
            continue

        sig_trades = simulate_signal_exit(df, srp, pap, entries, ticker, universe)
        all_signal_trades.extend(sig_trades)

        for hold in FIXED_HOLDS:
            fx_trades = simulate_fixed_hold(df, entries, ticker, universe, hold)
            all_fixed_trades.extend(fx_trades)

    return all_signal_trades, all_fixed_trades


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


def fixed_hold_stats(trades: list[dict], universe: str) -> list[dict]:
    """Compute stats per fixed hold period for a given universe."""
    results = []
    df = pd.DataFrame(trades) if trades else pd.DataFrame()

    for hold in FIXED_HOLDS:
        sub = df[df["hold"] == hold] if not df.empty else pd.DataFrame()
        if sub.empty or len(sub) == 0:
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


def exit_reason_breakdown(trades: list[dict]) -> dict:
    """Count exit reasons."""
    if not trades:
        return {}
    df = pd.DataFrame(trades)
    return df["exit_reason"].value_counts().to_dict()


def per_ticker_signal_stats(trades: list[dict]) -> pd.DataFrame:
    """Per-ticker stats for signal-based exits."""
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame(trades)
    grouped = df.groupby("ticker").agg(
        n          =("hit",       "count"),
        hit_rate   =("hit",       "mean"),
        avg_ret    =("ret",       "mean"),
        avg_days   =("days_held", "mean"),
        median_days=("days_held", "median"),
    ).reset_index()
    grouped["hit_rate"] = grouped["hit_rate"] * 100
    grouped["avg_ret"]  = grouped["avg_ret"] * 100
    return grouped.sort_values("avg_ret", ascending=False)


# ── Markdown report ───────────────────────────────────────────────────────────

def fmt_signal_stats_row(s: dict) -> str:
    n  = s["n"]
    hr = f"{s['hit_rate']:.1f}%" if not pd.isna(s.get("hit_rate", np.nan)) else "—"
    ar = f"{s['avg_ret']:+.2f}%"  if not pd.isna(s.get("avg_ret", np.nan)) else "—"
    mr = f"{s['median_ret']:+.2f}%" if not pd.isna(s.get("median_ret", np.nan)) else "—"
    ad = f"{s['avg_days']:.1f}"   if not pd.isna(s.get("avg_days", np.nan)) else "—"
    md = f"{s['median_days']:.0f}" if not pd.isna(s.get("median_days", np.nan)) else "—"
    return f"| {s['label']:<14} | {n:>9} | {hr:>8} | {ar:>10} | {mr:>12} | {ad:>9} | {md:>12} |"


def fmt_fixed_hold_table(fixed_rows: list[dict]) -> str:
    lines = [
        "| Hold (days) | # Trades | Hit Rate | Avg Return | Median Return |",
        "|-------------|----------|----------|------------|---------------|",
    ]
    for r in fixed_rows:
        n  = r["n"]
        hr = f"{r['hit_rate']:.1f}%"   if not pd.isna(r.get("hit_rate", np.nan)) else "—"
        ar = f"{r['avg_ret']:+.2f}%"   if not pd.isna(r.get("avg_ret", np.nan)) else "—"
        mr = f"{r['median_ret']:+.2f}%" if not pd.isna(r.get("median_ret", np.nan)) else "—"
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
            f"| {row.ticker:<10} | {row.n:>8} | {row.hit_rate:>7.1f}% | "
            f"{row.avg_ret:>+9.2f}% | {row.avg_days:>8.1f} | {row.median_days:>11.0f} |"
        )
    return "\n".join(lines)


def generate_report(
    bist_sig_trades: list[dict],
    usa_sig_trades:  list[dict],
    bist_fix_trades: list[dict],
    usa_fix_trades:  list[dict],
    today: str,
) -> str:

    bist_stats = trade_stats(bist_sig_trades, "BIST")
    usa_stats  = trade_stats(usa_sig_trades,  "USA")

    bist_fixed = fixed_hold_stats(bist_fix_trades, "BIST")
    usa_fixed  = fixed_hold_stats(usa_fix_trades,  "USA")

    bist_exit_reasons = exit_reason_breakdown(bist_sig_trades)
    usa_exit_reasons  = exit_reason_breakdown(usa_sig_trades)

    bist_ticker_df = per_ticker_signal_stats(bist_sig_trades)
    usa_ticker_df  = per_ticker_signal_stats(usa_sig_trades)

    # ── Best fixed hold period ──────────────────────────────────────────
    def best_hold(fixed_rows):
        valid = [r for r in fixed_rows if r["n"] >= 5 and not pd.isna(r.get("avg_ret", np.nan))]
        if not valid:
            return None
        return max(valid, key=lambda x: x["avg_ret"])

    bist_best_fixed = best_hold(bist_fixed)
    usa_best_fixed  = best_hold(usa_fixed)

    # ── Conclusion text ─────────────────────────────────────────────────
    def conclude(sig_s, best_fix, uni):
        if sig_s["n"] == 0:
            return f"Insufficient trades for {uni}."

        parts = []

        # Compare signal-exit avg return vs best fixed hold
        if best_fix and not pd.isna(sig_s["avg_ret"]):
            diff = sig_s["avg_ret"] - best_fix["avg_ret"]
            if diff > 0:
                parts.append(
                    f"Signal-based exit outperforms the best fixed hold "
                    f"({best_fix['hold']}d) by {diff:+.2f}% on average return "
                    f"({sig_s['avg_ret']:+.2f}% vs {best_fix['avg_ret']:+.2f}%)."
                )
            else:
                parts.append(
                    f"Fixed {best_fix['hold']}-day hold outperforms signal-based exit "
                    f"by {-diff:.2f}% on average return "
                    f"({best_fix['avg_ret']:+.2f}% vs {sig_s['avg_ret']:+.2f}%)."
                )

        # Average days held
        if not pd.isna(sig_s["avg_days"]):
            parts.append(
                f"Signal-based exits held for {sig_s['avg_days']:.1f} days on average "
                f"(median {sig_s['median_days']:.0f}d), "
                f"well within the 40-day safety cap."
            )

        # Hit rate note
        if not pd.isna(sig_s["hit_rate"]):
            hr_note = "above" if sig_s["hit_rate"] >= 55 else "below"
            parts.append(
                f"Hit rate of {sig_s['hit_rate']:.1f}% is {hr_note} the 55% baseline threshold."
            )

        return " ".join(parts)

    bist_conclusion = conclude(bist_stats, bist_best_fixed, "BIST")
    usa_conclusion  = conclude(usa_stats,  usa_best_fixed,  "USA")

    # ── Overall recommendation ─────────────────────────────────────────
    # Compare signal-based vs each fixed hold across both universes combined
    all_sig_trades = bist_sig_trades + usa_sig_trades
    combined_stats = trade_stats(all_sig_trades, "Combined")

    all_fix_rows = []
    combined_df  = pd.DataFrame(bist_fix_trades + usa_fix_trades) if (bist_fix_trades or usa_fix_trades) else pd.DataFrame()
    for hold in FIXED_HOLDS:
        sub = combined_df[combined_df["hold"] == hold] if not combined_df.empty else pd.DataFrame()
        if sub.empty:
            all_fix_rows.append({"hold": hold, "n": 0, "hit_rate": np.nan, "avg_ret": np.nan, "median_ret": np.nan})
        else:
            all_fix_rows.append({
                "hold":       hold,
                "n":          len(sub),
                "hit_rate":   sub["hit"].mean() * 100,
                "avg_ret":    sub["ret"].mean() * 100,
                "median_ret": sub["ret"].median() * 100,
            })

    overall_best_fixed = best_hold(all_fix_rows)

    def overall_recommendation():
        lines = []
        if combined_stats["n"] == 0:
            return "Not enough data to make a recommendation."

        if overall_best_fixed:
            sig_avg = combined_stats["avg_ret"] if not pd.isna(combined_stats["avg_ret"]) else 0
            fix_avg = overall_best_fixed["avg_ret"]
            if sig_avg > fix_avg:
                lines.append(
                    f"Signal-based exit is the preferred approach overall: "
                    f"avg return {sig_avg:+.2f}% vs best fixed hold "
                    f"({overall_best_fixed['hold']}d) at {fix_avg:+.2f}%."
                )
            else:
                lines.append(
                    f"Fixed {overall_best_fixed['hold']}-day hold is marginally better overall: "
                    f"avg return {fix_avg:+.2f}% vs signal-based {sig_avg:+.2f}%. "
                    f"However, signal exits provide dynamic risk management and shorter avg hold time."
                )

        # Optimal hold based on fixed comparison
        valid_holds = [r for r in all_fix_rows if r["n"] >= 5 and not pd.isna(r.get("avg_ret", np.nan))]
        if valid_holds:
            sorted_holds = sorted(valid_holds, key=lambda x: x["avg_ret"], reverse=True)
            top = sorted_holds[0]
            lines.append(
                f"Among fixed holds, {top['hold']} days yields the highest avg return "
                f"({top['avg_ret']:+.2f}%, hit rate {top['hit_rate']:.1f}%)."
            )

        if not pd.isna(combined_stats["avg_days"]):
            lines.append(
                f"Signal-based exits naturally self-select for hold duration "
                f"(avg {combined_stats['avg_days']:.1f}d, median {combined_stats['median_days']:.0f}d), "
                f"suggesting the market provides clear exit cues well before the 40-day cap."
            )

        return " ".join(lines)

    # ── Build markdown ─────────────────────────────────────────────────
    signal_header = (
        "| Universe       | # Trades | Hit Rate | Avg Return | Median Return | Avg Days | Median Days |\n"
        "|----------------|----------|----------|------------|---------------|----------|-------------|"
    )

    lines = [
        "# SRP + PAP Backtest v2 — Signal-Based Exit vs Fixed Hold",
        "",
        f"**Date generated:** {today}",
        f"**Period:** {START_DATE} → {END_DATE} (2 years daily)",
        f"**Max hold cap:** {MAX_HOLD} trading days",
        f"**Fixed hold periods tested:** {', '.join(str(h) for h in FIXED_HOLDS)} days",
        "",
        "## Entry Criteria",
        "",
        "| Universe | PAP State | SRP Threshold |",
        "|----------|-----------|---------------|",
        "| BIST     | Accepted or Edge | SRP score >= 60 |",
        "| USA      | Accepted or Edge | Any SRP signal (score > 0) |",
        "",
        "## Exit Criteria (Signal-Based)",
        "",
        "1. PAP state shifts to **Rejected**",
        "2. SRP fires a signal in the **opposite direction** (bearish after bullish entry, or vice versa)",
        "3. **Max hold = 40 days** (safety cap)",
        "",
        "---",
        "",
        "## 1. Signal-Based Exit Results",
        "",
        "### Overall by Universe",
        "",
        signal_header,
        fmt_signal_stats_row(bist_stats),
        fmt_signal_stats_row(usa_stats),
        "",
        "### Exit Reason Breakdown",
        "",
        "**BIST:**",
        "",
    ]

    for reason, cnt in sorted(bist_exit_reasons.items(), key=lambda x: -x[1]):
        total = bist_stats["n"] or 1
        lines.append(f"- {reason}: {cnt} ({cnt/total*100:.1f}%)")

    lines += [
        "",
        "**USA:**",
        "",
    ]
    for reason, cnt in sorted(usa_exit_reasons.items(), key=lambda x: -x[1]):
        total = usa_stats["n"] or 1
        lines.append(f"- {reason}: {cnt} ({cnt/total*100:.1f}%)")

    lines += [
        "",
        "### Per-Ticker Breakdown — BIST (Signal-Based Exit)",
        "",
        fmt_ticker_signal_table(bist_ticker_df),
        "",
        "### Per-Ticker Breakdown — USA (Signal-Based Exit)",
        "",
        fmt_ticker_signal_table(usa_ticker_df),
        "",
        "---",
        "",
        "## 2. Fixed Hold Period Comparison",
        "",
        "Same entry signals, exit at fixed number of days after entry.",
        "",
        "### BIST — Fixed Hold",
        "",
        fmt_fixed_hold_table(bist_fixed),
        "",
        "### USA — Fixed Hold",
        "",
        fmt_fixed_hold_table(usa_fixed),
        "",
        "### Combined (BIST + USA) — Fixed Hold",
        "",
        fmt_fixed_hold_table(all_fix_rows),
        "",
        "---",
        "",
        "## 3. Conclusion",
        "",
        "### BIST",
        "",
        bist_conclusion,
        "",
        "### USA",
        "",
        usa_conclusion,
        "",
        "### Overall Recommendation",
        "",
        overall_recommendation(),
        "",
        "---",
        "",
        "_Generated by backtest/srp_pap_backtest_v2.py_",
    ]

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("SRP + PAP Backtest v2 — Signal-Based Exit")
    print(f"Period: {START_DATE} → {END_DATE}")
    print("=" * 60)

    print("\n[1] Fetching BIST data …")
    bist_data = fetch_ohlcv(BIST_TICKERS, "bist")

    print("\n[2] Fetching USA data …")
    usa_data = fetch_ohlcv(USA_TICKERS, "usa")

    print("\n[3] Running BIST backtest …")
    bist_sig_trades, bist_fix_trades = run_universe(bist_data, "BIST")
    print(f"  BIST signal trades: {len(bist_sig_trades)}")
    print(f"  BIST fixed-hold trade records: {len(bist_fix_trades)}")

    print("\n[4] Running USA backtest …")
    usa_sig_trades, usa_fix_trades = run_universe(usa_data, "USA")
    print(f"  USA signal trades: {len(usa_sig_trades)}")
    print(f"  USA fixed-hold trade records: {len(usa_fix_trades)}")

    # Quick console summary
    print("\n=== Signal-Based Exit Summary ===")
    for trades, label in [(bist_sig_trades, "BIST"), (usa_sig_trades, "USA")]:
        s = trade_stats(trades, label)
        if s["n"] > 0:
            print(
                f"  {label:<6}: n={s['n']:>4}  hit={s['hit_rate']:.1f}%  "
                f"avg={s['avg_ret']:+.2f}%  median={s['median_ret']:+.2f}%  "
                f"avg_days={s['avg_days']:.1f}  median_days={s['median_days']:.0f}"
            )
        else:
            print(f"  {label}: No trades")

    print("\n=== Fixed Hold Comparison (Combined) ===")
    combined_df = pd.DataFrame(bist_fix_trades + usa_fix_trades) if (bist_fix_trades or usa_fix_trades) else pd.DataFrame()
    for hold in FIXED_HOLDS:
        sub = combined_df[combined_df["hold"] == hold] if not combined_df.empty else pd.DataFrame()
        if not sub.empty:
            print(
                f"  {hold:>2}d: n={len(sub):>4}  hit={sub['hit'].mean()*100:.1f}%  "
                f"avg={sub['ret'].mean()*100:+.2f}%  median={sub['ret'].median()*100:+.2f}%"
            )

    print("\n[5] Writing report …")
    report = generate_report(
        bist_sig_trades, usa_sig_trades,
        bist_fix_trades, usa_fix_trades,
        today=date.today().isoformat(),
    )
    report_path = BACKTEST_DIR / "srp_pap_backtest_v2.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"  Report saved → {report_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
