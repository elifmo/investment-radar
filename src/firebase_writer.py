import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore

logger = logging.getLogger(__name__)

_SERVICE_ACCOUNT = Path(__file__).parent.parent / "serviceAccountKey.json"


def init_firebase() -> firestore.client:
    """Initialize Firebase Admin SDK. Safe to call multiple times."""
    if not firebase_admin._apps:
        cred = credentials.Certificate(str(_SERVICE_ACCOUNT))
        firebase_admin.initialize_app(cred)
    return firestore.client()


def _build_streak_map(db: firestore.client, market: str, today: str) -> dict[str, int]:
    """Return {ticker: streak} from yesterday's candidates for this market.

    Looks back up to 30 days so streaks survive weekends and holidays.
    """
    col = db.collection("daily_candidates")
    streak_map: dict[str, int] = {}

    # Find the most recent past date that has records for this market
    for days_back in range(1, 31):
        past = (date.fromisoformat(today) - timedelta(days=days_back)).isoformat()
        docs = list(col.where("date", "==", past).where("market", "==", market.upper()).stream())
        if docs:
            for doc in docs:
                data = doc.to_dict()
                ticker = data.get("ticker")
                prev_streak = data.get("streak", 1)
                if ticker:
                    streak_map[ticker] = prev_streak
            logger.info("Streak base: %d tickers from %s (%s)", len(streak_map), past, market)
            break

    return streak_map


def _session_meta(market: str) -> dict:
    """Return 4H session window metadata using each market's local clock."""
    if market.upper() == "BIST":
        now = datetime.now(ZoneInfo("Europe/Istanbul"))
        mins = now.hour * 60 + now.minute
        if mins < 14 * 60 + 15:
            window = "10:00 – 14:00"
            run_hint = "10:15"
        elif mins < 18 * 60 + 15:
            window = "14:00 – 18:00"
            run_hint = "14:15"
        else:
            window = "Kapanış"
            run_hint = "18:15"
        return {
            "session_window": f"{window} · İstanbul",
            "session_tz": "Europe/Istanbul",
            "session_tz_label": "İstanbul",
            "session_note": "",
            "schedule_local": "10:15 · 14:15 · 18:15 · İstanbul",
            "typical_run_local": f"{run_hint} · İstanbul",
        }

    now = datetime.now(ZoneInfo("America/New_York"))
    mins = now.hour * 60 + now.minute
    if mins < 13 * 60 + 30:
        window = "09:30 – 13:30"
        run_hint = "09:30"
    elif mins < 16 * 60 + 15:
        window = "13:30 – 16:00"
        run_hint = "13:30"
    else:
        window = "After close"
        run_hint = "16:15"
    return {
        "session_window": f"{window} · New York",
        "session_tz": "America/New_York",
        "session_tz_label": "New York",
        "session_note": "",
        "schedule_local": "09:30 · 13:30 · 16:15 · New York",
        "typical_run_local": f"{run_hint} · New York",
    }


def _session_window(market: str) -> str:
    """Return the 4-hour session window label (legacy string field)."""
    return _session_meta(market)["session_window"]


def write_daily_candidates(
    db: firestore.client,
    candidates: list[dict],
    market: str,
    trade_date: str | None = None,
) -> int:
    """Write candidates to Firestore daily_candidates collection.

    Uses trade_date (last market close date) rather than today's date so
    weekend/holiday runs correctly tag data to the actual trading day.
    Deletes existing records for that date + market before writing new ones.
    Adds a `streak` field: consecutive days this ticker appeared in candidates.
    Returns number of documents written.
    """
    today = trade_date or date.today().isoformat()
    col = db.collection("daily_candidates")

    # Build streak map from most recent past run
    streak_map = _build_streak_map(db, market, today)

    # Delete today's existing records for this market
    existing = col.where("date", "==", today).where("market", "==", market.upper()).stream()
    batch = db.batch()
    deleted = 0
    for doc in existing:
        batch.delete(doc.reference)
        deleted += 1
    if deleted:
        batch.commit()
        logger.info("Deleted %d stale records for %s / %s", deleted, market, today)

    # Write new candidates with streak
    batch = db.batch()
    written = 0
    for c in candidates:
        ticker = c["ticker"]
        streak = streak_map.get(ticker, 0) + 1
        doc_id = f"{today}_{ticker}"
        ref = col.document(doc_id)
        evaluated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        session_meta = _session_meta(market)
        batch.set(ref, {
            **c,
            "date": today,
            "streak": streak,
            "evaluated_at": evaluated_at,
            "session_window": session_meta["session_window"],
            "session_tz": session_meta["session_tz"],
            "session_tz_label": session_meta["session_tz_label"],
            "session_note": session_meta["session_note"],
            "schedule_local": session_meta["schedule_local"],
        })
        if streak > 1:
            logger.info("  %s streak=%d", ticker, streak)
        written += 1

    if written:
        batch.commit()
        logger.info("Wrote %d candidates to Firestore (market=%s, date=%s)", written, market, today)
    else:
        logger.info("No candidates to write for %s on %s", market, today)

    # Always save scan metadata (even when list is empty) for dashboard header
    session_meta = _session_meta(market)
    evaluated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tf = (candidates[0].get("timeframe") if candidates else None) or "4h"
    db.collection("scan_meta").document(f"{today}_{market.upper()}").set({
        "date": today,
        "market": market.upper(),
        "evaluated_at": evaluated_at,
        "timeframe": tf,
        **session_meta,
    })

    return written


