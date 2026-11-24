"""
Crypto Ichimoku signals — daily cloud only (no TA score, no RSI).

ENTER — close above cloud top
EXIT  — close below cloud bottom
WAIT  — inside cloud or between levels
"""

from __future__ import annotations

from dataclasses import dataclass

from layers.ichimoku import cloud_state_at_close


@dataclass
class CryptoSignal:
    ichimoku_signal: str  # ENTER | EXIT | WAIT
    reason: str
    close: float | None = None
    cloud_top: float | None = None
    cloud_bottom: float | None = None
    above_cloud: bool = False
    below_cloud: bool = False
    in_cloud: bool = False
    cloud_breakout: bool = False
    cloud_break_down: bool = False
    tenkan: float | None = None
    kijun: float | None = None


def evaluate_crypto(df) -> CryptoSignal | None:
    """Evaluate latest daily bar for a crypto ticker."""
    state = cloud_state_at_close(df)
    if state is None:
        return None

    if state["above_cloud"]:
        if state.get("cloud_breakout"):
            sig, reason = "ENTER", "New daily cloud break — price crossed above cloud top"
        else:
            sig, reason = "ENTER", "Price above daily Ichimoku cloud — entry zone"
    elif state["below_cloud"]:
        if state.get("cloud_break_down"):
            sig, reason = "EXIT", "New break below daily cloud — exit zone"
        else:
            sig, reason = "EXIT", "Price below daily Ichimoku cloud — exit zone"
    else:
        sig, reason = "WAIT", "Price inside cloud — wait for clear break"

    return CryptoSignal(
        ichimoku_signal=sig,
        reason=reason,
        close=state["close"],
        cloud_top=state["cloud_top"],
        cloud_bottom=state["cloud_bottom"],
        above_cloud=state["above_cloud"],
        below_cloud=state["below_cloud"],
        in_cloud=state["in_cloud"],
        cloud_breakout=state.get("cloud_breakout", False),
        cloud_break_down=state.get("cloud_break_down", False),
        tenkan=state["tenkan"],
        kijun=state["kijun"],
    )


def scan_crypto(daily_data: dict[str, object]) -> list[dict]:
    """Build Firestore-ready rows for configured crypto tickers."""
    rows: list[dict] = []
    for ticker, df in daily_data.items():
        result = evaluate_crypto(df)
        if result is None:
            rows.append({
                "ticker": ticker,
                "ichimoku_signal": "WAIT",
                "reason": "Insufficient daily history for Ichimoku",
                "error": True,
            })
            continue
        rows.append({
            "ticker": ticker,
            "market": "CRYPTO",
            "asset_class": "crypto",
            "ichimoku_signal": result.ichimoku_signal,
            "reason": result.reason,
            "close": result.close,
            "cloud_top": result.cloud_top,
            "cloud_bottom": result.cloud_bottom,
            "above_cloud": result.above_cloud,
            "below_cloud": result.below_cloud,
            "in_cloud": result.in_cloud,
            "cloud_breakout": result.cloud_breakout,
            "cloud_break_down": result.cloud_break_down,
            "tenkan": result.tenkan,
            "kijun": result.kijun,
            "timeframe": "daily",
        })
    return rows
