"""
Portfolio Risk Summary Agent (Full — Phase 6).

Daily portfolio-level snapshot: concentration, warnings, macro alignment.
Writes agents/portfolio_summary. Optional Haiku blurb (English).
Weekly Sonnet paragraph on Mondays (or if weekly_summary missing/stale).
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date
from typing import Any

from src.agents.client import (
    ENGLISH_OUTPUT_RULE,
    get_anthropic_client,
    get_radar_user_id,
    write_agent_doc,
)

logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-5-20250929"
SECTOR_WARN_PCT = 33


def _doc(db: Any, path: str) -> dict:
    snap = db.collection("agents").document(path).get()
    return snap.to_dict() if snap.exists else {}


def _active_holdings(db: Any, uid: str) -> list[dict]:
    rows: list[dict] = []
    try:
        for doc in db.collection("radar_items").where("user_id", "==", uid).stream():
            data = doc.to_dict() or {}
            data["_id"] = doc.id
            if data.get("status") == "exited" or data.get("is_active") is False:
                continue
            if data.get("status") not in (None, "holding", "watching"):
                # keep holding + watching for exposure; prefer holding for "positions"
                pass
            rows.append(data)
    except Exception as exc:
        logger.warning("holdings load failed: %s", exc)
    return rows


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


def _exit_flags(db: Any) -> dict[str, dict]:
    out: dict[str, dict] = {}
    try:
        for d in db.collection("agents").document("radar_actions").collection("by_item").stream():
            data = d.to_dict() or {}
            out[d.id] = data
    except Exception as exc:
        logger.warning("radar_actions read failed: %s", exc)
    return out


def _build_snapshot(db: Any, holdings: list[dict], macro: dict, sector_doc: dict) -> dict:
    holding_only = [h for h in holdings if (h.get("status") or "watching") == "holding"]
    watching = [h for h in holdings if (h.get("status") or "") == "watching"]
    flags = _exit_flags(db)
    sectors_map = (sector_doc or {}).get("sectors") or {}

    scores: list[float] = []
    sector_counts: Counter[str] = Counter()
    weak: list[dict] = []
    warning_rows: list[dict] = []

    for h in holding_only:
        t = (h.get("ticker") or "").upper()
        if not t:
            continue
        c = _latest_candidate(db, t)
        sector = (c.get("sector") or h.get("sector") or "Unknown").strip()
        sector_counts[sector] += 1
        score = c.get("score")
        try:
            score_f = float(score) if score is not None else None
        except (TypeError, ValueError):
            score_f = None
        if score_f is not None:
            scores.append(score_f)
            if score_f < 45:
                weak.append({"ticker": t, "score": score_f, "sector": sector})

        flag_doc = flags.get(h.get("_id") or "", {}) or flags.get(h.get("id") or "", {})
        # also match by ticker
        if not flag_doc:
            for fd in flags.values():
                if (fd.get("ticker") or "").upper() == t:
                    flag_doc = fd
                    break
        flag = flag_doc.get("flag") or "ok"
        if flag in ("exit", "review"):
            warning_rows.append(
                {
                    "ticker": t,
                    "flag": flag,
                    "note": (flag_doc.get("note") or flag_doc.get("action") or "")[:160],
                }
            )

    n = len(holding_only) or 1
    # Ignore Unknown/blank for concentration — missing tags ≠ real sector pile-up
    known_counts = Counter(
        {s: c for s, c in sector_counts.items() if s and s.lower() not in ("unknown", "—", "-")}
    )
    unknown_n = sector_counts.get("Unknown", 0) + sector_counts.get("unknown", 0)
    top_sector, top_n = ("—", 0)
    if known_counts:
        top_sector, top_n = known_counts.most_common(1)[0]
    top_pct = round(100 * top_n / n) if holding_only and top_n else 0
    concentration_warning = bool(known_counts) and top_pct >= SECTOR_WARN_PCT and top_n >= 2

    macro_signal = (macro.get("signal") or "neutral").lower()
    # crude alignment: if concentrated in weakening sector → misaligned
    sector_label = None
    for k, v in sectors_map.items():
        if k.lower() == top_sector.lower():
            sector_label = v
            break
    if isinstance(sector_label, dict):
        sector_label = sector_label.get("label") or sector_label.get("status")

    if macro_signal == "cautious" and holding_only:
        macro_alignment = "stretched" if (concentration_warning or len(warning_rows) >= 2) else "partial"
    elif sector_label == "weakening" and top_pct >= 25:
        macro_alignment = "misaligned"
    elif macro_signal == "bullish" and not warning_rows:
        macro_alignment = "aligned"
    else:
        macro_alignment = "partial"

    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    return {
        "positions": len(holding_only),
        "watching": len(watching),
        "avg_score": avg_score,
        "warnings": len(warning_rows),
        "warning_items": warning_rows[:8],
        "weak_scores": weak[:6],
        "top_sector": top_sector,
        "top_sector_pct": top_pct,
        "concentration_warning": concentration_warning,
        "sector_tags_missing": unknown_n,
        "sector_breakdown": [
            {"sector": s, "count": c, "pct": round(100 * c / n)}
            for s, c in sector_counts.most_common(8)
        ],
        "macro_signal": macro_signal,
        "macro_alignment": macro_alignment,
        "tickers": [(h.get("ticker") or "").upper() for h in holding_only if h.get("ticker")],
    }


def _build_plain(snap: dict) -> dict:
    """Human-readable fields for the dashboard (no jargon chips as the main story)."""
    exits = [w for w in (snap.get("warning_items") or []) if w.get("flag") == "exit"]
    reviews = [w for w in (snap.get("warning_items") or []) if w.get("flag") == "review"]
    macro = (snap.get("macro_signal") or "neutral").lower()
    align = (snap.get("macro_alignment") or "partial").lower()

    if exits:
        verdict = "Needs attention"
        verdict_level = "bad"
    elif reviews or snap.get("concentration_warning") or align in ("stretched", "misaligned"):
        verdict = "Caution"
        verdict_level = "amber"
    else:
        verdict = "OK for now"
        verdict_level = "ok"

    if exits:
        names = ", ".join(w.get("ticker") or "?" for w in exits[:3])
        do_first = f"Do first: exit {names} — price hit your exit rule."
    elif reviews:
        names = ", ".join(w.get("ticker") or "?" for w in reviews[:3])
        do_first = f"Do first: review {names} — check size / thesis."
    elif snap.get("concentration_warning"):
        do_first = (
            f"Do first: avoid adding more {snap.get('top_sector')} "
            f"(~{snap.get('top_sector_pct')}% of holdings; soft cap {SECTOR_WARN_PCT}%)."
        )
    else:
        do_first = "Do first: nothing urgent on exits — follow Do today for any adds."

    if macro == "cautious" or align in ("stretched", "misaligned"):
        new_buys = "New buys: pause or keep very small — market stance is cautious."
    elif snap.get("concentration_warning"):
        new_buys = "New buys: OK only outside your crowded sector."
    elif exits:
        new_buys = "New buys: wait until exit actions are done."
    else:
        new_buys = "New buys: OK if a Priority A name fits your budget."

    facts: list[str] = []
    if snap.get("avg_score") is not None:
        score = snap["avg_score"]
        score_word = "solid" if score >= 60 else "soft" if score < 45 else "mixed"
        facts.append(f"Avg holding score {score} ({score_word}).")
    if snap.get("concentration_warning"):
        facts.append(
            f"Crowded in {snap.get('top_sector')} (~{snap.get('top_sector_pct')}%)."
        )
    elif snap.get("sector_tags_missing"):
        facts.append(
            f"Sector tags missing on {snap['sector_tags_missing']} holding(s) — "
            "concentration % is not reliable yet."
        )
    if macro == "cautious":
        facts.append("Macro backdrop: cautious / risk-off.")
    elif macro == "bullish":
        facts.append("Macro backdrop: constructive.")
    else:
        facts.append(f"Macro backdrop: {macro}.")

    summary = " ".join([do_first, new_buys] + facts[:2])
    return {
        "verdict": verdict,
        "verdict_level": verdict_level,
        "do_first": do_first,
        "new_buys": new_buys,
        "facts": facts,
        "summary": summary,
    }


def _fallback_summary(snap: dict) -> str:
    return _build_plain(snap)["summary"]


def _haiku_daily(snap: dict, plain: dict) -> str:
    client = get_anthropic_client()
    prompt = f"""Rewrite this portfolio risk note in 2 short sentences for a retail investor.
