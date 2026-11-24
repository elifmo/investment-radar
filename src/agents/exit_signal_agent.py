"""
Exit Signal Agent (Beta V1 — Phase 2).

For each holding in radar_items: flag exit / review / ok using exit_condition,
price/score from daily_candidates, macro + sector context.
Haiku writes a short English note.

Writes: agents/radar_actions/by_item/{radar_item_id}
"""

from __future__ import annotations

import logging
import re
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
_PRICE_RE = re.compile(
    r"(?:\$|usd\s*)?(\d{1,5}(?:[.,]\d{1,4})?)",
    re.IGNORECASE,
)


def _parse_exit_price(exit_condition: str | None) -> float | None:
    """Best-effort extract a stop/exit price from free-text exit_condition."""
    if not exit_condition:
        return None
    text = exit_condition.replace(",", "")
    # Prefer phrases like "below 97" / "stop 97.22" / "$97"
    candidates: list[float] = []
    for m in _PRICE_RE.finditer(text):
        try:
            val = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        if 0.5 < val < 100_000:
            candidates.append(val)
    if not candidates:
        return None
    # Heuristic: exit levels are usually near recent prices — take the first reasonable number
    return candidates[0]


def _load_macro(db: Any) -> dict:
    doc = db.collection("agents").document("macro_signal").get()
    return doc.to_dict() if doc.exists else {}


def _load_sectors(db: Any) -> dict[str, str]:
    doc = db.collection("agents").document("sector_rotation").get()
    data = doc.to_dict() if doc.exists else {}
    return (data or {}).get("sectors") or {}


def _sector_label_for_ticker(ticker: str, candidate: dict, sectors: dict[str, str]) -> str | None:
    """Match sector name from candidate or fuzzy key in sectors map."""
    sector = candidate.get("sector") or candidate.get("gics_sector")
    if sector and sector in sectors:
        return sectors[sector]
    # Case-insensitive / partial
    if sector:
        for k, v in sectors.items():
            if k.lower() == str(sector).lower():
                return v
    return None


def _latest_candidate(db: Any, ticker: str) -> dict:
    """Most recent USA daily_candidates doc for ticker (today preferred)."""
    today = date.today().isoformat()
    col = db.collection("daily_candidates")
    # Prefer today's doc id pattern if used: {date}_{ticker}
    for doc_id in (f"{today}_{ticker}", f"{today}_{ticker.upper()}"):
        snap = col.document(doc_id).get()
        if snap.exists:
            return snap.to_dict() or {}

    try:
        q = (
            col.where("ticker", "==", ticker)
            .where("market", "==", "USA")
            .limit(5)
            .stream()
        )
        rows = [d.to_dict() or {} for d in q]
        if not rows:
            # try uppercase
            q2 = (
                col.where("ticker", "==", ticker.upper())
                .where("market", "==", "USA")
                .limit(5)
                .stream()
            )
            rows = [d.to_dict() or {} for d in q2]
        if not rows:
            return {}
        rows.sort(key=lambda r: r.get("date") or "", reverse=True)
        return rows[0]
    except Exception as exc:
        logger.debug("candidate lookup failed for %s: %s", ticker, exc)
        return {}


def _live_price(ticker: str) -> float | None:
    try:
        hist = yf.Ticker(ticker).history(period="5d", interval="1d")
        if hist.empty:
            return None
        return round(float(hist["Close"].iloc[-1]), 2)
    except Exception:
        return None


def decide_flag(
    *,
    price: float | None,
    exit_price: float | None,
    support: float | None,
    score: float | None,
    sector_label: str | None,
    macro_signal: str | None,
) -> str:
    """
    exit  — price at/below exit condition or clearly below support
    review — weak score or soft support break (macro/sector are display-only)
    ok    — otherwise
    """
    if price is not None and exit_price is not None and price <= exit_price * 1.005:
        return "exit"
    if price is not None and support is not None and price < support * 0.99:
        return "exit"

    weak_score = score is not None and score < 45

    if price is not None and support is not None and price < support * 1.01:
        if weak_score:
            return "review"

    if score is not None and score < 35:
        return "review"

    return "ok"


def _action_label(flag: str) -> str:
    return {
        "exit": "Exit now",
        "review": "Review",
        "ok": "Hold",
    }.get(flag, "Hold")


def _fallback_note(
    ticker: str,
    flag: str,
    *,
    price: float | None,
    exit_price: float | None,
    support: float | None,
    score: float | None,
    sector_label: str | None,
    macro_signal: str | None,
    exit_condition: str | None,
) -> str:
    bits = [f"{ticker}: {_action_label(flag)}."]
    if flag == "exit":
        if exit_price is not None and price is not None:
            bits.append(f"Price {price} is at/below your exit level {exit_price}.")
        elif support is not None and price is not None:
            bits.append(f"Price {price} broke support {support}.")
        else:
            bits.append("Exit condition appears triggered.")
    elif flag == "review":
        bits.append(
            f"Score={score}, sector={sector_label or 'n/a'}, macro={macro_signal or 'n/a'}."
        )
        bits.append("Re-check thesis before adding size.")
    else:
        bits.append("No exit trigger; thesis can stay on track if your rules still hold.")
    if exit_condition:
        bits.append(f'Your rule: "{exit_condition[:120]}"')
    return " ".join(bits)


