"""
Investment Radar — Main Pipeline

Usage:
  python pipeline.py usa
  python pipeline.py bist
  python pipeline.py all
  python pipeline.py usa --daily   # force heatmap + ETF (normally ~23:15 TR only)
"""

import logging
import os
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
    write_fib_ema_radar,
    write_macro_regime,
    write_oversold_watch,
    write_quality_grades,
    write_sector_heatmap,
    write_sector_status,
)
from layers.oversold_scan import scan_oversold_watch
from layers.fib_ema_radar import scan_fib_ema_radar
from layers.relative_strength import compute_rs_ratings
from layers.sector_heatmap import compute_sector_heatmap, merge_heatmap_payload
from market_calendar import resolve_usa_snapshot_date
from sp500_universe import caps_from_universe, load_sp500_universe
from usa_universe import load_usa_scan_universe
from layers.sector_rotation import compute_sector_rotation, SECTOR_ETFS
from layers.macro_regime import compute_macro_regime
from layers.earnings_calendar import get_earnings_calendar
from layers.quality_grade import compute_quality_grades
from layers.ichimoku import cloud_state_at_close
from detailed_scorer import score_ticker
from entry_gate import evaluate_entry
from crypto_signal import scan_crypto

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent.parent / "config"


def _market_open_now(market: str) -> bool:
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    utc = datetime.now(timezone.utc)
    if market.upper() == "BIST":
        if utc.weekday() >= 5:
            return False
        mins = utc.hour * 60 + utc.minute
        return 7 * 60 <= mins < 15 * 60 + 5
    et = utc.astimezone(ZoneInfo("America/New_York"))
    if et.weekday() >= 5:
        return False
    mins = et.hour * 60 + et.minute
    return 9 * 60 + 30 <= mins < 16 * 60


def _should_run_usa_daily_reports(force: bool = False) -> bool:
    """Heatmap + ETF: after the New York cash close (16:10 ET), not a fixed UTC hour."""
    if force:
        return True
    if os.environ.get("RUN_DAILY_REPORTS", "").lower() in ("1", "true", "yes"):
        return True
    from market_calendar import usa_regular_close_settled
    return usa_regular_close_settled()


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
        return [], daily_data, scan_data, timeframe

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
    ]

    logger.info("  Final candidates: %d (min_score=%d, %s)", len(candidates), min_score, timeframe)
    for c in candidates:
        logger.info("  %s — score=%d  why=%s", c["ticker"], c["score"], c["why_today"])

    # USA enrichment layers (RS, sector) still need daily OHLCV
    daily_data = fetch_batch_daily(tickers) if timeframe == "4h" else scan_data
    return candidates, daily_data, scan_data, timeframe


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


def _entry_cfg(factors: dict) -> dict:
    return factors.get("entry") or {}


def _crypto_tickers(factors: dict) -> list[str]:
    raw = (factors.get("crypto") or {}).get("tickers") or []
    return [str(t).strip() for t in raw if str(t).strip()]


def _run_crypto_scan(db, factors: dict, trade_date: str | None) -> None:
    tickers = _crypto_tickers(factors)
    if not tickers:
        return
    try:
        logger.info("[CRYPTO] Ichimoku scan for %d tickers...", len(tickers))
        daily_data = fetch_batch_daily(tickers)
        rows = scan_crypto(daily_data)
        if not rows:
            logger.warning("[CRYPTO] No crypto rows produced")
            return
        for row in rows:
            logger.info(
                "[CRYPTO] %s close=%s signal=%s",
                row.get("ticker"),
                row.get("close"),
                row.get("ichimoku_signal"),
            )
        write_daily_candidates(db, rows, "crypto", trade_date=trade_date)
        logger.info("[CRYPTO] Wrote %d crypto signals", len(rows))
    except Exception:
        logger.exception("[CRYPTO] scan failed — leaving previous crypto docs in place")


def _run_fib_ema_radar(
    db,
    market: str,
    tickers: list[str],
    daily_data: dict,
    sector_map: dict,
    trade_date: str | None,
    factors: dict,
) -> None:
    """Fib 61.8/78.6 pullback → 4h EMA cross (early) → daily confirm."""
    if not daily_data:
        return
    cfg = factors.get("fib_ema_radar") or {}
    if cfg.get("enabled") is False:
        return
    logger.info("[%s] Fib EMA radar — fetching 4h for %d tickers...", market.upper(), len(tickers))
    try:
        four_h = fetch_batch_4h(tickers, chunk_size=60)
        items = scan_fib_ema_radar(
            daily_data,
            four_h,
            market=market,
            sector_map=sector_map,
            fib_tol_pct=float(cfg.get("fib_tol_pct", 1.5)),
            touch_lookback=int(cfg.get("touch_lookback", 20)),
            max_age_days=int(cfg.get("max_age_days", 5)),
            max_daily_lag_days=int(cfg.get("max_daily_lag_days", 1)),
        )
        write_fib_ema_radar(db, items, market, trade_date=trade_date)
        early = sum(1 for x in items if x.get("status") == "early_4h")
        conf = sum(1 for x in items if x.get("status") == "daily_confirmed")
        logger.info("[%s] Fib EMA radar: %d early_4h, %d daily_confirmed", market.upper(), early, conf)
    except Exception as exc:
        logger.warning("[%s] Fib EMA radar failed: %s", market.upper(), exc)


