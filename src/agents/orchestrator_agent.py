"""
Orchestrator Agent (Beta V1 — Phase 3).

Thinking editor: ranks actions, resolves conflicts, writes agents/daily_brief.
Produces Priority A/B/Watch + Trade/Swing/Position so the UI can explain
what to do, for how long, and why — not a wall of identical Enter €100 rows.
Does NOT recompute technical scores.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any

from src.agents.client import ENGLISH_OUTPUT_RULE, get_anthropic_client, write_agent_doc

logger = logging.getLogger(__name__)

SONNET_MODEL = "claude-sonnet-4-5-20250929"
_FLAG_PRIORITY = {"exit": 1, "review": 2, "ok": 3}

# Morning plan caps — clarity over coverage
MAX_PRIORITY_A = 1
MAX_PRIORITY_B = 2
MAX_DO_TODAY = 4

# Rough ETF / core-holding hints (Position horizon)
_POSITION_HINTS = frozenset(
    {
        "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "IVV", "VUSA", "VUAG",
        "VHYL", "VWRL", "CSPX", "EQQQ", "IEMA", "SXRV", "8PSG", "SEMI",
        "NUKL", "SMH", "XLU", "XLP", "XLV", "TLT", "IEF", "GLD", "IAU",
    }
)


def _doc(db: Any, path: str) -> dict:
    snap = db.collection("agents").document(path).get()
    return snap.to_dict() if snap.exists else {}


def _subcollection(db: Any, parent: str, child: str) -> list[dict]:
    rows: list[dict] = []
    try:
        for d in db.collection("agents").document(parent).collection(child).stream():
            data = d.to_dict() or {}
            data["_id"] = d.id
            rows.append(data)
    except Exception as exc:
        logger.warning("Failed reading agents/%s/%s: %s", parent, child, exc)
    return rows


def _recent_outcomes(db: Any, limit: int = 20) -> list[dict]:
    rows: list[dict] = []
    try:
        for d in db.collection("decision_log").limit(80).stream():
            data = d.to_dict() or {}
            data["_id"] = d.id
            rows.append(data)
    except Exception as exc:
        logger.warning("decision_log read failed: %s", exc)
        return []
    rows.sort(key=lambda r: r.get("date") or "", reverse=True)
    checked = [r for r in rows if r.get("outcome_checked")]
    return (checked or rows)[:limit]


def _is_position_name(ticker: str, sector: str | None = None) -> bool:
    t = (ticker or "").upper()
    if t in _POSITION_HINTS:
        return True
    if sector and "etf" in sector.lower():
        return True
    return False


def _infer_horizon(ticker: str, timing: str, sector: str | None = None) -> tuple[str, str]:
    """Return (horizon_key, short_label)."""
    if _is_position_name(ticker, sector):
        return "position", "Position · longer hold"
    if timing == "enter_now":
        return "trade", "Trade · ~2–3 weeks"
    return "swing", "Swing · multi-week"


def _invalidation_line(ticker: str, timing_row: dict, horizon: str) -> str:
    target = timing_row.get("entry_target")
    support_bit = ""
    note = timing_row.get("note") or ""
    # Pull a $ level from note if present
    m = re.search(r"\$([0-9]+(?:\.[0-9]+)?)", note)
    if m:
        support_bit = f"~${m.group(1)}"
    elif target is not None:
        try:
            support_bit = f"~${float(target):.2f}"
        except (TypeError, ValueError):
            support_bit = ""

    if horizon == "position":
        return (
            f"{ticker}: thesis breaks if you no longer want core exposure — "
            "size slower; don’t FOMO the open."
        )
    if support_bit:
        return (
            f"Weekly close below support {support_bit} → exit. "
            "Don’t average a broken level."
        )
    return f"{ticker}: exit if the setup / thesis that put it on the list breaks."


def _thesis_line(
    ticker: str,
    *,
    fit_v: str,
    timing_v: str,
    horizon: str,
    fit_reason: str,
    timing_note: str,
    demote_reason: str | None,
) -> str:
    if demote_reason:
        return demote_reason
    bits = []
    if timing_note:
        # Strip leading "TICKER: " / "TICKER "
        cleaned = re.sub(rf"^{re.escape(ticker)}[:\s]+", "", timing_note, flags=re.I)
        bits.append(cleaned[:140])
    elif fit_reason:
        cleaned = re.sub(rf"^{re.escape(ticker)}[:\s]+", "", fit_reason, flags=re.I)
        bits.append(cleaned[:140])
    if horizon == "trade" and timing_v == "enter_now":
        bits.append("Short idea — not a forever hold.")
    elif horizon == "position":
        bits.append("Core / longer hold — no rush today.")
    if fit_v == "overlap":
        bits.append("Theme already in your book.")
    text = " ".join(b for b in bits if b).strip()
    return text[:220] if text else f"{ticker}: see scan setup."


def _build_radar_actions(exit_rows: list[dict]) -> list[dict]:
    actions = []
    for r in exit_rows:
        flag = r.get("flag") or "ok"
        action = flag if flag != "ok" else "hold"
        actions.append(
            {
                "ticker": r.get("ticker"),
                "priority": _FLAG_PRIORITY.get(flag, 9),
                "action": action,
                "label": r.get("action") or (
                    "Exit now" if action == "exit"
                    else "Review" if action == "review"
                    else "Hold"
                ),
                "reason": (r.get("note") or "")[:220],
                "thesis": (r.get("note") or "")[:220],
                "horizon": "trade" if action in ("exit", "review") else "position",
                "horizon_label": (
                    "Was a trade" if action == "exit"
                    else "Check thesis" if action == "review"
                    else "Hold"
                ),
                "radar_item_id": r.get("radar_item_id") or r.get("_id"),
            }
        )
    actions.sort(key=lambda a: (a["priority"], a.get("ticker") or ""))
    for i, a in enumerate(actions, start=1):
        a["priority"] = i
    return actions


def _candidate_score_hint(sz: dict, tm: dict, entry_signal: str | None = None) -> float:
    """Higher = better for Priority A selection."""
    amt = float(sz.get("suggested_amount_eur") or 0)
    timing = tm.get("timing") or "wait"
    base = amt
    es = (entry_signal or "").upper()
    if es == "ENTER" or timing == "enter_now":
        base += 1000
    return base


def _build_candidates_ranked(
    fit_rows: list[dict],
    timing_rows: list[dict],
    sizing_rows: list[dict],
    candidate_meta: dict[str, dict] | None = None,
) -> list[dict]:
    """Rank + assign Priority A/B/Watch and horizon. Cap identical enters."""
    meta = candidate_meta or {}
    fit = {r.get("ticker"): r for r in fit_rows}
    timing = {r.get("ticker"): r for r in timing_rows}
    sizing = {r.get("ticker"): r for r in sizing_rows}
    tickers = set(fit) | set(timing) | set(sizing)

    raw: list[dict] = []
    for t in tickers:
        if not t:
            continue
        f = fit.get(t) or {}
        tm = timing.get(t) or {}
        sz = sizing.get(t) or {}
        fit_v = f.get("fit") or "good_fit"
        if fit_v == "no_fit":
            continue
        timing_v = tm.get("timing") or "wait"
        sector = (meta.get(t) or {}).get("sector") or f.get("sector")
        entry_sig = (meta.get(t) or {}).get("entry_signal")
        horizon, horizon_label = _infer_horizon(t, timing_v, sector)
        raw.append(
            {
                "ticker": t,
                "fit": fit_v,
                "timing_raw": timing_v,
                "amount_eur": int(sz.get("suggested_amount_eur") or 0),
                "target_price": tm.get("entry_target"),
                "sector": sector,
                "entry_signal": entry_sig,
                "horizon": horizon,
                "horizon_label": horizon_label,
                "fit_reason": (f.get("reason") or "")[:220],
                "timing_note": (tm.get("note") or "")[:220],
                "sizing_note": (sz.get("reasoning") or "")[:220],
                "_score": _candidate_score_hint(sz, tm, entry_sig),
            }
        )

    raw.sort(key=lambda x: (-x["_score"], x["ticker"]))

    a_count = 0
    b_count = 0
    sector_with_a: set[str] = set()
    ranked: list[dict] = []

    for item in raw:
        t = item["ticker"]
        fit_v = item["fit"]
        timing_v = item["timing_raw"]
        sector_key = (item.get("sector") or "Unknown").strip()
        demote_reason = None
        priority_tier = "watch"
        action = "watch"

        if fit_v == "overlap":
            priority_tier = "watch"
            action = "watch"
            demote_reason = (
                f"Setup OK, but theme/overlap vs your book — not your first ticket today."
            )
        elif timing_v == "enter_now" and fit_v == "good_fit":
            if a_count < MAX_PRIORITY_A and sector_key not in sector_with_a:
                priority_tier = "A"
                action = "enter_now"
                a_count += 1
                sector_with_a.add(sector_key)
            else:
                # Same defensive cluster / already have an A enter
                priority_tier = "watch"
                action = "watch"
                if sector_key in sector_with_a:
                    demote_reason = (
                        f"Same theme as your Priority A enter — don’t double up today."
                    )
                else:
                    demote_reason = (
                        "Weaker or redundant vs Priority A — keep as Watch, not Enter €clone."
                    )
        elif timing_v == "wait" and fit_v == "good_fit":
            if b_count < MAX_PRIORITY_B:
                priority_tier = "B"
                action = "wait"
                b_count += 1
            else:
                priority_tier = "watch"
                action = "watch"
                demote_reason = "Fine idea, but no urgency after today’s plan — Watch."
        else:
            priority_tier = "watch"
            action = "watch"

        horizon = item["horizon"]
        thesis = _thesis_line(
            t,
            fit_v=fit_v,
            timing_v=timing_v,
            horizon=horizon,
            fit_reason=item["fit_reason"],
            timing_note=item["timing_note"],
            demote_reason=demote_reason,
        )
        invalidation = _invalidation_line(t, {"entry_target": item["target_price"], "note": item["timing_note"]}, horizon)

        # Only show size for A enter or B wait — hide clone € on Watch
        amount = item["amount_eur"] if priority_tier in ("A", "B") else 0

        ranked.append(
            {
                "ticker": t,
                "action": action,
                "fit": fit_v,
                "priority_tier": priority_tier,
                "horizon": horizon,
                "horizon_label": item["horizon_label"],
                "amount_eur": amount,
                "target_price": item["target_price"],
                "sector": sector_key,
                "thesis": thesis,
                "reason": thesis,  # back-compat for older UI
                "invalidation": invalidation,
                "why_today": item["timing_note"] or item["fit_reason"],
            }
        )

    # Display order: A enter → B wait → Watch (overlap last among watches)
    order = {"A": 0, "B": 1, "watch": 2}
    action_order = {"enter_now": 0, "wait": 1, "watch": 2}
    ranked.sort(
        key=lambda x: (
            order.get(x["priority_tier"], 9),
            action_order.get(x["action"], 9),
            x["ticker"],
        )
    )
    return ranked


def _budget_allocation(candidates_ranked: list[dict]) -> dict:
    enter_now = sum(
        int(c.get("amount_eur") or 0)
        for c in candidates_ranked
        if c.get("action") == "enter_now" and c.get("priority_tier") == "A"
    )
    reserved = sum(
        int(c.get("amount_eur") or 0)
        for c in candidates_ranked
        if c.get("action") == "wait" and c.get("priority_tier") == "B"
    )
    return {
        "enter_now": enter_now,
        "reserved": reserved,
        "hold": max(0, 2000 - enter_now - reserved),
    }


def _build_do_today(
    radar_actions: list[dict],
    candidates_ranked: list[dict],
) -> list[dict]:
    """Merged morning plan: exits → reviews → Priority A → one Priority B."""
    plan: list[dict] = []

    for a in radar_actions:
        if a.get("action") not in ("exit", "review"):
            continue
        plan.append(
            {
                "kind": "radar",
                "ticker": a.get("ticker"),
                "action": a.get("action"),
                "priority_tier": "exit" if a.get("action") == "exit" else "review",
                "label": a.get("label"),
                "horizon": a.get("horizon"),
                "horizon_label": a.get("horizon_label"),
                "amount_eur": 0,
                "amount_note": "Sell first" if a.get("action") == "exit" else "Before new size",
                "thesis": a.get("thesis") or a.get("reason") or "",
            }
        )

    for c in candidates_ranked:
        if c.get("priority_tier") == "A" and c.get("action") == "enter_now":
            amt = int(c.get("amount_eur") or 0)
            plan.append(
                {
                    "kind": "candidate",
                    "ticker": c.get("ticker"),
                    "action": "enter_now",
                    "priority_tier": "A",
                    "label": "Enter",
                    "horizon": c.get("horizon"),
                    "horizon_label": c.get("horizon_label"),
                    "amount_eur": amt,
                    "amount_note": f"~{round(amt / 2000 * 100)}% of monthly budget" if amt else "",
                    "thesis": c.get("thesis") or "",
                    "invalidation": c.get("invalidation") or "",
                    "fit": c.get("fit"),
                }
            )
        elif c.get("priority_tier") == "B" and len(
            [p for p in plan if p.get("priority_tier") == "B"]
        ) < 1:
            # At most one B on the hero plan
            amt = int(c.get("amount_eur") or 0)
            plan.append(
                {
                    "kind": "candidate",
                    "ticker": c.get("ticker"),
                    "action": "wait",
                    "priority_tier": "B",
                    "label": "Wait",
                    "horizon": c.get("horizon"),
                    "horizon_label": c.get("horizon_label"),
                    "amount_eur": amt,
                    "amount_note": "later / quieter day" if amt else "no rush",
                    "thesis": c.get("thesis") or "",
                    "invalidation": c.get("invalidation") or "",
                    "fit": c.get("fit"),
                }
            )

    return plan[:MAX_DO_TODAY]


def _not_today(candidates_ranked: list[dict], do_today: list[dict]) -> list[dict]:
    shown = {(p.get("ticker") or "").upper() for p in do_today}
    out = []
    for c in candidates_ranked:
        t = (c.get("ticker") or "").upper()
        if not t or t in shown:
            continue
        if c.get("priority_tier") != "watch" and c.get("action") != "watch":
            continue
        out.append(
            {
                "ticker": t,
                "thesis": c.get("thesis") or "Watch — not first ticket today.",
            }
        )
    return out[:12]


def _market_why(macro: dict, sector: dict) -> dict:
    signal = (macro.get("signal") or "neutral").replace("_", "-")
    summary = (macro.get("summary") or "").strip()
    sector_sum = (sector.get("summary") or "").strip()
    headline = summary or f"Macro reads {signal}."
    sub = sector_sum or "Sector rotation shapes which names dominate the scan."
    return {
        "headline": headline[:280],
        "detail": sub[:280],
        "signal": signal,
    }


def _one_liner(do_today: list[dict], market: dict) -> str:
    exits = [p for p in do_today if p.get("action") == "exit"]
    enters = [p for p in do_today if p.get("action") == "enter_now"]
    waits = [p for p in do_today if p.get("action") == "wait"]
    parts = []
    if exits:
        parts.append(f"exit {exits[0].get('ticker')}")
    if enters:
        h = enters[0].get("horizon") or "trade"
        parts.append(f"one {h.title()} enter ({enters[0].get('ticker')})")
    if waits and not enters:
        parts.append(f"wait on {waits[0].get('ticker')}")
    if not parts:
        return "No forced trades today — hold and wait for a cleaner setup."
    core = ", then ".join(parts) if len(parts) > 1 else parts[0]
    return f"Do today: {core}. Everything else can wait."


def _fallback_summary(
    macro: dict,
    radar_actions: list[dict],
    candidates_ranked: list[dict],
    do_today: list[dict],
    market: dict,
) -> str:
    return _one_liner(do_today, market)


def _memory_blurb(outcomes: list[dict]) -> str:
    if not outcomes:
        return "No scored decisions yet — learning loop is warming up."
    correct = sum(1 for o in outcomes if o.get("outcome") == "correct")
    incorrect = sum(1 for o in outcomes if o.get("outcome") == "incorrect")
    pending = sum(1 for o in outcomes if not o.get("outcome_checked"))
    lines = [f"Recent log: {correct} correct, {incorrect} incorrect, {pending} pending."]
    fails = [o for o in outcomes if o.get("outcome") == "incorrect"][:3]
    for f in fails:
        lines.append(
            f"- Miss: {f.get('ticker')} {f.get('decision_type')} — {(f.get('reasoning') or '')[:80]}"
        )
    wins = [o for o in outcomes if o.get("outcome") == "correct"][:2]
    for w in wins:
        lines.append(f"- Hit: {w.get('ticker')} {w.get('decision_type')}")
    return "\n".join(lines)


def _load_candidate_meta(db: Any) -> dict[str, dict]:
    """Sector + entry_signal from latest USA daily_candidates docs."""
    meta: dict[str, dict] = {}
    try:
        from datetime import date, timedelta
        col = db.collection("daily_candidates")
        for days_back in range(0, 8):
            day = (date.today() - timedelta(days=days_back)).isoformat()
            try:
                docs = list(
                    col.where("date", "==", day).where("market", "==", "USA").stream()
                )
            except Exception:
                docs = []
            if not docs:
                continue
            for d in docs:
                data = d.to_dict() or {}
                t = (data.get("ticker") or "").upper()
                if t:
                    meta[t] = {
                        "sector": data.get("sector"),
                        "entry_signal": data.get("entry_signal"),
                    }
            if meta:
                break
    except Exception as exc:
        logger.debug("candidate meta load skipped: %s", exc)
    return meta


def _sonnet_polish(payload: dict, memory: str) -> dict:
    """Ask Sonnet to refine market_why + one-liner; keep ranked lists from code."""
    client = get_anthropic_client()
    compact = {
        "market_why": payload.get("market_why"),
        "do_today": payload.get("do_today"),
        "not_today": (payload.get("not_today") or [])[:8],
        "macro_context": payload.get("macro_context"),
        "draft_summary": payload.get("summary"),
        "memory": memory,
    }
    prompt = f"""You are the Orchestrator for an investment dashboard morning brief.
