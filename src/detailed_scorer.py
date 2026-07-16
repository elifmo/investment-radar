import logging

import pandas as pd

from ta_engine import Timeframe, analyze_ticker

logger = logging.getLogger(__name__)

_DEFAULT_WEIGHTS = {
    "ema_alignment": 20,
    "rsi_health": 15,
    "volume_spike": 20,
    "price_momentum": 15,
    "bollinger_position": 10,
    "sr_proximity": 10,
    "breakout": 10,
}

# Minimum bar-over-bar gain to award price_momentum points
_MOMENTUM_PCT = {"daily": 1.0, "4h": 0.75, "1h": 0.5}


def score_ticker(
    ticker: str,
    df: pd.DataFrame,
    weights: dict | None = None,
    timeframe: Timeframe = "daily",
) -> tuple[int, list[str]]:
    """Score a ticker 0-100 based on TA indicators.

    Returns (score, signals_list).
    """
    w = weights or _DEFAULT_WEIGHTS
    analysis = analyze_ticker(ticker, df, timeframe)

    if analysis["error"] or not analysis["indicators"]:
        logger.warning("Cannot score %s (%s): %s", ticker, timeframe, analysis.get("error"))
        return 0, []

    ind = analysis["indicators"]
    score = 0
    signals: list[str] = []
    bar_label = "4H bar" if timeframe == "4h" else "bar" if timeframe == "1h" else "today"

    # EMA alignment
    ema = ind["ema"]
    if ema["ema5"] > ema["ema20"] > ema["ema50"]:
        score += w["ema_alignment"]
        signals.append("✅ EMA fully aligned (5>20>50)")
    elif ema["ema5"] > ema["ema20"]:
        score += w["ema_alignment"] // 2
        signals.append("✅ EMA5 > EMA20 (short-term momentum)")

    # RSI health (daily and 4h only)
    rsi = ind["rsi"]
    if rsi:
        rv = rsi["value"]
        if 40 <= rv <= 70:
            score += w["rsi_health"]
            signals.append(f"✅ RSI {rv:.0f} = Healthy")
        elif rv < 35:
            signals.append(f"⚠️ RSI {rv:.0f} = Oversold (bounce possible)")
        elif rv > 80:
            signals.append(f"❌ RSI {rv:.0f} = Overheated")

    # Volume spike
    vol = ind["volume"]
    if vol["volume_ratio"] >= 1.5:
        score += w["volume_spike"]
        signals.append(f"✅ Volume {vol['volume_ratio']:.1f}x average")
    elif vol["volume_ratio"] >= 1.2:
        score += w["volume_spike"] // 2
        signals.append(f"⚠️ Volume {vol['volume_ratio']:.1f}x (moderate)")

    # Price momentum (last bar vs previous bar)
    close = ind["latest_close"]
    prev_close = float(df["Close"].iloc[-2])
    mom_pct = _MOMENTUM_PCT.get(timeframe, 1.0)
    if prev_close > 0:
        bar_chg = (close - prev_close) / prev_close * 100
        if bar_chg >= mom_pct:
            score += w["price_momentum"]
            signals.append(f"✅ Price +{bar_chg:.1f}% ({bar_label})")
        elif bar_chg <= -1.5:
            signals.append(f"❌ Price {bar_chg:.1f}% ({bar_label})")

    # Bollinger position
    bb = ind["bollinger"]
    if close > bb["middle"]:
        score += w["bollinger_position"]
        signals.append("✅ Price above BB midline")

    # Support proximity (within 5%)
    sr = ind["support_resistance"]
    if sr["price_vs_support_pct"] <= 5.0:
        score += w["sr_proximity"]
        signals.append(f"✅ Near support ({sr['nearest_support']:.2f})")

    # Breakout
    if analysis["is_breakout"] and ind["breakout"]["volume_confirmed"]:
        score += w["breakout"]
        signals.append(f"✅ Volume-confirmed breakout above {sr['nearest_resistance']:.2f}")
    elif analysis["is_breakout"]:
        score += w["breakout"] // 2
        signals.append("⚠️ Breakout (low volume — watch closely)")

    return min(score, 100), signals


def score_all(
    triggered_tickers: list[str],
    ohlcv_data: dict[str, pd.DataFrame],
    weights: dict | None = None,
    timeframe: Timeframe = "daily",
) -> list[dict]:
    """Score all triggered tickers. Returns list sorted by score descending."""
    scored = []
    for ticker in triggered_tickers:
        df = ohlcv_data.get(ticker)
        if df is None:
            continue
        try:
            score, signals = score_ticker(ticker, df, weights, timeframe)
            ind = analyze_ticker(ticker, df, timeframe)["indicators"]
            stoch = ind.get("stochastic") if ind else None
            scored.append({
                "ticker": ticker,
                "score": score,
                "signals": signals,
                "close":      round(float(df["Close"].iloc[-1]), 2),
                "support":    ind["support_resistance"]["nearest_support"] if ind else None,
                "resistance": ind["support_resistance"]["nearest_resistance"] if ind else None,
                "volume_ratio": round(ind["volume"]["volume_ratio"], 2) if ind else None,
                "rsi": round(ind["rsi"]["value"], 1) if ind and ind["rsi"] else None,
                "stoch_k": round(stoch["k"], 1) if stoch else None,
                "stoch_d": round(stoch["d"], 1) if stoch else None,
                "timeframe": timeframe,
            })
        except Exception as exc:
            logger.error("Scoring failed for %s (%s): %s", ticker, timeframe, exc)

    return sorted(scored, key=lambda x: x["score"], reverse=True)