def _enrich_usa_candidates(
    candidates: list[dict],
    all_tickers: list[str],
    sector_map: dict[str, str],
    daily_data: dict,
    db,
    decision_cfg: dict,
    entry_cfg: dict,
    weights: dict,
) -> list[dict]:
    """
    Indicators (RS, sector, macro, quality, earnings) + entry gate (daily score + cloud).
    Returns only ENTER and WAIT candidates (NO_SIGNAL excluded).
    """
    if not candidates:
        return candidates

    entry_min = float(entry_cfg.get("min_score", 65))
    entry_tf: Timeframe = "daily"

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

    # ── Entry gate (daily score + cloud) ──────────────────────────────────────
    enriched = []
    for c in candidates:
        ticker      = c["ticker"]
        sector_name = sector_map.get(ticker)
        sector_info = sector_status.get(sector_name, {}) if sector_name else {}
        grade_info  = grades.get(ticker, {})
        rs_info     = rs_ratings.get(ticker, {})

        daily_df = daily_data.get(ticker)
        daily_score = c.get("score")
        cloud = None
        if daily_df is not None and not daily_df.empty:
            try:
                daily_score, _ = score_ticker(ticker, daily_df, weights, entry_tf)
                cloud = cloud_state_at_close(daily_df)
            except Exception as exc:
                logger.warning("Daily entry scoring failed for %s: %s", ticker, exc)

        above_cloud = cloud.get("above_cloud") if cloud else False
        entry_result = evaluate_entry(daily_score, above_cloud, min_score=entry_min)
        reason = entry_result.reason
        if cloud and cloud.get("cloud_breakout") and entry_result.entry_signal == "ENTER":
            reason = f"{reason} — new daily cloud break"

        enriched_c = {
            **c,
            # Keep the scan-bar score/close (4h). Daily values live in daily_score + cloud fields.
            "score": c.get("score"),
            "daily_score": daily_score,
            "entry_signal": entry_result.entry_signal,
            "decision": entry_result.decision,
            "reason": reason,
            "position_size_multiplier": entry_result.position_size_multiplier,
            "above_cloud": above_cloud,
            "cloud_top": cloud.get("cloud_top") if cloud else None,
            "cloud_bottom": cloud.get("cloud_bottom") if cloud else None,
            "in_cloud": cloud.get("in_cloud") if cloud else None,
            "cloud_breakout": cloud.get("cloud_breakout") if cloud else False,
            "cloud_break_down": cloud.get("cloud_break_down") if cloud else False,
            "close": c.get("close"),
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

        if entry_result.entry_signal == "NO_SIGNAL":
            logger.info(
                "  %s → NO_SIGNAL (daily_score=%s, above_cloud=%s)",
                ticker,
                enriched_c.get("daily_score", "—"),
                above_cloud,
            )
            continue

        logger.info(
            "  %s → %-10s  daily_score=%s  cloud=%s  break=%s  rs=%s  grade=%s  sector=%s",
            ticker,
            enriched_c["entry_signal"],
            enriched_c.get("daily_score", "—"),
            "above" if above_cloud else "below/in",
            enriched_c.get("cloud_breakout"),
            enriched_c.get("rs_rating", "—"),
            enriched_c.get("quality_grade", "—"),
            enriched_c.get("sector_short_status", "—"),
        )
        enriched.append(enriched_c)

    return enriched


def run(market_arg: str, force_daily: bool = False) -> None:
    universe, factors = load_config()
    markets = ["usa", "bist"] if market_arg == "all" else [market_arg.lower()]
    db = init_firebase()

    for market in markets:
        if market == "usa":
            scan_mode = (factors.get("scan") or {}).get("universe", "sp500_nasdaq")
            raw_entries = load_usa_scan_universe(scan_mode)
            if not raw_entries:
                logger.error("No USA tickers resolved (scan.universe=%s)", scan_mode)
                continue
            tickers    = [e["ticker"] for e in raw_entries]
            sector_map = {e["ticker"]: e.get("sector", "Unknown") for e in raw_entries}
        else:
            raw_entries = universe.get(market)
            if not raw_entries:
                logger.error("No tickers found for market '%s' in universe.yaml", market)
                continue
            tickers    = raw_entries
            sector_map = {}

        candidates, daily_data, scan_data, scan_tf = run_market(market, tickers, factors)

        # Tag the last completed session. A fixed UTC "today" stamped Tuesday
        # onto a run that only had Monday's bar, and a crash after the heatmap
        # used to skip this write entirely.
        from datetime import date
        trade_date = None
        if market == "usa" and daily_data:
            trade_date = resolve_usa_snapshot_date(daily_data)
            logger.info("Trade date for USA: %s", trade_date)
        elif daily_data:
            today_utc = date.today().isoformat()
            sample_df = next(iter(daily_data.values()))
            if not sample_df.empty:
                last_bar = str(sample_df.index[-1].date())
                trade_date = today_utc if last_bar == today_utc or _market_open_now(market) else last_bar
                logger.info("Trade date for %s: %s (last_bar=%s)", market.upper(), trade_date, last_bar)

        # Persist the scored list before enrichment and heatmap. The last USA
        # run wrote the heatmap, then died before this write, so Monday vanished.
        write_daily_candidates(db, candidates, market, trade_date=trade_date)

        if market == "usa" and candidates:
            logger.info("[USA] Running enrichment layers + entry gate...")
            try:
                enriched = _enrich_usa_candidates(
                    candidates, tickers, sector_map, daily_data, db,
                    factors.get("decision", {}),
                    _entry_cfg(factors),
                    factors.get("weights", {}),
                )
                if enriched:
                    candidates = enriched
                    write_daily_candidates(db, candidates, market, trade_date=trade_date)
                else:
                    logger.warning("[USA] Entry gate kept nobody — leaving the scored list in place")
            except Exception:
                logger.exception("[USA] Enrichment failed — scored list already saved")
        elif market == "usa":
            logger.info("[USA] No candidates — refreshing macro + sector rotation only...")
            try:
                sector_status = compute_sector_rotation()
                if sector_status:
                    write_sector_status(db, sector_status)
                macro = compute_macro_regime()
                write_macro_regime(db, macro)
            except Exception as exc:
                logger.warning("USA macro/sector refresh failed: %s", exc)

        if market == "usa" and _should_run_usa_daily_reports(force_daily):
            logger.info("[USA] Daily close run — computing sector heatmap + ETF scan...")
            try:
                sp500_univ = load_sp500_universe()
                sp500_tickers = [e["ticker"] for e in sp500_univ]
                logger.info("[USA] Fetching heatmap OHLCV (regular close, not adjusted)...")
                watchlist_hm_data = fetch_batch_daily(tickers, auto_adjust=False)
                sp500_data = fetch_batch_daily(sp500_tickers, auto_adjust=False)
                sp500_caps = caps_from_universe(sp500_univ)

                hm_date = resolve_usa_snapshot_date(watchlist_hm_data)
                logger.info("[USA] Heatmap snapshot date: %s", hm_date)

                watchlist_hm = compute_sector_heatmap(
                    raw_entries, watchlist_hm_data, as_of_date=hm_date,
                )
                sp500_hm = compute_sector_heatmap(
                    sp500_univ, sp500_data, as_of_date=hm_date,
                    market_caps=sp500_caps, include_benchmarks=False,
                )
                heatmap = merge_heatmap_payload(watchlist_hm, sp500_hm)
                write_sector_heatmap(db, heatmap, trade_date=hm_date)
            except Exception as exc:
                logger.warning("Could not write sector heatmap: %s", exc)

            logger.info("[USA] Running ETF scan...")
            try:
                etf_results = scan_all_etfs()
                if etf_results:
                    write_etf_scan(db, etf_results, scan_date=trade_date)
                else:
                    logger.warning("ETF scan returned no results")
            except Exception as exc:
                logger.warning("Could not write ETF scan: %s", exc)
        elif market == "usa":
            logger.info(
                "[USA] Skipping heatmap + ETF (after NY close only; use --daily to force)",
            )

        if market == "usa":
            try:
                _run_crypto_scan(db, factors, trade_date)
            except Exception:
                logger.exception("[CRYPTO] USA pipeline continued after crypto failure")

        # Fib EMA radar (4h early + daily confirm) — both USA and BIST
        if daily_data:
            _run_fib_ema_radar(db, market, tickers, daily_data, sector_map, trade_date, factors)

        if market == "usa" and scan_data:
            os_cfg = factors.get("oversold") or {}
            try:
                qgrades = _read_cached_quality_grades(db, tickers)
                oversold_items = scan_oversold_watch(
                    tickers,
                    scan_data,
                    sector_map=sector_map,
                    quality_grades=qgrades,
                    timeframe=scan_tf,
                    stoch_threshold=float(os_cfg.get("stoch_k", 20)),
                    rsi_threshold=float(os_cfg.get("rsi", 35)),
                    max_items=int(os_cfg.get("max_items", 15)),
                )
                write_oversold_watch(db, oversold_items, trade_date=trade_date, timeframe=scan_tf)
            except Exception as exc:
                logger.warning("Oversold watch failed: %s", exc)

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a]
    force_daily = "--daily" in args
    args = [a for a in args if a != "--daily"]
    market = args[0] if args else "usa"
    if market not in ("usa", "bist", "all"):
        logger.error("Usage: python pipeline.py [usa|bist|all] [--daily]")
        sys.exit(1)
    run(market, force_daily=force_daily)
