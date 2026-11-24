"""
Same 3-gate ENTRY, three EXIT scenarios — 2y all stocks.

ENTRY (fixed):
  score >= 65  AND  close > daily Ichimoku cloud top

EXITS:
  A) hard     — zorunlu: −15% from entry (thesis broken proxy for written exit)
  B) ema200   — trend: daily close < EMA200
  C) protect  — kâr koruma: after +12% peak, stop rises to breakeven;
                then trail 10% off peak; still hard −20% catastrophe stop

  python3 backtest/radar_exit_scenarios.py
"""

from __future__ import annotations

import argparse
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
import yfinance as yf

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[1]
PERIOD = "2y"
MIN_SCORE = 65
TENKAN, KIJUN, SENKOU_B = 9, 26, 52
MIN_BARS = 120

W = {
    "ema_alignment": 20,
    "rsi_health": 15,
    "volume_spike": 20,
    "price_momentum": 15,
    "bollinger_position": 10,
    "sr_proximity": 10,
    "breakout": 10,
}

# Exit params
HARD_STOP = 0.15          # A: −15%
PROTECT_ARM = 0.12        # C: arm after +12%
PROTECT_TRAIL = 0.10      # C: 10% off peak after armed
PROTECT_HARD = 0.20       # C: −20% never blow up


def load_stocks(limit: int | None = None) -> list[str]:
    sp = yaml.safe_load((ROOT / "config/sp500.yaml").read_text())
    uni = yaml.safe_load((ROOT / "config/universe.yaml").read_text())
    stocks = sorted({x["ticker"] for x in sp["sp500"]} | {x["ticker"] for x in uni["usa"]})
    return stocks[:limit] if limit else stocks


