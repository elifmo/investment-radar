"""
Fibonacci retracement / extension levels from a swing high–low range.

Levels: 0, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100% (+ optional extensions).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

Direction = Literal["up", "down"]  # up = swing low→high; down = swing high→low

RETRACEMENT_RATIOS = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)
EXTENSION_RATIOS = (1.272, 1.618, 2.0)


@dataclass
class FibLevels:
    swing_high: float
    swing_low: float
    high_date: str
    low_date: str
    direction: Direction
    levels: dict[str, float]  # label → price
    close: float
    nearest_level: str | None
    nearest_pct: float | None


def _label(ratio: float) -> str:
    if ratio == 0.0:
        return "0%"
    if ratio == 1.0:
        return "100%"
    if ratio == 0.5:
        return "50%"
    pct = f"{ratio * 100:.1f}".rstrip("0").rstrip(".")
    return f"{pct}%"


def price_at_ratio(high: float, low: float, ratio: float, direction: Direction) -> float:
    """
    Retracement price for a move.
    - direction=up (impulse up): 0% = high, 100% = low (pullback from top)
    - direction=down (impulse down): 0% = low, 100% = high (bounce from bottom)
    """
    span = high - low
    if direction == "up":
        return high - span * ratio
    return low + span * ratio


def fib_from_swing(
    high: float,
    low: float,
    *,
    high_date: str = "",
    low_date: str = "",
    direction: Direction = "up",
    close: float | None = None,
    include_extensions: bool = False,
) -> FibLevels:
    if high < low:
        high, low = low, high
    ratios = list(RETRACEMENT_RATIOS)
    if include_extensions:
        ratios.extend(EXTENSION_RATIOS)

    levels = {_label(r): round(price_at_ratio(high, low, r, direction), 4) for r in ratios}

    nearest_level = None
    nearest_pct = None
    if close is not None and levels:
        best = min(levels.items(), key=lambda kv: abs(kv[1] - close))
        nearest_level = best[0]
        nearest_pct = round((close / best[1] - 1) * 100, 2) if best[1] else None

    return FibLevels(
        swing_high=round(high, 4),
        swing_low=round(low, 4),
        high_date=high_date,
        low_date=low_date,
        direction=direction,
        levels=levels,
        close=round(close, 4) if close is not None else 0.0,
        nearest_level=nearest_level,
        nearest_pct=nearest_pct,
    )


def fib_from_lookback(
    df: pd.DataFrame,
    *,
    lookback: int = 252,
    direction: Direction | None = None,
    include_extensions: bool = False,
) -> FibLevels | None:
    """
    Auto swing: max High / min Low over lookback.
    Direction inferred from which came first (or override).
    """
    if df is None or len(df) < 20:
        return None

    d = df.iloc[-min(len(df), lookback):].copy()
    hi_idx = int(d["High"].values.argmax())
    lo_idx = int(d["Low"].values.argmin())
    high = float(d["High"].iloc[hi_idx])
    low = float(d["Low"].iloc[lo_idx])
    high_date = str(d.index[hi_idx].date()) if hasattr(d.index[hi_idx], "date") else str(d.index[hi_idx])
    low_date = str(d.index[lo_idx].date()) if hasattr(d.index[lo_idx], "date") else str(d.index[lo_idx])
    close = float(d["Close"].iloc[-1])

    if direction is None:
        # If low happened after high → impulse down, then bounce (fib from high→low)
        # If high after low → impulse up, then pullback (fib from low→high = up)
        direction = "down" if lo_idx > hi_idx else "up"

    return fib_from_swing(
        high,
        low,
        high_date=high_date,
        low_date=low_date,
        direction=direction,
        close=close,
        include_extensions=include_extensions,
    )
