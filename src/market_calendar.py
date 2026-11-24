"""US market session helpers — snapshot dates aligned with official daily close."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

logger = logging.getLogger(__name__)

_NY = ZoneInfo("America/New_York")
# 16:00 ET close, plus a few minutes for Yahoo to publish the official daily bar.
# Do not use a fixed UTC hour — that is 16:00 only in summer (EDT) and 15:00 in winter (EST).
_USA_CLOSE_ET_MIN = 16 * 60 + 10


def usa_regular_close_settled(now: datetime | None = None) -> bool:
    """True if today's US regular-session close should be final on Yahoo Finance."""
    now = now or datetime.now(timezone.utc)
    et = now.astimezone(_NY)
    if et.weekday() >= 5:
        return False
    return et.hour * 60 + et.minute >= _USA_CLOSE_ET_MIN


def _last_bar_date(df: pd.DataFrame) -> str | None:
    if df is None or df.empty:
        return None
    idx = pd.to_datetime(df.index)
    if idx.tz is not None:
        idx = idx.tz_convert("America/New_York").tz_localize(None)
    return str(idx[-1].date())


def resolve_usa_snapshot_date(
    daily_data: dict[str, pd.DataFrame],
    as_of_date: str | None = None,
) -> str:
    """
    Pick the trading date whose *official daily close* should be shown.

    Before US close (or within buffer), never use today's partial bar — use the
    previous completed session so prices match TradingView's daily close.
    """
    today = date.today().isoformat()
    requested = as_of_date or today

    sample = next((df for df in daily_data.values() if df is not None and not df.empty), None)
    if sample is None or sample.empty:
        return requested

    idx = pd.to_datetime(sample.index)
    if idx.tz is not None:
        idx = idx.tz_convert("America/New_York").tz_localize(None)

    last_bar = str(idx[-1].date())

    if requested != today:
        return requested

    if usa_regular_close_settled():
        logger.info("US close settled — using latest bar %s", last_bar)
        return last_bar

    if last_bar == today and len(idx) >= 2:
        prev = str(idx[-2].date())
        logger.info(
            "US session not settled — using previous close %s (skipping partial %s)",
            prev, today,
        )
        return prev

    if last_bar != today:
        return last_bar
    return str(idx[-2].date()) if len(idx) >= 2 else today
