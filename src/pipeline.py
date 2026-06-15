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
from firebase_writer import (
    init_firebase,
    write_daily_candidates,
    write_macro_regime,
    write_quality_grades,
    write_sector_status,
)
from layers.relative_strength import compute_rs_ratings
from layers.sector_rotation import compute_sector_rotation, SECTOR_ETFS
from layers.macro_regime import compute_macro_regime
from layers.earnings_calendar import get_earnings_calendar
from layers.quality_grade import compute_quality_grades
from decision_engine import decide

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


def run_market(market: str, tickers: list[str], factors: dict) -> tuple[list[dict], dict]:
    """
    Run core pipeline (fetch → event filter → score) for a market.

    Returns:
        (candidates, daily_data) — daily_data exposed so USA enrichment can reuse it.
    """
    min_score = factors.get("min_score", 65)
    weights   = factors.get("weights", {})
    thresh    = factors.get("thresholds", {})

    logger.info("── %s pipeline: %d tickers ──", market.upper(), len(tickers))

    logger.info("[1/3] Fetching daily data...")
    daily_data = fetch_batch_daily(tickers)
    logger.info("  Fetched: %d / %d tickers", len(daily_data), len(tickers))

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
        return [], daily_data

    logger.info("[3/3] Scoring %d triggered tickers...", len(triggered_tickers))
    scored = score_all(triggered_tickers, daily_data, weights)

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

    return candidates, daily_data


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


def _read_cached_quality_grades(db, tickers: list[str]) -> dict[str, dict]:
    """Read quality grades from Firestore cache. Returns what's available."""
    result = {}
    try:
        col = db.collection("quality_grades")
        for ticker in tickers:
            snap = col.document(ticker).get()
            if snap.exists:
                result[ticker] = snap.to_dict()
    except Exception as exc:
        logger.warning("Could not read quality grades from Firebase: %s", exc)
    return result


