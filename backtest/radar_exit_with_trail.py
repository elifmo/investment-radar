"""
Exit comparison + TRAIL

ENTRY: score >= 65 AND daily cloud top

EXITS:
  ema100 / ema200
  be_10 / be_15 / be_20     — +X% olunca stop=alis; alisina donunce sat
  trail_10 / trail_15 / trail_20 — zirveden %X dusunce sat (trail)

  python3 backtest/radar_exit_with_trail.py
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

MODES = (
    "ema100",
    "ema200",
    "be_10",
    "be_15",
    "be_20",
    "trail_10",
    "trail_15",
    "trail_20",
)

LABELS = {
    "ema100": "EMA100 alti sat",
    "ema200": "EMA200 alti sat",
    "be_10": "Alisa stop: +%10 olunca stop=alis",
    "be_15": "Alisa stop: +%15 olunca stop=alis",
    "be_20": "Alisa stop: +%20 olunca stop=alis",
    "trail_10": "Trail: zirveden %10 dusunce sat",
    "trail_15": "Trail: zirveden %15 dusunce sat",
    "trail_20": "Trail: zirveden %20 dusunce sat",
}


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

    tenkan = (h.rolling(TENKAN).max() + l.rolling(TENKAN).min()) / 2
    kijun = (h.rolling(KIJUN).max() + l.rolling(KIJUN).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(KIJUN)
    span_b = ((h.rolling(SENKOU_B).max() + l.rolling(SENKOU_B).min()) / 2).shift(KIJUN)
    cloud_top = pd.concat([span_a, span_b], axis=1).max(axis=1)
    d["above_cloud"] = c > cloud_top

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


def backtest(df: pd.DataFrame, mode: str) -> dict:
    trades: list[float] = []
    days_list: list[float] = []
    pos = None
    equity = 1.0
    in_mkt = 0
    peak = 0.0
    be_armed = False

    be_arm = {"be_10": 0.10, "be_15": 0.15, "be_20": 0.20}.get(mode)
    trail_pct = {"trail_10": 0.10, "trail_15": 0.15, "trail_20": 0.20}.get(mode)

    for i, row in df.iterrows():
        px = float(row["Close"])
        if pos is None:
            if bool(row["enter"]):
                pos = {"date": i, "px": px}
                peak = px
                be_armed = False
            continue

        in_mkt += 1
        peak = max(peak, px)
        entry = pos["px"]
        ret = (px - entry) / entry
        exit_now = False

        if mode == "ema100":
            ema = row["ema100"]
            exit_now = pd.notna(ema) and px < float(ema)
        elif mode == "ema200":
            ema = row["ema200"]
            exit_now = pd.notna(ema) and px < float(ema)
        elif be_arm is not None:
            if ret >= be_arm:
                be_armed = True
            if be_armed and px <= entry:
                exit_now = True
        elif trail_pct is not None:
            # Trail: sat if drop from peak >= trail_pct
            if peak > 0 and (peak - px) / peak >= trail_pct:
                exit_now = True

        if exit_now:
            pnl = (px - entry) / entry
            equity *= 1 + pnl
            trades.append(pnl * 100)
            try:
                days_list.append(float((i - pos["date"]).days))
            except Exception:
                days_list.append(0.0)
            pos = None

    if pos is not None:
        px = float(df["Close"].iloc[-1])
        pnl = (px - pos["px"]) / pos["px"]
        equity *= 1 + pnl
        trades.append(pnl * 100)
        try:
            days_list.append(float((df.index[-1] - pos["date"]).days))
        except Exception:
            pass

    bh = (float(df["Close"].iloc[-1]) / float(df["Close"].iloc[0]) - 1) * 100
    compound = (equity - 1) * 100
    if not trades:
        return {
            "n": 0, "win": 0.0, "compound": 0.0, "buy_hold": round(bh, 2),
            "beats_bh": False, "avg_days": 0.0, "in_mkt": 0.0,
        }
    arr = np.array(trades)
    return {
        "n": len(arr),
        "win": round(float((arr > 0).mean() * 100), 1),
        "compound": round(compound, 2),
        "buy_hold": round(bh, 2),
        "beats_bh": compound > bh,
        "avg_days": round(float(np.mean(days_list)), 1) if days_list else 0.0,
        "in_mkt": round(100 * in_mkt / max(len(df), 1), 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stocks-limit", type=int, default=None)
    ap.add_argument("--out", default=str(ROOT / "backtest/radar_exit_with_trail.csv"))
    args = ap.parse_args()

    stocks = load_stocks(args.stocks_limit)
    print("=" * 70)
    print("AL: skor>=65 + gunluk bulut ustu")
    print("SAT secenekleri:")
    for m in MODES:
        print(f"  - {LABELS[m]}")
    print("Trail = zirve fiyattan %X dusunce sat (ornek: 100→150→135 ise %10 trail satar)")
    print(f"hisse={len(stocks)}  2y")
    print("=" * 70)

    t0 = time.time()
    data = batch_download(stocks)
    print(f"indirdi {len(data)}/{len(stocks)}\n")

    rows = []
    for i, (sym, raw) in enumerate(data.items(), 1):
        if i % 50 == 0:
            print(f"  {i}/{len(data)}…", flush=True)
        try:
            frame = build_frame(raw)
            for mode in MODES:
                r = backtest(frame, mode)
                r["symbol"] = sym
                r["mode"] = mode
                rows.append(r)
        except Exception:
            pass

    df = pd.DataFrame(rows)
    Path(args.out).write_text(df.to_csv(index=False))

    bh_rank = sorted(
        ((s, float(d["Close"].iloc[-1] / d["Close"].iloc[0] - 1) * 100) for s, d in data.items()),
        key=lambda x: x[1],
        reverse=True,
    )
    top = {s for s, _ in bh_rank[: max(1, int(len(bh_rank) * 0.10))]}

    print("\n1000€ ile tipik hisse (ortadan) + buyuk yukselenler:\n")
    for mode in MODES:
        g = df[df["mode"] == mode]
        med_s = float(g["compound"].median())
        med_t = float(g["buy_hold"].median())
        beat = 100 * float(g["beats_bh"].mean())
        big = g[g["symbol"].isin(top)]
        big_s = float(big["compound"].median()) if len(big) else 0
        big_t = float(big["buy_hold"].median()) if len(big) else 0
        print(f"--- {LABELS[mode]} ---")
        print(f"  Tipik: kural ~{1000*(1+med_s/100):.0f}€ | tut ~{1000*(1+med_t/100):.0f}€ | {beat:.0f}/100 tutmaktan iyi")
        print(f"  Buyuk yukselen %10: kural ~{1000*(1+big_s/100):.0f}€ | tut ~{1000*(1+big_t/100):.0f}€")
        print(f"  islem~{g['n'].median():.0f}  tutma~{g['avg_days'].median():.0f}g  win%{g['win'].median():.0f}")
        print()

    print(f"CSV → {args.out}")
    print(f"bitti {time.time()-t0:.0f}s\n")


if __name__ == "__main__":
    main()
