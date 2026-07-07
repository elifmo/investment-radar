"""
Sector heatmap data — per-stock performance + market cap for treemap dashboard.

Computes 1D / 5D / ~30D / ~6M / ~1Y price changes for the USA watchlist universe,
grouped by GICS sector. Supports historical snapshots via as_of_date (YYYY-MM-DD).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import pandas as pd
import yfinance as yf

from layers.sector_rotation import SECTOR_ETFS

logger = logging.getLogger(__name__)

_SECTOR_TO_ETF = SECTOR_ETFS

# Approximate trading-day lookbacks (21 ≈ 1 month, 126 ≈ 6 months, 252 ≈ 1 year)
_DAYS_1M = 21
_DAYS_6M = 126
_DAYS_1Y = 252


def _stock_changes(closes: pd.Series) -> dict[str, float | None]:
    """Return all standard period changes for a close series."""
    return {
        "change_1d":   _pct_change(closes, 1),
        "change_5d":   _pct_change(closes, 5),
        "change_30d":  _pct_change(closes, _DAYS_1M),
        "change_126d": _pct_change(closes, _DAYS_6M),
        "change_252d": _pct_change(closes, _DAYS_1Y),
    }


def _normalize_dates(index: pd.Index) -> pd.DatetimeIndex:
    idx = pd.to_datetime(index)
    if idx.tz is not None:
        idx = idx.tz_convert("America/New_York").tz_localize(None)
    return pd.DatetimeIndex(idx.normalize())


def _closes_as_of(closes: pd.Series, as_of_date: str | None) -> pd.Series:
    """Return daily closes up to and including as_of_date (inclusive)."""
    if not as_of_date:
        return closes.dropna()
    target = pd.Timestamp(as_of_date).normalize()
    idx = _normalize_dates(closes.index)
    mask = idx <= target
    sliced = closes.loc[mask]
    return sliced.dropna()


def _pct_change(closes: pd.Series, days: int) -> float | None:
    if len(closes) < days + 1:
        return None
    return round((float(closes.iloc[-1] / closes.iloc[-1 - days]) - 1) * 100, 2)


def _fetch_market_caps(tickers: list[str], cached: dict[str, float] | None = None) -> dict[str, float]:
    """Return {ticker: market_cap_usd}; use cached caps first, parallel-fetch the rest."""
    caps: dict[str, float] = dict(cached or {})
    missing = [t for t in tickers if t not in caps]

    def _one(ticker: str) -> tuple[str, float | None]:
        try:
            t = yf.Ticker(ticker)
            fi = getattr(t, "fast_info", None)
            cap = None
            if fi is not None:
                cap = fi.get("market_cap") or fi.get("marketCap")
            if not cap:
                info = t.info or {}
                cap = info.get("marketCap")
                if not cap and info.get("sharesOutstanding"):
                    hist = t.history(period="5d")
                    if not hist.empty:
                        cap = float(info["sharesOutstanding"]) * float(hist["Close"].iloc[-1])
            if cap and cap > 0:
                return ticker, float(cap)
        except Exception as exc:
            logger.debug("Market cap fetch failed for %s: %s", ticker, exc)
        return ticker, None

    if missing:
        workers = min(24, max(4, len(missing) // 20))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_one, t) for t in missing]
            for fut in as_completed(futures):
                ticker, cap = fut.result()
                if cap:
                    caps[ticker] = cap

    return caps


def _fetch_benchmarks(as_of_date: str | None = None) -> dict:
    """SPY (S&P 500) and UUP (US Dollar ETF) performance for benchmark strip."""
    result: dict = {}
    for symbol, label in [("SPY", "sp500"), ("UUP", "dollar")]:
        try:
            df = yf.Ticker(symbol).history(period="2y", interval="1d", auto_adjust=False)
            if df.empty:
                continue
            closes = _closes_as_of(df["Close"], as_of_date)
            if len(closes) < 2:
                continue
            result[label] = {
                "symbol": symbol,
                "label":  "S&P 500" if symbol == "SPY" else "US Dollar",
                "etf":    symbol,
                "price":  round(float(closes.iloc[-1]), 2),
                **_stock_changes(closes),
            }
        except Exception as exc:
            logger.debug("Benchmark fetch failed for %s: %s", symbol, exc)
    return result


def list_trading_days(
    daily_data: dict[str, pd.DataFrame],
    as_of_date: str | None = None,
    lookback: int = 30,
) -> list[str]:
    """Return recent trading-day ISO strings from the widest daily series."""
    best: pd.DatetimeIndex | None = None
    for df in daily_data.values():
        if df is None or df.empty:
            continue
        idx = _normalize_dates(df.index)
        if best is None or len(idx) > len(best):
            best = idx
    if best is None or len(best) == 0:
        return []

    if as_of_date:
        cutoff = pd.Timestamp(as_of_date).normalize()
        best = best[best <= cutoff]

    days = [d.strftime("%Y-%m-%d") for d in best[-lookback:]]
    return days


def compute_sector_heatmap(
    universe: list[dict],
    daily_data: dict[str, pd.DataFrame],
    as_of_date: str | None = None,
    market_caps: dict[str, float] | None = None,
    include_stocks: bool = True,
    include_benchmarks: bool = True,
) -> dict:
    """
    Build heatmap payload for Firestore sector_heatmap/{date}.

    Args:
        universe: [{ticker, sector, market_cap?}, ...]
        daily_data: {ticker: daily OHLCV DataFrame}
        as_of_date: snapshot date (YYYY-MM-DD); latest bar if omitted
        market_caps: optional pre-fetched caps (avoids refetch during backfill)
        include_stocks: if False, return sector aggregates only (faster backfill)

    Returns:
        {as_of_date, updated_at, stocks: [...], sectors: [...]}
    """
    snapshot_date = as_of_date or date.today().isoformat()
    tickers = [e["ticker"] for e in universe]
    cached_caps = {
        e["ticker"]: float(e["market_cap"])
        for e in universe
        if e.get("market_cap")
    }
    if market_caps is not None:
        caps = {**cached_caps, **market_caps}
    else:
        caps = _fetch_market_caps(tickers, cached=cached_caps)
        logger.info("Market caps ready for %d / %d tickers", len(caps), len(tickers))

    stocks: list[dict] = []
    for entry in universe:
        ticker = entry["ticker"]
        sector = entry.get("sector", "Unknown")
        df = daily_data.get(ticker)
        if df is None or df.empty:
            continue

        closes = _closes_as_of(df["Close"], as_of_date)
        if len(closes) < 2:
            continue

        price = round(float(closes.iloc[-1]), 2)
        market_cap = caps.get(ticker)
        if not market_cap:
            market_cap = max(price * 1_000_000, 1.0)

        stocks.append({
            "ticker":     ticker,
            "sector":     sector,
            "etf":        _SECTOR_TO_ETF.get(sector, ""),
            "price":      price,
            "market_cap": round(market_cap),
            **_stock_changes(closes),
        })

    sector_groups: dict[str, list[dict]] = {}
    for s in stocks:
        sector_groups.setdefault(s["sector"], []).append(s)

    sectors: list[dict] = []
    for sector, members in sorted(sector_groups.items()):
        total_cap = sum(m["market_cap"] for m in members)

        def _weighted(field: str) -> float | None:
            vals = [(m[field], m["market_cap"]) for m in members if m.get(field) is not None]
            if not vals or total_cap <= 0:
                return None
            return round(sum(v * w for v, w in vals) / total_cap, 2)

        sectors.append({
            "sector":       sector,
            "etf":          _SECTOR_TO_ETF.get(sector, ""),
            "stock_count":  len(members),
            "market_cap":   total_cap,
            "change_1d":    _weighted("change_1d"),
            "change_5d":    _weighted("change_5d"),
            "change_30d":   _weighted("change_30d"),
            "change_126d":  _weighted("change_126d"),
            "change_252d":  _weighted("change_252d"),
        })

    logger.info(
        "Sector heatmap (%s): %d stocks across %d sectors",
        snapshot_date, len(stocks), len(sectors),
    )
    benchmarks = _fetch_benchmarks(as_of_date) if include_benchmarks else {}
    payload: dict = {
        "as_of_date": snapshot_date,
        "updated_at": date.today().isoformat(),
        "sectors":    sectors,
        "benchmarks": benchmarks,
        "sector_stock_count": len(stocks),
        "price_basis": "regular_close",
        "data_source": "yahoo_finance",
    }
    if include_stocks:
        payload["stocks"] = stocks
    return payload


def merge_heatmap_payload(
    watchlist: dict,
    sp500: dict,
    *,
    store_sp500_stocks: bool = True,
) -> dict:
    """Combine watchlist (themes) + full S&P 500 (11 sectors) into one Firestore doc."""
    merged = {
        **watchlist,
        "sectors": sp500.get("sectors") or watchlist.get("sectors") or [],
        "benchmarks": watchlist.get("benchmarks") or sp500.get("benchmarks") or {},
        "meta": {
            "watchlist_count": len(watchlist.get("stocks") or []),
            "sp500_count": sp500.get("sector_stock_count") or len(sp500.get("stocks") or []),
            "sp500_sectors": len(sp500.get("sectors") or []),
        },
    }
    if store_sp500_stocks and sp500.get("stocks"):
        merged["stocks_sp500"] = sp500["stocks"]
    return merged
