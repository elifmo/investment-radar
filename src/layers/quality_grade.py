"""
Task 1 — Quality Grade Module (weekly)

Assigns A/B/C/D grade to each US ticker based on:
- Net income trend (last 2 quarters)
- Debt-to-equity vs sector median
"""

import logging
from datetime import date

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def _get_net_income_trend(ticker_obj) -> str:
    """Return 'growing', 'flat', or 'declining' based on last 2 quarters."""
    try:
        fin = ticker_obj.quarterly_financials
        if fin is None or fin.empty:
            return "flat"

        # Find Net Income row (key varies by yfinance version)
        ni_row = None
        for key in ["Net Income", "Net Income From Continuing Operations", "Net Income Common Stockholders"]:
            if key in fin.index:
                ni_row = fin.loc[key]
                break
        if ni_row is None:
            return "flat"

        ni_row = ni_row.dropna()
        if len(ni_row) < 2:
            return "flat"

        # Most recent quarter is the first column
        ni_recent = float(ni_row.iloc[0])
        ni_prior  = float(ni_row.iloc[1])

        if ni_prior == 0:
            return "flat"
        change = (ni_recent - ni_prior) / abs(ni_prior)
        if change > 0.03:
            return "growing"
        if change < -0.03:
            return "declining"
        return "flat"
    except Exception as exc:
        logger.debug("Net income trend failed: %s", exc)
        return "flat"


def _get_consecutive_decline(ticker_obj) -> bool:
    """True if net income declined for 2+ consecutive quarters."""
    try:
        fin = ticker_obj.quarterly_financials
        if fin is None or fin.empty:
            return False
        ni_row = None
        for key in ["Net Income", "Net Income From Continuing Operations", "Net Income Common Stockholders"]:
            if key in fin.index:
                ni_row = fin.loc[key]
                break
        if ni_row is None:
            return False

        ni_row = ni_row.dropna()
        if len(ni_row) < 3:
            return False

        q0 = float(ni_row.iloc[0])  # most recent
        q1 = float(ni_row.iloc[1])
        q2 = float(ni_row.iloc[2])
        return q0 < q1 and q1 < q2
    except Exception:
        return False


def _get_debt_to_equity(ticker_obj) -> float | None:
    """Return most recent quarter D/E ratio, or None on failure."""
    try:
        bs = ticker_obj.quarterly_balance_sheet
        if bs is None or bs.empty:
            return None

        total_debt = None
        for key in ["Total Debt", "Long Term Debt", "Long Term Debt And Capital Lease Obligation"]:
            if key in bs.index:
                row = bs.loc[key].dropna()
                if not row.empty:
                    total_debt = float(row.iloc[0])
                    break

        total_equity = None
        for key in ["Stockholders Equity", "Total Stockholders Equity", "Common Stock Equity"]:
            if key in bs.index:
                row = bs.loc[key].dropna()
                if not row.empty:
                    total_equity = float(row.iloc[0])
                    break

        if total_debt is None or total_equity is None or total_equity <= 0:
            return None
        return total_debt / total_equity
    except Exception as exc:
        logger.debug("D/E fetch failed: %s", exc)
        return None


def _is_de_rising(ticker_obj) -> bool:
    """True if D/E increased from 2 quarters ago to most recent."""
    try:
        bs = ticker_obj.quarterly_balance_sheet
        if bs is None or bs.empty:
            return False

        debt_row = equity_row = None
        for key in ["Total Debt", "Long Term Debt"]:
            if key in bs.index:
                debt_row = bs.loc[key].dropna()
                break
        for key in ["Stockholders Equity", "Total Stockholders Equity", "Common Stock Equity"]:
            if key in bs.index:
                equity_row = bs.loc[key].dropna()
                break

        if debt_row is None or equity_row is None or len(debt_row) < 2 or len(equity_row) < 2:
            return False

        de_recent = float(debt_row.iloc[0]) / max(float(equity_row.iloc[0]), 1)
        de_prior  = float(debt_row.iloc[1]) / max(float(equity_row.iloc[1]), 1)
        return de_recent > de_prior
    except Exception:
        return False


def _assign_grade(ni_trend: str, de_ratio: float | None, sector_median_de: float,
                  consecutive_decline: bool, de_rising: bool) -> str:
    if de_ratio is None:
        de_ratio = sector_median_de

    if consecutive_decline and de_rising:
        return "D"
    if ni_trend == "declining" or de_ratio > sector_median_de * 1.5:
        return "C"
    if ni_trend == "growing" and de_ratio < sector_median_de * 1.0:
        return "A"
    if ni_trend in ("growing", "flat") and de_ratio < sector_median_de * 1.5:
        return "B"
    return "C"


def compute_quality_grades(
    tickers: list[str],
    sector_map: dict[str, str],
) -> dict[str, dict]:
    """
    Compute A/B/C/D quality grade for each ticker.

    Returns:
        {ticker: {grade, net_income_trend, debt_to_equity, updated_at}}
    """
    today = date.today().isoformat()

    # Step 1: fetch D/E and NI trend for all tickers
    raw: dict[str, dict] = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            ni_trend = _get_net_income_trend(t)
            de_ratio = _get_debt_to_equity(t)
            consec   = _get_consecutive_decline(t)
            de_rising = _is_de_rising(t)
            raw[ticker] = {
                "ni_trend": ni_trend,
                "de_ratio": de_ratio,
                "consec_decline": consec,
                "de_rising": de_rising,
                "sector": sector_map.get(ticker, "Unknown"),
            }
        except Exception as exc:
            logger.warning("Quality data fetch failed for %s: %s", ticker, exc)
            raw[ticker] = {
                "ni_trend": "flat", "de_ratio": None,
                "consec_decline": False, "de_rising": False,
                "sector": sector_map.get(ticker, "Unknown"),
            }

    # Step 2: compute sector-median D/E
    sector_de: dict[str, list[float]] = {}
    for ticker, data in raw.items():
        sec = data["sector"]
        de  = data["de_ratio"]
        if de is not None and de > 0:
            sector_de.setdefault(sec, []).append(de)

    sector_medians: dict[str, float] = {}
    for sec, vals in sector_de.items():
        sector_medians[sec] = float(pd.Series(vals).median())

    fallback_median = float(pd.Series([v for vals in sector_de.values() for v in vals]).median()) if sector_de else 1.0

    # Step 3: assign grades
    result: dict[str, dict] = {}
    for ticker, data in raw.items():
        sec    = data["sector"]
        median = sector_medians.get(sec, fallback_median)
        grade  = _assign_grade(
            data["ni_trend"], data["de_ratio"], median,
            data["consec_decline"], data["de_rising"],
        )
        de_val = data["de_ratio"]
        result[ticker] = {
            "ticker":          ticker,
            "grade":           grade,
            "net_income_trend": data["ni_trend"],
            "debt_to_equity":  round(de_val, 3) if de_val is not None else None,
            "sector":          sec,
            "updated_at":      today,
        }
        logger.debug("%s → grade=%s  ni=%s  d/e=%.2f  median=%.2f",
                     ticker, grade, data["ni_trend"], de_val or 0, median)

    logger.info("Quality grades computed for %d tickers", len(result))
    return result
