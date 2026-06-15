"""
Task 3 — Sector Rotation Engine (weekly)

Classifies 11 US sector ETFs as Leading / Improving / Weakening / Lagging
on two time windows, and maps each ticker to its sector's status.
"""

import logging
from datetime import date

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

SECTOR_ETFS = {
    "Technology":             "XLK",
    "Financials":             "XLF",
    "Health Care":            "XLV",
    "Consumer Discretionary": "XLY",
    "Consumer Staples":       "XLP",
    "Industrials":            "XLI",
    "Energy":                 "XLE",
    "Materials":              "XLB",
    "Utilities":              "XLU",
    "Real Estate":            "XLRE",
    "Communication Services": "XLC",
}

ETF_TO_SECTOR = {v: k for k, v in SECTOR_ETFS.items()}


def _classify(rs: float, momentum: float) -> str:
    if rs > 0 and momentum > 0:
        return "LEADING"
    if rs < 0 and momentum > 0:
        return "IMPROVING"
    if rs > 0 and momentum < 0:
        return "WEAKENING"
    return "LAGGING"


def _compute_status(
    etf_close: pd.Series,
    spy_close: pd.Series,
    short_window: int = 20,
    short_mom: int = 10,
    long_window: int = 126,
    long_mom: int = 20,
) -> dict:
    """Compute short and long sector status for one ETF."""
    if len(etf_close) < long_window + long_mom + 5:
        return {
            "short_status": "LAGGING", "long_status": "LAGGING",
            "rs_short": 0.0, "rs_long": 0.0,
        }

    def rs_at(end_idx: int, window: int) -> float:
        if end_idx < window:
            return 0.0
        start_idx = end_idx - window
        etf_ret = float(etf_close.iloc[end_idx] / etf_close.iloc[start_idx] - 1)
        spy_ret = float(spy_close.iloc[end_idx] / spy_close.iloc[start_idx] - 1)
        return etf_ret - spy_ret

    n = len(etf_close) - 1  # last index

    rs_short_now  = rs_at(n, short_window)
    rs_short_prev = rs_at(n - short_mom, short_window)
    rs_long_now   = rs_at(n, long_window)
    rs_long_prev  = rs_at(n - long_mom, long_window)

    rs_short_mom = rs_short_now - rs_short_prev
    rs_long_mom  = rs_long_now  - rs_long_prev

    return {
        "short_status": _classify(rs_short_now, rs_short_mom),
        "long_status":  _classify(rs_long_now,  rs_long_mom),
        "rs_short":     round(rs_short_now, 4),
        "rs_long":      round(rs_long_now,  4),
    }


def compute_sector_rotation(
    short_window: int = 20,
    short_mom: int = 10,
    long_window: int = 126,
    long_mom: int = 20,
) -> dict[str, dict]:
    """
    Download ETF + SPY data and classify all 11 sectors.

    Returns:
        {sector_name: {etf, short_status, long_status, rs_short, rs_long, updated_at}}
    """
    today = date.today().isoformat()
    all_symbols = ["SPY"] + list(SECTOR_ETFS.values())

    try:
        raw = yf.download(
            tickers=" ".join(all_symbols),
            period="2y",
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
    except Exception as exc:
        logger.error("Sector ETF download failed: %s", exc)
        return {}

    def get_close(symbol: str) -> pd.Series | None:
        try:
            if len(all_symbols) == 1:
                return raw["Close"]
            col = raw["Close"][symbol]
            return col.dropna()
        except Exception:
            return None

    spy_close = get_close("SPY")
    if spy_close is None or len(spy_close) < long_window + long_mom + 5:
        logger.error("Insufficient SPY data for sector rotation")
        return {}

    result: dict[str, dict] = {}
    for sector, etf in SECTOR_ETFS.items():
        etf_close = get_close(etf)
        if etf_close is None or len(etf_close) < 30:
            logger.warning("Insufficient data for %s (%s)", etf, sector)
            result[sector] = {
                "sector": sector, "etf": etf,
                "short_status": "LAGGING", "long_status": "LAGGING",
                "rs_short": 0.0, "rs_long": 0.0,
                "updated_at": today,
            }
            continue

        # Align series on common dates
        combined = pd.DataFrame({"etf": etf_close, "spy": spy_close}).dropna()
        if len(combined) < 30:
            logger.warning("Aligned data too short for %s", etf)
            continue

        status = _compute_status(
            combined["etf"], combined["spy"],
            short_window, short_mom, long_window, long_mom,
        )
        result[sector] = {
            "sector": sector,
            "etf":    etf,
            **status,
            "updated_at": today,
        }
        logger.info("%s (%s): short=%s  long=%s  rs_short=%.2f%%  rs_long=%.2f%%",
                    etf, sector,
                    result[sector]["short_status"], result[sector]["long_status"],
                    result[sector]["rs_short"] * 100, result[sector]["rs_long"] * 100)

    return result
