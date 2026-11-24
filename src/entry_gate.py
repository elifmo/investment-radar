"""
Stock entry gate — score + daily Ichimoku cloud only.

Macro, sector, RS, quality, earnings are indicators elsewhere; they do not affect entry_signal.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EntryResult:
    entry_signal: str   # ENTER | WAIT | NO_SIGNAL
    reason: str
    # Backward-compatible aliases for UI / agents still reading decision fields
    decision: str       # BUY | WATCH | SKIP
    position_size_multiplier: float = 1.0


def evaluate_entry(
    score: float | int | None,
    above_cloud: bool | None,
    *,
    min_score: float = 65,
) -> EntryResult:
    """
    ENTER  — score >= min_score and close above daily cloud top
    WAIT   — score OK but not above cloud yet
    NO_SIGNAL — score below threshold
    """
    sc = float(score) if score is not None else 0.0
    cloud_ok = bool(above_cloud)

    if sc < min_score:
        return EntryResult(
            entry_signal="NO_SIGNAL",
            reason=f"Score {sc:.0f} below entry threshold ({min_score:.0f})",
            decision="SKIP",
            position_size_multiplier=0.0,
        )

    if cloud_ok:
        return EntryResult(
            entry_signal="ENTER",
            reason=f"Score {sc:.0f} + above daily cloud",
            decision="BUY",
            position_size_multiplier=1.0,
        )

    return EntryResult(
        entry_signal="WAIT",
        reason=f"Score {sc:.0f} OK — wait for price above daily cloud",
        decision="WATCH",
        position_size_multiplier=1.0,
    )
