"""
Averaging Down Agent (Full — Phase 5).

For holdings with material drawdown (P&L < -10%), evaluate whether adding is OK.
Suggest avg-down only if: score > 40, near support, sector not weakening (macro is display-only).

Writes: agents/avg_down/by_item/{radar_item_id}
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import yfinance as yf

from src.agents.client import get_radar_user_id

logger = logging.getLogger(__name__)

DRAWDOWN_PCT = -10.0  # need at least this unrealized loss
NEAR_SUPPORT_PCT = 3.0  # within 3% of support


def _doc(db: Any, path: str) -> dict:
    snap = db.collection("agents").document(path).get()
    return snap.to_dict() if snap.exists else {}


def _holdings(db: Any, uid: str) -> list[dict]:
    rows = []
    try:
        for doc in db.collection("radar_items").where("user_id", "==", uid).stream():
            data = doc.to_dict() or {}
            data["_id"] = doc.id
            if data.get("status") != "holding":
                continue
            if data.get("is_active") is False:
                continue
            rows.append(data)
    except Exception as exc:
        logger.warning("avg_down holdings failed: %s", exc)
    return rows


def _trades_for(db: Any, uid: str, radar_id: str) -> list[dict]:
    rows = []
    try:
        for d in (
            db.collection("trade_entries")
            .where("user_id", "==", uid)
            .where("radar_item_id", "==", radar_id)
            .stream()
        ):
            rows.append(d.to_dict() or {})
    except Exception:
        pass
    return rows


def _avg_cost(trades: list[dict]) -> tuple[float | None, float]:
    qty = 0.0
    cost = 0.0
    for t in sorted(trades, key=lambda x: x.get("trade_date") or ""):
        q = float(t.get("quantity") or 0)
        p = float(t.get("price") or 0)
        if not q or not p:
            continue
        side = (t.get("side") or "buy").lower()
        if side == "buy":
            cost += q * p
            qty += q
        elif side == "sell" and qty > 0:
            sell = min(q, qty)
            avg = cost / qty
            cost -= avg * sell
            qty -= sell
    if qty <= 0:
        return None, 0.0
    return cost / qty, qty


def _live_price(ticker: str) -> float | None:
    try:
        hist = yf.Ticker(ticker).history(period="5d", interval="1d")
        if hist.empty:
            return None
        return round(float(hist["Close"].iloc[-1]), 2)
    except Exception:
        return None


def _latest_candidate(db: Any, ticker: str) -> dict:
    today = date.today().isoformat()
    col = db.collection("daily_candidates")
    for doc_id in (f"{today}_{ticker}", f"{today}_{ticker.upper()}"):
        snap = col.document(doc_id).get()
        if snap.exists:
            return snap.to_dict() or {}
    try:
        q = col.where("ticker", "==", ticker.upper()).where("market", "==", "USA").limit(3).stream()
        rows = [d.to_dict() or {} for d in q]
        rows.sort(key=lambda r: r.get("date") or "", reverse=True)
        return rows[0] if rows else {}
    except Exception:
        return {}


def _sector_status(sector: str | None, sectors_map: dict) -> str | None:
    if not sector:
        return None
    if sector in sectors_map:
        v = sectors_map[sector]
        return v if isinstance(v, str) else (v or {}).get("label") or (v or {}).get("status")
    for k, v in sectors_map.items():
        if k.lower() == sector.lower():
            return v if isinstance(v, str) else (v or {}).get("label") or (v or {}).get("status")
    return None


def evaluate(
    *,
    ticker: str,
    price: float | None,
    avg_cost: float | None,
    support: float | None,
    score: float | None,
    sector_status: str | None,
    macro_signal: str | None,
) -> dict:
    if avg_cost is None or avg_cost <= 0 or price is None:
        return {
            "recommendation": "n/a",
            "conditions_met": 0,
            "conditions_required": 3,
            "pnl_pct": None,
            "note": f"{ticker}: need average cost and price to judge averaging down.",
            "checks": {},
        }

    pnl_pct = round((price / avg_cost - 1) * 100, 1)
    if pnl_pct > DRAWDOWN_PCT:
        return {
            "recommendation": "not_applicable",
            "conditions_met": 0,
            "conditions_required": 3,
            "pnl_pct": pnl_pct,
            "note": (
                f"{ticker}: drawdown {pnl_pct}% is milder than {DRAWDOWN_PCT}% threshold — "
                "averaging down is not the question today."
            ),
            "checks": {},
        }

    score_ok = score is not None and score > 40
    near_support = False
    if support and support > 0 and price is not None:
        dist = (price / support - 1) * 100
        near_support = abs(dist) <= NEAR_SUPPORT_PCT or (-1 <= dist <= NEAR_SUPPORT_PCT)
    sector_ok = (sector_status or "") != "weakening"

    checks = {
        "score_above_40": score_ok,
        "near_support": near_support,
        "sector_not_weakening": sector_ok,
    }
    met = sum(1 for v in checks.values() if v)
    recommend = "consider" if met == 3 else "wait"

    bits = []
    if recommend == "consider":
        bits.append(
            f"{ticker}: all 3 avg-down checks pass (score {score}, near support, sector OK)."
        )
        bits.append(f"Unrealized ~{pnl_pct}%. Only add if your thesis is still intact — size small.")
    else:
        fail = [k.replace("_", " ") for k, v in checks.items() if not v]
        bits.append(
            f"{ticker}: avg-down wait — {met}/3 conditions. Missing: {', '.join(fail) or 'n/a'}."
        )
        bits.append(f"P&L ~{pnl_pct}%. Do not catch a falling knife if sector/score disagree.")

    return {
        "recommendation": recommend,
        "conditions_met": met,
        "conditions_required": 4,
        "pnl_pct": pnl_pct,
        "note": " ".join(bits),
        "checks": checks,
        "score": score,
        "support": support,
        "price": price,
        "avg_cost": round(avg_cost, 2),
    }


def run(db: Any) -> dict[str, dict]:
    today = date.today().isoformat()
    uid = get_radar_user_id()
    holdings = _holdings(db, uid)
    sector_doc = _doc(db, "sector_rotation")
    sectors_map = (sector_doc or {}).get("sectors") or {}

    db.collection("agents").document("avg_down").set(
        {"updated_at": today, "layer": "beta_full"}, merge=True
    )

    out: dict[str, dict] = {}
    for h in holdings:
        rid = h.get("_id")
        ticker = (h.get("ticker") or "").upper()
        if not rid or not ticker:
            continue
        trades = _trades_for(db, uid, rid)
        avg_cost, qty = _avg_cost(trades)
        c = _latest_candidate(db, ticker)
        price = c.get("close") or c.get("price")
        try:
            price = float(price) if price is not None else _live_price(ticker)
        except (TypeError, ValueError):
            price = _live_price(ticker)
        support = c.get("support")
        try:
            support = float(support) if support is not None else None
        except (TypeError, ValueError):
            support = None
        score = c.get("score")
        try:
            score = float(score) if score is not None else None
        except (TypeError, ValueError):
            score = None
        sector = c.get("sector") or h.get("sector")
        st = _sector_status(sector, sectors_map)

        result = evaluate(
            ticker=ticker,
            price=price,
            avg_cost=avg_cost,
            support=support,
            score=score,
            sector_status=st,
            macro_signal=None,
        )
        payload = {
            "ticker": ticker,
            "radar_item_id": rid,
            "qty": qty,
            "date": today,
            "updated_at": today,
            "layer": "beta_full",
            **result,
        }
        (
            db.collection("agents")
            .document("avg_down")
            .collection("by_item")
            .document(rid)
            .set(payload, merge=True)
        )
        out[rid] = payload

    logger.info("avg_down written for %d holdings", len(out))
    return out
