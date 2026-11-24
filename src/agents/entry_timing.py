"""
Entry Timing (Beta V1 — Phase 2).

enter_now vs wait from entry_signal (score + daily cloud). Support distance is optional context only.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


def evaluate_timing(c: dict) -> dict:
    price = c.get("close") or c.get("price")
    support = c.get("support")
    try:
        price = float(price) if price is not None else None
        support = float(support) if support is not None else None
    except (TypeError, ValueError):
        price, support = None, None

    ticker = (c.get("ticker") or "").upper()
    entry_signal = (c.get("entry_signal") or "").upper()
    decision = (c.get("decision") or "").upper()
    entry_target = None

    if entry_signal == "ENTER" or decision == "BUY":
        timing = "enter_now"
        note = c.get("reason") or f"{ticker}: score + above daily cloud — entry zone."
        if support and support > 0:
            entry_target = round(support * 1.02, 2)
    elif entry_signal == "WAIT" or decision == "WATCH":
        timing = "wait"
        note = c.get("reason") or f"{ticker}: wait for price above daily cloud."
        if support and support > 0:
            entry_target = round(support * 1.02, 2)
            if price is not None and support > 0:
                dist_pct = (price / support - 1) * 100
                note = (
                    f"{c.get('reason') or ticker + ': below cloud.'} "
                    f"Support ${support:.2f} ({dist_pct:+.1f}% from price)."
                )
    else:
        timing = "wait"
        note = f"{ticker}: no entry signal — wait."

    return {
        "ticker": ticker,
        "timing": timing,
        "entry_target": entry_target,
        "note": note,
    }


def run_for_candidates(db: Any, candidates: list[dict], fit_map: dict[str, dict]) -> dict[str, dict]:
    """Only evaluate good_fit / overlap; still write wait notes for no_fit lightly."""
    today = date.today().isoformat()
    db.collection("agents").document("entry_timing").set(
        {"updated_at": today, "layer": "beta_v1"}, merge=True
    )

    out: dict[str, dict] = {}
    for c in candidates:
        ticker = (c.get("ticker") or "").upper()
        if not ticker:
            continue
        fit = (fit_map.get(ticker) or {}).get("fit", "good_fit")
        if fit == "no_fit":
            result = {
                "ticker": ticker,
                "timing": "wait",
                "entry_target": None,
                "note": f"{ticker}: skipped for timing — does not fit the portfolio.",
            }
        else:
            result = evaluate_timing(c)

        payload = {**result, "updated_at": today, "layer": "beta_v1"}
        (
            db.collection("agents")
            .document("entry_timing")
            .collection("by_ticker")
            .document(ticker)
            .set(payload, merge=True)
        )
        out[ticker] = payload

    logger.info("Entry timing written for %d candidates", len(out))
    return out
