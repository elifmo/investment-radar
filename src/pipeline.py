"""
Investment Radar — Main Pipeline

Usage:
  python pipeline.py usa
  python pipeline.py bist
  python pipeline.py all
"""

import logging
import sys
from pathlib import Path

import yaml

from data_fetcher import fetch_batch_daily
from event_filter import run_event_filter
from detailed_scorer import score_all
from firebase_writer import init_firebase, write_daily_candidates

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_config() -> tuple[dict, dict]:
    universe = yaml.safe_load((_CONFIG_DIR / "universe.yaml").read_text())
    factors  = yaml.safe_load((_CONFIG_DIR / "factors.yaml").read_text())
    return universe, factors


def run_market(market: str, tickers: list[str], factors: dict) -> list[dict]:
    min_score = factors.get("min_score", 65)
    weights   = factors.get("weights", {})
    thresh    = factors.get("thresholds", {})

    logger.info("── %s pipeline: %d tickers ──", market.upper(), len(tickers))

    # Step 1: Fetch data
    logger.info("[1/3] Fetching daily data...")
    daily_data = fetch_batch_daily(tickers)
    logger.info("  Fetched: %d / %d tickers", len(daily_data), len(tickers))

    # Step 2: Event filter
    logger.info("[2/3] Running event filter...")
    events = run_event_filter(
        daily_data,
        market=market.upper(),
        volume_threshold=thresh.get("volume_spike_ratio", 1.5),
        price_move_pct=thresh.get("price_move_pct", 2.0),
        rsi_oversold=thresh.get("rsi_oversold", 35),
        rsi_lookback=thresh.get("rsi_bounce_lookback", 5),
        support_prox_pct=thresh.get("support_proximity_pct", 2.0),
    )
    triggered_tickers = [e["ticker"] for e in events]
    trigger_map       = {e["ticker"]: e["triggers"] for e in events}
    logger.info("  Triggered: %d / %d", len(triggered_tickers), len(daily_data))

    if not triggered_tickers:
        logger.info("  No events detected for %s today.", market.upper())
        return []

    # Step 3: Score triggered tickers
    logger.info("[3/3] Scoring %d triggered tickers...", len(triggered_tickers))
    scored = score_all(triggered_tickers, daily_data, weights)

    # Filter by minimum score and take top 10
    candidates = [
        {
            **c,
            "market":    market.upper(),
            "triggers":  trigger_map.get(c["ticker"], []),
            "why_today": _build_why(c, trigger_map.get(c["ticker"], [])),
        }
        for c in scored
        if c["score"] >= min_score
    ][:10]

    logger.info("  Final candidates: %d (min_score=%d)", len(candidates), min_score)
    for c in candidates:
        logger.info("  %s — score=%d  why=%s", c["ticker"], c["score"], c["why_today"])

    return candidates


def _build_why(candidate: dict, triggers: list[str]) -> str:
    parts = []
    if candidate.get("score", 0) >= 80:
        parts.append("Strong setup")
    if "volume_spike" in triggers:
        ratio = candidate.get("volume_ratio")
        parts.append(f"Volume {ratio:.1f}x" if ratio else "Volume spike")
    if "ema_crossover" in triggers:
        parts.append("EMA crossover")
    if "rsi_bounce" in triggers:
        parts.append("RSI bounce")
    if "52w_high_break" in triggers:
        parts.append("52-week high break")
    if "price_move" in triggers:
        parts.append("Price surge")
    if "support_proximity" in triggers:
        parts.append("Near support")
    return ", ".join(parts) if parts else ", ".join(triggers).replace("_", " ")


def run(market_arg: str) -> None:
    universe, factors = load_config()

    markets = ["usa", "bist"] if market_arg == "all" else [market_arg.lower()]

    db = init_firebase()

    for market in markets:
        tickers = universe.get(market)
        if not tickers:
            logger.error("No tickers found for market '%s' in universe.yaml", market)
            continue

        candidates = run_market(market, tickers, factors)
        write_daily_candidates(db, candidates, market)

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    market = sys.argv[1] if len(sys.argv) > 1 else "usa"
    if market not in ("usa", "bist", "all"):
        logger.error("Usage: python pipeline.py [usa|bist|all]")
        sys.exit(1)
    run(market)