def write_macro_regime(db: firestore.client, regime: dict) -> None:
    """Write macro regime to macro_regime/current (single document, overwrite)."""
    db.collection("macro_regime").document("current").set(regime)
    logger.info("Macro regime written: %s", regime.get("regime"))


def write_quality_grades(db: firestore.client, grades: dict[str, dict]) -> None:
    """Upsert one document per ticker in quality_grades/{ticker}."""
    col = db.collection("quality_grades")
    batch = db.batch()
    for ticker, data in grades.items():
        batch.set(col.document(ticker), data)
    if grades:
        batch.commit()
    logger.info("Quality grades written: %d tickers", len(grades))


def write_sector_status(db: firestore.client, sector_data: dict[str, dict]) -> None:
    """
    Upsert sector_status/{etf} for each sector.
    Also appends this week's snapshot to sector_status_history (keyed by ISO week).
    """
    from datetime import date as _date

    col     = db.collection("sector_status")
    hist    = db.collection("sector_status_history")
    week_key = _date.today().strftime("%Y-W%W")

    batch = db.batch()
    for sector, data in sector_data.items():
        etf = data.get("etf", sector)
        batch.set(col.document(etf), data)
        # History: one doc per sector per week
        hist_doc = hist.document(f"{week_key}_{etf}")
        batch.set(hist_doc, {**data, "week": week_key})
    if sector_data:
        batch.commit()
    logger.info("Sector status written: %d sectors (week=%s)", len(sector_data), week_key)


def write_sector_heatmap(db: firestore.client, heatmap: dict, trade_date: str | None = None) -> None:
    """Upsert sector_heatmap/current and sector_heatmap/{YYYY-MM-DD}."""
    date_key = trade_date or heatmap.get("as_of_date") or heatmap.get("updated_at")
    payload = {**heatmap, "as_of_date": date_key}

    col = db.collection("sector_heatmap")
    col.document("current").set(payload)
    col.document(date_key).set(payload)

    index_ref = col.document("_index")
    index_snap = index_ref.get()
    dates: list[str] = []
    if index_snap.exists:
        dates = list(index_snap.to_dict().get("dates") or [])
    if date_key not in dates:
        dates.append(date_key)
    dates = sorted(set(dates), reverse=True)[:252]

    index_ref.set({"dates": dates, "latest": dates[0] if dates else date_key})
    logger.info(
        "Sector heatmap written: %s — %d watchlist, %d sp500 stocks, %d sectors (%d days indexed)",
        date_key,
        len(payload.get("stocks", [])),
        len(payload.get("stocks_sp500", [])),
        len(payload.get("sectors", [])),
        len(dates),
    )


def write_etf_scan(db: firestore.client, results: list[dict], scan_date: str | None = None) -> None:
    """Upsert etf_scans/current and etf_scans/{YYYY-MM-DD}."""
    date_key = scan_date or (results[0].get("as_of_date") if results else date.today().isoformat())
    payload = {
        "as_of_date": date_key,
        "updated_at": date.today().isoformat(),
        "count": len(results),
        "etfs": results,
    }

    col = db.collection("etf_scans")
    col.document("current").set(payload)
    col.document(date_key).set(payload)

    index_ref = col.document("_index")
    index_snap = index_ref.get()
    dates: list[str] = []
    if index_snap.exists:
        dates = list(index_snap.to_dict().get("dates") or [])
    if date_key not in dates:
        dates.append(date_key)
    dates = sorted(set(dates), reverse=True)[:90]

    index_ref.set({"dates": dates, "latest": dates[0] if dates else date_key})
    logger.info("ETF scan written: %s — %d ETFs (%d days indexed)", date_key, len(results), len(dates))


def write_oversold_watch(
    db: firestore.client,
    items: list[dict],
    trade_date: str | None = None,
    timeframe: str = "4h",
) -> None:
    """Upsert oversold_watch/current — full-universe oversold list for Opportunities tab."""
    from datetime import date as _date, datetime, timezone

    date_key = trade_date or _date.today().isoformat()
    payload = {
        "as_of_date": date_key,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timeframe": timeframe,
        "count": len(items),
        "items": items,
    }
    col = db.collection("oversold_watch")
    col.document("current").set(payload)
    col.document(date_key).set(payload)
    logger.info("Oversold watch written: %s — %d items (%s)", date_key, len(items), timeframe)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    db = init_firebase()
    test_candidates = [
        {
            "ticker": "NVDA",
            "market": "USA",
            "score": 85,
            "triggers": ["volume_spike", "ema_crossover"],
            "why_today": "Volume spike, EMA crossover",
            "signals": ["✅ EMA fully aligned", "✅ Volume 2.3x average"],
            "support": 140.0,
            "resistance": 155.0,
            "volume_ratio": 2.3,
            "rsi": 62.0,
        }
    ]
    n = write_daily_candidates(db, test_candidates, "USA")
    logger.info("Test write complete: %d document(s)", n)
