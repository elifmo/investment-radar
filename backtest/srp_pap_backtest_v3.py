"""
SRP + PAP Backtest v3 — Bounce vs Trend Analysis
=================================================
Same entry signals as v2:
  BIST: PAP state is Accepted or Edge AND SRP score >= 60
  USA:  PAP state is Accepted or Edge (any SRP signal, score > 0)

Extended fixed hold periods: 5, 10, 20, 40, 60, 90, 120 days

New analyses:
  1. Full return curve table (5→120d) per universe
  2. Maximum Favorable Excursion (MFE): peak gain achieved at ANY point
     during a 120-day window → tells us the "true potential" of each signal
  3. Drawdown from MFE by day 120: if it gives back >50% of MFE → bounce

Usage:
    /Users/Elifcik/Desktop/apps/investment-radar/.venv/bin/python3 backtest/srp_pap_backtest_v3.py
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
BIST_TICKERS = ["EREGL.IS", "TOASO.IS", "TUPRS.IS", "THYAO.IS", "KCHOL.IS"]
USA_TICKERS  = ["SPY", "AAPL", "MSFT", "NVDA", "AMZN", "META"]

START_DATE  = (date.today() - timedelta(days=2*365+10)).isoformat()
END_DATE    = date.today().isoformat()

MFE_WINDOW  = 120          # look-forward bars for MFE computation
FIXED_HOLDS = [5, 10, 20, 40, 60, 90, 120]


# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch_ohlcv(tickers: list[str], cache_key: str) -> dict[str, pd.DataFrame]:
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
    vol_ma   = vol.rolling(vol_baseline).mean()
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

        body             = abs(bar_cl - bar_op)
        target_room_score = min(100.0, (body / bar_atr) * 60)

        if i >= 6:
            prior_change = cl.iloc[i - 1] - cl.iloc[i - 6]
            trend_turn_score = (80.0 if (bull_sweep and prior_change < 0) or
                                        (not bull_sweep and prior_change > 0)
                                else 30.0)
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

        bins           = np.linspace(w_min, w_max, n_rows + 1)
        counts, edges  = np.histogram(window, bins=bins)
        row_mids       = (edges[:-1] + edges[1:]) / 2

        poc_idx = counts.argmax()
        poc     = row_mids[poc_idx]

        total         = counts.sum()
        target        = int(total * value_area_pct)
        included      = {poc_idx}
        included_count = counts[poc_idx]
        lo_idx, hi_idx = poc_idx, poc_idx

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
            cog_first, cog_second = w_first.mean(), w_second.mean()
            rotation = "Up"   if cog_second > cog_first * 1.001 else \
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

        poc_dist     = abs(cur_price - poc) / (w_max - w_min + 1e-10)
        poc_score    = max(0.0, 40.0 * (1 - poc_dist * 2))
        va_width     = (vah - val) / (w_max - w_min + 1e-10)
        va_score     = max(0.0, 20.0 * (1 - va_width))

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


# ── Entry signal detection ────────────────────────────────────────────────────

def detect_entries(df: pd.DataFrame, srp: pd.DataFrame, pap: pd.DataFrame,
                   universe: str) -> list[dict]:
    n  = len(df)
    op = df["Open"] if "Open" in df.columns else df["Close"]
    entries = []

    # Leave at least MFE_WINDOW bars after entry
    for i in range(1, n - MFE_WINDOW - 2):
        srp_score = srp["score"].iloc[i]
        srp_dir   = srp["direction"].iloc[i]
        pap_state = pap["acceptance_state"].iloc[i]

        if srp_dir == "" or pd.isna(srp_score) or srp_score == 0.0:
            continue
        if pap_state == "" or pd.isna(pap_state):
            continue
        if pap_state not in ("Accepted", "Edge"):
            continue
        if universe == "BIST" and srp_score < 60:
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


# ── Fixed hold simulation ─────────────────────────────────────────────────────

def simulate_fixed_hold(df: pd.DataFrame, entries: list[dict],
                        ticker: str, universe: str, hold: int) -> list[dict]:
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


# ── MFE computation ───────────────────────────────────────────────────────────

def compute_mfe(df: pd.DataFrame, entries: list[dict],
                ticker: str, universe: str) -> list[dict]:
    """
    For each entry, look forward MFE_WINDOW bars.
    For BULLISH entries:
        MFE  = max(Close) relative to entry_price over the window
        Day-120 price for drawdown calculation
    For BEARISH entries:
        MFE  = min(Close) relative to entry_price (we use absolute return magnitude)

    Returns list of dicts with:
        mfe           : max favourable return seen in window
        mfe_day       : bar offset when MFE was reached
        ret_day120    : return at bar entry_bar + 120 (or last available)
        drawdown_from_mfe : (mfe - ret_day120) if bullish; measures how much was given back
    """
    cl = df["Close"]
    n  = len(df)
    records = []

    for e in entries:
        entry_bar   = e["entry_bar"]
        entry_price = e["entry_price"]
        srp_dir     = e["srp_dir"]

        end_bar = min(entry_bar + MFE_WINDOW, n - 1)
        if end_bar <= entry_bar:
            continue

        forward_cl = cl.iloc[entry_bar + 1: end_bar + 1].values
        if len(forward_cl) == 0:
            continue

        returns = (forward_cl - entry_price) / entry_price

        if srp_dir == "bullish":
            mfe_idx = int(np.argmax(returns))
            mfe     = float(returns[mfe_idx])
        else:  # bearish — treat as short: gain when price falls
            mfe_idx = int(np.argmin(returns))
            mfe     = float(-returns[mfe_idx])   # positive when profitable

        mfe_day = mfe_idx + 1   # 1-based offset from entry

        # Return at day-120 endpoint (last forward bar we have)
        ret_end = float(returns[-1])
        if srp_dir == "bearish":
            ret_end = -ret_end   # flip sign for short

        # How much of the MFE was given back by the end of the window?
        if mfe > 0:
            drawdown_from_mfe = mfe - ret_end          # positive = gave back gains
            pct_given_back    = drawdown_from_mfe / mfe * 100
        else:
            drawdown_from_mfe = 0.0
            pct_given_back    = 0.0

        records.append({
            "ticker":            ticker,
            "universe":          universe,
            "entry_price":       entry_price,
            "srp_dir":           srp_dir,
            "mfe":               mfe * 100,          # in pct
            "mfe_day":           mfe_day,
            "ret_day120":        ret_end * 100,       # in pct
            "drawdown_from_mfe": drawdown_from_mfe * 100,  # in pct
            "pct_given_back":    pct_given_back,
            "is_bounce":         int(pct_given_back > 50),
        })

    return records


# ── Per-universe runner ────────────────────────────────────────────────────────

def run_universe(data: dict[str, pd.DataFrame],
                 universe: str) -> tuple[list[dict], list[dict]]:
    all_fixed_trades = []
    all_mfe_records  = []

    for ticker, df in data.items():
        print(f"  [{universe}] {ticker} ({len(df)} bars) …")
        srp = compute_srp(df)
        pap = compute_pap(df)

        entries = detect_entries(df, srp, pap, universe)
        print(f"    Entries: {len(entries)}")
        if not entries:
            continue

        for hold in FIXED_HOLDS:
            fx = simulate_fixed_hold(df, entries, ticker, universe, hold)
            all_fixed_trades.extend(fx)

        mfe = compute_mfe(df, entries, ticker, universe)
        all_mfe_records.extend(mfe)

    return all_fixed_trades, all_mfe_records


# ── Statistics ────────────────────────────────────────────────────────────────

def return_curve(fixed_trades: list[dict], universe: str) -> list[dict]:
    """Avg return + hit rate at each hold period for a universe."""
    df = pd.DataFrame(fixed_trades) if fixed_trades else pd.DataFrame()
    rows = []
    for hold in FIXED_HOLDS:
        sub = df[df["hold"] == hold] if not df.empty else pd.DataFrame()
        if sub.empty:
            rows.append({"hold": hold, "n": 0,
                         "avg_ret": np.nan, "median_ret": np.nan,
                         "hit_rate": np.nan})
        else:
            rows.append({
                "hold":       hold,
                "n":          len(sub),
                "avg_ret":    sub["ret"].mean() * 100,
                "median_ret": sub["ret"].median() * 100,
                "hit_rate":   sub["hit"].mean() * 100,
            })
    return rows


def mfe_summary(mfe_records: list[dict], universe: str) -> dict:
    df = pd.DataFrame(mfe_records) if mfe_records else pd.DataFrame()
    sub = df[df["universe"] == universe] if not df.empty else pd.DataFrame()
    if sub.empty:
        return {"universe": universe, "n": 0,
                "avg_mfe": np.nan, "avg_mfe_day": np.nan,
                "avg_ret_d120": np.nan, "avg_dd_from_mfe": np.nan,
                "bounce_rate": np.nan}
    return {
        "universe":        universe,
        "n":               len(sub),
        "avg_mfe":         sub["mfe"].mean(),
        "avg_mfe_day":     sub["mfe_day"].mean(),
        "avg_ret_d120":    sub["ret_day120"].mean(),
        "avg_dd_from_mfe": sub["drawdown_from_mfe"].mean(),
        "bounce_rate":     sub["is_bounce"].mean() * 100,
    }


def mfe_per_ticker(mfe_records: list[dict]) -> pd.DataFrame:
    if not mfe_records:
        return pd.DataFrame()
    df = pd.DataFrame(mfe_records)
    g = df.groupby(["universe", "ticker"]).agg(
        n             =("mfe",          "count"),
        avg_mfe       =("mfe",          "mean"),
        avg_mfe_day   =("mfe_day",      "mean"),
        avg_ret_d120  =("ret_day120",   "mean"),
        avg_dd        =("drawdown_from_mfe", "mean"),
        bounce_rate   =("is_bounce",    "mean"),
    ).reset_index()
    g["bounce_rate"] = g["bounce_rate"] * 100
    return g.sort_values(["universe", "avg_mfe"], ascending=[True, False])


# ── Verdict logic ─────────────────────────────────────────────────────────────

def bounce_or_trend(curve_rows: list[dict], mfe_s: dict, universe: str) -> str:
    """
    Synthesise the data into a plain-English verdict.
    Rules:
      - TREND: return curve keeps rising past 40d AND pct_given_back <= 50%
      - BOUNCE: return curve peaks before 20d OR pct_given_back > 50%
      - MIXED: somewhere in between
    """
    valid = [r for r in curve_rows if not pd.isna(r.get("avg_ret")) and r["n"] >= 1]
    if not valid:
        return "Insufficient data."

    rets       = [(r["hold"], r["avg_ret"]) for r in valid]
    best_hold, best_ret = max(rets, key=lambda x: x[1])
    ret_at_40  = next((r["avg_ret"] for r in valid if r["hold"] == 40), np.nan)
    ret_at_120 = next((r["avg_ret"] for r in valid if r["hold"] == 120), np.nan)

    bounce_rate = mfe_s.get("bounce_rate", np.nan)
    avg_mfe     = mfe_s.get("avg_mfe", np.nan)
    avg_mfe_day = mfe_s.get("avg_mfe_day", np.nan)

    parts = []

    # 1. Shape of the return curve
    if not pd.isna(ret_at_40) and not pd.isna(ret_at_120):
        if ret_at_120 > ret_at_40 * 1.10:
            parts.append(
                f"The return curve is **rising**: avg return improves from "
                f"{ret_at_40:+.2f}% at 40d to {ret_at_120:+.2f}% at 120d — "
                f"consistent with a TREND starter, not a short-term bounce."
            )
        elif ret_at_120 < ret_at_40 * 0.80:
            parts.append(
                f"The return curve is **declining** after 40d: return drops from "
                f"{ret_at_40:+.2f}% (40d) to {ret_at_120:+.2f}% (120d) — "
                f"typical bounce behaviour where early gains fade."
            )
        else:
            parts.append(
                f"The return curve is **flat** between 40d ({ret_at_40:+.2f}%) and "
                f"120d ({ret_at_120:+.2f}%) — gains are captured early and then "
                f"held, suggesting a moderately trending signal."
            )

    # 2. Best hold
    parts.append(
        f"Peak average return of {best_ret:+.2f}% is achieved at the {best_hold}-day hold."
    )

    # 3. MFE / drawdown-from-MFE
    if not pd.isna(avg_mfe):
        parts.append(
            f"The signal's true potential (MFE) averages {avg_mfe:+.2f}%, "
            f"typically reached around day {avg_mfe_day:.0f}."
        )

    if not pd.isna(bounce_rate):
        if bounce_rate > 60:
            parts.append(
                f"{bounce_rate:.0f}% of trades give back >50% of their MFE by day 120 — "
                f"strong evidence these are **SHORT-TERM BOUNCES**, not persistent trends."
            )
        elif bounce_rate > 40:
            parts.append(
                f"{bounce_rate:.0f}% of trades give back >50% of their MFE by day 120 — "
                f"**MIXED** behaviour: some trades sustain gains while others fade."
            )
        else:
            parts.append(
                f"Only {bounce_rate:.0f}% of trades give back >50% of their MFE by day 120 — "
                f"most signals sustain their gains, pointing to **TREND-STARTING** behaviour."
            )

    # 4. Final label
    if not pd.isna(bounce_rate) and not pd.isna(ret_at_40) and not pd.isna(ret_at_120):
        is_trend_curve  = ret_at_120 >= ret_at_40 * 0.90   # curve does not collapse
        is_low_giveBack = bounce_rate <= 50
        if is_trend_curve and is_low_giveBack:
            verdict = "TREND STARTER"
        elif not is_trend_curve and not is_low_giveBack:
            verdict = "SHORT-TERM BOUNCE"
        else:
            verdict = "MIXED (bounce with partial trend follow-through)"
    else:
        verdict = "INCONCLUSIVE"

    parts.append(f"\n**Verdict for {universe}: {verdict}**")
    return " ".join(parts)


# ── Report builder ────────────────────────────────────────────────────────────

def fmt_curve_table(rows: list[dict]) -> str:
    lines = [
        "| Hold (days) | # Trades | Avg Return | Median Return | Hit Rate |",
        "|-------------|----------|------------|---------------|----------|",
    ]
    for r in rows:
        n  = r["n"]
        ar = f"{r['avg_ret']:+.2f}%"    if not pd.isna(r.get("avg_ret", np.nan)) else "—"
        mr = f"{r['median_ret']:+.2f}%" if not pd.isna(r.get("median_ret", np.nan)) else "—"
        hr = f"{r['hit_rate']:.1f}%"    if not pd.isna(r.get("hit_rate", np.nan)) else "—"
        lines.append(f"| {r['hold']:>11} | {n:>8} | {ar:>10} | {mr:>13} | {hr:>8} |")
    return "\n".join(lines)


def fmt_mfe_table(summaries: list[dict]) -> str:
    lines = [
        "| Universe | # Trades | Avg MFE | Avg Day MFE | Avg Return @120d | Avg DD from MFE | Bounce Rate |",
        "|----------|----------|---------|-------------|------------------|-----------------|-------------|",
    ]
    for s in summaries:
        n   = s["n"]
        mfe = f"{s['avg_mfe']:+.2f}%"     if not pd.isna(s.get("avg_mfe", np.nan)) else "—"
        day = f"{s['avg_mfe_day']:.0f}"   if not pd.isna(s.get("avg_mfe_day", np.nan)) else "—"
        r120 = f"{s['avg_ret_d120']:+.2f}%" if not pd.isna(s.get("avg_ret_d120", np.nan)) else "—"
        dd  = f"{s['avg_dd_from_mfe']:.2f}%" if not pd.isna(s.get("avg_dd_from_mfe", np.nan)) else "—"
        br  = f"{s['bounce_rate']:.0f}%"  if not pd.isna(s.get("bounce_rate", np.nan)) else "—"
        lines.append(
            f"| {s['universe']:<8} | {n:>8} | {mfe:>7} | {day:>11} | {r120:>16} | {dd:>15} | {br:>11} |"
        )
    return "\n".join(lines)


def fmt_mfe_ticker_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No data_"
    lines = [
        "| Universe | Ticker | # | Avg MFE | Avg Day | Ret @120d | Avg DD | Bounce % |",
        "|----------|--------|---|---------|---------|-----------|--------|----------|",
    ]
    for row in df.itertuples():
        lines.append(
            f"| {row.universe:<8} | {row.ticker:<10} | {row.n:>3} | "
            f"{row.avg_mfe:>+7.2f}% | {row.avg_mfe_day:>7.0f} | "
            f"{row.avg_ret_d120:>+9.2f}% | {row.avg_dd:>+6.2f}% | "
            f"{row.bounce_rate:>8.0f}% |"
        )
    return "\n".join(lines)


def generate_report(
    bist_fixed: list[dict],
    usa_fixed:  list[dict],
    bist_mfe:   list[dict],
    usa_mfe:    list[dict],
    today: str,
) -> str:
    bist_curve = return_curve(bist_fixed, "BIST")
    usa_curve  = return_curve(usa_fixed,  "USA")

    # Combined
    combined_fixed  = bist_fixed + usa_fixed
    combined_curve  = return_curve(combined_fixed, "All")

    bist_mfe_s = mfe_summary(bist_mfe + usa_mfe, "BIST")
    usa_mfe_s  = mfe_summary(bist_mfe + usa_mfe, "USA")

    # Rebuild with universe filter properly
    bist_mfe_s = mfe_summary(bist_mfe, "BIST")
    usa_mfe_s  = mfe_summary(usa_mfe,  "USA")

    all_mfe    = bist_mfe + usa_mfe
    ticker_df  = mfe_per_ticker(all_mfe)

    bist_verdict = bounce_or_trend(bist_curve, bist_mfe_s, "BIST")
    usa_verdict  = bounce_or_trend(usa_curve,  usa_mfe_s,  "USA")

    # ── Best and worst hold for each universe
    def best_worst(curve_rows):
        valid = [r for r in curve_rows if not pd.isna(r.get("avg_ret")) and r["n"] >= 1]
        if not valid:
            return None, None
        best  = max(valid, key=lambda x: x["avg_ret"])
        worst = min(valid, key=lambda x: x["avg_ret"])
        return best, worst

    bist_best, bist_worst = best_worst(bist_curve)
    usa_best,  usa_worst  = best_worst(usa_curve)

    lines = [
        "# SRP + PAP Backtest v3 — Bounce vs Trend Analysis",
        "",
        f"**Date generated:** {today}",
        f"**Period:** {START_DATE} → {END_DATE} (2 years daily)",
        f"**Fixed hold periods:** {', '.join(str(h) for h in FIXED_HOLDS)} days",
        f"**MFE look-forward window:** {MFE_WINDOW} days",
        "",
        "## Entry Criteria (identical to v2)",
        "",
        "| Universe | PAP State | SRP Threshold |",
        "|----------|-----------|---------------|",
        "| BIST     | Accepted or Edge | SRP score >= 60 |",
        "| USA      | Accepted or Edge | Any SRP signal (score > 0) |",
        "",
        "---",
        "",
        "## 1. Full Return Curve Table",
        "",
        "Same entry signals, exit at each fixed number of days after entry.",
        "",
        "### BIST",
        "",
        fmt_curve_table(bist_curve),
        "",
        "### USA",
        "",
        fmt_curve_table(usa_curve),
        "",
        "### Combined (BIST + USA)",
        "",
        fmt_curve_table(combined_curve),
        "",
        "---",
        "",
        "## 2. Maximum Favorable Excursion (MFE) Analysis",
        "",
        (
            "For each trade, we look forward **120 trading days** from entry and record:\n"
            "- **MFE**: the peak gain (for bullish signals) or peak gain-equivalent (for bearish) at any bar\n"
            "- **MFE day**: how many days after entry the peak was reached\n"
            "- **Return @120d**: the actual return at day 120\n"
            "- **DD from MFE**: MFE minus Return@120d (how much was given back)\n"
            "- **Bounce Rate**: % of trades where >50% of MFE was given back by day 120"
        ),
        "",
        "### MFE Summary by Universe",
        "",
        fmt_mfe_table([bist_mfe_s, usa_mfe_s]),
        "",
        "### MFE by Ticker",
        "",
        fmt_mfe_ticker_table(ticker_df),
        "",
        "---",
        "",
        "## 3. Verdict: Bounce or Trend Starter?",
        "",
        "### BIST",
        "",
        bist_verdict,
        "",
        "### USA",
        "",
        usa_verdict,
        "",
    ]

    # Highlight best/worst hold
    lines += [
        "---",
        "",
        "## 4. Key Highlights",
        "",
        "### BIST",
    ]
    if bist_best:
        lines.append(
            f"- Best hold period: **{bist_best['hold']} days** → avg return {bist_best['avg_ret']:+.2f}%  "
            f"(hit rate {bist_best['hit_rate']:.1f}%)"
        )
        if bist_worst:
            lines.append(
                f"- Worst hold period: **{bist_worst['hold']} days** → avg return {bist_worst['avg_ret']:+.2f}%"
            )
    else:
        lines.append("- Too few trades for highlights.")

    lines.append("")
    lines.append("### USA")
    if usa_best:
        lines.append(
            f"- Best hold period: **{usa_best['hold']} days** → avg return {usa_best['avg_ret']:+.2f}%  "
            f"(hit rate {usa_best['hit_rate']:.1f}%)"
        )
        if usa_worst:
            lines.append(
                f"- Worst hold period: **{usa_worst['hold']} days** → avg return {usa_worst['avg_ret']:+.2f}%"
            )
    else:
        lines.append("- Too few trades for highlights.")

    if bist_mfe_s["n"] > 0 and usa_mfe_s["n"] > 0:
        lines += [
            "",
            "### MFE Highlights",
            f"- BIST signals reach their peak gain (MFE avg {bist_mfe_s['avg_mfe']:.2f}%) "
            f"around day {bist_mfe_s['avg_mfe_day']:.0f} on average.",
            f"- USA signals reach their peak gain (MFE avg {usa_mfe_s['avg_mfe']:.2f}%) "
            f"around day {usa_mfe_s['avg_mfe_day']:.0f} on average.",
            f"- BIST bounce rate (>50% MFE given back by d120): **{bist_mfe_s['bounce_rate']:.0f}%**",
            f"- USA  bounce rate (>50% MFE given back by d120): **{usa_mfe_s['bounce_rate']:.0f}%**",
        ]

    lines += [
        "",
        "---",
        "",
        "_Generated by backtest/srp_pap_backtest_v3.py_",
    ]

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("SRP + PAP Backtest v3 — Bounce vs Trend Analysis")
    print(f"Period: {START_DATE} → {END_DATE}")
    print(f"Fixed holds: {FIXED_HOLDS}")
    print(f"MFE window: {MFE_WINDOW} days")
    print("=" * 60)

    print("\n[1] Fetching BIST data …")
    bist_data = fetch_ohlcv(BIST_TICKERS, "bist")

    print("\n[2] Fetching USA data …")
    usa_data = fetch_ohlcv(USA_TICKERS, "usa")

    print("\n[3] Running BIST backtest …")
    bist_fixed, bist_mfe = run_universe(bist_data, "BIST")
    print(f"  BIST fixed-hold records: {len(bist_fixed)}")
    print(f"  BIST MFE records:        {len(bist_mfe)}")

    print("\n[4] Running USA backtest …")
    usa_fixed, usa_mfe = run_universe(usa_data, "USA")
    print(f"  USA fixed-hold records:  {len(usa_fixed)}")
    print(f"  USA MFE records:         {len(usa_mfe)}")

    # Console summary
    print("\n=== Return Curve (Combined) ===")
    combined = pd.DataFrame(bist_fixed + usa_fixed) if (bist_fixed or usa_fixed) else pd.DataFrame()
    for hold in FIXED_HOLDS:
        sub = combined[combined["hold"] == hold] if not combined.empty else pd.DataFrame()
        if not sub.empty:
            print(
                f"  {hold:>3}d: n={len(sub):>4}  hit={sub['hit'].mean()*100:.1f}%  "
                f"avg={sub['ret'].mean()*100:+.2f}%  median={sub['ret'].median()*100:+.2f}%"
            )

    print("\n=== MFE Summary ===")
    for records, uni in [(bist_mfe, "BIST"), (usa_mfe, "USA")]:
        s = mfe_summary(records, uni)
        if s["n"] > 0:
            print(
                f"  {uni}: n={s['n']}  MFE={s['avg_mfe']:+.2f}%  day={s['avg_mfe_day']:.0f}  "
                f"ret@120d={s['avg_ret_d120']:+.2f}%  bounce%={s['bounce_rate']:.0f}%"
            )

    print("\n[5] Writing report …")
    report = generate_report(
        bist_fixed, usa_fixed,
        bist_mfe,   usa_mfe,
        today=date.today().isoformat(),
    )
    report_path = BACKTEST_DIR / "srp_pap_backtest_v3.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"  Report saved → {report_path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
