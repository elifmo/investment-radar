"""
Auto trendline breakout — pivot-based resistance/support lines.

Bullish: price closes above a descending resistance trendline (lower highs).
Bearish: price closes below an ascending support trendline (higher lows).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

Signal = Literal["BULL_BREAKOUT", "BEAR_BREAKOUT", "NONE"]

LOOKBACK_BARS = 252  # ~1 trading year of daily bars


@dataclass
class TrendlineBreakout:
    signal: Signal
    line_type: str
    close: float
    line_level: float
    break_pct: float
    touches: int
    slope_pct_per_bar: float
    pivot_dates: list[str]
    reason: str


def _pivot_highs(df: pd.DataFrame, dates: list[str], window: int = 5) -> list[tuple[int, float, str]]:
    out: list[tuple[int, float, str]] = []
    for i in range(window, len(df) - window):
        hi = float(df["High"].iloc[i])
        if hi == float(df["High"].iloc[i - window : i + window + 1].max()):
            out.append((i, hi, dates[i]))
    return out


def _pivot_lows(df: pd.DataFrame, dates: list[str], window: int = 5) -> list[tuple[int, float, str]]:
    out: list[tuple[int, float, str]] = []
    for i in range(window, len(df) - window):
        lo = float(df["Low"].iloc[i])
        if lo == float(df["Low"].iloc[i - window : i + window + 1].min()):
            out.append((i, lo, dates[i]))
    return out


def _line_at(slope: float, intercept: float, idx: int) -> float:
    return slope * idx + intercept


def _fit_line(p1: tuple[int, float], p2: tuple[int, float]) -> tuple[float, float]:
    i1, y1 = p1
    i2, y2 = p2
    if i2 == i1:
        return 0.0, y1
    slope = (y2 - y1) / (i2 - i1)
    return slope, y1 - slope * i1


def _count_touches(
    df: pd.DataFrame,
    slope: float,
    intercept: float,
    i_start: int,
    i_end: int,
    *,
    kind: Literal["resistance", "support"],
    tol_pct: float = 1.5,
) -> int:
    touches = 0
    for i in range(i_start, i_end + 1):
        level = _line_at(slope, intercept, i)
        if level <= 0:
            continue
        if kind == "resistance":
            hi = float(df["High"].iloc[i])
            if abs(hi - level) / level * 100 <= tol_pct:
                touches += 1
        else:
            lo = float(df["Low"].iloc[i])
            if abs(lo - level) / level * 100 <= tol_pct:
                touches += 1
    return touches


def _valid_resistance_segment(
    df: pd.DataFrame,
    slope: float,
    intercept: float,
    i1: int,
    i2: int,
) -> bool:
    """Line must slope down; bodies should stay mostly below until breakout."""
    if slope >= 0:
        return False
    for i in range(i1, i2):
        level = _line_at(slope, intercept, i)
        if float(df["Close"].iloc[i]) > level * 1.02:
            return False
    return True


def _valid_support_segment(
    df: pd.DataFrame,
    slope: float,
    intercept: float,
    i1: int,
    i2: int,
) -> bool:
    if slope <= 0:
        return False
    for i in range(i1, i2):
        level = _line_at(slope, intercept, i)
        if float(df["Close"].iloc[i]) < level * 0.98:
            return False
    return True


def find_descending_resistance_geometry(
    df: pd.DataFrame,
    *,
    lookback: int = 252,
    pivot_window: int = 5,
    min_touches: int = 2,
    require_breakout: bool = False,
) -> dict | None:
    """
    Return descending resistance line geometry for plotting / detection.

    If require_breakout=False, returns the most recent valid descending-high
    trendline even when the latest bar has not broken out yet.
    """
    if df is None or len(df) < 60:
        return None

    d = df.iloc[-min(len(df), lookback):].copy()
    dates = [str(x.date()) if hasattr(x, "date") else str(x) for x in d.index]
    d = d.reset_index(drop=True)
    n = len(d)
    if n < pivot_window * 2 + 10:
        return None

    close = float(d["Close"].iloc[-1])
    prev_close = float(d["Close"].iloc[-2])
    highs = _pivot_highs(d, dates, pivot_window)

    best_breakout: dict | None = None
    best_line: dict | None = None

    for j in range(len(highs) - 1, 0, -1):
        for i in range(j - 1, -1, -1):
            p1, p2 = highs[i], highs[j]
            if p2[1] >= p1[1]:
                continue
            slope, intercept = _fit_line((p1[0], p1[1]), (p2[0], p2[1]))
            if not _valid_resistance_segment(d, slope, intercept, p1[0], p2[0]):
                continue
            touches = _count_touches(d, slope, intercept, p1[0], p2[0], kind="resistance")
            if touches < min_touches:
                continue

            lvl_now = _line_at(slope, intercept, n - 1)
            geom = {
                "p1_idx": p1[0],
                "p1_price": p1[1],
                "p1_date": p1[2],
                "p2_idx": p2[0],
                "p2_price": p2[1],
                "p2_date": p2[2],
                "slope": slope,
                "intercept": intercept,
                "line_today": lvl_now,
                "touches": touches,
                "close": close,
                "break_pct": (close / lvl_now - 1) * 100 if lvl_now else 0.0,
                "has_breakout": close > lvl_now and prev_close <= _line_at(slope, intercept, n - 2),
                "lookback_bars": n,
            }
            if best_line is None or p2[0] > best_line["p2_idx"]:
                best_line = geom

            if geom["has_breakout"]:
                if best_breakout is None or geom["break_pct"] > best_breakout["break_pct"]:
                    best_breakout = geom

    if require_breakout:
        return best_breakout
    return best_breakout or best_line


def detect_trendline_breakout(
    df: pd.DataFrame,
    *,
    lookback: int = 252,  # ~1 trading year
    pivot_window: int = 5,
    min_touches: int = 2,
) -> TrendlineBreakout | None:
    """
    Detect auto trendline breakout on the latest bar.

    Uses the best recent descending-high or ascending-low pivot pair.
    """
    if df is None or len(df) < 60:
        return None

    d = df.iloc[-min(len(df), lookback):].copy()
    dates = [str(x.date()) if hasattr(x, "date") else str(x) for x in d.index]
    d = d.reset_index(drop=True)
    n = len(d)
    if n < pivot_window * 2 + 10:
        return None

    close = float(d["Close"].iloc[-1])
    prev_close = float(d["Close"].iloc[-2])
    idx_now = n - 1
    idx_prev = n - 2

    bull_geom = find_descending_resistance_geometry(
        df, lookback=lookback, pivot_window=pivot_window, min_touches=min_touches, require_breakout=True,
    )
    best_bull: TrendlineBreakout | None = None
    if bull_geom:
        p1d, p2d = bull_geom["p1_date"], bull_geom["p2_date"]
        best_bull = TrendlineBreakout(
            signal="BULL_BREAKOUT",
            line_type="descending_resistance",
            close=round(close, 4),
            line_level=round(bull_geom["line_today"], 4),
            break_pct=round(bull_geom["break_pct"], 2),
            touches=bull_geom["touches"],
            slope_pct_per_bar=round(bull_geom["slope"] / bull_geom["line_today"] * 100, 4)
            if bull_geom["line_today"]
            else 0.0,
            pivot_dates=[p1d, p2d],
            reason=f"Broke above descending trendline ({p1d} → {p2d})",
        )

    lows = _pivot_lows(d, dates, pivot_window)

    best_bear: TrendlineBreakout | None = None
    for j in range(len(lows) - 1, 0, -1):
        for i in range(j - 1, -1, -1):
            p1, p2 = lows[i], lows[j]
            if p2[1] <= p1[1]:
                continue
            slope, intercept = _fit_line((p1[0], p1[1]), (p2[0], p2[1]))
            if not _valid_support_segment(d, slope, intercept, p1[0], p2[0]):
                continue
            touches = _count_touches(d, slope, intercept, p1[0], p2[0], kind="support")
            if touches < min_touches:
                continue
            lvl_now = _line_at(slope, intercept, idx_now)
            lvl_prev = _line_at(slope, intercept, idx_prev)
            if close < lvl_now and prev_close >= lvl_prev:
                brk = (lvl_now / close - 1) * 100
                cand = TrendlineBreakout(
                    signal="BEAR_BREAKOUT",
                    line_type="ascending_support",
                    close=round(close, 4),
                    line_level=round(lvl_now, 4),
                    break_pct=round(brk, 2),
                    touches=touches,
                    slope_pct_per_bar=round(slope / lvl_now * 100, 4) if lvl_now else 0.0,
                    pivot_dates=[p1[2], p2[2]],
                    reason=f"Broke below ascending trendline ({p1[2]} → {p2[2]})",
                )
                if best_bear is None or brk > best_bear.break_pct:
                    best_bear = cand
        if best_bear:
            break

    if best_bull and best_bear:
        return best_bull if best_bull.break_pct >= best_bear.break_pct else best_bear
    return best_bull or best_bear
