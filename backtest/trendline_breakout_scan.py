#!/usr/bin/env python3
"""Scan universe for auto trendline breakouts on daily bars."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data_fetcher import fetch_batch_daily
from layers.trendline_breakout import detect_trendline_breakout
from usa_universe import load_usa_scan_universe


def main() -> None:
    entries = load_usa_scan_universe("sp500_nasdaq")
    sector_map = {e["ticker"]: e.get("sector", "") for e in entries}
    tickers = list(sector_map.keys())
    print(f"Scanning {len(tickers)} tickers for auto trendline breakouts...\n")

    daily = fetch_batch_daily(tickers, period="1y", chunk_size=80)
    bull: list[dict] = []
    bear: list[dict] = []

    for ticker, df in daily.items():
        result = detect_trendline_breakout(df)
        if result is None:
            continue
        row = {
            "ticker": ticker,
            "sector": sector_map.get(ticker, ""),
            **result.__dict__,
        }
        if result.signal == "BULL_BREAKOUT":
            bull.append(row)
        else:
            bear.append(row)

    bull.sort(key=lambda x: x["break_pct"], reverse=True)
    bear.sort(key=lambda x: x["break_pct"], reverse=True)

    bar_date = ""
    if daily:
        any_df = next(iter(daily.values()))
        bar_date = str(any_df.dropna().index[-1].date())

    print(f"Bar date: {bar_date}")
    print(f"BULL breakouts (descending resistance): {len(bull)}")
    print(f"BEAR breakouts (ascending support):     {len(bear)}\n")

    def show(title: str, rows: list[dict], limit: int = 25) -> None:
        print("=" * 88)
        print(title)
        print("=" * 88)
        for r in rows[:limit]:
            print(
                f"{r['ticker']:6}  ${r['close']:8.2f}  line ${r['line_level']:8.2f}  "
                f"break +{r['break_pct']:.2f}%  touches={r['touches']}  {r['sector']}"
            )
            print(f"       {r['reason']}  pivots: {', '.join(r['pivot_dates'])}")
        if len(rows) > limit:
            print(f"... +{len(rows) - limit} more")
        print()

    show("BULL — Auto trendline breakout (yukari)", bull)
    show("BEAR — Auto trendline breakdown (asagi)", bear)


if __name__ == "__main__":
    main()
