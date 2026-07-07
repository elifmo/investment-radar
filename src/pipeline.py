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

from data_fetcher import fetch_batch_daily, fetch_batch_4h
from event_filter import run_event_filter
from detailed_scorer import score_all
from ta_engine import Timeframe
from etf_scanner import scan_all_etfs
from firebase_writer import (
    init_firebase,
    write_daily_candidates,
    write_etf_scan,
    write_macro_regime,
    write_quality_grades,
    write_sector_heatmap,
    write_sector_status,
)
from layers.relative_strength import compute_rs_ratings
from layers.sector_heatmap import compute_sector_heatmap, merge_heatmap_payload
from market_calendar import resolve_usa_snapshot_date
from sp500_universe import caps_from_universe, load_sp500_universe
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


def _market_open_now(market: str) -> bool:
    from datetime import datetime, timezone
    utc = datetime.now(timezone.utc)
    day = utc.weekday()  # 0=Mon … 4=Fri
    if day >= 5:
        return False
    mins = utc.hour * 60 + utc.minute
    if market.upper() == "BIST":
        return 7 * 60 <= mins < 15 * 60 + 5
    else:  # USA
        return 13 * 60 + 30 <= mins < 20 * 60


def load_config() -> tuple[dict, dict]:
    universe = yaml.safe_load((_CONFIG_DIR / "universe.yaml").read_text())
    factors  = yaml.safe_load((_CONFIG_DIR / "factors.yaml").read_text())
    return universe, factors


def _scan_timeframe(factors: dict) -> Timeframe:
    tf = (factors.get("scan") or {}).get("timeframe", "daily")
    return "4h" if tf == "4h" else "daily"


def _event_thresholds(factors: dict, timeframe: Timeframe) -> dict:
    key = "thresholds_4h" if timeframe == "4h" else "thresholds"
    base = factors.get(key) or factors.get("thresholds", {})
    return {
        "volume_threshold": base.get("volume_spike_ratio", 1.5),
        "price_move_pct": base.get("price_move_pct", 2.0),
        "rsi_oversold": base.get("rsi_oversold", 35),
        "rsi_lookback": base.get("rsi_bounce_lookback", 5),
        "support_prox_pct": base.get("support_proximity_pct", 2.0),
    }


def run_market(market: str, tickers: list[str], factors: dict) -> tuple[list[dict], dict]:
    """
    Run core pipeline (fetch → event filter → score) for a market.

    Returns:
        (candidates, daily_data) — daily_data for USA enrichment layers.
    """
    min_score = factors.get("min_score", 65)
    weights   = factors.get("weights", {})
    timeframe = _scan_timeframe(factors)
    thresh    = _event_thresholds(factors, timeframe)

    logger.info("── %s pipeline: %d tickers (scan=%s) ──", market.upper(), len(tickers), timeframe)

    logger.info("[1/3] Fetching %s scan data...", timeframe)
    if timeframe == "4h":
        scan_data = fetch_batch_4h(tickers)
    else:
        scan_data = fetch_batch_daily(tickers)
    logger.info("  Fetched: %d / %d tickers", len(scan_data), len(tickers))

    logger.info("[2/3] Running event filter (%s)...", timeframe)
    events = run_event_filter(
        scan_data,
        market=market.upper(),
        **thresh,
    )
    triggered_tickers = [e["ticker"] for e in events]
    trigger_map       = {e["ticker"]: e["triggers"] for e in events}
    logger.info("  Triggered: %d / %d", len(triggered_tickers), len(scan_data))

    if not triggered_tickers:
        logger.info("  No events detected for %s (%s).", market.upper(), timeframe)
        daily_data = fetch_batch_daily(tickers) if timeframe == "4h" else scan_data
        return [], daily_data

    logger.info("[3/3] Scoring %d triggered tickers (%s)...", len(triggered_tickers), timeframe)
    scored = score_all(triggered_tickers, scan_data, weights, timeframe=timeframe)

    candidates = [
        {
            **c,
            "market":    market.upper(),
            "triggers":  trigger_map.get(c["ticker"], []),
            "why_today": _build_why(c, trigger_map.get(c["ticker"], []), timeframe),
            "timeframe": timeframe,
        }
        for c in scored
        if c["score"] >= min_score
    ][:10]

    logger.info("  Final candidates: %d (min_score=%d, %s)", len(candidates), min_score, timeframe)
    for c in candidates:
        logger.info("  %s — score=%d  why=%s", c["ticker"], c["score"], c["why_today"])

    # USA enrichment layers (RS, sector) still need daily OHLCV
    daily_data = fetch_batch_daily(tickers) if timeframe == "4h" else scan_data
    return candidates, daily_data


def _build_why(candidate: dict, triggers: list[str], timeframe: Timeframe = "daily") -> str:
    parts = []
    if candidate.get("score", 0) >= 80:
        parts.append("Strong setup")
    if timeframe == "4h":
        parts.append("4H scan")
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

        # Use today's date when market is open (intraday runs); fall back to
        # last bar date so weekend/holiday runs still tag the correct trading day.
        from datetime import date, datetime, timezone
        today_utc = date.today().isoformat()
        trade_date = None
        if daily_data:
            sample_df = next(iter(daily_data.values()))
            if not sample_df.empty:
                last_bar = str(sample_df.index[-1].date())
                trade_date = today_utc if last_bar == today_utc or _market_open_now(market) else last_bar
                logger.info("Trade date for %s: %s (last_bar=%s)", market.upper(), trade_date, last_bar)

        if market == "usa":
            logger.info("[USA] Computing sector heatmap (watchlist + S&P 500)...")
            try:
                sp500_univ = load_sp500_universe()
                sp500_tickers = [e["ticker"] for e in sp500_univ]
                logger.info("[USA] Fetching heatmap OHLCV (regular close, not adjusted)...")
                watchlist_hm_data = fetch_batch_daily(tickers, auto_adjust=False)
                sp500_data = fetch_batch_daily(sp500_tickers, auto_adjust=False)
                logger.info("[USA] Fetching 4H session data for heatmap...")
                watchlist_h4 = fetch_batch_4h(tickers, auto_adjust=False)
                sp500_h4 = fetch_batch_4h(sp500_tickers, auto_adjust=False)
                sp500_caps = caps_from_universe(sp500_univ)

                hm_date = resolve_usa_snapshot_date(watchlist_hm_data)
                logger.info("[USA] Heatmap snapshot date: %s", hm_date)

                watchlist_hm = compute_sector_heatmap(
                    raw_entries, watchlist_hm_data, as_of_date=hm_date,
                    h4_data=watchlist_h4,
                )
                sp500_hm = compute_sector_heatmap(
                    sp500_univ, sp500_data, as_of_date=hm_date,
                    market_caps=sp500_caps, include_benchmarks=False,
                    h4_data=sp500_h4,
                )
                heatmap = merge_heatmap_payload(watchlist_hm, sp500_hm)
                write_sector_heatmap(db, heatmap, trade_date=hm_date)
            except Exception as exc:
                logger.warning("Could not write sector heatmap: %s", exc)

            logger.info("[USA] Running ETF scan...")
            try:
                etf_results = scan_all_etfs()
                if etf_results:
                    write_etf_scan(db, etf_results)
                else:
                    logger.warning("ETF scan returned no results")
            except Exception as exc:
                logger.warning("Could not write ETF scan: %s", exc)

            if candidates:
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
