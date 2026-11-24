"""
SRP (Stop Run Reversal Planner) + PAP (Price Acceptance Profile) Backtest
=========================================================================
Tests both indicators on BIST and USA universes over 2 years of daily data.

Trade rule: buy next-day open when signal fires, sell 5 days later.
Compare: hit rate (positive 5-day return), average return, # signals.

Usage:
    /Users/Elifcik/Desktop/apps/investment-radar/.venv/bin/python3 backtest/srp_pap_backtest.py
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

HOLD_DAYS = 5  # buy next open, sell 5 bars later


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
                vol_baseline: int = 34) -> pd.Series:
    """
    Simplified SRP indicator. Returns reversalScore series (0-100) per bar.

    Detection logic:
      - Bullish: bar sweeps below N-bar low (low < rolling_low.shift(1)),
                 then closes back above previous low
      - Bearish: bar sweeps above N-bar high (high > rolling_high.shift(1)),
                 then closes back below previous high

    Scores:
      sweepScore     = wickScore*0.56 + penScore*0.34 + volumeScore*0.10
      reversalScore  = sweepScore*0.22 + closeBackScore*0.22 + confirmScore*0.22
                     + volumeScore*0.12 + targetRoomScore*0.14 + trendTurnScore*0.08
    """
    if len(df) < max(lookback, atr_period, vol_baseline) + 5:
        return pd.Series(np.nan, index=df.index)

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

    results = pd.Series(0.0, index=df.index)

    for i in range(max(lookback, atr_period, vol_baseline) + 1, len(df)):
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
        # 1. wickScore: how far price swept beyond the level vs ATR
        if bull_sweep:
            sweep_depth = max(0, rlo - bar_lo)
            wick_upper  = bar_hi - max(bar_cl, bar_op)
            wick_lower  = min(bar_cl, bar_op) - bar_lo
            close_pct   = (bar_cl - bar_lo) / bar_range  # close back score: higher = better
            confirm_bull = bar_cl > bar_op  # bullish close
        else:  # bear_sweep
            sweep_depth = max(0, bar_hi - rhi)
            wick_upper  = bar_hi - max(bar_cl, bar_op)
            wick_lower  = min(bar_cl, bar_op) - bar_lo
            close_pct   = (bar_hi - bar_cl) / bar_range  # close back score
            confirm_bull = bar_cl < bar_op  # bearish close

        # wickScore: wick size relative to ATR (0-100)
        wick_size = (wick_lower if bull_sweep else wick_upper)
        wick_score = min(100.0, (wick_size / bar_atr) * 50)

        # penScore: sweep depth penetration vs ATR (0-100)
        pen_score = min(100.0, (sweep_depth / bar_atr) * 40)

        # volumeScore: volume ratio to baseline (0-100)
        vr = vol_ratio.iloc[i]
        vol_score = min(100.0, (vr - 1.0) * 50 + 50) if not pd.isna(vr) else 50.0
        vol_score = max(0.0, vol_score)

        # sweepScore
        sweep_score = wick_score * 0.56 + pen_score * 0.34 + vol_score * 0.10

        # closeBackScore: how strongly price closed back inside the range (0-100)
        close_back_score = min(100.0, close_pct * 100)

        # confirmationScore: full candle body confirming reversal direction (0-100)
        confirm_score = 80.0 if confirm_bull else 30.0

        # targetRoomScore: room to next structure in the direction of reversal (0-100)
        # Proxy: look-ahead not used; use body size ratio as proxy for room
        body = abs(bar_cl - bar_op)
        target_room_score = min(100.0, (body / bar_atr) * 60)

        # trendTurnScore: prior trend was opposing the reversal (0-100)
        # Proxy: previous 5-bar direction opposing this bar's direction
        if i >= 6:
            prior_change = cl.iloc[i - 1] - cl.iloc[i - 6]
            if bull_sweep:
                trend_turn_score = 80.0 if prior_change < 0 else 30.0
            else:
                trend_turn_score = 80.0 if prior_change > 0 else 30.0
        else:
            trend_turn_score = 50.0

        # reversalScore
        reversal_score = (
            sweep_score       * 0.22 +
            close_back_score  * 0.22 +
            confirm_score     * 0.22 +
            vol_score         * 0.12 +
            target_room_score * 0.14 +
            trend_turn_score  * 0.08
        )

        results.iloc[i] = reversal_score

    return results


# ── PAP — Price Acceptance Profile ───────────────────────────────────────────

def compute_pap(df: pd.DataFrame,
                lookback: int = 320,
                n_rows: int = 26,
                value_area_pct: float = 0.70) -> pd.DataFrame:
    """
    Simplified PAP indicator. Returns DataFrame with columns:
      poc, vah, val, acceptance_state, rotation,
      acceptance_score, cog (center of gravity)

    For each bar i, computes profile on the trailing `lookback` bars.
    acceptance_state: 'Accepted' | 'Rejected' | 'Edge'
    rotation:         'Up' | 'Down' | 'Neutral'
    acceptance_score: 0-100

    For performance, only compute every bar (daily resolution on 2-year data
    this is ~500 iterations, manageable).
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

        # Build histogram: count how many bars closed in each row
        bins = np.linspace(w_min, w_max, n_rows + 1)
        counts, edges = np.histogram(window, bins=bins)
        row_mids = (edges[:-1] + edges[1:]) / 2

        # POC = row with most time
        poc_idx = counts.argmax()
        poc = row_mids[poc_idx]

        # Value area: start from POC, expand to capture 70% of time
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

        # Center of gravity
        total_weighted = (counts * row_mids).sum()
        cog = total_weighted / total if total > 0 else poc

        # Rotation: COG first half vs second half
        half = lookback // 2
        w_first = cl.iloc[i - lookback + 1: i - half + 1].values
        w_second = cl.iloc[i - half + 1: i + 1].values
        if len(w_first) > 0 and len(w_second) > 0:
            cog_first = w_first.mean()
            cog_second = w_second.mean()
            rotation = "Up" if cog_second > cog_first * 1.001 else \
                       "Down" if cog_second < cog_first * 0.999 else "Neutral"
        else:
            rotation = "Neutral"

        # Acceptance state
        row_height = (w_max - w_min) / n_rows
        edge_band = row_height * 1.5  # within 1.5 rows of boundary
        if cur_price < val - edge_band or cur_price > vah + edge_band:
            state = "Rejected"
        elif (cur_price < val + edge_band and cur_price >= val - edge_band) or \
             (cur_price > vah - edge_band and cur_price <= vah + edge_band):
            state = "Edge"
        else:
            state = "Accepted"

        # acceptanceScore (0-100)
        # Components:
        #   1. proximity to POC (0-40): closer = higher
        #   2. value area width (0-20): narrower = better acceptance
        #   3. rotation alignment (0-20): 20 if rotation matches direction toward POC, 10 neutral
        #   4. rejection speed / state (0-20): Accepted=20, Edge=10, Rejected=0

        # 1. POC proximity
        poc_dist = abs(cur_price - poc) / (w_max - w_min + 1e-10)
        poc_score = max(0.0, 40.0 * (1 - poc_dist * 2))

        # 2. Value area width relative to total range
        va_width = (vah - val) / (w_max - w_min + 1e-10)
        va_score = max(0.0, 20.0 * (1 - va_width))

        # 3. Rotation alignment with "toward POC" direction
        toward_poc_up = cur_price < poc
        if (rotation == "Up" and toward_poc_up) or (rotation == "Down" and not toward_poc_up):
            rot_score = 20.0
        elif rotation == "Neutral":
            rot_score = 10.0
        else:
            rot_score = 5.0

        # 4. State bonus
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


