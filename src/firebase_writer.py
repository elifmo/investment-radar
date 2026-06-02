import logging
from datetime import date, timedelta
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


def write_daily_candidates(db: firestore.client, candidates: list[dict], market: str) -> int:
    """Write today's candidates to Firestore daily_candidates collection.

    Deletes existing records for today + market before writing new ones.
    Adds a `streak` field: consecutive days this ticker appeared in top 10.
    Returns number of documents written.
    """
    today = date.today().isoformat()
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
        batch.set(ref, {**c, "date": today, "streak": streak})
        if streak > 1:
            logger.info("  %s streak=%d", ticker, streak)
        written += 1

    if written:
        batch.commit()
        logger.info("Wrote %d candidates to Firestore (market=%s, date=%s)", written, market, today)
    else:
        logger.info("No candidates to write for %s on %s", market, today)

    return written


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
