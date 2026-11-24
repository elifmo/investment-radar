"""
Ichimoku universe scan — 4 scenarios × Bitcoin / ETF / All stocks

Scenarios:
  1d_ichi_rsi   — daily Ichimoku + RSI divergence
  1d_ichi       — daily Ichimoku only
  4h_ichi_rsi   — 4h Ichimoku + RSI divergence
  4h_ichi       — 4h Ichimoku only

Universes:
  bitcoin — BTC-USD, ETH-USD
  etf     — config/etfs.yaml + SPY/QQQ/IWM
  stock   — SP500 ∪ config/universe.yaml USA (~511)

Yahoo: 1d → 2y; 4h → ~60d max.

  python3 backtest/ichimoku_universe_scan.py
  python3 backtest/ichimoku_universe_scan.py --stocks-limit 80
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
TENKAN, KIJUN, SENKOU_B = 9, 26, 52
RSI_N, RSI_OB = 14, 70
PERIOD_1D, PERIOD_4H = "2y", "60d"
SCENARIOS = ("1d_ichi_rsi", "1d_ichi", "4h_ichi_rsi", "4h_ichi")
MIN_BARS = SENKOU_B + KIJUN + 15


def load_universes(stocks_limit: int | None = None) -> dict[str, list[str]]:
    sp = yaml.safe_load((ROOT / "config/sp500.yaml").read_text())
    uni = yaml.safe_load((ROOT / "config/universe.yaml").read_text())
    etf = yaml.safe_load((ROOT / "config/etfs.yaml").read_text())
    stocks = sorted({x["ticker"] for x in sp["sp500"]} | {x["ticker"] for x in uni["usa"]})
    if stocks_limit:
        stocks = stocks[:stocks_limit]
    etfs = [x["ticker"] for x in etf["etfs"]]
    for t in ("SPY", "QQQ", "IWM"):
        if t not in etfs:
            etfs.append(t)
    return {"bitcoin": ["BTC-USD", "ETH-USD"], "etf": etfs, "stock": stocks}


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        # single-ticker multiindex from batch sometimes
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    cols = ["Open", "High", "Low", "Close", "Volume"]
    if any(c not in df.columns for c in cols):
        return None
    out = df[cols].dropna()
    return out if len(out) >= MIN_BARS else None


def batch_download(symbols: list[str], interval: str, period: str) -> dict[str, pd.DataFrame]:
    """Download in chunks; return {symbol: ohlcv}."""
    out: dict[str, pd.DataFrame] = {}
    chunk = 40
    for i in range(0, len(symbols), chunk):
        part = symbols[i : i + chunk]
        print(f"  download {interval} {i+1}-{i+len(part)}/{len(symbols)}…", flush=True)
        try:
            raw = yf.download(
                part,
                interval=interval,
                period=period,
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
        except Exception as exc:
            print(f"    batch fail ({exc}); falling back one-by-one")
            for s in part:
                try:
                    one = yf.download(s, interval=interval, period=period, auto_adjust=True, progress=False)
                    norm = _normalize_ohlcv(one)
                    if norm is not None:
                        out[s] = norm
                except Exception:
                    pass
            continue

        if len(part) == 1:
            s = part[0]
            norm = _normalize_ohlcv(raw)
            if norm is not None:
                out[s] = norm
            continue

        # Multi-ticker: columns MultiIndex (ticker, field)
        if isinstance(raw.columns, pd.MultiIndex):
            tickers = raw.columns.get_level_values(0).unique()
            for s in part:
                if s not in tickers:
                    continue
                try:
                    sub = raw[s]
                    norm = _normalize_ohlcv(sub)
                    if norm is not None:
                        out[s] = norm
                except Exception:
                    pass
        time.sleep(0.4)
    return out


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    hi, lo, close = df["High"], df["Low"], df["Close"]
    df["tenkan"] = (hi.rolling(TENKAN).max() + lo.rolling(TENKAN).min()) / 2
    df["kijun"] = (hi.rolling(KIJUN).max() + lo.rolling(KIJUN).min()) / 2
    df["span_a"] = ((df["tenkan"] + df["kijun"]) / 2).shift(KIJUN)
    df["span_b"] = ((hi.rolling(SENKOU_B).max() + lo.rolling(SENKOU_B).min()) / 2).shift(KIJUN)
    df["cloud_top"] = df[["span_a", "span_b"]].max(axis=1)
    df["cloud_bottom"] = df[["span_a", "span_b"]].min(axis=1)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(RSI_N).mean()
    loss = (-delta.clip(upper=0)).rolling(RSI_N).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    return df


def add_divergence(df: pd.DataFrame, lookback: int = 5) -> pd.DataFrame:
    df = df.copy()
    n = len(df)
    bear = np.zeros(n, dtype=bool)
    bull = np.zeros(n, dtype=bool)
    close = df["Close"].to_numpy(float)
    rsi = df["rsi"].to_numpy(float)
    lb = lookback
    for i in range(lb * 2, n):
        w1c, w0c = close[i - lb : i], close[i - lb * 2 : i - lb]
        w1r, w0r = rsi[i - lb : i], rsi[i - lb * 2 : i - lb]
        if np.isnan(w1r).any() or np.isnan(w0r).any():
            continue
        if w1c.max() > w0c.max() and w1r.max() < w0r.max():
            bear[i] = True
        if w1c.min() < w0c.min() and w1r.min() > w0r.min():
            bull[i] = True
    df["bearish_div"] = bear
    df["bullish_div"] = bull
    return df


def generate_signals(df: pd.DataFrame, use_rsi_div: bool) -> pd.DataFrame:
    df = df.copy()
    n = len(df)
    signal = np.array([None] * n, dtype=object)
    case = np.array([None] * n, dtype=object)
    close = df["Close"].to_numpy(float)
    tenkan = df["tenkan"].to_numpy(float)
    kijun = df["kijun"].to_numpy(float)
    ctop = df["cloud_top"].to_numpy(float)
    cbot = df["cloud_bottom"].to_numpy(float)
    rsi = df["rsi"].to_numpy(float)
    bear = df["bearish_div"].to_numpy(bool) if "bearish_div" in df.columns else np.zeros(n, bool)
    bull = df["bullish_div"].to_numpy(bool) if "bullish_div" in df.columns else np.zeros(n, bool)

    for i in range(1, n):
        if np.isnan(tenkan[i]) or np.isnan(kijun[i]) or np.isnan(ctop[i]) or np.isnan(cbot[i]):
            continue
        price = close[i]
        tk_up = tenkan[i - 1] <= kijun[i - 1] and tenkan[i] > kijun[i]
        tk_dn = tenkan[i - 1] >= kijun[i - 1] and tenkan[i] < kijun[i]
        above = price > ctop[i]
        below = price < cbot[i]
        in_cloud = cbot[i] <= price <= ctop[i]

        if above and tk_up and (np.isnan(rsi[i]) or rsi[i] < RSI_OB):
            signal[i], case[i] = "BUY", "Case1"
        elif below and tk_dn:
            signal[i], case[i] = "SELL", "Case2"
        elif above and abs(price - kijun[i]) / max(abs(kijun[i]), 1e-9) < 0.005 and (
            np.isnan(rsi[i]) or rsi[i] > 40
        ):
            signal[i], case[i] = "BUY", "Case3"
        elif (not np.isnan(ctop[i - 1])) and close[i - 1] < ctop[i - 1] and price > ctop[i]:
            signal[i], case[i] = "BUY", "Case4"
        elif in_cloud:
            signal[i], case[i] = "WAIT", "Case5"

        if use_rsi_div:
            if bear[i] and above:
                signal[i], case[i] = "EXIT", "RSI_Bear"
            if bull[i] and below:
                signal[i], case[i] = "WATCH", "RSI_Bull"

    df["signal"] = signal
    df["case"] = case
    return df


def backtest(df: pd.DataFrame) -> dict:
    trades: list[float] = []
    pos = None
    equity = 1.0
    in_mkt = 0
    for _, row in df.iterrows():
        px = float(row["Close"])
        cbot = row["cloud_bottom"]
        below = bool(pd.notna(cbot) and px < float(cbot))
        sig = row["signal"]
        if pos is None:
            if sig == "BUY":
                pos = {"px": px}
            continue
        in_mkt += 1
        if below or sig in ("SELL", "EXIT"):
            pnl = (px - pos["px"]) / pos["px"]
            equity *= 1 + pnl
            trades.append(pnl * 100)
            pos = None
    bh = (float(df["Close"].iloc[-1]) / float(df["Close"].iloc[0]) - 1) * 100
    compound = (equity - 1) * 100
    if not trades:
        return {
            "n": 0,
            "win": 0.0,
            "avg": 0.0,
            "compound": 0.0,
            "buy_hold": round(bh, 2),
            "in_mkt": 0.0,
            "beats_bh": False,
            "ok": True,
        }
    arr = np.array(trades)
    return {
        "n": len(arr),
        "win": round(float((arr > 0).mean() * 100), 1),
        "avg": round(float(arr.mean()), 2),
        "compound": round(compound, 2),
        "buy_hold": round(bh, 2),
        "in_mkt": round(100 * in_mkt / max(len(df), 1), 1),
        "beats_bh": compound > bh,
        "ok": True,
    }


def eval_symbol(symbol: str, ohlcv: pd.DataFrame, scenario: str) -> dict:
    use_rsi = scenario.endswith("_rsi")
    df = add_indicators(ohlcv)
    if use_rsi:
        df = add_divergence(df)
    else:
        df = df.copy()
        df["bearish_div"] = False
        df["bullish_div"] = False
    df = generate_signals(df, use_rsi_div=use_rsi)
    out = backtest(df)
    out.update({"symbol": symbol, "scenario": scenario, "bars": len(df)})
    return out


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (bucket, scenario), g in df.groupby(["bucket", "scenario"]):
        ok = g[g["ok"] == True]  # noqa: E712
        if ok.empty:
            continue
        wt = ok[ok["n"] > 0]
        rows.append(
            {
                "bucket": bucket,
                "scenario": scenario,
                "tickers": len(ok),
                "with_trades": len(wt),
                "med_compound%": round(float(ok["compound"].median()), 2),
                "avg_compound%": round(float(ok["compound"].mean()), 2),
                "med_buyhold%": round(float(ok["buy_hold"].median()), 2),
                "pct_beat_bh": round(100 * float(ok["beats_bh"].mean()), 1),
                "med_trades": round(float(ok["n"].median()), 1),
                "med_win%": round(float(wt["win"].median()), 1) if len(wt) else 0.0,
                "med_in_mkt%": round(float(ok["in_mkt"].median()), 1),
            }
        )
    return pd.DataFrame(rows).sort_values(["bucket", "scenario"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stocks-limit", type=int, default=None)
    ap.add_argument("--out", default=str(ROOT / "backtest/ichimoku_universe_results.csv"))
    args = ap.parse_args()

    universes = load_universes(args.stocks_limit)
    all_syms = sorted({s for syms in universes.values() for s in syms})
    print(
        f"Universe: bitcoin={len(universes['bitcoin'])}  "
        f"etf={len(universes['etf'])}  stock={len(universes['stock'])}  "
        f"unique={len(all_syms)}"
    )
    print(f"Scenarios: {', '.join(SCENARIOS)}")
    print(f"Periods: 1d={PERIOD_1D}  4h={PERIOD_4H}\n")

    t0 = time.time()
    print("=== Fetch 1d ===")
    data_1d = batch_download(all_syms, "1d", PERIOD_1D)
    print(f"  got {len(data_1d)}/{len(all_syms)}")
    print("=== Fetch 4h ===")
    data_4h = batch_download(all_syms, "4h", PERIOD_4H)
    print(f"  got {len(data_4h)}/{len(all_syms)}")

    # bucket lookup
    bucket_of = {}
    for b, syms in universes.items():
        for s in syms:
            bucket_of[s] = b

    rows = []
    for sym in all_syms:
        bucket = bucket_of.get(sym, "stock")
        for sc in SCENARIOS:
            src = data_4h if sc.startswith("4h") else data_1d
            if sym not in src:
                rows.append(
                    {
                        "symbol": sym,
                        "bucket": bucket,
                        "scenario": sc,
                        "ok": False,
                        "n": 0,
                        "win": 0,
                        "avg": 0,
                        "compound": 0,
                        "buy_hold": 0,
                        "in_mkt": 0,
                        "beats_bh": False,
                        "bars": 0,
                    }
                )
                continue
            try:
                r = eval_symbol(sym, src[sym], sc)
                r["bucket"] = bucket
                rows.append(r)
            except Exception:
                rows.append(
                    {
                        "symbol": sym,
                        "bucket": bucket,
                        "scenario": sc,
                        "ok": False,
                        "n": 0,
                        "win": 0,
                        "avg": 0,
                        "compound": 0,
                        "buy_hold": 0,
                        "in_mkt": 0,
                        "beats_bh": False,
                        "bars": 0,
                    }
                )

    df = pd.DataFrame(rows)
    out_path = Path(args.out)
    df.to_csv(out_path, index=False)
    summary = summarize(df)

    print("\n" + "=" * 78)
    print("SUMMARY  (median compound vs buy&hold)")
    print("=" * 78)
    print(summary.to_string(index=False))

    print("\n" + "=" * 78)
    print("BEST scenario per bucket  (highest % beating buy&hold)")
    print("=" * 78)
    for bucket in ("bitcoin", "etf", "stock"):
        sub = summary[summary["bucket"] == bucket]
        if sub.empty:
            continue
        best = sub.sort_values(["pct_beat_bh", "med_compound%"], ascending=False).iloc[0]
        print(
            f"  {bucket:8s} → {best['scenario']:14s}  "
            f"beat_BH={best['pct_beat_bh']}%  "
            f"med_compound={best['med_compound%']}% vs med_BH={best['med_buyhold%']}%  "
            f"(n={int(best['tickers'])})"
        )

    # Per-scenario stock coverage
    print("\n--- Stock coverage (ok rows) ---")
    for sc in SCENARIOS:
        g = df[(df["bucket"] == "stock") & (df["scenario"] == sc)]
        print(f"  {sc:14s}  ok={int((g['ok']==True).sum())}/{len(g)}")  # noqa: E712

    stocks = df[(df["bucket"] == "stock") & (df["scenario"] == "1d_ichi_rsi") & (df["ok"] == True)]
    if len(stocks):
        print("\n--- All-stocks 1d_ichi_rsi TOP 15 compound ---")
        print(stocks.nlargest(15, "compound")[["symbol", "compound", "buy_hold", "n", "win"]].to_string(index=False))
        print("\n--- All-stocks 1d_ichi_rsi BOTTOM 15 compound ---")
        print(stocks.nsmallest(15, "compound")[["symbol", "compound", "buy_hold", "n", "win"]].to_string(index=False))

    # Bitcoin / ETF detail tables
    for bucket in ("bitcoin", "etf"):
        print(f"\n--- {bucket.upper()} detail ---")
        sub = df[(df["bucket"] == bucket) & (df["ok"] == True)][
            ["symbol", "scenario", "compound", "buy_hold", "n", "win", "beats_bh"]
        ]
        if len(sub):
            print(sub.sort_values(["symbol", "scenario"]).to_string(index=False))

    print(f"\nCSV → {out_path}")
    print(f"Done in {time.time()-t0:.0f}s\n")


if __name__ == "__main__":
    main()
