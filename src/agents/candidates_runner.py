"""Candidates agent runner: Fit → Timing → Sizing for latest USA candidates."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from src.agents import entry_timing, portfolio_fit, position_sizing

logger = logging.getLogger(__name__)


def _latest_usa_candidate_date(db: Any) -> str | None:
    """Prefer today; else walk back ~10 calendar days for the newest USA scan with rows."""
    today = date.today()
    for i in range(0, 11):
        day = (today - timedelta(days=i)).isoformat()
        try:
            docs = list(
                db.collection("daily_candidates")
                .where("date", "==", day)
                .where("market", "==", "USA")
                .limit(1)
                .stream()
            )
        except Exception as exc:
            logger.error("Failed probing daily_candidates for %s: %s", day, exc)
            continue
        if docs:
            return day
    return None


def _usa_candidates_for_date(db: Any, day: str) -> list[dict]:
    rows: list[dict] = []
    try:
        for doc in (
            db.collection("daily_candidates")
            .where("date", "==", day)
            .where("market", "==", "USA")
            .stream()
        ):
            data = doc.to_dict() or {}
            entry_sig = (data.get("entry_signal") or "").upper()
            dec = (data.get("decision") or "").upper()
            if entry_sig == "NO_SIGNAL" or dec == "SKIP":
                continue
            rows.append(data)
    except Exception as exc:
        logger.error("Failed loading daily_candidates for %s: %s", day, exc)
    rows.sort(key=lambda r: float(r.get("score") or 0), reverse=True)
    # Cap LLM-adjacent work; sizing is cheap but keep list bounded
    return rows[:40]


def run(db: Any) -> dict:
    day = _latest_usa_candidate_date(db)
    if not day:
        logger.warning("Candidates runner: no USA daily_candidates found")
        return {"fit": {}, "timing": {}, "sizing": {}, "date": None}

    candidates = _usa_candidates_for_date(db, day)
    logger.info("Candidates runner: %d USA names for %s", len(candidates), day)
    if not candidates:
        return {"fit": {}, "timing": {}, "sizing": {}, "date": day}

    fit_map = portfolio_fit.run_for_candidates(db, candidates)
    timing_map = entry_timing.run_for_candidates(db, candidates, fit_map)
    sizing_map = position_sizing.run_for_candidates(db, candidates, fit_map, timing_map)
    return {"fit": fit_map, "timing": timing_map, "sizing": sizing_map, "date": day}
