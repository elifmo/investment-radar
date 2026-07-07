"""
S&P 500 universe — load tickers + GICS sectors for full-index heatmap.

Source: public constituents CSV (refreshed via scripts/refresh_sp500_universe.py).
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import yaml

from layers.sector_rotation import SECTOR_ETFS

logger = logging.getLogger(__name__)

_CONFIG = Path(__file__).parent.parent / "config" / "sp500.yaml"
_CSV_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/"
    "master/data/constituents.csv"
)

# Wikipedia / dataset GICS labels → our 11 SPDR sector names
_GICS_TO_SECTOR = {
    "Information Technology": "Technology",
    "Health Care":            "Health Care",
    "Financials":             "Financials",
    "Consumer Discretionary": "Consumer Discretionary",
    "Consumer Staples":       "Consumer Staples",
    "Industrials":            "Industrials",
    "Energy":                 "Energy",
    "Materials":              "Materials",
    "Utilities":              "Utilities",
    "Real Estate":            "Real Estate",
    "Communication Services": "Communication Services",
}


def normalize_ticker(symbol: str) -> str:
    """Yahoo Finance uses BRK-B not BRK.B."""
    return symbol.strip().upper().replace(".", "-")


def normalize_sector(gics: str) -> str:
    sector = _GICS_TO_SECTOR.get(gics.strip())
    if not sector:
        logger.warning("Unknown GICS sector %r — using Unknown", gics)
        return "Unknown"
    return sector


def load_sp500_universe(config_path: Path | None = None) -> list[dict]:
    """Return [{ticker, sector, market_cap?}, ...] from config/sp500.yaml."""
    path = config_path or _CONFIG
    if not path.exists():
        raise FileNotFoundError(
            f"S&P 500 config missing: {path}\n"
            "Run: python3 scripts/refresh_sp500_universe.py"
        )
    raw = yaml.safe_load(path.read_text()) or {}
    entries = raw.get("sp500") or []
    return [
        {
            "ticker": normalize_ticker(e["ticker"]),
            "sector": e.get("sector", "Unknown"),
            "market_cap": e.get("market_cap"),
        }
        for e in entries
        if e.get("ticker")
    ]


def parse_constituents_csv(text: str) -> list[dict]:
    """Parse S&P 500 constituents CSV into universe entries."""
    rows: list[dict] = []
    reader = csv.DictReader(text.splitlines())
    for row in reader:
        symbol = row.get("Symbol") or row.get("symbol")
        gics = row.get("GICS Sector") or row.get("gics sector") or ""
        if not symbol:
            continue
        rows.append({
            "ticker": normalize_ticker(symbol),
            "sector": normalize_sector(gics),
        })
    return rows


def caps_from_universe(universe: list[dict]) -> dict[str, float]:
    """Extract pre-cached market caps from universe entries."""
    caps: dict[str, float] = {}
    for e in universe:
        cap = e.get("market_cap")
        if cap and cap > 0:
            caps[e["ticker"]] = float(cap)
    return caps
