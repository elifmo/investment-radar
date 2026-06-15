"""
Task 6 — Decision Engine

Combines Quality Grade, RS Rating, Sector Rotation, Macro Regime and
Earnings Calendar into a single BUY / BUY_SMALL / WATCH / SKIP decision
with a position-size multiplier.

Decision tree (3 diagrams from the spec):
  Diagram 1 — Quality gate
  Diagram 2 — High RS path
  Diagram 3 — Low RS / contrarian path
  Diagram B — Macro multiplier + earnings adjustment
"""

from dataclasses import dataclass


@dataclass
class Decision:
    decision: str   # BUY | BUY_SMALL | WATCH | SKIP
    reason: str
    size: float     # position_size_multiplier in [0.0, 1.0]


def decide(
    candidate: dict,
    rs_threshold: float = 70,
    drop_threshold: float = -0.20,
) -> Decision:
    """
    Run the decision tree for a single enriched candidate.

    Required candidate fields (None-safe — missing fields default to neutral):
      quality_grade        str  A/B/C/D
      rs_rating            int  1-99
      sector_short_status  str  LEADING/IMPROVING/WEAKENING/LAGGING
      sector_long_status   str  LEADING/IMPROVING/WEAKENING/LAGGING
      volume_ratio         float
      return_30d           float  negative = drop
      macro_regime         str  RISK_ON/RISK_OFF/NEUTRAL
      days_to_earnings     int | None
    """
    grade         = candidate.get("quality_grade") or "B"
    rs            = candidate.get("rs_rating") or 0
    sector_short  = candidate.get("sector_short_status") or "LAGGING"
    sector_long   = candidate.get("sector_long_status")  or "LAGGING"
    volume_ratio  = candidate.get("volume_ratio") or 0.0
    return_30d    = candidate.get("return_30d") or 0.0
    regime        = candidate.get("macro_regime") or "NEUTRAL"
    days_earn     = candidate.get("days_to_earnings")

    # ── Diagram 1: Quality gate ───────────────────────────────────────────────
    if grade == "D":
        return Decision("SKIP", "Quality grade D — fundamentals deteriorating", size=0.0)

    # ── Diagram 2: High RS path ───────────────────────────────────────────────
    if rs >= rs_threshold:
        sector_ok = sector_short in ("LEADING", "IMPROVING")
        volume_ok = volume_ratio >= 1.0

        if sector_ok and volume_ok:
            decision = "BUY"
            reason   = "All layers aligned"
        else:
            decision = "WATCH"
            reason   = (
                f"RS strong but sector={sector_short}, "
                f"volume={volume_ratio:.2f}x — wait 1-2 days for confirmation"
            )

    # ── Diagram 3: Low RS / contrarian path ──────────────────────────────────
    else:
        if return_30d <= drop_threshold:
            if sector_long in ("LEADING", "IMPROVING") and grade in ("A", "B"):
                decision = "BUY_SMALL"
                reason   = "Contrarian dip — quality intact, sector healthy long-term"
            else:
                decision = "SKIP"
                reason   = "Large drop and sector weak long-term — likely real decline, not a dip"
        else:
            decision = "WATCH"
            reason   = "Weak RS without a large drop — unclear, monitor"

    # ── Diagram B: Macro multiplier ───────────────────────────────────────────
    size = 1.0
    if decision == "BUY":
        if regime == "RISK_OFF":
            size    = 0.65
            reason += " | Risk-Off: reduced size"
    elif decision == "BUY_SMALL":
        size = 0.4   # contrarian sizing regardless of regime

    # ── Earnings adjustment ───────────────────────────────────────────────────
    if decision in ("BUY", "BUY_SMALL") and days_earn is not None and days_earn <= 5:
        size  *= 0.7
        reason += " | Earnings within 5 days: size reduced further"

    size = round(max(0.0, min(1.0, size)), 2)
    return Decision(decision, reason, size)