def _enrich_usa_candidates(
    candidates: list[dict],
    all_tickers: list[str],
    sector_map: dict[str, str],
    daily_data: dict,
    db,
    decision_cfg: dict,
) -> list[dict]:
    """
    Run enrichment layers (RS, Sector, Macro, Quality, Earnings) and the
    decision engine on the USA top-10 candidates.
    """
    if not candidates:
        return candidates

    rs_threshold   = float(decision_cfg.get("rs_threshold",   70))
    drop_threshold = float(decision_cfg.get("drop_threshold", -0.20))

    # ── Layer 2: RS Rating (full-universe ranking) ────────────────────────────
    logger.info("[USA] Computing RS ratings for %d tickers...", len(daily_data))
    rs_ratings = compute_rs_ratings(daily_data)

    # ── Layer 3: Sector Rotation ──────────────────────────────────────────────
    logger.info("[USA] Computing sector rotation...")
    sector_status = compute_sector_rotation(
        short_window=int(decision_cfg.get("sector_short_window",     20)),
        short_mom=   int(decision_cfg.get("sector_short_mom_window", 10)),
        long_window= int(decision_cfg.get("sector_long_window",      126)),
        long_mom=    int(decision_cfg.get("sector_long_mom_window",  20)),
    )
    if sector_status:
        try:
            write_sector_status(db, sector_status)
            logger.info("[USA] Sector status written for %d sectors.", len(sector_status))
        except Exception as exc:
            logger.warning("Could not write sector status: %s", exc)

    # ── Layer 4: Macro Regime ─────────────────────────────────────────────────
    logger.info("[USA] Computing macro regime...")
    macro = compute_macro_regime(
        trend_window= int(decision_cfg.get("macro_trend_window",  20)),
        smooth_window=int(decision_cfg.get("macro_smooth_window",  5)),
    )
    try:
        write_macro_regime(db, macro)
        logger.info("[USA] Macro regime: %s", macro.get("regime"))
    except Exception as exc:
        logger.warning("Could not write macro regime: %s", exc)

    # ── Layer 1: Quality Grades (cache-first) ─────────────────────────────────
    candidate_tickers = [c["ticker"] for c in candidates]
    grades = _read_cached_quality_grades(db, candidate_tickers)
    missing = [t for t in candidate_tickers if t not in grades]
    if missing:
        logger.info("[USA] Computing quality grades (%d uncached) against full universe...", len(missing))
        fresh = compute_quality_grades(all_tickers, sector_map)
        grades.update(fresh)
        if fresh:
            try:
                write_quality_grades(db, fresh)
            except Exception as exc:
                logger.warning("Could not write quality grades: %s", exc)
    else:
        logger.info("[USA] Quality grades loaded from Firebase cache.")

    # ── Layer 5: Earnings Calendar (candidates only) ──────────────────────────
    logger.info("[USA] Fetching earnings calendar for %d candidates...", len(candidate_tickers))
    earnings = get_earnings_calendar(candidate_tickers)

    # ── Decision Engine ───────────────────────────────────────────────────────
    enriched = []
    for c in candidates:
        ticker      = c["ticker"]
        sector_name = sector_map.get(ticker)
        sector_info = sector_status.get(sector_name, {}) if sector_name else {}
        grade_info  = grades.get(ticker, {})
        rs_info     = rs_ratings.get(ticker, {})

        enriched_c = {
            **c,
            "rs_rating":           rs_info.get("rs_rating"),
            "return_30d":          rs_info.get("return_30d"),
            "spy_return_30d":      rs_info.get("spy_return_30d"),
            "sector":              sector_name,
            "sector_short_status": sector_info.get("short_status"),
            "sector_long_status":  sector_info.get("long_status"),
            "quality_grade":       grade_info.get("grade"),
            "macro_regime":        macro.get("regime"),
            "days_to_earnings":    earnings.get(ticker),
        }

        try:
            result = decide(
                enriched_c,
                rs_threshold=rs_threshold,
                drop_threshold=drop_threshold,
            )
            enriched_c["decision"]                 = result.decision
            enriched_c["reason"]                   = result.reason
            enriched_c["position_size_multiplier"] = result.size
        except Exception as exc:
            logger.warning("Decision engine failed for %s: %s", ticker, exc)
            enriched_c["decision"]                 = "WATCH"
            enriched_c["reason"]                   = "Decision engine error — defaulting to WATCH"
            enriched_c["position_size_multiplier"] = 1.0

        logger.info(
            "  %s → decision=%-8s  rs=%s  grade=%s  sector_short=%-9s  earnings_in=%sd",
            ticker,
            enriched_c["decision"],
            enriched_c.get("rs_rating", "—"),
            enriched_c.get("quality_grade", "—"),
            enriched_c.get("sector_short_status", "—"),
            enriched_c.get("days_to_earnings", "—"),
        )
        enriched.append(enriched_c)

    return enriched


def run(market_arg: str) -> None:
    universe, factors = load_config()
    markets = ["usa", "bist"] if market_arg == "all" else [market_arg.lower()]
    db = init_firebase()

    for market in markets:
        raw_entries = universe.get(market)
        if not raw_entries:
            logger.error("No tickers found for market '%s' in universe.yaml", market)
            continue

        # universe.yaml: USA entries are {ticker, sector} dicts; BIST entries are plain strings
        if isinstance(raw_entries[0], dict):
            tickers    = [e["ticker"] for e in raw_entries]
            sector_map = {e["ticker"]: e.get("sector", "Unknown") for e in raw_entries}
        else:
            tickers    = raw_entries
            sector_map = {}

        candidates, daily_data = run_market(market, tickers, factors)

        # Derive last trading date from price data (handles weekend/holiday runs)
        trade_date = None
        if daily_data:
            sample_df = next(iter(daily_data.values()))
            if not sample_df.empty:
                trade_date = str(sample_df.index[-1].date())
                logger.info("Last trading date for %s: %s", market.upper(), trade_date)

        if market == "usa" and candidates:
            logger.info("[USA] Running enrichment layers + decision engine...")
            candidates = _enrich_usa_candidates(
                candidates, tickers, sector_map, daily_data, db,
                factors.get("decision", {}),
            )

        write_daily_candidates(db, candidates, market, trade_date=trade_date)

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    market = sys.argv[1] if len(sys.argv) > 1 else "usa"
    if market not in ("usa", "bist", "all"):
        logger.error("Usage: python pipeline.py [usa|bist|all]")
        sys.exit(1)
    run(market)
