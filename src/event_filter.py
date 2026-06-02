import logging
from typing import TypedDict

import pandas as pd

from ta_engine import calculate_rsi, calculate_support_resistance

logger = logging.getLogger(__name__)


class EventResult(TypedDict):
    ticker: str
    market: str
    triggers: list[str]
    triggered: bool


# ── Individual event detectors ─────────────────────────────────────────────────


def detect_volume_spike(df: pd.DataFrame, threshold: float = 1.5) -> bool:
    avg_vol = df["Volume"].rolling(20).mean().iloc[-1]
    if avg_vol <= 0:
        return False
    return bool(df["Volume"].iloc[-1] > avg_vol * threshold)


def detect_ema_crossover(df: pd.DataFrame) -> bool:
    """EMA5 crossed above EMA20 in the last 2 bars (fresh crossover)."""
    if len(df) < 22:
        return False
    e5  = df["Close"].ewm(span=5,  adjust=False).mean()
    e20 = df["Close"].ewm(span=20, adjust=False).mean()
    return bool(e5.iloc[-2] <= e20.iloc[-2] and e5.iloc[-1] > e20.iloc[-1])


def detect_rsi_bounce(df: pd.DataFrame, oversold: float = 35, lookback: int = 5) -> bool:
    """RSI was below oversold within last N bars and is now rising."""
    if len(df) < 20:
        return False
    rsi = calculate_rsi(df["Close"])
    recent_rsi = rsi.iloc[-lookback:]
    return bool(recent_rsi.min() < oversold and rsi.iloc[-1] > rsi.iloc[-2])


def detect_price_move(df: pd.DataFrame, pct: float = 2.0) -> bool:
    """Today's close is more than pct% higher than yesterday's close."""
    if len(df) < 2:
        return False
    prev = float(df["Close"].iloc[-2])
    curr = float(df["Close"].iloc[-1])
    if prev <= 0:
        return False
    return bool((curr - prev) / prev * 100 >= pct)


def detect_support_proximity(df: pd.DataFrame, pct: float = 2.0) -> bool:
    """Price is within pct% of the nearest support level."""
    if len(df) < 22:
        return False
    support, _ = calculate_support_resistance(df, lookback=20)
    close = float(df["Close"].iloc[-1])
    if support <= 0:
        return False
    return bool(abs(close - support) / support * 100 <= pct)


def detect_52w_high_break(df: pd.DataFrame) -> bool:
    """Today's close exceeds the prior 52-week high (excluding today)."""
    if len(df) < 60:
        return False
    prior_high = float(df["High"].iloc[-252:-1].max()) if len(df) >= 252 else float(df["High"].iloc[:-1].max())
    return bool(float(df["Close"].iloc[-1]) > prior_high)


# ── Main filter ────────────────────────────────────────────────────────────────


def run_event_filter(
    daily_data: dict[str, pd.DataFrame],
    market: str,
    volume_threshold: float = 1.5,
    price_move_pct: float = 2.0,
    rsi_oversold: float = 35,
    rsi_lookback: int = 5,
    support_prox_pct: float = 2.0,
) -> list[EventResult]:
    """Scan all tickers for meaningful events. Returns only those that triggered."""
    results: list[EventResult] = []

    for ticker, df in daily_data.items():
        triggers: list[str] = []
        try:
            if detect_volume_spike(df, volume_threshold):
                triggers.append("volume_spike")
            if detect_ema_crossover(df):
                triggers.append("ema_crossover")
            if detect_rsi_bounce(df, rsi_oversold, rsi_lookback):
                triggers.append("rsi_bounce")
            if detect_price_move(df, price_move_pct):
                triggers.append("price_move")
            if detect_support_proximity(df, support_prox_pct):
                triggers.append("support_proximity")
            if detect_52w_high_break(df):
                triggers.append("52w_high_break")
        except Exception as exc:
            logger.warning("Event filter failed for %s: %s", ticker, exc)
            continue

        if triggers:
            results.append(EventResult(
                ticker=ticker,
                market=market,
                triggers=triggers,
                triggered=True,
            ))
            logger.info("%s [%s]: %s", ticker, market, ", ".join(triggers))

    logger.info("Event filter: %d / %d tickers triggered", len(results), len(daily_data))
    return results


# ── Standalone test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from data_fetcher import fetch_batch_daily

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    usa_tickers  = ["MSFT", "NVDA", "AAPL", "TSLA", "GOOGL"]
    bist_tickers = ["FROTO.IS", "ASELS.IS", "TUPRS.IS", "EREGL.IS", "AKBNK.IS"]

    logger.info("=== USA ===")
    usa_data = fetch_batch_daily(usa_tickers)
    usa_events = run_event_filter(usa_data, "USA")
    for e in usa_events:
        print(f"  {e['ticker']:12s}  triggers: {e['triggers']}")

    logger.info("=== BIST ===")
    bist_data = fetch_batch_daily(bist_tickers)
    bist_events = run_event_filter(bist_data, "BIST")
    for e in bist_events:
        print(f"  {e['ticker']:12s}  triggers: {e['triggers']}")

    if not usa_events and not bist_events:
        print("\nNo events triggered today. Market may be quiet.")
