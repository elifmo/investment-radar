"""Daily Ichimoku cloud (9/26/52) — shared by stock entry gate and crypto signals."""

from __future__ import annotations

import pandas as pd

TENKAN = 9
KIJUN = 26
SENKOU_B = 52


def _mid(high: pd.Series, low: pd.Series, period: int) -> pd.Series:
    return (high.rolling(period).max() + low.rolling(period).min()) / 2


def add_ichimoku(df: pd.DataFrame) -> pd.DataFrame:
    """Append tenkan, kijun, span_a/b, cloud_top, cloud_bottom columns."""
    d = df.copy()
    h, l = d["High"], d["Low"]
    tenkan = _mid(h, l, TENKAN)
    kijun = _mid(h, l, KIJUN)
    span_a = ((tenkan + kijun) / 2).shift(KIJUN)
    span_b = _mid(h, l, SENKOU_B).shift(KIJUN)
    d["tenkan"] = tenkan
    d["kijun"] = kijun
    d["span_a"] = span_a
    d["span_b"] = span_b
    d["cloud_top"] = pd.concat([span_a, span_b], axis=1).max(axis=1)
    d["cloud_bottom"] = pd.concat([span_a, span_b], axis=1).min(axis=1)
    return d


def cloud_state_at_close(df: pd.DataFrame) -> dict | None:
    """
    Latest-bar cloud position.

    Returns None if insufficient history or NaN cloud levels.
    """
    if df is None or len(df) < SENKOU_B + KIJUN + 5:
        return None

    d = add_ichimoku(df)
    row = d.iloc[-1]
    close = float(row["Close"])
    ctop = row["cloud_top"]
    cbot = row["cloud_bottom"]
    if pd.isna(ctop) or pd.isna(cbot):
        return None

    ctop_f = float(ctop)
    cbot_f = float(cbot)
    above = close > ctop_f
    below = close < cbot_f
    in_cloud = not above and not below

    cloud_breakout = False
    cloud_break_down = False
    if len(d) >= 2:
        prev = d.iloc[-2]
        prev_close = float(prev["Close"])
        prev_top = prev["cloud_top"]
        prev_bot = prev["cloud_bottom"]
        if pd.notna(prev_top):
            cloud_breakout = above and prev_close <= float(prev_top)
        if pd.notna(prev_bot):
            cloud_break_down = below and prev_close >= float(prev_bot)

    return {
        "close": round(close, 4),
        "cloud_top": round(ctop_f, 4),
        "cloud_bottom": round(cbot_f, 4),
        "tenkan": round(float(row["tenkan"]), 4) if pd.notna(row["tenkan"]) else None,
        "kijun": round(float(row["kijun"]), 4) if pd.notna(row["kijun"]) else None,
        "above_cloud": above,
        "below_cloud": below,
        "in_cloud": in_cloud,
        "cloud_breakout": cloud_breakout,
        "cloud_break_down": cloud_break_down,
    }
