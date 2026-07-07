#!/usr/bin/env python3
"""
Download S&P 500 constituents + optional market caps → config/sp500.yaml.

Usage:
  python3 scripts/refresh_sp500_universe.py
  python3 scripts/refresh_sp500_universe.py --skip-caps   # faster, caps filled on next pipeline run
"""

from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import urllib.request
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sp500_universe import _CSV_URL, parse_constituents_csv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_OUT = Path(__file__).parent.parent / "config" / "sp500.yaml"


def _fetch_caps(tickers: list[str], workers: int = 16) -> dict[str, float]:
    import yfinance as yf

    caps: dict[str, float] = {}

    def one(ticker: str) -> tuple[str, float | None]:
        try:
            fi = getattr(yf.Ticker(ticker), "fast_info", None)
            cap = None
            if fi is not None:
                cap = fi.get("market_cap") or fi.get("marketCap")
            if not cap:
                cap = (yf.Ticker(ticker).info or {}).get("marketCap")
            return ticker, float(cap) if cap and cap > 0 else None
        except Exception:
            return ticker, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, t): t for t in tickers}
        done = 0
        for fut in as_completed(futures):
            ticker, cap = fut.result()
            if cap:
                caps[ticker] = cap
            done += 1
            if done % 50 == 0:
                logger.info("  Market caps: %d / %d", done, len(tickers))

    logger.info("Fetched market caps for %d / %d tickers", len(caps), len(tickers))
    return caps


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh S&P 500 universe config")
    parser.add_argument("--skip-caps", action="store_true", help="Skip market-cap fetch")
    args = parser.parse_args()

    logger.info("Downloading S&P 500 constituents...")
    with urllib.request.urlopen(_CSV_URL, timeout=60) as resp:
        text = resp.read().decode("utf-8")

    entries = parse_constituents_csv(text)
    if len(entries) < 400:
        logger.error("Expected ~500 constituents, got %d", len(entries))
        sys.exit(1)

    tickers = [e["ticker"] for e in entries]
    if not args.skip_caps:
        caps = _fetch_caps(tickers)
        for e in entries:
            if e["ticker"] in caps:
                e["market_cap"] = int(caps[e["ticker"]])

    payload = {
        "updated_at": date.today().isoformat(),
        "source": _CSV_URL,
        "count": len(entries),
        "sp500": entries,
    }
    _OUT.write_text(yaml.dump(payload, default_flow_style=False, sort_keys=False))
    logger.info("Wrote %d tickers to %s", len(entries), _OUT)


if __name__ == "__main__":
    main()
