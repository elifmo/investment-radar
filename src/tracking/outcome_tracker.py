"""
Outcome Tracker (Beta V1 — Phase 3).

Scores decision_log entries after their window:
- exit: 7–14d — correct if price fell vs recommended_price (hold would have hurt)
- enter_now: 14–30d — correct if price up; also store alpha vs SPY when possible
- wait: 30d — correct if target hit or price did not run away >10% without pullback (soft)
- review: 14d — informational; mark checked without strict correct/incorrect unless price broke badly
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)

WINDOWS = {
    "exit": 10,
    "review": 14,
    "enter_now": 21,
    "wait": 30,
}


def _parse_day(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _price_on_or_after(ticker: str, day: date) -> float | None:
    try:
        hist = yf.Ticker(ticker).history(
            start=day.isoformat(),
            end=(day + timedelta(days=10)).isoformat(),
            interval="1d",
        )
        if hist.empty:
            return None
        return round(float(hist["Close"].iloc[0]), 2)
    except Exception as exc:
        logger.debug("price fetch failed %s: %s", ticker, exc)
        return None


def _price_now(ticker: str) -> float | None:
    try:
        hist = yf.Ticker(ticker).history(period="5d", interval="1d")
        if hist.empty:
            return None
        return round(float(hist["Close"].iloc[-1]), 2)
    except Exception:
        return None


def _spy_return(start: date, end: date) -> float | None:
    try:
        hist = yf.Ticker("SPY").history(
            start=start.isoformat(),
            end=(end + timedelta(days=3)).isoformat(),
            interval="1d",
        )
        if len(hist) < 2:
            return None
        a = float(hist["Close"].iloc[0])
        b = float(hist["Close"].iloc[-1])
        if a <= 0:
            return None
        return (b / a) - 1.0
    except Exception:
        return None


def _score_outcome(row: dict, price_now: float, price_then: float | None) -> tuple[str, float | None, float | None]:
    """Returns outcome, pct_change, alpha_vs_spy."""
    dtype = row.get("decision_type")
    rec = row.get("recommended_price")
    try:
        rec_f = float(rec) if rec is not None else float(price_then) if price_then is not None else None
    except (TypeError, ValueError):
        rec_f = None

    if rec_f is None or rec_f <= 0:
        return "unknown", None, None

    pct = (price_now / rec_f) - 1.0
    day0 = _parse_day(row.get("date")) or date.today()
    spy_ret = _spy_return(day0, date.today())
    alpha = (pct - spy_ret) if spy_ret is not None else None

    if dtype == "exit":
        # Correct if price is lower (exit avoided further loss) or flat-to-down
        outcome = "correct" if pct <= 0 else "incorrect"
    elif dtype == "enter_now":
        # Prefer alpha when available
        if alpha is not None:
            outcome = "correct" if alpha >= 0 else "incorrect"
        else:
            outcome = "correct" if pct > 0 else "incorrect"
    elif dtype == "wait":
        target = row.get("target_price")
        try:
            target_f = float(target) if target is not None else None
        except (TypeError, ValueError):
            target_f = None
        if target_f and price_now <= target_f * 1.02:
            outcome = "correct"  # got the pullback
        elif pct >= 0.10:
            outcome = "incorrect"  # ran without you
        else:
            outcome = "correct"  # patience ok
    elif dtype == "review":
        outcome = "correct" if abs(pct) < 0.08 else ("incorrect" if pct < -0.08 else "correct")
    else:
        outcome = "unknown"

    return outcome, round(pct * 100, 2), round(alpha * 100, 2) if alpha is not None else None


def run(db: Any) -> int:
    today = date.today()
    updated = 0
    try:
        docs = list(db.collection("decision_log").stream())
    except Exception as exc:
        logger.error("decision_log stream failed: %s", exc)
        return 0

    for doc in docs:
        data = doc.to_dict() or {}
        if data.get("outcome_checked"):
            continue
        dtype = data.get("decision_type")
        window = WINDOWS.get(dtype, 14)
        day0 = _parse_day(data.get("date"))
        if not day0:
            continue
        if today < day0 + timedelta(days=window):
            continue

        ticker = (data.get("ticker") or "").upper()
        if not ticker:
            continue

        price_then = None
        try:
            if data.get("recommended_price") is not None:
                price_then = float(data["recommended_price"])
        except (TypeError, ValueError):
            price_then = None
        if price_then is None:
            price_then = _price_on_or_after(ticker, day0)

        price_now = _price_now(ticker)
        if price_now is None:
            logger.warning("No current price for %s — skip outcome", ticker)
            continue

        outcome, pct_change, alpha = _score_outcome(data, price_now, price_then)
        db.collection("decision_log").document(doc.id).set(
            {
                "outcome_checked": True,
                "outcome": outcome,
                "price_at_check": price_now,
                "price_at_decision": price_then,
                "pct_change": pct_change,
                "alpha_vs_spy_pct": alpha,
                "checked_at": datetime.utcnow().isoformat() + "Z",
            },
            merge=True,
        )
        updated += 1
        logger.info(
            "Outcome %s %s → %s (pct=%s alpha=%s)",
            ticker,
            dtype,
            outcome,
            pct_change,
            alpha,
        )

    logger.info("Outcome tracker updated %d decisions", updated)
    return updated