def _haiku_note(ctx: dict) -> str:
    client = get_anthropic_client()
    prompt = f"""You are the Exit Signal Agent for a portfolio dashboard.
Write 2 short sentences in English explaining the action flag.

Ticker: {ctx['ticker']}
Flag (authoritative — do not soften exit to hold): {ctx['flag']}
Action label: {ctx['action']}
Price: {ctx['price']} | Exit level parsed: {ctx['exit_price']} | Support: {ctx['support']}
Score: {ctx['score']} | Sector: {ctx['sector_label']} | Macro: {ctx['macro_signal']}
User exit rule: {ctx['exit_condition']}

{ENGLISH_OUTPUT_RULE}
Be direct. If flag is exit, say to exit or sell now. If review, say what to check. If ok, say hold.
Do not invent prices."""

    message = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=180,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()
    return text or _fallback_note(
        ctx["ticker"],
        ctx["flag"],
        price=ctx["price"],
        exit_price=ctx["exit_price"],
        support=ctx["support"],
        score=ctx["score"],
        sector_label=ctx["sector_label"],
        macro_signal=ctx["macro_signal"],
        exit_condition=ctx["exit_condition"],
    )


def run(db: Any) -> dict:
    today = date.today().isoformat()
    uid = get_radar_user_id()
    macro = _load_macro(db)
    macro_signal = (macro or {}).get("signal")
    sectors = _load_sectors(db)

    holdings = []
    try:
        q = (
            db.collection("radar_items")
            .where("user_id", "==", uid)
            .where("status", "==", "holding")
            .stream()
        )
        for doc in q:
            data = doc.to_dict() or {}
            data["_id"] = doc.id
            if data.get("is_active") is False:
                continue
            holdings.append(data)
    except Exception as exc:
        logger.error("Failed to load holdings: %s", exc)
        return {}

    db.collection("agents").document("radar_actions").set(
        {"updated_at": today, "layer": "beta_v1", "count": len(holdings)},
        merge=True,
    )

    results: dict[str, dict] = {}
    for item in holdings:
        ticker = (item.get("ticker") or "").upper().strip()
        if not ticker:
            continue
        item_id = item["_id"]
        cand = _latest_candidate(db, ticker)
        price = cand.get("close") or cand.get("price")
        if price is None:
            price = _live_price(ticker)
        else:
            try:
                price = float(price)
            except (TypeError, ValueError):
                price = _live_price(ticker)

        support = cand.get("support")
        try:
            support = float(support) if support is not None else None
        except (TypeError, ValueError):
            support = None

        score = cand.get("score")
        try:
            score = float(score) if score is not None else None
        except (TypeError, ValueError):
            score = None

        exit_condition = item.get("exit_condition") or ""
        exit_price = _parse_exit_price(exit_condition)
        sector_label = _sector_label_for_ticker(ticker, cand, sectors)

        flag = decide_flag(
            price=price,
            exit_price=exit_price,
            support=support,
            score=score,
            sector_label=sector_label,
            macro_signal=macro_signal,
        )
        action = _action_label(flag)
        ctx = {
            "ticker": ticker,
            "flag": flag,
            "action": action,
            "price": price,
            "exit_price": exit_price,
            "support": support,
            "score": score,
            "sector_label": sector_label,
            "macro_signal": macro_signal,
            "exit_condition": exit_condition,
        }
        try:
            note = _haiku_note(ctx)
        except Exception as exc:
            logger.warning("Haiku exit note failed for %s (%s)", ticker, exc)
            note = _fallback_note(
                ticker,
                flag,
                price=price,
                exit_price=exit_price,
                support=support,
                score=score,
                sector_label=sector_label,
                macro_signal=macro_signal,
                exit_condition=exit_condition,
            )

        payload = {
            "radar_item_id": item_id,
            "ticker": ticker,
            "date": today,
            "flag": flag,
            "action": action,
            "note": note,
            "score": score,
            "price": price,
            "exit_price": exit_price,
            "support": support,
            "sector_label": sector_label,
            "macro_signal": macro_signal,
            "updated_at": today,
            "layer": "beta_v1",
        }
        (
            db.collection("agents")
            .document("radar_actions")
            .collection("by_item")
            .document(item_id)
            .set(payload, merge=True)
        )
        results[item_id] = payload
        logger.info("Exit signal %s %s → %s", ticker, item_id, flag)

    logger.info("Exit agent done (%d holdings)", len(results))
    return results
