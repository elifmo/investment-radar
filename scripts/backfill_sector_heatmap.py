#!/usr/bin/env python3
"""
Backfill historical sector heatmap snapshots to Firestore.

Usage:
  python3 scripts/backfill_sector_heatmap.py              # last 30 trading days
  python3 scripts/backfill_sector_heatmap.py --days 252  # ~1 year of snapshots
  python3 scripts/backfill_sector_heatmap.py --days 10
  python3 scripts/backfill_sector_heatmap.py --date 2026-07-03
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data_fetcher import fetch_batch_daily
from firebase_writer import init_firebase, write_sector_heatmap
from layers.sector_heatmap import (
    _fetch_market_caps,
    compute_sector_heatmap,
    list_trading_days,
    merge_heatmap_payload,
)
from market_calendar import resolve_usa_snapshot_date
from sp500_universe import caps_from_universe, load_sp500_universe

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_CONFIG = Path(__file__).parent.parent / "config" / "universe.yaml"


def _last_weekday(weekday: int) -> str:
    """Return ISO date of the most recent weekday (0=Mon … 3=Thu)."""
    d = date.today()
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d.isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill sector heatmap history")
    parser.add_argument("--days", type=int, default=30, help="Trading days to backfill")
    parser.add_argument("--date", type=str, help="Single date YYYY-MM-DD")
    parser.add_argument("--last-thursday", action="store_true", help="Backfill last Thursday only")
    args = parser.parse_args()

    universe = yaml.safe_load(_CONFIG.read_text()).get("usa") or []
    if not universe:
        logger.error("No USA tickers in universe.yaml")
        sys.exit(1)

    tickers = [e["ticker"] for e in universe]
    sp500_univ = load_sp500_universe()
    sp500_tickers = [e["ticker"] for e in sp500_univ]

    logger.info("Fetching watchlist daily data (%d tickers, regular close)...", len(tickers))
    daily_data = fetch_batch_daily(tickers, auto_adjust=False)
    logger.info("Fetched %d / %d watchlist tickers", len(daily_data), len(tickers))

    logger.info("Fetching S&P 500 daily data (%d tickers, regular close)...", len(sp500_tickers))
    sp500_data = fetch_batch_daily(sp500_tickers, auto_adjust=False)
    logger.info("Fetched %d / %d S&P 500 tickers", len(sp500_data), len(sp500_tickers))

    ref_data = sp500_data if len(sp500_data) >= len(daily_data) else daily_data
    if args.last_thursday:
        target_dates = [_last_weekday(3)]
    elif args.date:
        target_dates = [args.date]
    else:
        target_dates = list_trading_days(ref_data, lookback=args.days)

    if not target_dates:
        logger.error("No trading days found to backfill")
        sys.exit(1)

    logger.info("Backfilling %d day(s): %s … %s", len(target_dates), target_dates[0], target_dates[-1])
    wl_caps = _fetch_market_caps(tickers)
    sp500_caps = caps_from_universe(sp500_univ)
    if len(sp500_caps) < len(sp500_univ) // 2:
        sp500_caps = _fetch_market_caps(sp500_tickers, cached=sp500_caps)

    latest_day = target_dates[-1]
    db = init_firebase()

    for day in target_dates:
        store_sp500_stocks = day == latest_day
        wl = compute_sector_heatmap(
            universe, daily_data, as_of_date=day, market_caps=wl_caps,
        )
        sp = compute_sector_heatmap(
            sp500_univ, sp500_data, as_of_date=day, market_caps=sp500_caps,
            include_stocks=store_sp500_stocks, include_benchmarks=False,
        )
        heatmap = merge_heatmap_payload(wl, sp, store_sp500_stocks=store_sp500_stocks)
        if not heatmap.get("stocks") and not heatmap.get("sectors"):
            logger.warning("Skipping %s — no data", day)
            continue
        write_sector_heatmap(db, heatmap, trade_date=day)

    logger.info("Backfill complete.")


if __name__ == "__main__":
    main()