You receive a pre-built "Do today" plan. Do NOT invent tickers or change priorities.
Your job: make the English crystal clear for a retail investor.

Input JSON:
{json.dumps(compact, ensure_ascii=True, default=str)}

Return ONLY valid JSON with keys:
- summary: one short sentence starting with "Do today:" (exit before buy if both exist).
- market_why: object with "headline" (1 sentence: why these names exist today) and "detail" (1 sentence: portfolio overlap / what to de-prioritize).
- conflict_notes: array of short strings (empty if none).
- lesson: one sentence from memory (or say learning is still warming up).

Rules:
- Prefer Priority / Trade / Swing / Position language.
- Never say "buy everything" or list 6 identical enters.
- Be direct. English only.

{ENGLISH_OUTPUT_RULE}"""

    message = client.messages.create(
        model=SONNET_MODEL,
        max_tokens=550,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()
    if "```" in text:
        m = re.search(r"\{[\s\S]*\}", text)
        text = m.group(0) if m else text
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Orchestrator JSON parse failed — keeping draft summary")
        return {
            "summary": payload.get("summary"),
            "market_why": payload.get("market_why"),
            "conflict_notes": [],
            "lesson": "Learning loop active; treat early outcomes carefully.",
        }
    mw = parsed.get("market_why")
    if not isinstance(mw, dict):
        mw = payload.get("market_why")
    else:
        base = payload.get("market_why") or {}
        mw = {
            "headline": mw.get("headline") or base.get("headline"),
            "detail": mw.get("detail") or base.get("detail"),
            "signal": base.get("signal"),
        }
    return {
        "summary": parsed.get("summary") or payload.get("summary"),
        "market_why": mw,
        "conflict_notes": parsed.get("conflict_notes") or [],
        "lesson": parsed.get("lesson") or "",
    }


def run(db: Any) -> dict:
    today = date.today().isoformat()
    macro = _doc(db, "macro_signal")
    sector = _doc(db, "sector_rotation")

    exit_rows = _subcollection(db, "radar_actions", "by_item")
    fit_rows = _subcollection(db, "candidate_fit", "by_ticker")
    timing_rows = _subcollection(db, "entry_timing", "by_ticker")
    sizing_rows = _subcollection(db, "position_sizing", "by_ticker")
    outcomes = _recent_outcomes(db)
    candidate_meta = _load_candidate_meta(db)

    radar_actions = _build_radar_actions(exit_rows)
    candidates_ranked = _build_candidates_ranked(
        fit_rows, timing_rows, sizing_rows, candidate_meta
    )
    holdings_ok = [a["ticker"] for a in radar_actions if a.get("action") == "hold"]
    do_today = _build_do_today(radar_actions, candidates_ranked)
    not_today = _not_today(candidates_ranked, do_today)
    budget = _budget_allocation(candidates_ranked)
    market = _market_why(macro, sector)

    macro_ctx = (
        f"{(macro.get('signal') or 'neutral').title()}"
        + (f" — {macro.get('summary', '')[:120]}" if macro.get("summary") else "")
    )
    if sector.get("summary"):
        macro_ctx = f"{macro_ctx} | Sectors: {sector['summary'][:120]}"

    draft = {
        "date": today,
        "macro_context": macro_ctx,
        "market_why": market,
        "do_today": do_today,
        "not_today": not_today,
        "my_radar_actions": radar_actions,
        "candidates_ranked": candidates_ranked,
        "no_action_needed": holdings_ok,
        "holdings_ok": holdings_ok,
        "budget_allocation": budget,
        "summary": _fallback_summary(macro, radar_actions, candidates_ranked, do_today, market),
        "guidance_version": 2,
    }

    memory = _memory_blurb(outcomes)
    try:
        polished = _sonnet_polish(draft, memory)
        draft["summary"] = polished.get("summary") or draft["summary"]
        draft["market_why"] = polished.get("market_why") or draft["market_why"]
        draft["conflict_notes"] = polished.get("conflict_notes") or []
        draft["lesson"] = polished.get("lesson") or ""
    except Exception as exc:
        logger.warning("Sonnet orchestrator failed (%s) — code brief only", exc)
        draft["conflict_notes"] = []
        draft["lesson"] = memory.split("\n")[0]

    draft["updated_at"] = today
    draft["layer"] = "beta_v1"
    write_agent_doc(db, "daily_brief", draft)
    logger.info(
        "daily_brief written: %d do_today, %d candidates (A/B/Watch)",
        len(do_today),
        len(candidates_ranked),
    )
    return draft