def batch_download(symbols: list[str]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    chunk = 40
    for i in range(0, len(symbols), chunk):
        part = symbols[i : i + chunk]
        print(f"  download {i+1}-{i+len(part)}/{len(symbols)}…", flush=True)
        try:
            raw = yf.download(
                part, interval="1d", period=PERIOD, group_by="ticker",
                auto_adjust=True, progress=False, threads=True,
            )
        except Exception as exc:
            print(f"    fail: {exc}")
            continue
        if len(part) == 1:
            df = raw
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if df is not None and not df.empty and "Close" in df.columns:
                d = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
                if len(d) >= MIN_BARS:
                    out[part[0]] = d
        elif isinstance(raw.columns, pd.MultiIndex):
            tickers = set(raw.columns.get_level_values(0).unique())
            for s in part:
                if s not in tickers:
                    continue
                try:
                    sub = raw[s][["Open", "High", "Low", "Close", "Volume"]].dropna()
                    if len(sub) >= MIN_BARS:
                        out[s] = sub
                except Exception:
                    pass
        time.sleep(0.3)
    return out


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def build_frame(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c, h, l, v = d["Close"], d["High"], d["Low"], d["Volume"]
    ema5, ema20, ema50 = _ema(c, 5), _ema(c, 20), _ema(c, 50)
    d["ema100"] = _ema(c, 100)
    d["ema200"] = _ema(c, 200)
    d["ema50"] = ema50

    tenkan = (h.rolling(TENKAN).max() + l.rolling(TENKAN).min()) / 2
    kijun = (h.rolling(KIJUN).max() + l.rolling(KIJUN).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(KIJUN)
    span_b = ((h.rolling(SENKOU_B).max() + l.rolling(SENKOU_B).min()) / 2).shift(KIJUN)
    d["cloud_top"] = pd.concat([span_a, span_b], axis=1).max(axis=1)
    d["above_cloud"] = c > d["cloud_top"]

    delta = c.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
    vol_ratio = v / v.rolling(20).mean().replace(0, np.nan)
    bar_chg = c.pct_change() * 100
    bb_mid = c.rolling(20).mean()
    support = l.rolling(20).min()
    resist = h.rolling(20).max()
    near_sup = ((c - support) / c.replace(0, np.nan) * 100) <= 5.0
    breakout = (c > resist.shift(1)) & (vol_ratio >= 1.2)

    score = pd.Series(0.0, index=d.index)
    score += np.where(ema5 > ema20, np.where(ema20 > ema50, W["ema_alignment"], W["ema_alignment"] // 2), 0)
    score += np.where((rsi >= 40) & (rsi <= 70), W["rsi_health"], 0)
    score += np.where(vol_ratio >= 1.5, W["volume_spike"], np.where(vol_ratio >= 1.2, W["volume_spike"] // 2, 0))
    score += np.where(bar_chg >= 1.0, W["price_momentum"], 0)
    score += np.where(c > bb_mid, W["bollinger_position"], 0)
    score += np.where(near_sup, W["sr_proximity"], 0)
    score += np.where(breakout & (vol_ratio >= 1.5), W["breakout"], np.where(breakout, W["breakout"] // 2, 0))
    d["score"] = score.clip(upper=100)
    d["enter"] = (d["score"] >= MIN_SCORE) & d["above_cloud"].fillna(False)
    return d


def _stats(trades: list[float], equity: float, bh: float, in_mkt: int, n_bars: int, days: list[float]) -> dict:
    compound = (equity - 1) * 100
    if not trades:
        return {
            "n": 0, "win": 0.0, "avg": 0.0, "compound": 0.0,
            "buy_hold": round(bh, 2), "in_mkt": 0.0, "beats_bh": False,
            "avg_days": 0.0,
        }
    arr = np.array(trades)
    return {
        "n": len(arr),
        "win": round(float((arr > 0).mean() * 100), 1),
        "avg": round(float(arr.mean()), 2),
        "compound": round(compound, 2),
        "buy_hold": round(bh, 2),
        "in_mkt": round(100 * in_mkt / max(n_bars, 1), 1),
        "beats_bh": compound > bh,
        "avg_days": round(float(np.mean(days)), 1) if days else 0.0,
    }


def backtest_exit(df: pd.DataFrame, mode: str) -> dict:
    """mode: hard | ema200 | ema100 | protect"""
    trades: list[float] = []
    days_held: list[float] = []
    pos = None
    equity = 1.0
    in_mkt = 0
    peak = 0.0
    armed = False

    for i, row in df.iterrows():
        px = float(row["Close"])
        if pos is None:
            if bool(row["enter"]) and pd.notna(row.get("cloud_top")):
                pos = {"date": i, "px": px}
                peak = px
                armed = False
            continue

        in_mkt += 1
        peak = max(peak, px)
        entry = pos["px"]
        ret = (px - entry) / entry
        reason = None

        if mode == "hard":
            if px <= entry * (1 - HARD_STOP):
                reason = "hard_-15%"
            # also take profit? no — only hard invalidation; need another way to exit winners
            # For pure hard-stop-only you'd never sell winners — add optional time? 
            # Better: hard stop OR close below EMA200 as secondary for this mode? 
            # User said zorunlu = their rule. For winners without rule, use weekly-style:
            # exit if from peak drawdown > 25% after +20% (wide). Keep simple:
            # hard -15% OR (after +25% peak, give back to +10% from entry = lock some)
            if ret >= 0.25 and px <= entry * 1.10:
                reason = "hard_lock_+10"
            # If never hits, exit at end — handled after loop skip; force exit if below cloud for months?
            # Add: if held and close < ema200 as soft — NO keep pure
            # Actually without winner exit, open positions inflate. Close at end MTM in stats.
            # Mid-test: exit if dd from peak >= 30% (catastrophic giveback)
            if peak > entry and (peak - px) / peak >= 0.30:
                reason = "hard_peak_dd30"

        elif mode == "ema200":
            ema = row["ema200"]
            if pd.notna(ema) and px < float(ema):
                reason = "ema200"

        elif mode == "ema100":
            ema = row["ema100"]
            if pd.notna(ema) and px < float(ema):
                reason = "ema100"

        elif mode == "protect":
            if px <= entry * (1 - PROTECT_HARD):
                reason = "hard_-20%"
            else:
                if ret >= PROTECT_ARM:
                    armed = True
                if armed:
                    stop = max(entry, peak * (1 - PROTECT_TRAIL))
                    if px <= stop:
                        reason = "protect_trail_or_BE"

        if reason:
            pnl = (px - entry) / entry
            equity *= 1 + pnl
            trades.append(pnl * 100)
            try:
                days_held.append(float((i - pos["date"]).days))
            except Exception:
                days_held.append(0.0)
            pos = None

    # Mark open pos to last close
    if pos is not None:
        px = float(df["Close"].iloc[-1])
        pnl = (px - pos["px"]) / pos["px"]
        equity *= 1 + pnl
        trades.append(pnl * 100)
        days_held.append(0.0)

    bh = (float(df["Close"].iloc[-1]) / float(df["Close"].iloc[0]) - 1) * 100
    return _stats(trades, equity, bh, in_mkt, len(df), days_held)


def big_winner_stats(results: pd.DataFrame, data: dict[str, pd.DataFrame], mode: str) -> dict:
    bh = sorted(
        ((s, float(df["Close"].iloc[-1] / df["Close"].iloc[0] - 1) * 100) for s, df in data.items()),
        key=lambda x: x[1],
        reverse=True,
    )
    n_top = max(1, int(len(bh) * 0.10))
    winners = {s for s, _ in bh[:n_top]}
    sub = results[(results["mode"] == mode) & (results["symbol"].isin(winners))]
    return {
        "top_n": n_top,
        "med_compound": round(float(sub["compound"].median()), 2) if len(sub) else 0,
        "med_bh": round(float(sub["buy_hold"].median()), 2) if len(sub) else 0,
        "pct_beat": round(100 * float(sub["beats_bh"].mean()), 1) if len(sub) else 0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stocks-limit", type=int, default=None)
    ap.add_argument("--out", default=str(ROOT / "backtest/radar_exit_scenarios.csv"))
    args = ap.parse_args()

    modes = ("hard", "ema100", "ema200", "protect")
    stocks = load_stocks(args.stocks_limit)

    print("=" * 72)
    print("EXIT SCENARIO TEST — same entry, different exits")
    print("  ENTRY: score>=65 + daily cloud top")
    print("  A hard    : −15% zorunlu (+ peak DD30 / lock)")
    print("  B ema100  : trend çıkış EMA100")
    print("  C ema200  : trend çıkış EMA200 (daha geniş)")
    print("  D protect : +12% olunca BE+trail %10, hard −20%")
    print(f"  stocks={len(stocks)}  period={PERIOD}")
    print("=" * 72)

    t0 = time.time()
    data = batch_download(stocks)
    print(f"Downloaded {len(data)}/{len(stocks)}\n")

    rows = []
    for i, (sym, raw) in enumerate(data.items(), 1):
        if i % 50 == 0:
            print(f"  backtest {i}/{len(data)}…", flush=True)
        try:
            frame = build_frame(raw)
            bh = (float(raw["Close"].iloc[-1]) / float(raw["Close"].iloc[0]) - 1) * 100
            for mode in modes:
                r = backtest_exit(frame, mode)
                r["symbol"] = sym
                r["mode"] = mode
                r["buy_hold"] = round(bh, 2)
                r["beats_bh"] = r["compound"] > bh
                rows.append(r)
        except Exception:
            pass

    df = pd.DataFrame(rows)
    Path(args.out).write_text(df.to_csv(index=False))

    print("\n" + "=" * 72)
    print("ÖZET — hangisi hem genel kâr hem trend?")
    print("=" * 72)
    print(f"{'mode':10s} {'med_strat%':>10s} {'med_tut%':>10s} {'beat_tut%':>10s} "
          f"{'med_trades':>10s} {'med_win%':>9s} {'med_days':>9s}")

    summary_rows = []
    for mode in modes:
        g = df[df["mode"] == mode]
        big = big_winner_stats(df, data, mode)
        line = {
            "mode": mode,
            "med_compound": round(float(g["compound"].median()), 2),
            "med_bh": round(float(g["buy_hold"].median()), 2),
            "pct_beat_bh": round(100 * float(g["beats_bh"].mean()), 1),
            "med_trades": round(float(g["n"].median()), 1),
            "med_win": round(float(g["win"].median()), 1),
            "med_days": round(float(g["avg_days"].median()), 1),
            "big_med_compound": big["med_compound"],
            "big_med_bh": big["med_bh"],
            "big_pct_beat": big["pct_beat"],
        }
        summary_rows.append(line)
        print(
            f"{mode:10s} {line['med_compound']:10.1f} {line['med_bh']:10.1f} "
            f"{line['pct_beat_bh']:9.1f}% {line['med_trades']:10.1f} "
            f"{line['med_win']:8.1f}% {line['med_days']:8.1f}"
        )

    print("\n--- En iyi %10 hisse (büyük yükselenler) üzerinde ---")
    print(f"{'mode':10s} {'strat_med%':>10s} {'tut_med%':>10s} {'beat%':>8s}")
    for line in summary_rows:
        print(
            f"{line['mode']:10s} {line['big_med_compound']:10.1f} "
            f"{line['big_med_bh']:10.1f} {line['big_pct_beat']:7.1f}%"
        )

    # Winner by pct beat BH overall, then by med compound
    best = max(summary_rows, key=lambda x: (x["pct_beat_bh"], x["med_compound"]))
    best_big = max(summary_rows, key=lambda x: (x["big_pct_beat"], x["big_med_compound"]))

    print("\n--- Düz yorum ---")
    print(f"  Genel (tutmaktan iyi çıkan %): en iyi → {best['mode']}")
    print(f"  Büyük yükselenlerde: en iyi → {best_big['mode']}")
    print(
        "  hard = zorunlu stop proxy (−15%). "
        "ema100/200 = trend çıkış. "
        "protect = +12% sonrası kâr koruma."
    )
    print(f"\nCSV → {args.out}")
    print(f"Done {time.time()-t0:.0f}s\n")


if __name__ == "__main__":
    main()
