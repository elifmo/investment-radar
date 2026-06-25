import logging

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_REQUIRED_COLUMNS = {"Open", "High", "Low", "Close", "Volume"}
_MIN_ROWS_DAILY = 60
_MIN_ROWS_4H = 20


def _fetch_ohlcv(tickers: list[str], period: str, interval: str) -> dict[str, pd.DataFrame]:
    result: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            df = yf.Ticker(ticker).history(period=period, interval=interval)
            if df.empty or not _REQUIRED_COLUMNS.issubset(df.columns):
                logger.warning("No valid data for %s (%s) — skipping", ticker, interval)
                continue
            result[ticker] = df[list(_REQUIRED_COLUMNS)]
            logger.info("Fetched %d rows for %s (%s)", len(df), ticker, interval)
        except Exception as exc:
            logger.error("Failed to fetch %s (%s): %s", ticker, interval, exc)
    return result


def fetch_ticker_data(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Fetch 1-year daily OHLCV for a small ticker list (one-by-one)."""
    return _fetch_ohlcv(tickers, period="1y", interval="1d")


def fetch_batch_daily(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Batch download daily OHLCV for large ticker lists (single yfinance call).

    Faster than fetch_ticker_data() for 50+ tickers.
    Falls back to individual fetch on failure.
    """
    if not tickers:
        return {}

    result: dict[str, pd.DataFrame] = {}
    try:
        raw = yf.download(
            tickers=" ".join(tickers),
            period="1y",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            threads=True,
            progress=False,
        )
        for ticker in tickers:
            try:
                if len(tickers) == 1:
                    df = raw.copy()
                else:
                    df = raw[ticker].copy()
                df = df.dropna(how="all")
                if df.empty or len(df) < _MIN_ROWS_DAILY:
                    logger.warning("Insufficient data for %s in batch — skipping", ticker)
                    continue
                # Normalise column names (batch download uses Price/Ticker multi-index)
                df.columns = [c if isinstance(c, str) else c[0] for c in df.columns]
                if not _REQUIRED_COLUMNS.issubset(df.columns):
                    logger.warning("Missing columns for %s — skipping", ticker)
                    continue
                result[ticker] = df[list(_REQUIRED_COLUMNS)]
                logger.info("Batch fetched %d rows for %s", len(df), ticker)
            except Exception as exc:
                logger.warning("Batch parse failed for %s: %s — retrying individually", ticker, exc)
                fallback = _fetch_ohlcv([ticker], "1y", "1d")
                result.update(fallback)
    except Exception as exc:
        logger.error("Batch download failed: %s — falling back to individual fetches", exc)
        return _fetch_ohlcv(tickers, "1y", "1d")

    return result


def fetch_hourly_data(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Fetch 7-day hourly OHLCV data."""
    return _fetch_ohlcv(tickers, period="7d", interval="1h")


def fetch_batch_4h(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Batch download 4-hour OHLCV (~60 days) for intraday scanning.

    Used by the pipeline when scan.timeframe is 4h. Falls back to
    individual fetches on failure.
    """
    if not tickers:
        return {}

    result: dict[str, pd.DataFrame] = {}
    try:
        raw = yf.download(
            tickers=" ".join(tickers),
            period="60d",
            interval="4h",
            group_by="ticker",
            auto_adjust=True,
            threads=True,
            progress=False,
        )
        for ticker in tickers:
            try:
                if len(tickers) == 1:
                    df = raw.copy()
                else:
                    df = raw[ticker].copy()
                df = df.dropna(how="all")
                if df.empty or len(df) < _MIN_ROWS_4H:
                    logger.warning("Insufficient 4h data for %s in batch — skipping", ticker)
                    continue
                df.columns = [c if isinstance(c, str) else c[0] for c in df.columns]
                if not _REQUIRED_COLUMNS.issubset(df.columns):
                    logger.warning("Missing columns for %s (4h) — skipping", ticker)
                    continue
                result[ticker] = df[list(_REQUIRED_COLUMNS)]
                logger.info("Batch fetched %d 4h rows for %s", len(df), ticker)
            except Exception as exc:
                logger.warning("4h batch parse failed for %s: %s — retrying individually", ticker, exc)
                fallback = _fetch_ohlcv([ticker], "60d", "4h")
                for t, fdf in fallback.items():
                    if len(fdf) >= _MIN_ROWS_4H:
                        result[t] = fdf
    except Exception as exc:
        logger.error("4h batch download failed: %s — falling back to individual fetches", exc)
        for ticker, df in _fetch_ohlcv(tickers, "60d", "4h").items():
            if len(df) >= _MIN_ROWS_4H:
                result[ticker] = df

    return result


def get_latest_price(df: pd.DataFrame) -> float:
    return float(df["Close"].iloc[-1])


def get_latest_volume(df: pd.DataFrame) -> float:
    return float(df["Volume"].iloc[-1])


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    tickers = ["MSFT", "NVDA", "AAPL", "TSLA", "GOOGL"]
    logger.info("Testing batch download with %d tickers...", len(tickers))
    data = fetch_batch_daily(tickers)
    for ticker, df in data.items():
        logger.info("%s: %d rows, last close: $%.2f", ticker, len(df), get_latest_price(df))
