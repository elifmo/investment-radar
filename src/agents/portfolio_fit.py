"""
Portfolio Fit (Beta V1 — Phase 2).

For each daily_candidate: good_fit / overlap / no_fit vs current radar holdings.
Sector concentration cap default 33%.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date
from typing import Any

from src.agents.client import get_radar_user_id

logger = logging.getLogger(__name__)

SECTOR_CAP = 0.33


def _active_holdings(db: Any, uid: str) -> list[dict]:
    rows: list[dict] = []
    try:
        for doc in (
            db.collection("radar_items")
            .where("user_id", "==", uid)
            .where("is_active", "==", True)
            .stream()
        ):
            data = doc.to_dict() or {}
            data["_id"] = doc.id
            if data.get("status") == "exited":
                continue
            rows.append(data)
    except Exception as exc:
        logger.warning("holdings load failed: %s", exc)
        # Fallback without is_active composite
        try:
            for doc in db.collection("radar_items").where("user_id", "==", uid).stream():
                data = doc.to_dict() or {}
                data["_id"] = doc.id
                if data.get("status") == "exited" or data.get("is_active") is False:
                    continue
                rows.append(data)
        except Exception as exc2:
            logger.error("holdings fallback failed: %s", exc2)
    return rows


def _sector_of(item: dict, candidate_lookup: dict[str, dict]) -> str:
    t = (item.get("ticker") or "").upper()
    c = candidate_lookup.get(t) or {}
    return (c.get("sector") or item.get("sector") or "Unknown").strip()


def evaluate_fit(
    ticker: str,
    sector: str,
    holdings: list[dict],
    candidate_lookup: dict[str, dict],
) -> dict:
    ticker_u = ticker.upper()
    held_tickers = {(h.get("ticker") or "").upper() for h in holdings}
    if ticker_u in held_tickers:
        return {
            "fit": "overlap",
            "reason": f"{ticker_u} is already on your radar.",
        }

    n = len(holdings)
    if n == 0:
        return {
            "fit": "good_fit",
            "reason": f"{ticker_u} diversifies an empty sleeve.",
        }

    sectors = [_sector_of(h, candidate_lookup) for h in holdings]
    counts = Counter(sectors)
    sector_key = sector or "Unknown"
    current = counts.get(sector_key, 0)
    projected = (current + 1) / (n + 1)

    same_sector_tickers = [
        (h.get("ticker") or "").upper()
        for h in holdings
        if _sector_of(h, candidate_lookup) == sector_key
    ]

    if projected > SECTOR_CAP and current >= 1:
        pct = round(projected * 100)
        held = ", ".join(same_sector_tickers[:4]) or "existing names"
        return {
            "fit": "no_fit",
            "reason": (
                f"Adding {ticker_u} would push {sector_key} to ~{pct}% "
                f"(cap {int(SECTOR_CAP*100)}%). You already hold {held}."
            ),
            "projected_sector_pct": pct,
        }

    if same_sector_tickers and projected > SECTOR_CAP * 0.85:
        return {
            "fit": "overlap",
            "reason": (
                f"{ticker_u} overlaps {sector_key} with {', '.join(same_sector_tickers[:3])}. "
                "Size carefully if you still want exposure."
            ),
            "projected_sector_pct": round(projected * 100),
        }

    return {
        "fit": "good_fit",
        "reason": f"{ticker_u} fits — {sector_key} stays within concentration limits.",
        "projected_sector_pct": round(projected * 100),
    }


def run_for_candidates(db: Any, candidates: list[dict]) -> dict[str, dict]:
    today = date.today().isoformat()
    uid = get_radar_user_id()
    holdings = _active_holdings(db, uid)
    lookup = {(c.get("ticker") or "").upper(): c for c in candidates}

    db.collection("agents").document("candidate_fit").set(
        {"updated_at": today, "layer": "beta_v1"}, merge=True
    )

    out: dict[str, dict] = {}
    for c in candidates:
        ticker = (c.get("ticker") or "").upper()
        if not ticker:
            continue
        sector = (c.get("sector") or "Unknown").strip()
        result = evaluate_fit(ticker, sector, holdings, lookup)
        payload = {
            "ticker": ticker,
            "fit": result["fit"],
            "reason": result["reason"],
            "projected_sector_pct": result.get("projected_sector_pct"),
            "updated_at": today,
            "layer": "beta_v1",
        }
        (
            db.collection("agents")
            .document("candidate_fit")
            .collection("by_ticker")
            .document(ticker)
            .set(payload, merge=True)
        )
        out[ticker] = payload

    logger.info("Portfolio fit written for %d candidates", len(out))
    return out
