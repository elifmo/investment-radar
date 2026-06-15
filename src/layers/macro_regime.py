"""
Task 4 — Macro Regime Indicator (daily)

Combines 10Y Treasury yield trend and DXY trend (smoothed with 5-day MA)
into a single Risk-On / Risk-Off / Neutral regime flag.
"""

import logging
from datetime import date

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_TICKERS = {"tnx": "^TNX", "dxy": "DX-Y.NYB"}


def _fetch_macro_series(trend_window: int, smooth_window: int) -> dict[str, pd.Series] | None:
    needed = trend_window + smooth_window + 10
    result = {}
    for name, symbol in _TICKERS.items():
        try:
            df = yf.Ticker(symbol).history(period="6mo", interval="1d")
            if df.empty or len(df) < needed:
                logger.warning("%s has insufficient data (%d rows)", symbol, len(df))
                return None
            result[name] = df["Close"]
        except Exception as exc:
            logger.error("Failed to fetch %s: %s", symbol, exc)
            return None
    return result


def compute_macro_regime(
    trend_window: int = 20,
    smooth_window: int = 5,
) -> dict:
    """
    Compute macro regime from TNX and DXY trends.

    Returns:
        {regime, tnx_trend_20d, dxy_trend_20d, updated_at}
    """
    today = date.today().isoformat()
    default = {
        "regime": "NEUTRAL",
        "tnx_trend_20d": 0.0,
        "dxy_trend_20d": 0.0,
        "updated_at": today,
    }

    series = _fetch_macro_series(trend_window, smooth_window)
    if series is None:
        logger.warning("Macro regime defaulting to NEUTRAL (data unavailable)")
        return default

    def smoothed_trend(s: pd.Series) -> float:
        """Compute smooth 20-day trend: rolling (close - close[20d ago]), then 5-day MA."""
        trend_series = s - s.shift(trend_window)
        smoothed = trend_series.rolling(smooth_window).mean()
        val = smoothed.dropna()
        return float(val.iloc[-1]) if not val.empty else 0.0

    tnx_close = series["tnx"]
    dxy_close  = series["dxy"]

    tnx_trend = smoothed_trend(tnx_close)
    dxy_trend  = smoothed_trend(dxy_close)

    # Raw 20d trend for reporting
    tnx_raw = float(tnx_close.iloc[-1] - tnx_close.iloc[-(trend_window + 1)])
    dxy_raw  = float(dxy_close.iloc[-1] - dxy_close.iloc[-(trend_window + 1)])

    score = 0
    score += -1 if tnx_trend > 0 else 1   # rising yield = headwind
    score += -1 if dxy_trend > 0 else 1   # rising dollar = headwind

    regime = "RISK_ON" if score >= 1 else "RISK_OFF" if score <= -1 else "NEUTRAL"

    result = {
        "regime":        regime,
        "tnx_trend_20d": round(tnx_raw, 4),
        "dxy_trend_20d": round(dxy_raw, 4),
        "tnx_smoothed":  round(tnx_trend, 4),
        "dxy_smoothed":  round(dxy_trend, 4),
        "score":         score,
        "updated_at":    today,
    }
    logger.info("Macro regime: %s (score=%d, TNX 20d=%.3f, DXY 20d=%.3f)",
                regime, score, tnx_raw, dxy_raw)
    return result
