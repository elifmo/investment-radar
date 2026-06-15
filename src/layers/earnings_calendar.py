"""
Task 5 — Earnings Calendar Integration

Fetches next earnings date for each ticker and computes days_to_earnings.
Uses yfinance ticker.calendar (reliable for US tickers).
"""

import logging
from datetime import date

import yfinance as yf

logger = logging.getLogger(__name__)


def get_earnings_calendar(tickers: list[str]) -> dict[str, int | None]:
    """
    Compute days until next earnings for each ticker.

    Returns:
        {ticker: days_to_earnings}  — None if no upcoming date available
    """
    today = date.today()
    result: dict[str, int | None] = {}

    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            cal = t.calendar

            # calendar can be a dict or DataFrame depending on yfinance version
            earnings_date = None
            if isinstance(cal, dict):
                raw = cal.get("Earnings Date")
                if raw:
                    # Can be a list of timestamps or a single value
                    if isinstance(raw, (list, tuple)) and raw:
                        earnings_date = raw[0]
                    else:
                        earnings_date = raw
            elif hasattr(cal, "loc"):
                # DataFrame format: row index "Earnings Date"
                try:
                    raw = cal.loc["Earnings Date"]
                    earnings_date = raw.iloc[0] if hasattr(raw, "iloc") else raw
                except (KeyError, IndexError):
                    pass

            if earnings_date is not None:
                # Normalize to date
                if hasattr(earnings_date, "date"):
                    earnings_date = earnings_date.date()
                elif isinstance(earnings_date, str):
                    from datetime import datetime
                    earnings_date = datetime.fromisoformat(earnings_date).date()

                delta = (earnings_date - today).days
                result[ticker] = delta if delta >= 0 else None
            else:
                result[ticker] = None
        except Exception as exc:
            logger.debug("Earnings calendar failed for %s: %s", ticker, exc)
            result[ticker] = None

    found = sum(1 for v in result.values() if v is not None)
    logger.info("Earnings calendar: %d / %d tickers have upcoming dates", found, len(tickers))
    return result
