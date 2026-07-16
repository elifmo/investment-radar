"""
USA scan universe — merge S&P 500, Nasdaq-100, and watchlist extras.

Used by the main pipeline (candidates + oversold). Heatmap still uses sp500.yaml
directly via sp500_universe.load_sp500_universe().
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from sp500_universe import load_sp500_universe, normalize_ticker

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent.parent / "config"
_NASDAQ_CONFIG = _CONFIG_DIR / "nasdaq100.yaml"
_UNIVERSE_CONFIG = _CONFIG_DIR / "universe.yaml"


def load_nasdaq100_universe(config_path: Path | None = None) -> list[dict]:
    """Return [{ticker, sector?}, ...] from config/nasdaq100.yaml."""
    path = config_path or _NASDAQ_CONFIG
    if not path.exists():
        raise FileNotFoundError(
            f"Nasdaq-100 config missing: {path}\n"
            "Run: python3 scripts/refresh_nasdaq100_universe.py"
        )
    raw = yaml.safe_load(path.read_text()) or {}
    entries = raw.get("nasdaq100") or []
    return [
        {
            "ticker": normalize_ticker(e["ticker"]),
            "sector": e.get("sector", "Unknown"),
        }
        for e in entries
        if e.get("ticker")
    ]


def load_watchlist_extras() -> list[dict]:
    """Tickers in universe.yaml that are not index members (ARM, TSM, etc.)."""
    raw = yaml.safe_load(_UNIVERSE_CONFIG.read_text()) or {}
    return [
        {
            "ticker": normalize_ticker(e["ticker"]),
            "sector": e.get("sector", "Unknown"),
        }
        for e in (raw.get("usa") or [])
        if isinstance(e, dict) and e.get("ticker")
    ]


def merge_universe_entries(*groups: list[dict]) -> list[dict]:
    """Deduplicate by ticker; first non-Unknown sector wins."""
    by_ticker: dict[str, dict] = {}
    for group in groups:
        for entry in group:
            ticker = entry["ticker"]
            sector = entry.get("sector") or "Unknown"
            if ticker not in by_ticker:
                by_ticker[ticker] = {"ticker": ticker, "sector": sector}
            elif by_ticker[ticker]["sector"] == "Unknown" and sector != "Unknown":
                by_ticker[ticker]["sector"] = sector
    return sorted(by_ticker.values(), key=lambda e: e["ticker"])


def load_usa_scan_universe(mode: str = "sp500_nasdaq") -> list[dict]:
    """
    Resolve USA tickers for pipeline scanning.

    Modes:
      watchlist     — config/universe.yaml only (~175)
      sp500         — S&P 500 only (~503)
      sp500_nasdaq  — S&P 500 + Nasdaq-100 + watchlist extras (~520)
    """
    mode = (mode or "sp500_nasdaq").strip().lower()

    if mode == "watchlist":
        entries = load_watchlist_extras()
        logger.info("USA scan universe: watchlist (%d tickers)", len(entries))
        return entries

    sp500 = load_sp500_universe()

    if mode == "sp500":
        entries = merge_universe_entries(sp500)
        logger.info("USA scan universe: S&P 500 (%d tickers)", len(entries))
        return entries

    if mode == "sp500_nasdaq":
        nasdaq = load_nasdaq100_universe()
        extras = load_watchlist_extras()
        sp500_tickers = {e["ticker"] for e in sp500}
        nasdaq_only = [e for e in nasdaq if e["ticker"] not in sp500_tickers]
        extras_only = [e for e in extras if e["ticker"] not in sp500_tickers
                       and e["ticker"] not in {e["ticker"] for e in nasdaq}]
        entries = merge_universe_entries(sp500, nasdaq_only, extras_only)
        logger.info(
            "USA scan universe: S&P 500 + Nasdaq extras + watchlist "
            "(%d = %d + %d + %d)",
            len(entries), len(sp500), len(nasdaq_only), len(extras_only),
        )
        return entries

    raise ValueError(f"Unknown USA scan universe mode: {mode!r}")
