"""
Task 2 — Relative Strength / RS Rating (daily)

Computes 1-99 percentile RS Rating for each ticker vs SPY,
based on 30-trading-day return outperformance.
"""

import logging

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def _fetch_spy(window: int = 35) -> pd.DataFrame | None:
    """Download SPY with enough history for the return window."""
    try:
        df = yf.Ticker("SPY").history(period="3mo", interval="1d")
        if df.empty or len(df) < window:
            return None
        return df
    except Exception as exc:
        logger.error("Failed to fetch SPY: %s", exc)
        return None


def compute_rs_ratings(
    daily_data: dict[str, pd.DataFrame],
    window: int = 30,
    spy_df: pd.DataFrame | None = None,
) -> dict[str, dict]:
    """
    Compute RS Rating (1-99) for each ticker in daily_data.

    Args:
        daily_data: {ticker: ohlcv_df} already fetched
        window:     trading-day look-back for return (default 30)
        spy_df:     pre-fetched SPY DataFrame (fetched here if None)

    Returns:
        {ticker: {rs_rating, return_30d, spy_return_30d}}
    """
    if spy_df is None:
        spy_df = _fetch_spy(window + 5)

    if spy_df is None or len(spy_df) < window + 1:
        logger.warning("SPY data insufficient — RS ratings skipped")
        return {}

    spy_close = spy_df["Close"]
    spy_return = float(spy_close.iloc[-1] / spy_close.iloc[-(window + 1)] - 1)

    # Compute relative performance for each ticker
    perf: dict[str, dict] = {}
    for ticker, df in daily_data.items():
        if df is None or len(df) < window + 1:
            continue
        try:
            close = df["Close"]
            ticker_return = float(close.iloc[-1] / close.iloc[-(window + 1)] - 1)
            rel_perf = ticker_return - spy_return
            perf[ticker] = {
                "rel_perf":       rel_perf,
                "return_30d":     round(ticker_return, 4),
                "spy_return_30d": round(spy_return, 4),
            }
        except Exception as exc:
            logger.debug("RS calc failed for %s: %s", ticker, exc)

    if len(perf) < 2:
        logger.warning("Too few tickers for RS percentile ranking (%d)", len(perf))
        return {t: {**v, "rs_rating": 50} for t, v in perf.items()}

    # Percentile-rank relative performance → 1-99
    series = pd.Series({t: v["rel_perf"] for t, v in perf.items()})
    pct_ranks = series.rank(pct=True)  # values in (0, 1]

    result: dict[str, dict] = {}
    for ticker, pct in pct_ranks.items():
        rs = max(1, min(99, round(pct * 98 + 1)))
        result[ticker] = {
            "rs_rating":      int(rs),
            "return_30d":     perf[ticker]["return_30d"],
            "spy_return_30d": perf[ticker]["spy_return_30d"],
        }

    logger.info("RS ratings computed for %d tickers (SPY 30d: %.1f%%)",
                len(result), spy_return * 100)
    return result
