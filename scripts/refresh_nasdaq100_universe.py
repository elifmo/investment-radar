#!/usr/bin/env python3
"""
Download Nasdaq-100 constituents → config/nasdaq100.yaml.

Usage:
  python3 scripts/refresh_nasdaq100_universe.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

import urllib.request
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sp500_universe import normalize_ticker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_JSON_URL = "https://yfiua.github.io/index-constituents/constituents-nasdaq100.json"
_OUT = Path(__file__).parent.parent / "config" / "nasdaq100.yaml"
_SP500 = Path(__file__).parent.parent / "config" / "sp500.yaml"


def _sector_from_sp500(ticker: str, sp500_sectors: dict[str, str]) -> str:
    return sp500_sectors.get(ticker, "Unknown")


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh Nasdaq-100 universe config")
    parser.parse_args()

    logger.info("Downloading Nasdaq-100 constituents...")
    req = urllib.request.Request(_JSON_URL, headers={"User-Agent": "investment-radar/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        rows = json.loads(resp.read().decode("utf-8"))

    sp500_sectors: dict[str, str] = {}
    if _SP500.exists():
        raw = yaml.safe_load(_SP500.read_text()) or {}
        for e in raw.get("sp500") or []:
            if e.get("ticker"):
                sp500_sectors[normalize_ticker(e["ticker"])] = e.get("sector", "Unknown")

    entries = []
    for row in rows:
        symbol = row.get("Symbol") or row.get("symbol")
        if not symbol:
            continue
        ticker = normalize_ticker(symbol)
        entries.append({
            "ticker": ticker,
            "sector": _sector_from_sp500(ticker, sp500_sectors),
        })

    if len(entries) < 90:
        logger.error("Expected ~100 constituents, got %d", len(entries))
        sys.exit(1)

    payload = {
        "updated_at": date.today().isoformat(),
        "source": _JSON_URL,
        "count": len(entries),
        "nasdaq100": entries,
    }
    _OUT.write_text(yaml.dump(payload, default_flow_style=False, sort_keys=False))
    logger.info("Wrote %d tickers to %s", len(entries), _OUT)


if __name__ == "__main__":
    main()
