"""
Earnings Preview Agent (Beta V1 — Phase 1).

Flags radar + candidate tickers with days_to_earnings ≤ 14.
Writes agents/earnings_preview/{ticker} with risk_level + English note.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import yfinance as yf

from src.agents.client import (
    ENGLISH_OUTPUT_RULE,
    get_anthropic_client,
    get_radar_user_id,
)

logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"
EARNINGS_HORIZON_DAYS = 14


def _risk_level(days: int | None, avg_move_pct: float | None) -> str:
    if days is not None and days <= 7 and (avg_move_pct or 0) > 8:
        return "high"
    if days is not None and days <= 7:
        return "medium"
    if (avg_move_pct or 0) > 8:
        return "medium"
    return "low"


def _avg_earnings_move(ticker: str, lookback: int = 8) -> float | None:
    """Rough average absolute % move around past earnings (best-effort)."""
    try:
        t = yf.Ticker(ticker)
        ed = t.get_earnings_dates(limit=lookback)
        if ed is None or ed.empty:
            return None
        hist = t.history(period="5y", interval="1d")
        if hist.empty:
            return None
        moves: list[float] = []
        # Column names vary; use index as earnings date
        for ts in list(ed.index)[:lookback]:
            try:
                d = ts.date() if hasattr(ts, "date") else date.fromisoformat(str(ts)[:10])
            except Exception:
                continue
            # nearest trading day on/after earnings
            window = hist.loc[str(d) :].head(3)
            if len(window) < 2:
                continue
            p0 = float(window["Close"].iloc[0])
            p1 = float(window["Close"].iloc[-1])
            if p0 > 0:
                moves.append(abs(p1 / p0 - 1) * 100)
        if not moves:
            return None
        return round(sum(moves) / len(moves), 1)
    except Exception as exc:
        logger.debug("Earnings move calc failed for %s: %s", ticker, exc)
        return None


def _collect_tickers(db: Any, uid: str) -> dict[str, int | None]:
    """
    Return {ticker: days_to_earnings} for names within horizon.
    Prefer days from daily_candidates; radar holdings always considered.
    """
    today = date.today().isoformat()
    wanted: dict[str, int | None] = {}

    # Radar holdings / watching for this user
    try:
        radar = (
            db.collection("radar_items")
            .where("user_id", "==", uid)
            .where("is_active", "==", True)
            .stream()
        )
        for doc in radar:
            data = doc.to_dict() or {}
            t = (data.get("ticker") or "").upper().strip()
            if t:
                wanted.setdefault(t, None)
    except Exception as exc:
        logger.warning("radar_items query failed: %s", exc)

    # Candidates with days_to_earnings
    try:
        cand = (
            db.collection("daily_candidates")
            .where("date", "==", today)
            .where("market", "==", "USA")
            .stream()
        )
        for doc in cand:
            data = doc.to_dict() or {}
            t = (data.get("ticker") or "").upper().strip()
            days = data.get("days_to_earnings")
            if t and days is not None:
                try:
                    days_i = int(days)
                except (TypeError, ValueError):
                    continue
                if days_i <= EARNINGS_HORIZON_DAYS:
                    wanted[t] = days_i
                elif t in wanted and wanted[t] is None:
                    wanted[t] = days_i
    except Exception as exc:
        logger.warning("daily_candidates earnings scan failed: %s", exc)

    # Drop names with no days or beyond horizon (unless we can fill days later)
    return {t: d for t, d in wanted.items() if d is None or d <= EARNINGS_HORIZON_DAYS}


def _fallback_note(ticker: str, days: int | None, avg_move: float | None, risk: str) -> str:
    day_txt = f"in {days} day(s)" if days is not None else "soon"
    move_txt = f" Typical move ~±{avg_move}%." if avg_move is not None else ""
    if risk == "high":
        action = "Consider reducing size before the report."
    elif risk == "medium":
        action = "Watch position size and avoid adding blindly into the print."
    else:
        action = "Note it on the calendar; no urgent size cut from earnings alone."
    return f"{ticker} reports {day_txt}.{move_txt} Risk: {risk}. {action}"


def _haiku_note(ticker: str, days: int | None, avg_move: float | None, risk: str) -> str:
    client = get_anthropic_client()
    prompt = f"""You are the Earnings Preview Agent.
Write exactly 1 sentence in English for a portfolio dashboard tag/detail.

Ticker: {ticker}
Days to earnings: {days}
Avg historical move %: {avg_move}
Risk level (authoritative): {risk}

{ENGLISH_OUTPUT_RULE}
Be concrete about volatility risk. Do not invent dates or percentages."""

    message = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=120,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()
    return text or _fallback_note(ticker, days, avg_move, risk)


def run(db: Any) -> dict:
    today = date.today().isoformat()
    uid = get_radar_user_id()
    tickers = _collect_tickers(db, uid)
    written: dict[str, dict] = {}

    for ticker, days in sorted(tickers.items()):
        # If days unknown, try candidate field only — skip far-away unknowns
        if days is None:
            continue
        avg_move = _avg_earnings_move(ticker)
        risk = _risk_level(days, avg_move)
        try:
            note = _haiku_note(ticker, days, avg_move, risk)
        except Exception as exc:
            logger.warning("Haiku earnings note failed for %s (%s)", ticker, exc)
            note = _fallback_note(ticker, days, avg_move, risk)

        payload = {
            "ticker": ticker,
            "days_to_earnings": days,
            "avg_move_pct": avg_move,
            "risk_level": risk,
            "note": note,
            "updated_at": today,
            "layer": "beta_v1",
        }
        # Path: agents/earnings_preview/by_ticker/{TICKER}
        db.collection("agents").document("earnings_preview").set(
            {"updated_at": today, "layer": "beta_v1"},
            merge=True,
        )
        (
            db.collection("agents")
            .document("earnings_preview")
            .collection("by_ticker")
            .document(ticker)
            .set(payload, merge=True)
        )
        written[ticker] = payload
        logger.info("Earnings preview %s days=%s risk=%s", ticker, days, risk)

    logger.info("Earnings preview done (%d tickers)", len(written))
    return written
