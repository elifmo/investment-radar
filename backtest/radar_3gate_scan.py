"""
3-gate Radar logic — 2y all-stocks backtest

Gates (as agreed):
  1) Fırsat     : TA score >= MIN_SCORE  (Radar checklist)
  2) Şimdi mi?  : Close > Ichimoku cloud top  (green light only)
  3) Çıkış      : Close < EMA50  (structural exit proxy — NOT Ichimoku/RSI noise)
                 (per-ticker written exits don't exist for 500 names)

Universe: SP500 ∪ config/universe.yaml
Period  : 2y daily

  python3 backtest/radar_3gate_scan.py
  python3 backtest/radar_3gate_scan.py --stocks-limit 80
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

# Score weights (match config/factors.yaml)
W = {
    "ema_alignment": 20,
    "rsi_health": 15,
    "volume_spike": 20,
    "price_momentum": 15,
    "bollinger_position": 10,
    "sr_proximity": 10,
    "breakout": 10,
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
                part,
                interval="1d",
                period=PERIOD,
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
        except Exception as exc:
            print(f"    batch fail: {exc}")
            continue

        if len(part) == 1:
            s = part[0]
            df = raw
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if df is not None and not df.empty and "Close" in df.columns:
                d = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
                if len(d) >= MIN_BARS:
                    out[s] = d
            continue

        if isinstance(raw.columns, pd.MultiIndex):
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
        time.sleep(0.35)
    return out


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def build_frame(df: pd.DataFrame, min_score: int = MIN_SCORE) -> pd.DataFrame:
    """Vectorized score + cloud + EMA50."""
    d = df.copy()
    c, h, l, v = d["Close"], d["High"], d["Low"], d["Volume"]

    ema5, ema20, ema50 = _ema(c, 5), _ema(c, 20), _ema(c, 50)
    d["ema50"] = ema50

    # Ichimoku cloud (current position)
    tenkan = (h.rolling(TENKAN).max() + l.rolling(TENKAN).min()) / 2
    kijun = (h.rolling(KIJUN).max() + l.rolling(KIJUN).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(KIJUN)
    span_b = ((h.rolling(SENKOU_B).max() + l.rolling(SENKOU_B).min()) / 2).shift(KIJUN)
    d["cloud_top"] = pd.concat([span_a, span_b], axis=1).max(axis=1)
    d["cloud_bottom"] = pd.concat([span_a, span_b], axis=1).min(axis=1)
    d["above_cloud"] = c > d["cloud_top"]

    # RSI
    delta = c.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    vol_ma = v.rolling(20).mean()
    vol_ratio = v / vol_ma.replace(0, np.nan)
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

    d["gate1"] = d["score"] >= min_score
    d["gate2"] = d["above_cloud"].fillna(False)
    d["enter"] = d["gate1"] & d["gate2"]
    d["exit_rule"] = c < ema50  # structural exit proxy
    return d


def backtest_symbol(df: pd.DataFrame) -> dict:
    """Long-only, one position. Enter on enter signal when flat; exit on exit_rule."""
    trades: list[dict] = []
    pos = None
    equity = 1.0
    in_mkt = 0

    for i, row in df.iterrows():
        px = float(row["Close"])
        if pos is None:
            if bool(row["enter"]) and pd.notna(row["cloud_top"]) and pd.notna(row["ema50"]):
                pos = {"date": i, "px": px, "score": float(row["score"])}
            continue

        in_mkt += 1
        if bool(row["exit_rule"]):
            pnl = (px - pos["px"]) / pos["px"]
            equity *= 1 + pnl
            trades.append(
                {
                    "entry": pos["date"],
                    "exit": i,
                    "entry_px": round(pos["px"], 2),
                    "exit_px": round(px, 2),
                    "pnl_pct": round(pnl * 100, 2),
                    "entry_score": round(pos["score"], 0),
                    "days": (i - pos["date"]).days if hasattr(i - pos["date"], "days") else None,
                }
            )
            pos = None

    bh = (float(df["Close"].iloc[-1]) / float(df["Close"].iloc[0]) - 1) * 100
    compound = (equity - 1) * 100
    if not trades:
        return {
            "ok": True,
            "n": 0,
            "win": 0.0,
            "avg": 0.0,
            "compound": 0.0,
            "buy_hold": round(bh, 2),
            "in_mkt": 0.0,
            "beats_bh": False,
            "avg_days": 0.0,
            "med_entry_score": 0.0,
        }

    pnls = np.array([t["pnl_pct"] for t in trades])
    days = [t["days"] for t in trades if t["days"] is not None]
    scores = [t["entry_score"] for t in trades]
    return {
        "ok": True,
        "n": len(trades),
        "win": round(float((pnls > 0).mean() * 100), 1),
        "avg": round(float(pnls.mean()), 2),
        "compound": round(compound, 2),
        "buy_hold": round(bh, 2),
        "in_mkt": round(100 * in_mkt / max(len(df), 1), 1),
        "beats_bh": compound > bh,
        "avg_days": round(float(np.mean(days)), 1) if days else 0.0,
        "med_entry_score": round(float(np.median(scores)), 0),
        "trades": trades,
    }


def catch_big_winners(results: pd.DataFrame, data: dict[str, pd.DataFrame], top_pct: float = 0.10) -> dict:
    """Among top buy&hold winners, how often did 3-gate enter & what share of move captured?"""
    bh = []
    for sym, df in data.items():
        ret = float(df["Close"].iloc[-1] / df["Close"].iloc[0] - 1) * 100
        bh.append((sym, ret))
    bh.sort(key=lambda x: x[1], reverse=True)
    n_top = max(1, int(len(bh) * top_pct))
    winners = {s for s, _ in bh[:n_top]}

    sub = results[results["symbol"].isin(winners) & (results["ok"] == True)]  # noqa: E712
    entered = sub[sub["n"] > 0]
    return {
        "top_n": n_top,
        "entered": int(len(entered)),
        "never_entered": int(n_top - len(entered)),
        "med_compound_on_winners": round(float(entered["compound"].median()), 2) if len(entered) else 0,
        "med_bh_on_winners": round(float(sub["buy_hold"].median()), 2) if len(sub) else 0,
        "pct_entered": round(100 * len(entered) / max(n_top, 1), 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stocks-limit", type=int, default=None)
    ap.add_argument("--min-score", type=int, default=MIN_SCORE)
    ap.add_argument("--out", default=str(ROOT / "backtest/radar_3gate_results.csv"))
    args = ap.parse_args()
    min_score = args.min_score

    stocks = load_stocks(args.stocks_limit)
    print("=" * 70)
    print("3-GATE TEST  (2y daily, ALL stocks)")
    print("  1) score >=", min_score)
    print("  2) close > Ichimoku cloud top")
    print("  3) exit when close < EMA50  (NOT ichi/RSI noise)")
    print(f"  universe={len(stocks)}")
    print("=" * 70)

    t0 = time.time()
    data = batch_download(stocks)
    print(f"Downloaded {len(data)}/{len(stocks)}\n")

    rows = []
    for i, (sym, raw) in enumerate(data.items(), 1):
        if i % 50 == 0:
            print(f"  backtest {i}/{len(data)}…", flush=True)
        try:
            frame = build_frame(raw, min_score=min_score)
            r = backtest_symbol(frame)
            r["symbol"] = sym
            r.pop("trades", None)
            r["ok"] = True
            rows.append(r)
        except Exception as exc:
            rows.append(
                {
                    "symbol": sym,
                    "ok": False,
                    "n": 0,
                    "win": 0,
                    "avg": 0,
                    "compound": 0,
                    "buy_hold": 0,
                    "in_mkt": 0,
                    "beats_bh": False,
                    "avg_days": 0,
                    "med_entry_score": 0,
                    "error": str(exc)[:80],
                }
            )

    df = pd.DataFrame(rows)
    out = Path(args.out)
    df.to_csv(out, index=False)

    ok = df[df["ok"] == True]  # noqa: E712
    with_tr = ok[ok["n"] > 0]
    big = catch_big_winners(ok, data)

    print("\n" + "=" * 70)
    print("SONUÇ — düz Türkçe")
    print("=" * 70)
    print(f"  Hisse (data var)     : {len(ok)}")
    print(f"  En az 1 trade olan  : {len(with_tr)}")
    print(f"  Ortadaki strateji    : %{ok['compound'].median():.1f}  (medyan compound)")
    print(f"  Ortadaki sadece tut  : %{ok['buy_hold'].median():.1f}")
    print(f"  Tutmaktan iyi çıkan  : %{100*ok['beats_bh'].mean():.1f}  ({int(ok['beats_bh'].sum())}/{len(ok)} hisse)")
    if len(with_tr):
        print(f"  Ort. trade sayısı    : {with_tr['n'].median():.0f}")
        print(f"  Ort. tutma süresi    : ~{with_tr['avg_days'].median():.0f} gün")
        print(f"  Kazanan trade oranı  : %{with_tr['win'].median():.0f} (medyan)")

    print("\n--- Büyük kazananlar (2y en iyi %10 hisse) ---")
    print(f"  Adet                 : {big['top_n']}")
    print(f"  Sisteme girebilen    : {big['entered']}  (%{big['pct_entered']})")
    print(f"  Hiç girememiş        : {big['never_entered']}")
    print(f"  Onlarda strateji med : %{big['med_compound_on_winners']}")
    print(f"  Onlarda tut med      : %{big['med_bh_on_winners']}")

    print("\n--- TOP 15 strateji compound ---")
    print(
        ok.nlargest(15, "compound")[
            ["symbol", "compound", "buy_hold", "n", "win", "avg_days", "beats_bh"]
        ].to_string(index=False)
    )
    print("\n--- BOTTOM 15 ---")
    print(
        ok.nsmallest(15, "compound")[
            ["symbol", "compound", "buy_hold", "n", "win", "avg_days", "beats_bh"]
        ].to_string(index=False)
    )

    print(f"\nCSV → {out}")
    print(f"Done in {time.time()-t0:.0f}s\n")


if __name__ == "__main__":
    main()
