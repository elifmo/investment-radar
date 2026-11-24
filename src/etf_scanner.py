"""
Daily ETF technical scanner — EUR-focused support/resistance + strategy signals.

Outputs rows suitable for Excel export and Firestore etf_scans/{date}.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
import yfinance as yf

logger = logging.getLogger(__name__)

_CONFIG = Path(__file__).parent.parent / "config" / "etfs.yaml"


def load_etf_config(config_path: Path | None = None) -> list[dict]:
    path = config_path or _CONFIG
    raw = yaml.safe_load(path.read_text()) or {}
    return list(raw.get("etfs") or [])


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0).rolling(period).mean()
    down = (-delta.clip(upper=0)).rolling(period).mean()
    rs = up / down
    return 100 - (100 / (1 + rs))


def _cluster_levels(points: list[float], tolerance: float = 0.025) -> list[dict[str, Any]]:
    if not points:
        return []
    clusters: list[dict[str, Any]] = []
    for level in sorted(points, reverse=True):
        merged = False
        for cluster in clusters:
            center = cluster["price"]
            if abs(level - center) / center < tolerance:
                cluster["price"] = (cluster["price"] * cluster["touches"] + level) / (cluster["touches"] + 1)
                cluster["touches"] += 1
                merged = True
                break
        if not merged:
            clusters.append({"price": level, "touches": 1})
    return sorted(clusters, key=lambda x: x["price"], reverse=True)


def _swing_levels(df: pd.DataFrame, window: int = 4) -> tuple[list[dict], list[dict]]:
    highs: list[float] = []
    lows: list[float] = []
    for i in range(window, len(df) - window):
        hi_window = df["High"].iloc[i - window : i + window + 1]
        lo_window = df["Low"].iloc[i - window : i + window + 1]
        if df["High"].iloc[i] >= hi_window.max():
            highs.append(float(df["High"].iloc[i]))
        if df["Low"].iloc[i] <= lo_window.min():
            lows.append(float(df["Low"].iloc[i]))
    return _cluster_levels(highs), _cluster_levels(lows)


def _pct_change(price: float, closes: pd.Series, days: int) -> float | None:
    if len(closes) < days + 1:
        return None
    return round((price / float(closes.iloc[-1 - days]) - 1) * 100, 2)


def _trend_label(price: float, e20: float, e50: float, e200: float, chg_21d: float | None, rsi: float) -> str:
    score = sum([
        price > e20,
        e20 > e50,
        e50 > e200,
        (chg_21d or 0) > 0,
        45 <= rsi <= 70,
    ])
    if score <= 1:
        return "Weak"
    if score <= 3:
        return "Neutral"
    return "Strong"


def _signal_label(price: float, e20: float, e50: float, rsi: float, chg_5d: float | None) -> str:
    if rsi > 70:
        return "Overbought"
    if rsi < 40:
        return "Oversold"
    if price > e20 and (chg_5d or 0) > 0:
        return "Momentum"
    if price < e20 and price > e50:
        return "Pullback"
    if price < e50:
        return "Downtrend"
    return "Neutral"


def _action_label(trend: str, signal: str) -> str:
    if signal == "Overbought":
        return "Wait — pullback"
    if signal == "Oversold":
        return "Small size — at support"
    if signal == "Pullback":
        return "Wait for support"
    if trend == "Strong" and signal in ("Momentum", "Neutral"):
        return "Buy — pullback limit"
    return "Watch"


def scan_etf(entry: dict, fx_eurusd: float | None = None) -> dict[str, Any] | None:
    """Run technical scan for one ETF config entry."""
    ticker = entry["ticker"]
    ccy = entry.get("currency", "EUR")

    try:
        daily = yf.download(ticker, period="1y", interval="1d", auto_adjust=False, progress=False)
    except Exception as exc:
        logger.warning("Fetch failed for %s: %s", ticker, exc)
        return None

    if daily is None or daily.empty:
        logger.warning("No data for %s", ticker)
        return None

    if isinstance(daily.columns, pd.MultiIndex):
        daily.columns = daily.columns.get_level_values(0)

    df = daily.dropna().copy()
    if len(df) < 60:
        logger.warning("Insufficient history for %s", ticker)
        return None

    df["EMA20"] = _ema(df["Close"], 20)
    df["EMA50"] = _ema(df["Close"], 50)
    df["EMA200"] = _ema(df["Close"], 200)
    df["RSI"] = _rsi(df["Close"])

    last = df.iloc[-1]
    price_native = float(last["Close"])
    e20 = float(last["EMA20"])
    e50 = float(last["EMA50"])
    e200 = float(last["EMA200"])
    rsi = float(last["RSI"])

    if ccy == "USD" and fx_eurusd:
        to_eur = lambda x: round(x / fx_eurusd, 2)
        price = to_eur(price_native)
    else:
        to_eur = lambda x: round(x, 2)
        price = round(price_native, 2)

    resistances, supports = _swing_levels(df.tail(120), window=4)
    supports = [x for x in supports if x["price"] < price_native][:3]
    resistances = [x for x in resistances if x["price"] > price_native][:3]
    supports.sort(key=lambda x: x["price"], reverse=True)
    resistances.sort(key=lambda x: x["price"])

    w52h = float(df["High"].tail(252).max())
    w52l = float(df["Low"].tail(252).min())
    vol_ratio = round(float(last["Volume"]) / float(df["Volume"].tail(20).mean()), 2)

    chg_1d = _pct_change(price_native, df["Close"], 1)
    chg_5d = _pct_change(price_native, df["Close"], 5)
    chg_21d = _pct_change(price_native, df["Close"], 21)
    chg_63d = _pct_change(price_native, df["Close"], 63)

    trend = _trend_label(price_native, e20, e50, e200, chg_21d, rsi)
    signal = _signal_label(price_native, e20, e50, rsi, chg_5d)
    action = _action_label(trend, signal)

    sup1 = supports[0]["price"] if supports else None
    sup2 = supports[1]["price"] if len(supports) > 1 else None
    res1 = resistances[0]["price"] if resistances else w52h
    res2 = resistances[1]["price"] if len(resistances) > 1 else None

    entry_price = sup1 or price_native * 0.97
    stop_price = (sup2 or sup1 or price_native * 0.95) * 0.99

    short_name = entry.get("short_name", ticker)
    full_name = entry.get("full_name", short_name)
    bux_symbol = entry.get("bux_symbol", ticker.split(".")[0])
    bux_name = entry.get("bux_name", full_name)

    return {
        "ticker": ticker,
        "bux_symbol": bux_symbol,
        "bux_name": bux_name,
        "isin": entry.get("isin", ""),
        "exchange": entry.get("exchange", ""),
        "short_name": short_name,
        "full_name": full_name,
        "ticker_label": f"{bux_symbol} — {short_name}",
        "currency": ccy,
        "price_eur": to_eur(price_native),
        "price_native": round(price_native, 2),
        "as_of_date": str(df.index[-1].date()),
        "change_1d": chg_1d,
        "change_5d": chg_5d,
        "change_21d": chg_21d,
        "change_63d": chg_63d,
        "high_52w_eur": to_eur(w52h),
        "low_52w_eur": to_eur(w52l),
        "rsi": round(rsi, 1),
        "ema20_eur": to_eur(e20),
        "ema50_eur": to_eur(e50),
        "ema200_eur": to_eur(e200),
        "above_ema20": price_native > e20,
        "above_ema50": price_native > e50,
        "volume_ratio": vol_ratio,
        "trend": trend,
        "signal": signal,
        "action": action,
        "support_1_eur": to_eur(sup1) if sup1 else None,
        "support_2_eur": to_eur(sup2) if sup2 else None,
        "resistance_1_eur": to_eur(res1),
        "resistance_2_eur": to_eur(res2) if res2 else None,
        "entry_eur": to_eur(entry_price),
        "stop_eur": to_eur(stop_price),
        "target_eur": to_eur(res1),
        "role": entry.get("role", ""),
        "risk": entry.get("risk", ""),
    }


def scan_all_etfs(config_path: Path | None = None) -> list[dict[str, Any]]:
    """Scan all ETFs from config; returns list of result dicts."""
    entries = load_etf_config(config_path)
    fx = None
    try:
        fx_df = yf.download("EURUSD=X", period="5d", interval="1d", auto_adjust=False, progress=False)
        if not fx_df.empty:
            if isinstance(fx_df.columns, pd.MultiIndex):
                fx_df.columns = fx_df.columns.get_level_values(0)
            fx = float(fx_df["Close"].iloc[-1])
    except Exception as exc:
        logger.warning("EUR/USD fetch failed: %s", exc)

    results: list[dict[str, Any]] = []
    for entry in entries:
        row = scan_etf(entry, fx_eurusd=fx)
        if row:
            results.append(row)
            logger.info("Scanned %s — €%.2f (%s)", row["ticker_label"], row["price_eur"], row["signal"])
    return results


def results_to_dataframe(results: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert scan results to a flat DataFrame for Excel export."""
    rows = []
    for r in results:
        rows.append({
            "Bux Sembol": r["bux_symbol"],
            "Bux'ta Ara": r["bux_name"],
            "Ticker + İsim": r["ticker_label"],
            "Yahoo Ticker": r["ticker"],
            "ISIN": r.get("isin", ""),
            "Borsa": r.get("exchange", ""),
            "Kısa İsim": r["short_name"],
            "Tam Fon Adı": r["full_name"],
            "Para Birimi": r["currency"],
            "Date": r["as_of_date"],
            "Price (EUR)": r["price_eur"],
            "Price (native)": r["price_native"],
            "1D %": r["change_1d"],
            "5D %": r["change_5d"],
            "1M (21D) %": r["change_21d"],
            "3M (63D) %": r["change_63d"],
            "52W high (EUR)": r["high_52w_eur"],
            "52W low (EUR)": r["low_52w_eur"],
            "RSI": r["rsi"],
            "EMA20 (EUR)": r["ema20_eur"],
            "EMA50 (EUR)": r["ema50_eur"],
            "EMA200 (EUR)": r["ema200_eur"],
            "Above EMA20?": "Yes" if r["above_ema20"] else "No",
            "Above EMA50?": "Yes" if r["above_ema50"] else "No",
            "Volume ratio": r["volume_ratio"],
            "Trend": r["trend"],
            "Signal": r["signal"],
            "Support 1 (EUR)": r["support_1_eur"],
            "Support 2 (EUR)": r["support_2_eur"],
            "Resistance 1 (EUR)": r["resistance_1_eur"],
            "Resistance 2 (EUR)": r["resistance_2_eur"],
            "Limit entry (EUR)": r["entry_eur"],
            "Stop (EUR)": r["stop_eur"],
            "Target 1 (EUR)": r["target_eur"],
            "Action": r["action"],
            "Role": r["role"],
            "Risk": r["risk"],
        })
    return pd.DataFrame(rows)
