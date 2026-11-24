"""
Ichimoku as FILTER (recommended mode) — not the main scalp engine.

Rules vs original:
  ENTER : only Case1 (strong TK cross above cloud) or Case4 (cloud breakout)
          — drop Case3 Kijun bounce spam
  EXIT  : close below cloud bottom, OR Case2 strong sell
          — no tight Kijun stop, no auto-exit on every RSI bearish div

Groups: Bitcoin | ETFs | Stocks (borsa)

  python3 backtest/ichimoku_filter_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from ichimoku_strategy import (
    INTERVAL,
    PERIOD,
    add_ichimoku,
    add_rsi,
    fetch_data,
    find_divergence,
    generate_signals,
)

# Universe by bucket
BITCOIN = ["BTC-USD", "ETH-USD"]
ETFS = [
    "SPY",
    "QQQ",
    "VUSA.AS",  # S&P 500 (Bux)
    "VHYL.AS",  # High dividend
    "SEMI.AS",  # Semiconductors
]
STOCKS = ["AAPL", "MSFT", "INTC", "RKLB", "ASTS", "NVDA"]

ALLOW_ENTRY_CASES = {"Case1_Guclu_AL", "Case4_Bulut_Kirilim"}


def backtest_filter(df: pd.DataFrame) -> dict:
    """Ichimoku confirmation filter + trend exit (below cloud)."""
    trades = []
    position = None
    equity = 1.0
    in_market_bars = 0
    total_bars = 0

    for i, row in df.iterrows():
        total_bars += 1
        price = float(row["Close"])
        case = row["case"]
        signal = row["signal"]
        below_cloud = price < float(row["cloud_bottom"]) if pd.notna(row["cloud_bottom"]) else False

        if position is None:
            if signal == "BUY" and case in ALLOW_ENTRY_CASES:
                position = {
                    "entry_date": i,
                    "entry_price": price,
                    "case": case,
                }
        else:
            in_market_bars += 1
            exit_reason = None
            if below_cloud:
                exit_reason = "Below_cloud"
            elif signal == "SELL" and case == "Case2_Guclu_SAT":
                exit_reason = "Case2_Guclu_SAT"

            if exit_reason:
                pnl = (price - position["entry_price"]) / position["entry_price"]
                equity *= 1 + pnl
                trades.append(
                    {
                        "Giriş": position["entry_date"],
                        "Çıkış": i,
                        "Giriş $": round(position["entry_price"], 2),
                        "Çıkış $": round(price, 2),
                        "PnL %": round(pnl * 100, 2),
                        "Case": position["case"],
                        "Çıkış nedeni": exit_reason,
                    }
                )
                position = None

    # Close open position at end mark-to-market (not counted as trade) — skip
    result_df = pd.DataFrame(trades)
    buy_hold = (float(df["Close"].iloc[-1]) / float(df["Close"].iloc[0]) - 1) * 100
    time_in = round(100 * in_market_bars / max(total_bars, 1), 1)

    if result_df.empty:
        return {
            "trades": result_df,
            "n": 0,
            "win_rate": 0.0,
            "avg_pnl": 0.0,
            "sum_pnl": 0.0,
            "compound": 0.0,
            "buy_hold": round(buy_hold, 2),
            "time_in_mkt": time_in,
            "beats_bh": False,
        }

    win_rate = float((result_df["PnL %"] > 0).mean() * 100)
    avg_pnl = float(result_df["PnL %"].mean())
    sum_pnl = float(result_df["PnL %"].sum())
    compound = (equity - 1) * 100

    return {
        "trades": result_df,
        "n": len(result_df),
        "win_rate": round(win_rate, 1),
        "avg_pnl": round(avg_pnl, 2),
        "sum_pnl": round(sum_pnl, 2),
        "compound": round(compound, 2),
        "buy_hold": round(buy_hold, 2),
        "time_in_mkt": time_in,
        "beats_bh": compound > buy_hold,
    }


def run_one(symbol: str) -> dict:
    df = fetch_data(symbol, INTERVAL, PERIOD)
    if df.empty or len(df) < 80:
        raise RuntimeError(f"no/short data ({len(df)})")
    df = add_ichimoku(df)
    df = add_rsi(df)
    df = find_divergence(df)
    df = generate_signals(df)
    out = backtest_filter(df)
    out["symbol"] = symbol
    return out


def run_bucket(name: str, symbols: list[str]) -> pd.DataFrame:
    rows = []
    print(f"\n{'=' * 60}")
    print(f"  {name}  |  filter mode  |  {INTERVAL} {PERIOD}")
    print(f"  Enter: Case1/Case4 only  |  Exit: below cloud / Case2")
    print(f"{'=' * 60}")
    for sym in symbols:
        try:
            r = run_one(sym)
            rows.append(
                {
                    "Symbol": r["symbol"],
                    "Trades": r["n"],
                    "Win%": r["win_rate"],
                    "Avg%": r["avg_pnl"],
                    "Compound%": r["compound"],
                    "BuyHold%": r["buy_hold"],
                    "InMkt%": r["time_in_mkt"],
                    "vs BH": "WIN" if r["beats_bh"] else "lose",
                }
            )
            print(f"\n  {sym}: trades={r['n']}  compound={r['compound']}%  "
                  f"buy&hold={r['buy_hold']}%  in-market={r['time_in_mkt']}%  "
                  f"[{'beats BH' if r['beats_bh'] else 'behind BH'}]")
            if not r["trades"].empty and len(r["trades"]) <= 12:
                print(r["trades"].to_string(index=False))
            elif not r["trades"].empty:
                print(r["trades"].tail(8).to_string(index=False))
        except Exception as exc:
            print(f"\n  FAIL {sym}: {exc}")
            rows.append(
                {
                    "Symbol": sym,
                    "Trades": 0,
                    "Win%": 0,
                    "Avg%": 0,
                    "Compound%": 0,
                    "BuyHold%": 0,
                    "InMkt%": 0,
                    "vs BH": "n/a",
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    btc = run_bucket("BITCOIN / CRYPTO", BITCOIN)
    etf = run_bucket("ETFs", ETFS)
    stk = run_bucket("BORSA (hisseler)", STOCKS)

    print("\n" + "=" * 60)
    print("ÖZET TABLOLAR")
    print("=" * 60)
    print("\n--- Bitcoin ---")
    print(btc.to_string(index=False))
    print("\n--- ETFs ---")
    print(etf.to_string(index=False))
    print("\n--- Borsa ---")
    print(stk.to_string(index=False))

    def bucket_takeaway(df: pd.DataFrame, label: str) -> str:
        ok = df[df["vs BH"] == "WIN"]
        if ok.empty:
            return f"{label}: filtre buy&hold’u geçemedi → DCA / tut + Radar exit daha mantıklı."
        return (
            f"{label}: {len(ok)}/{len(df)} isimde filtre BH’yi geçti "
            f"(ort. compound {ok['Compound%'].mean():.1f}% vs BH {ok['BuyHold%'].mean():.1f}%)."
        )

    print("\n--- Yorum ---")
    print(bucket_takeaway(btc, "Bitcoin"))
    print(bucket_takeaway(etf, "ETF"))
    print(bucket_takeaway(stk, "Borsa"))
    print()


if __name__ == "__main__":
    main()
