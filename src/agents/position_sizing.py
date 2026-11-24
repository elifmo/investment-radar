"""
Position Sizing (Beta V1 — Phase 2).

Pure math from monthly budget + score + fit + timing. Macro is display-only elsewhere.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_BUDGET = 2000.0
_CONFIG = Path(__file__).resolve().parents[2] / "config" / "factors.yaml"


def _monthly_budget() -> float:
    try:
        raw = yaml.safe_load(_CONFIG.read_text()) or {}
        val = raw.get("monthly_budget_eur", _DEFAULT_BUDGET)
        return float(val)
    except Exception:
        return _DEFAULT_BUDGET


def evaluate_size(
    *,
    ticker: str,
    score: float | None,
    fit: str,
    timing: str,
    budget: float,
) -> dict:
    if fit == "no_fit":
        return {
            "ticker": ticker,
            "suggested_amount_eur": 0,
            "portfolio_weight_pct": 0,
            "reasoning": f"{ticker}: no allocation — does not fit portfolio.",
        }

    score_v = float(score) if score is not None else 50.0
    if score_v > 75 and fit == "good_fit":
        frac = 0.15
    elif score_v >= 65:
        frac = 0.10
    else:
        frac = 0.08

    if timing == "wait":
        frac *= 0.7  # reserve, not full deploy
    if fit == "overlap":
        frac *= 0.6

    amount = round(budget * frac, 0)
    amount = min(amount, round(budget * 0.20, 0))
    weight_pct = round((amount / budget) * 100, 1) if budget else 0

    reasoning = (
        f"{ticker}: suggest €{int(amount)} (~{weight_pct}% of €{int(budget)} monthly budget) "
        f"given score {score_v:.0f}, fit={fit}, timing={timing}."
    )
    return {
        "ticker": ticker,
        "suggested_amount_eur": int(amount),
        "portfolio_weight_pct": weight_pct,
        "reasoning": reasoning,
    }


def run_for_candidates(
    db: Any,
    candidates: list[dict],
    fit_map: dict[str, dict],
    timing_map: dict[str, dict],
) -> dict[str, dict]:
    today = date.today().isoformat()
    budget = _monthly_budget()

    db.collection("agents").document("position_sizing").set(
        {"updated_at": today, "layer": "beta_v1", "monthly_budget_eur": budget},
        merge=True,
    )

    out: dict[str, dict] = {}
    for c in candidates:
        ticker = (c.get("ticker") or "").upper()
        if not ticker:
            continue
        fit = (fit_map.get(ticker) or {}).get("fit", "good_fit")
        timing = (timing_map.get(ticker) or {}).get("timing", "wait")
        score = c.get("score")
        result = evaluate_size(
            ticker=ticker,
            score=score,
            fit=fit,
            timing=timing,
            budget=budget,
        )
        payload = {**result, "updated_at": today, "layer": "beta_v1"}
        (
            db.collection("agents")
            .document("position_sizing")
            .collection("by_ticker")
            .document(ticker)
            .set(payload, merge=True)
        )
        out[ticker] = payload

    logger.info("Position sizing written for %d candidates (budget=€%.0f)", len(out), budget)
    return out
