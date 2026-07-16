"""
Oversold Watch — scan full universe for extreme RSI / Stochastic readings.

Unlike the main candidates funnel (momentum + bounce), this surfaces
limit-order territory: stocks that are oversold but may not have
started recovering yet (e.g. ORCL with Stoch 10, RSI 27).
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from ta_engine import Timeframe, analyze_ticker

logger = logging.getLogger(__name__)

_TIER_ORDER = {"deep": 0, "stoch": 1, "rsi": 2}


def scan_oversold_watch(
    tickers: list[str],
    ohlcv_data: dict[str, pd.DataFrame],
    sector_map: dict[str, str] | None = None,
    quality_grades: dict[str, dict] | None = None,
    timeframe: Timeframe = "daily",
    stoch_threshold: float = 20.0,
    rsi_threshold: float = 35.0,
    max_items: int = 15,
) -> list[dict[str, Any]]:
    """Return oversold tickers sorted deepest-first (stoch + RSI combined)."""
    sector_map = sector_map or {}
    quality_grades = quality_grades or {}
    rows: list[dict[str, Any]] = []

    for ticker in tickers:
        if ticker == "SPY":
            continue
        df = ohlcv_data.get(ticker)
        if df is None or len(df) < 25:
            continue

        try:
            analysis = analyze_ticker(ticker, df, timeframe)
            ind = analysis.get("indicators")
            if not ind:
                continue

            stoch = ind.get("stochastic")
            rsi = ind.get("rsi")
            stoch_k = stoch["k"] if stoch else None
            stoch_d = stoch["d"] if stoch else None
            rsi_val = rsi["value"] if rsi else None

            stoch_hit = stoch_k is not None and stoch_k < stoch_threshold
            rsi_hit = rsi_val is not None and rsi_val < rsi_threshold
            if not (stoch_hit or rsi_hit):
                continue

            if stoch_hit and rsi_hit:
                tier = "deep"
            elif stoch_hit:
                tier = "stoch"
            else:
                tier = "rsi"

            sr = ind["support_resistance"]
            grade_info = quality_grades.get(ticker, {})
            grade = grade_info.get("grade")

            rows.append({
                "ticker": ticker,
                "close": round(ind["latest_close"], 2),
                "stoch_k": round(stoch_k, 1) if stoch_k is not None else None,
                "stoch_d": round(stoch_d, 1) if stoch_d is not None else None,
                "rsi": round(rsi_val, 1) if rsi_val is not None else None,
                "tier": tier,
                "support": round(sr["nearest_support"], 2),
                "resistance": round(sr["nearest_resistance"], 2),
                "sector": sector_map.get(ticker),
                "quality_grade": grade,
                "timeframe": timeframe,
            })
        except Exception as exc:
            logger.debug("Oversold scan failed for %s: %s", ticker, exc)

    rows.sort(
        key=lambda r: (
            _TIER_ORDER.get(r["tier"], 9),
            r["stoch_k"] if r["stoch_k"] is not None else 100,
            r["rsi"] if r["rsi"] is not None else 100,
        ),
    )
    result = rows[:max_items]
    logger.info(
        "Oversold watch: %d / %d tickers (showing %d)",
        len(rows), len(tickers), len(result),
    )
    return result
