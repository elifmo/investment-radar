"""
Fib EMA Radar — early (4h) + daily confirmation signals.

1. 1Y up-swing Fibonacci pullback to 61.8% or 78.6%
2. EMA5 crosses above EMA20 on 4h (early radar)
3. Same cross later confirmed on daily (daily_confirmed)
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import pandas as pd

from layers.fibonacci import fib_from_lookback

logger = logging.getLogger(__name__)

FIB_LABELS = ("61.8%", "78.6%")
TOL_PCT = 1.5
TOUCH_LOOKBACK = 20
CROSS_4H_LOOKBACK = 40   # search window; keep only if age ≤ MAX_AGE_DAYS
CROSS_DAILY_LOOKBACK = 12
MAX_AGE_DAYS = 5
MAX_DAILY_LAG_DAYS = 1  # daily confirm must land within 1 day of the 4h cross


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _to_date(ts) -> date | None:
    if ts is None:
        return None
    if hasattr(ts, "date"):
        try:
            return ts.date()
        except Exception:
            pass
    s = str(ts)[:10]
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def _ts_str(ts) -> str | None:
    if ts is None:
        return None
    if hasattr(ts, "isoformat"):
        try:
            return ts.isoformat()
        except Exception:
            pass
    return str(ts)


def _last_bull_cross(df: pd.DataFrame, lookback_bars: int) -> tuple[bool, Any]:
    if df is None or len(df) < 22 + lookback_bars:
        return False, None
    e5 = _ema(df["Close"], 5)
    e20 = _ema(df["Close"], 20)
    for off in range(1, lookback_bars + 1):
        i, j = -off, -off - 1
        if float(e5.iloc[j]) <= float(e20.iloc[j]) and float(e5.iloc[i]) > float(e20.iloc[i]):
            return True, df.index[i]
    return False, None


def _ema_above(df: pd.DataFrame) -> tuple[bool, float, float]:
    e5 = float(_ema(df["Close"], 5).iloc[-1])
    e20 = float(_ema(df["Close"], 20).iloc[-1])
    return e5 > e20, round(e5, 4), round(e20, 4)


def _touched_fib(
    df: pd.DataFrame,
    level: float,
    *,
    lookback: int = TOUCH_LOOKBACK,
    tol: float = TOL_PCT,
) -> tuple[bool, Any, float | None]:
    if not level or level <= 0 or len(df) < 5:
        return False, None, None
    window = df.iloc[-min(lookback, len(df)) :]
    best_dist = 999.0
    best_ts = None
    best_lo = None
    for i in range(len(window)):
        lo = float(window["Low"].iloc[i])
        dist = abs(lo - level) / level * 100
        if dist <= tol and dist < best_dist:
            best_dist = dist
            best_ts = window.index[i]
            best_lo = lo
    return best_ts is not None, best_ts, best_lo


def scan_fib_ema_radar(
    daily_data: dict[str, pd.DataFrame],
    four_hour_data: dict[str, pd.DataFrame],
    *,
    market: str = "USA",
    sector_map: dict[str, str] | None = None,
    fib_tol_pct: float = TOL_PCT,
    touch_lookback: int = TOUCH_LOOKBACK,
    max_age_days: int = MAX_AGE_DAYS,
    max_daily_lag_days: int = MAX_DAILY_LAG_DAYS,
) -> list[dict[str, Any]]:
    """
    Return radar rows sorted: daily_confirmed first, then early_4h.
    Includes both early 4h crosses and daily-confirmed setups.
    """
    sector_map = sector_map or {}
    market_u = market.upper()
    rows: list[dict[str, Any]] = []

    for ticker, raw in daily_data.items():
        if raw is None or len(raw.dropna()) < 80:
            continue
        df = raw.dropna()
        fib = fib_from_lookback(df, lookback=252, include_extensions=False)
        if fib is None or fib.direction != "up":
            continue

        touches: list[dict] = []
        for label in FIB_LABELS:
            lvl = fib.levels.get(label)
            ok, ts, lo = _touched_fib(df, float(lvl) if lvl else 0.0, lookback=touch_lookback, tol=fib_tol_pct)
            if ok and lvl is not None:
                touches.append({
                    "label": label,
                    "price": round(float(lvl), 4),
                    "touch_date": str(_to_date(ts)),
                    "touch_low": round(float(lo), 4) if lo is not None else None,
                })
        if not touches:
            continue

        fib_touch_date = max(date.fromisoformat(t["touch_date"]) for t in touches if t.get("touch_date"))

        df4 = four_hour_data.get(ticker)
        if df4 is None or len(df4.dropna()) < 30:
            continue
        df4 = df4.dropna()

        ok4, ts4 = _last_bull_cross(df4, CROSS_4H_LOOKBACK)
        if not ok4 or ts4 is None:
            continue
        d4 = _to_date(ts4)
        if d4 is None or fib_touch_date > d4:
            continue

        above4, e5_4, e20_4 = _ema_above(df4)
        ok_d, ts_d = _last_bull_cross(df, CROSS_DAILY_LOOKBACK)
        above_d, e5_d, e20_d = _ema_above(df)
        d_daily = _to_date(ts_d) if ok_d else None

        daily_lag = (d_daily - d4).days if d_daily is not None else None
        late_daily = daily_lag is not None and daily_lag > max_daily_lag_days
        if late_daily:
            continue
        daily_confirmed = bool(
            ok_d
            and d_daily is not None
            and d_daily >= d4
            and above_d
            and daily_lag is not None
            and daily_lag <= max_daily_lag_days
        )
        # Early radar: 4h cross happened; keep even if daily not confirmed yet
        # Prefer rows where 4h EMA still above OR daily confirmed
        if not above4 and not daily_confirmed:
            continue

        as_of = _to_date(df.index[-1])
        if as_of is None:
            continue
        if daily_confirmed:
            if (as_of - d_daily).days > max_age_days:
                continue
        elif (as_of - d4).days > max_age_days:
            continue

        status = "daily_confirmed" if daily_confirmed else "early_4h"
        close = round(float(df["Close"].iloc[-1]), 4)
        swing_high = float(fib.swing_high) if fib.swing_high else None
        drop_pct = round((close / swing_high - 1) * 100, 1) if swing_high else None
        display = ticker.replace(".IS", "") if market_u == "BIST" else ticker

        rows.append({
            "ticker": display,
            "yf_ticker": ticker,
            "market": market_u,
            "sector": sector_map.get(ticker, ""),
            "close": close,
            "drop_pct": drop_pct,
            "status": status,
            "fib_touches": touches,
            "fib_labels": [t["label"] for t in touches],
            "fib_touch_date": str(fib_touch_date),
            "h4_cross_at": _ts_str(ts4),
            "h4_cross_date": str(d4),
            "h4_ema5": e5_4,
            "h4_ema20": e20_4,
            "h4_still_above": above4,
            "daily_cross_at": _ts_str(ts_d) if daily_confirmed else None,
            "daily_cross_date": str(d_daily) if daily_confirmed else None,
            "daily_ema5": e5_d,
            "daily_ema20": e20_d,
            "daily_still_above": above_d,
            "swing_high": fib.swing_high,
            "swing_low": fib.swing_low,
            "swing_high_date": fib.high_date,
            "swing_low_date": fib.low_date,
            "nearest_fib": fib.nearest_level,
        })

    rows.sort(key=lambda r: (
        r.get("status") == "daily_confirmed",
        r.get("daily_cross_date") or "",
        r.get("h4_cross_date") or "",
        r["ticker"],
    ), reverse=True)
    return rows
