"""
Decision Logger (Beta V1 — Phase 3).

Writes decision_log entries from today's daily_brief actions (exit / enter_now / wait / review).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


def _log_id(day: str, ticker: str, decision_type: str) -> str:
    return f"dec_{day}_{ticker}_{decision_type}".replace(" ", "_")


def run(db: Any) -> list[str]:
    today = date.today().isoformat()
    brief_snap = db.collection("agents").document("daily_brief").get()
    if not brief_snap.exists:
        logger.warning("No daily_brief — skip decision logger")
        return []
    brief = brief_snap.to_dict() or {}
    written: list[str] = []

    for action in brief.get("my_radar_actions") or []:
        dtype = action.get("action")
        if dtype not in {"exit", "review"}:
            continue
        ticker = (action.get("ticker") or "").upper()
        if not ticker:
            continue
        doc_id = _log_id(today, ticker, dtype)
        # Find matching radar_actions price if available
        price = None
        try:
            item_id = action.get("radar_item_id")
            if item_id:
                snap = (
                    db.collection("agents")
                    .document("radar_actions")
                    .collection("by_item")
                    .document(item_id)
                    .get()
                )
                if snap.exists:
                    price = (snap.to_dict() or {}).get("price")
        except Exception:
            pass

        payload = {
            "decision_id": doc_id,
            "ticker": ticker,
            "decision_type": dtype,
            "agent": "exit_signal_agent" if dtype == "exit" else "orchestrator",
            "recommended_price": price,
            "reasoning": action.get("reason") or action.get("label") or "",
            "date": today,
            "outcome_checked": False,
            "layer": "beta_v1",
        }
        existing = db.collection("decision_log").document(doc_id).get()
        if existing.exists and existing.to_dict().get("outcome_checked"):
            continue
        db.collection("decision_log").document(doc_id).set(payload, merge=True)
        written.append(doc_id)

    for cand in brief.get("candidates_ranked") or []:
        dtype = cand.get("action")
        if dtype not in {"enter_now", "wait"}:
            continue
        ticker = (cand.get("ticker") or "").upper()
        if not ticker:
            continue
        doc_id = _log_id(today, ticker, dtype)
        price = cand.get("target_price") if dtype == "wait" else None

        # Pull price from daily_candidates today
        try:
            cs = db.collection("daily_candidates").document(f"{today}_{ticker}").get()
            if cs.exists:
                price = (cs.to_dict() or {}).get("close") or price
        except Exception:
            pass

        payload = {
            "decision_id": doc_id,
            "ticker": ticker,
            "decision_type": dtype,
            "agent": "candidates_runner",
            "recommended_price": price,
            "target_price": cand.get("target_price"),
            "amount_eur": cand.get("amount_eur"),
            "reasoning": cand.get("reason") or "",
            "date": today,
            "outcome_checked": False,
            "layer": "beta_v1",
        }
        existing = db.collection("decision_log").document(doc_id).get()
        if existing.exists and existing.to_dict().get("outcome_checked"):
            continue
        db.collection("decision_log").document(doc_id).set(payload, merge=True)
        written.append(doc_id)

    logger.info("Decision logger wrote %d entries", len(written))
    return written