Keep the same meaning. No jargon (avoid words like alignment, stretched, concentration cap).
Start from what to do, then why.

Draft:
{plain.get('do_first')}
{plain.get('new_buys')}
Facts: {plain.get('facts')}

Snapshot (reference only): warnings={snap.get('warnings')} macro={snap.get('macro_signal')}
{ENGLISH_OUTPUT_RULE}
Return plain text only."""
    message = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=180,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()
    return text[:500] if text else plain["summary"]


def _sonnet_weekly(snap: dict, plain: dict, prev_weekly: str | None) -> str:
    client = get_anthropic_client()
    prompt = f"""Write a short weekly portfolio review (3–4 sentences).
Plain English. What improved/worsened, what to do this week, what can wait.
No jargon pile-up.

Today's plain read:
verdict={plain.get('verdict')}
{plain.get('do_first')}
{plain.get('new_buys')}
facts={plain.get('facts')}

Previous weekly: {prev_weekly or "(none)"}
{ENGLISH_OUTPUT_RULE}
Return plain text only."""
    message = client.messages.create(
        model=SONNET_MODEL,
        max_tokens=350,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()
    return text[:900] if text else ""


def _need_weekly(existing: dict) -> bool:
    today = date.today()
    # Mondays, or missing/stale (>6 days)
    if today.weekday() == 0:
        return True
    ws = existing.get("weekly_updated_at") or existing.get("weekly_summary_date")
    if not ws:
        return True
    try:
        d = date.fromisoformat(str(ws)[:10])
        return (today - d).days >= 6
    except ValueError:
        return True


def run(db: Any) -> dict:
    today = date.today().isoformat()
    uid = get_radar_user_id()
    holdings = _active_holdings(db, uid)
    macro = _doc(db, "macro_signal")
    sector = _doc(db, "sector_rotation")
    existing = _doc(db, "portfolio_summary")

    snap = _build_snapshot(db, holdings, macro, sector)
    plain = _build_plain(snap)
    summary = plain["summary"]
    try:
        summary = _haiku_daily(snap, plain)
    except Exception as exc:
        logger.warning("Haiku risk blurb failed: %s", exc)

    weekly = existing.get("weekly_summary") or ""
    weekly_date = existing.get("weekly_summary_date")
    if _need_weekly(existing):
        try:
            weekly = _sonnet_weekly(snap, plain, existing.get("weekly_summary"))
            weekly_date = today
        except Exception as exc:
            logger.warning("Sonnet weekly risk failed: %s", exc)
            # Never clone the daily blurb into Weekly — leave blank if LLM fails
            if weekly == summary:
                weekly = ""

    # Drop weekly if it is just a duplicate of daily (old fallbacks)
    if weekly and weekly.strip() == summary.strip():
        weekly = ""

    payload = {
        **snap,
        "date": today,
        "updated_at": today,
        "summary": summary,
        "verdict": plain["verdict"],
        "verdict_level": plain["verdict_level"],
        "do_first": plain["do_first"],
        "new_buys": plain["new_buys"],
        "facts": plain["facts"],
        "weekly_summary": weekly,
        "weekly_summary_date": weekly_date,
        "layer": "beta_full",
    }
    write_agent_doc(db, "portfolio_summary", payload)
    logger.info(
        "portfolio_summary: %d holdings, %d warnings, top=%s %s%%",
        snap["positions"],
        snap["warnings"],
        snap["top_sector"],
        snap["top_sector_pct"],
    )
    return payload