# ── Signal generation ─────────────────────────────────────────────────────────

def generate_signals(df: pd.DataFrame, ticker: str,
                     srp_score: pd.Series, pap: pd.DataFrame) -> pd.DataFrame:
    """
    Generate trade signals under different filter regimes.
    Trade: enter at next day open, exit 5 bars later at close.

    Returns DataFrame with one row per bar (where signal is possible).
    """
    cl = df["Close"]
    op = df["Open"] if "Open" in df.columns else df["Close"]
    n = len(df)

    rows = []
    for i in range(1, n - HOLD_DAYS - 1):
        srp_val   = srp_score.iloc[i]
        pap_state = pap["acceptance_state"].iloc[i]
        pap_score = pap["acceptance_score"].iloc[i]

        if pd.isna(srp_val) or srp_val == 0.0:
            continue
        if pap_state == "":
            continue

        entry_price = float(op.iloc[i + 1])  # next day open
        exit_price  = float(cl.iloc[i + HOLD_DAYS])  # 5 bars later close
        if entry_price <= 0:
            continue

        ret_5d = (exit_price - entry_price) / entry_price

        rows.append({
            "ticker":       ticker,
            "date":         df.index[i],
            "srp_score":    float(srp_val),
            "pap_state":    pap_state,
            "pap_score":    float(pap_score) if not pd.isna(pap_score) else np.nan,
            "entry_price":  entry_price,
            "exit_price":   exit_price,
            "ret_5d":       ret_5d,
            "hit":          int(ret_5d > 0),
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ── Backtest per universe ─────────────────────────────────────────────────────

def backtest_universe(data: dict[str, pd.DataFrame], label: str) -> pd.DataFrame:
    """Run all indicators on all tickers. Returns combined signals DataFrame."""
    all_signals = []

    for ticker, df in data.items():
        print(f"  Computing indicators for {ticker} ({len(df)} bars) …")
        srp_score = compute_srp(df)
        pap_df    = compute_pap(df)
        sigs = generate_signals(df, ticker, srp_score, pap_df)
        if not sigs.empty:
            sigs["universe"] = label
            all_signals.append(sigs)

    if not all_signals:
        return pd.DataFrame()
    return pd.concat(all_signals, ignore_index=True)


# ── Filter combinations ───────────────────────────────────────────────────────

def compute_filter_stats(signals: pd.DataFrame, mask: pd.Series, label: str) -> dict:
    """Compute hit rate and avg return for a filtered subset."""
    sub = signals[mask] if not mask.empty else pd.DataFrame()
    if sub.empty or len(sub) == 0:
        return {"filter": label, "n": 0, "hit_rate": np.nan, "avg_ret": np.nan, "median_ret": np.nan}
    return {
        "filter":     label,
        "n":          len(sub),
        "hit_rate":   sub["hit"].mean() * 100,
        "avg_ret":    sub["ret_5d"].mean() * 100,
        "median_ret": sub["ret_5d"].median() * 100,
    }


def run_filter_analysis(signals: pd.DataFrame, label: str) -> list[dict]:
    """Run all filter combinations and return results list."""
    if signals.empty:
        return []

    results = []

    # Baseline: all signals (any SRP activity)
    results.append(compute_filter_stats(
        signals, pd.Series(True, index=signals.index), "Baseline (all SRP signals)"
    ))

    # SRP >= 66
    mask_66 = signals["srp_score"] >= 66
    results.append(compute_filter_stats(signals, mask_66, "SRP >= 66"))

    # SRP >= 70
    mask_70 = signals["srp_score"] >= 70
    results.append(compute_filter_stats(signals, mask_70, "SRP >= 70"))

    # SRP >= 75
    mask_75 = signals["srp_score"] >= 75
    results.append(compute_filter_stats(signals, mask_75, "SRP >= 75"))

    # PAP: Accepted or Edge (not Rejected)
    mask_pap_acc = signals["pap_state"].isin(["Accepted", "Edge"])
    results.append(compute_filter_stats(signals, mask_pap_acc, "PAP: Accepted or Edge"))

    # PAP: Accepted only
    mask_pap_only = signals["pap_state"] == "Accepted"
    results.append(compute_filter_stats(signals, mask_pap_only, "PAP: Accepted only"))

    # Combined: SRP >= 66 AND PAP Accepted/Edge
    mask_combo = mask_66 & mask_pap_acc
    results.append(compute_filter_stats(signals, mask_combo, "Combined: SRP>=66 + PAP Acc/Edge"))

    # Combined: SRP >= 70 AND PAP Accepted/Edge
    mask_combo70 = mask_70 & mask_pap_acc
    results.append(compute_filter_stats(signals, mask_combo70, "Combined: SRP>=70 + PAP Acc/Edge"))

    return results


# ── SPY regime analysis ───────────────────────────────────────────────────────

def spy_regime_analysis(usa_signals: pd.DataFrame, spy_pap: pd.DataFrame) -> dict:
    """
    Evaluate how PAP state on SPY predicts individual stock 5d returns.
    Merge SPY pap state onto each signal's date.
    """
    spy_pap_clean = spy_pap[["acceptance_state"]].copy()
    spy_pap_clean.columns = ["spy_pap_state"]
    spy_pap_clean.index.name = "date"

    # Only non-SPY tickers
    stock_sigs = usa_signals[usa_signals["ticker"] != "SPY"].copy()

    if stock_sigs.empty:
        return {}

    merged = stock_sigs.merge(
        spy_pap_clean, left_on="date", right_index=True, how="left"
    )

    results = {}
    for state in ["Accepted", "Edge", "Rejected", ""]:
        sub = merged[merged["spy_pap_state"] == state] if state else merged[merged["spy_pap_state"].isna()]
        if len(sub) == 0:
            continue
        label = state if state else "Unknown"
        results[label] = {
            "n":        len(sub),
            "hit_rate": sub["hit"].mean() * 100,
            "avg_ret":  sub["ret_5d"].mean() * 100,
        }

    return results


# ── Per-ticker breakdown ──────────────────────────────────────────────────────

def per_ticker_stats(signals: pd.DataFrame, filter_mask: pd.Series | None = None) -> pd.DataFrame:
    """Per-ticker hit rate and avg return."""
    sub = signals[filter_mask] if filter_mask is not None and not filter_mask.empty else signals
    if sub.empty:
        return pd.DataFrame()

    grouped = sub.groupby("ticker").agg(
        n       =("hit",    "count"),
        hit_rate=("hit",    "mean"),
        avg_ret =("ret_5d", "mean"),
        max_ret =("ret_5d", "max"),
        min_ret =("ret_5d", "min"),
    ).reset_index()
    grouped["hit_rate"] = grouped["hit_rate"] * 100
    grouped["avg_ret"]  = grouped["avg_ret"] * 100
    grouped["max_ret"]  = grouped["max_ret"] * 100
    grouped["min_ret"]  = grouped["min_ret"] * 100
    return grouped.sort_values("avg_ret", ascending=False)


# ── Report generation ─────────────────────────────────────────────────────────

def fmt_table(results: list[dict]) -> str:
    """Format filter results as markdown table."""
    lines = [
        "| Filter | # Signals | Hit Rate | Avg 5d Ret | Median 5d Ret |",
        "|--------|-----------|----------|------------|---------------|",
    ]
    for r in results:
        n    = r["n"]
        hr   = f"{r['hit_rate']:.1f}%" if not pd.isna(r.get("hit_rate", np.nan)) else "—"
        ar   = f"{r['avg_ret']:+.2f}%" if not pd.isna(r.get("avg_ret", np.nan)) else "—"
        mr   = f"{r['median_ret']:+.2f}%" if not pd.isna(r.get("median_ret", np.nan)) else "—"
        lines.append(f"| {r['filter']:<40} | {n:>9} | {hr:>8} | {ar:>10} | {mr:>13} |")
    return "\n".join(lines)


def fmt_ticker_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No data_"
    lines = [
        "| Ticker | # Signals | Hit Rate | Avg 5d Ret | Max | Min |",
        "|--------|-----------|----------|------------|-----|-----|",
    ]
    for row in df.itertuples():
        lines.append(
            f"| {row.ticker:<10} | {row.n:>9} | {row.hit_rate:>7.1f}% | "
            f"{row.avg_ret:>+9.2f}% | {row.max_ret:>+5.2f}% | {row.min_ret:>+5.2f}% |"
        )
    return "\n".join(lines)


def generate_md_report(
    bist_results: list[dict],
    usa_results:  list[dict],
    bist_sigs:    pd.DataFrame,
    usa_sigs:     pd.DataFrame,
    spy_regime:   dict,
    today:        str,
) -> str:
    lines = [
        "# SRP + PAP Backtest Report",
        "",
        f"**Date generated:** {today}",
        f"**Period:** {START_DATE} → {END_DATE} (2 years daily)",
        f"**Hold period:** {HOLD_DAYS} trading days (buy next open, exit on close)",
        f"**BIST tickers:** {', '.join(BIST_TICKERS)}",
        f"**USA tickers:** {', '.join(USA_TICKERS)}",
        "",
        "---",
        "",
        "## Indicator Implementation Notes",
        "",
        "### Stop Run Reversal Planner (SRP)",
        "- Lookback = 34 bars, ATR = 14, Volume baseline = 34",
        "- Detects bars that sweep below recent N-bar low (bullish) or above recent N-bar high (bearish)",
        "  then close back inside the range",
        "- sweepScore = wickScore×0.56 + penScore×0.34 + volumeScore×0.10",
        "- reversalScore = sweepScore×0.22 + closeBackScore×0.22 + confirmScore×0.22",
        "  + volumeScore×0.12 + targetRoomScore×0.14 + trendTurnScore×0.08",
        "- Score range: 0–100 (only non-zero on sweep bars)",
        "",
        "### Price Acceptance Profile (PAP)",
        "- Lookback = 320 bars, 26 histogram rows, value area = 70%",
        "- Builds time-at-price histogram; finds POC, VAH, VAL",
        "- Acceptance state: Accepted (inside VA), Edge (within 1.5 rows of boundary), Rejected (outside VA)",
        "- Rotation: COG shift from first half to second half of lookback window",
        "- acceptanceScore = POC proximity (0-40) + VA width bonus (0-20) + rotation alignment (0-20) + state bonus (0-20)",
        "",
        "---",
        "",
        "## BIST Results",
        f"(Tickers: {', '.join(BIST_TICKERS)})",
        "",
    ]

    if bist_sigs.empty:
        lines.append("_No signals generated for BIST tickers._")
    else:
        # PAP state distribution
        pap_dist = bist_sigs["pap_state"].value_counts()
        lines += [
            "### PAP State Distribution (all BIST bars with SRP activity)",
            "",
        ]
        for state, cnt in pap_dist.items():
            lines.append(f"- {state}: {cnt} ({cnt/len(bist_sigs)*100:.1f}%)")
        lines.append("")

        # SRP score distribution
        srp_pct = {
            ">= 50": (bist_sigs["srp_score"] >= 50).sum(),
            ">= 60": (bist_sigs["srp_score"] >= 60).sum(),
            ">= 66": (bist_sigs["srp_score"] >= 66).sum(),
            ">= 70": (bist_sigs["srp_score"] >= 70).sum(),
            ">= 75": (bist_sigs["srp_score"] >= 75).sum(),
        }
        lines += [
            "### SRP Score Distribution (BIST)",
            "",
        ]
        for k, v in srp_pct.items():
            lines.append(f"- Score {k}: {v} signals ({v/len(bist_sigs)*100:.1f}%)")
        lines.append("")

        lines += [
            "### Filter Performance — BIST",
            "",
            fmt_table(bist_results),
            "",
            "### Per-Ticker Breakdown — BIST (Baseline / all SRP signals)",
            "",
            fmt_ticker_table(per_ticker_stats(bist_sigs)),
            "",
            "### Per-Ticker Breakdown — BIST (SRP >= 66 filter)",
            "",
            fmt_ticker_table(per_ticker_stats(bist_sigs, bist_sigs["srp_score"] >= 66)),
        ]

    lines += [
        "",
        "---",
        "",
        "## USA Results",
        f"(Tickers: {', '.join(USA_TICKERS)})",
        "",
    ]

    if usa_sigs.empty:
        lines.append("_No signals generated for USA tickers._")
    else:
        pap_dist_usa = usa_sigs["pap_state"].value_counts()
        lines += [
            "### PAP State Distribution (all USA bars with SRP activity)",
            "",
        ]
        for state, cnt in pap_dist_usa.items():
            lines.append(f"- {state}: {cnt} ({cnt/len(usa_sigs)*100:.1f}%)")
        lines.append("")

        srp_pct_usa = {
            ">= 50": (usa_sigs["srp_score"] >= 50).sum(),
            ">= 60": (usa_sigs["srp_score"] >= 60).sum(),
            ">= 66": (usa_sigs["srp_score"] >= 66).sum(),
            ">= 70": (usa_sigs["srp_score"] >= 70).sum(),
            ">= 75": (usa_sigs["srp_score"] >= 75).sum(),
        }
        lines += [
            "### SRP Score Distribution (USA)",
            "",
        ]
        for k, v in srp_pct_usa.items():
            lines.append(f"- Score {k}: {v} signals ({v/len(usa_sigs)*100:.1f}%)")
        lines.append("")

        lines += [
            "### Filter Performance — USA",
            "",
            fmt_table(usa_results),
            "",
            "### Per-Ticker Breakdown — USA (Baseline / all SRP signals)",
            "",
            fmt_ticker_table(per_ticker_stats(usa_sigs)),
            "",
            "### Per-Ticker Breakdown — USA (SRP >= 66 filter)",
            "",
            fmt_ticker_table(per_ticker_stats(usa_sigs, usa_sigs["srp_score"] >= 66)),
        ]

    # SPY regime analysis
    lines += [
        "",
        "---",
        "",
        "## SPY PAP as Market Regime Indicator",
        "",
        "When SPY is in a given PAP acceptance state, how do individual USA stocks perform (5d)?",
        "",
        "| SPY State | # Observations | Hit Rate | Avg 5d Ret |",
        "|-----------|----------------|----------|------------|",
    ]
    for state, stats in spy_regime.items():
        lines.append(
            f"| {state:<10} | {stats['n']:>14} | {stats['hit_rate']:>7.1f}% | {stats['avg_ret']:>+9.2f}% |"
        )

    # SRP score distribution across both markets
    all_sigs = pd.concat([s for s in [bist_sigs, usa_sigs] if not s is None and not s.empty],
                         ignore_index=True)

    lines += [
        "",
        "---",
        "",
        "## Recommendations",
        "",
        "### BIST Recommendations",
        "",
    ]

    if not bist_sigs.empty and bist_results:
        # Find best filter for BIST
        valid = [r for r in bist_results if r["n"] >= 10 and not pd.isna(r.get("avg_ret", np.nan))]
        if valid:
            best = max(valid, key=lambda x: x["avg_ret"])
            best_hr = max(valid, key=lambda x: x["hit_rate"])
            lines += [
                f"- **Best avg return filter:** `{best['filter']}` → {best['avg_ret']:+.2f}% avg, {best['hit_rate']:.1f}% hit rate",
                f"- **Best hit rate filter:** `{best_hr['filter']}` → {best_hr['hit_rate']:.1f}% hit rate, {best_hr['avg_ret']:+.2f}% avg",
                "",
                "**BIST-specific notes:**",
                "- BIST stocks have higher volatility; SRP wick sweeps are frequent due to low liquidity gaps",
                "- PAP filter adds value by avoiding trades during rejected/trending-away regimes",
                "- Recommended threshold: **SRP >= 66 + PAP Accepted/Edge** (Combined filter)",
                "- Consider higher SRP threshold (70+) if false positives dominate in strong trending markets",
            ]
    else:
        lines.append("- Insufficient data for BIST recommendations.")

    lines += [
        "",
        "### USA Recommendations",
        "",
    ]

    if not usa_sigs.empty and usa_results:
        valid_usa = [r for r in usa_results if r["n"] >= 10 and not pd.isna(r.get("avg_ret", np.nan))]
        if valid_usa:
            best_usa = max(valid_usa, key=lambda x: x["avg_ret"])
            best_hr_usa = max(valid_usa, key=lambda x: x["hit_rate"])
            lines += [
                f"- **Best avg return filter:** `{best_usa['filter']}` → {best_usa['avg_ret']:+.2f}% avg, {best_usa['hit_rate']:.1f}% hit rate",
                f"- **Best hit rate filter:** `{best_hr_usa['filter']}` → {best_hr_usa['hit_rate']:.1f}% hit rate, {best_hr_usa['avg_ret']:+.2f}% avg",
                "",
                "**USA-specific notes:**",
                "- Large caps (SPY, AAPL, MSFT, NVDA) have well-defined liquidity pools; SRP signals are rarer",
                "- PAP is particularly useful as a regime filter — SPY Accepted state improves stock hit rates",
                "- Recommended threshold: **SRP >= 66 + PAP Accepted/Edge** for standard signals",
                "- For high-conviction early signals: **SRP >= 70** (captures strongest sweeps)",
            ]
    else:
        lines.append("- Insufficient data for USA recommendations.")

    lines += [
        "",
        "---",
        "",
        "## Pipeline Integration — Required Code Changes",
        "",
        "To add SRP + PAP to the existing pipeline (`src/`), the following changes are needed:",
        "",
        "### 1. New module: `src/srp_indicator.py`",
        "```python",
        "# Expose: compute_srp(df) -> pd.Series (score per bar)",
        "# Parameters: lookback=34, atr_period=14, vol_baseline=34",
        "# Call from pipeline after OHLCV fetch",
        "```",
        "",
        "### 2. New module: `src/pap_indicator.py`",
        "```python",
        "# Expose: compute_pap(df) -> pd.DataFrame (poc, vah, val, state, score per bar)",
        "# Parameters: lookback=320, n_rows=26, value_area_pct=0.70",
        "# Note: PAP lookback=320 requires at least 320 bars of history (~15 months daily)",
        "```",
        "",
        "### 3. Update `src/event_filter.py`",
        "```python",
        "# Add to run_event_filter():",
        "#   srp_score = compute_srp(df)",
        "#   pap_df    = compute_pap(df)",
        "#   if srp_score.iloc[-1] >= 66:",
        "#       triggers.append('srp_reversal')",
        "#   pap_state = pap_df['acceptance_state'].iloc[-1]",
        "#   if pap_state in ['Accepted', 'Edge']:",
        "#       triggers.append('pap_accepted')",
        "```",
        "",
        "### 4. Update `src/detailed_scorer.py`",
        "```python",
        "# Add SRP and PAP components to score_ticker():",
        "#   srp component: up to +15 pts (srp_score/100 * 15)",
        "#   pap component: +10 pts if Accepted, +5 if Edge, 0 if Rejected",
        "#   Adjust _DEFAULT_WEIGHTS to accommodate new components",
        "```",
        "",
        "### 5. Update `src/decision_engine.py`",
        "```python",
        "# Add optional srp_score and pap_state fields to candidate dict",
        "# Gate: if srp_score is present and < 66, treat as WATCH even if RS passes",
        "# Gate: if pap_state == 'Rejected', downgrade BUY -> WATCH",
        "```",
        "",
        "### 6. Update `src/firebase_writer.py`",
        "```python",
        "# Add srp_score, pap_state, pap_score fields to Firestore document",
        "# Add pap_poc, pap_vah, pap_val for display in dashboard",
        "```",
        "",
        "### 7. Minimum data requirements",
        "- SRP: needs max(34, 14, 34) + 5 = 39 bars minimum (easily met for daily data)",
        "- PAP: needs 320 bars minimum (~15 months of daily data)",
        "- For BIST tickers: verify data availability >= 320 bars before enabling PAP",
        "",
        "---",
        "",
        "_Generated by backtest/srp_pap_backtest.py_",
    ]

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("SRP + PAP Backtest")
    print(f"Period: {START_DATE} → {END_DATE}")
    print("=" * 60)

    # Fetch data
    print("\n[1] Fetching BIST data …")
    bist_data = fetch_ohlcv(BIST_TICKERS, "bist")

    print("\n[2] Fetching USA data …")
    usa_data = fetch_ohlcv(USA_TICKERS, "usa")

    # Run backtests
    print("\n[3] Running BIST backtest …")
    bist_sigs = backtest_universe(bist_data, "BIST")
    print(f"  BIST: {len(bist_sigs)} total signal bars")

    print("\n[4] Running USA backtest …")
    usa_sigs = backtest_universe(usa_data, "USA")
    print(f"  USA: {len(usa_sigs)} total signal bars")

    # Filter analysis
    print("\n[5] Computing filter statistics …")
    bist_results = run_filter_analysis(bist_sigs, "BIST")
    usa_results  = run_filter_analysis(usa_sigs, "USA")

    # SPY regime analysis
    print("\n[6] SPY regime analysis …")
    spy_pap = pd.DataFrame()
    if "SPY" in usa_data:
        spy_pap = compute_pap(usa_data["SPY"])
    spy_regime = spy_regime_analysis(usa_sigs, spy_pap)

    # Print quick summary
    print("\n=== BIST Summary ===")
    for r in bist_results:
        ar = f"{r['avg_ret']:+.2f}%" if not pd.isna(r.get("avg_ret", np.nan)) else "—"
        hr = f"{r['hit_rate']:.1f}%" if not pd.isna(r.get("hit_rate", np.nan)) else "—"
        print(f"  {r['filter']:<45} n={r['n']:>4}  hit={hr}  avg={ar}")

    print("\n=== USA Summary ===")
    for r in usa_results:
        ar = f"{r['avg_ret']:+.2f}%" if not pd.isna(r.get("avg_ret", np.nan)) else "—"
        hr = f"{r['hit_rate']:.1f}%" if not pd.isna(r.get("hit_rate", np.nan)) else "—"
        print(f"  {r['filter']:<45} n={r['n']:>4}  hit={hr}  avg={ar}")

    print("\n=== SPY Regime ===")
    for state, stats in spy_regime.items():
        print(f"  SPY {state:<10}: n={stats['n']:>4}  hit={stats['hit_rate']:.1f}%  avg={stats['avg_ret']:+.2f}%")

    # Write report
    print("\n[7] Writing report …")
    report = generate_md_report(
        bist_results, usa_results,
        bist_sigs, usa_sigs,
        spy_regime,
        today=date.today().isoformat(),
    )
    report_path = BACKTEST_DIR / "srp_pap_backtest.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"  Report saved → {report_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
