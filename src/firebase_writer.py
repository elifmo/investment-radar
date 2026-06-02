import logging
from datetime import date
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


def write_daily_candidates(db: firestore.client, candidates: list[dict], market: str) -> int:
    """Write today's candidates to Firestore daily_candidates collection.

    Deletes existing records for today + market before writing new ones.
    Returns number of documents written.
    """
    today = date.today().isoformat()
    col = db.collection("daily_candidates")

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

    # Write new candidates
    batch = db.batch()
    written = 0
    for c in candidates:
        doc_id = f"{today}_{c['ticker']}"
        ref = col.document(doc_id)
        batch.set(ref, {**c, "date": today})
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
