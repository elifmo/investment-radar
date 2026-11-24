"""
Macro Agent (Beta V1 — Phase 1).

Code decides bullish / neutral / cautious from existing macro_regime + SPY/VIX.
Haiku writes a short English summary (headlines are context only).

Writes: agents/macro_signal
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import yfinance as yf

from src.agents.client import ENGLISH_OUTPUT_RULE, get_anthropic_client, write_agent_doc

logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"


def _ema(series, span: int) -> float | None:
    if series is None or len(series) < span:
        return None
    return float(series.ewm(span=span, adjust=False).mean().iloc[-1])


def _fetch_market_snapshot() -> dict[str, Any]:
    """SPY price/EMAs + VIX. Best-effort; missing fields stay None."""
    out: dict[str, Any] = {
        "spy_price": None,
        "spy_ema_50": None,
        "spy_ema_200": None,
        "vix": None,
    }
    try:
        spy = yf.Ticker("SPY").history(period="1y", interval="1d")
        if not spy.empty:
            close = spy["Close"]
            out["spy_price"] = round(float(close.iloc[-1]), 2)
            out["spy_ema_50"] = round(_ema(close, 50) or 0, 2) or None
            out["spy_ema_200"] = round(_ema(close, 200) or 0, 2) or None
    except Exception as exc:
        logger.warning("SPY fetch failed: %s", exc)

    try:
        vix_hist = yf.Ticker("^VIX").history(period="1mo", interval="1d")
        if not vix_hist.empty:
            out["vix"] = round(float(vix_hist["Close"].iloc[-1]), 2)
    except Exception as exc:
        logger.warning("VIX fetch failed: %s", exc)

    return out


def _fetch_macro_headlines(limit: int = 5) -> list[str]:
    """Best-effort headlines via yfinance news on a macro proxy ticker."""
    headlines: list[str] = []
    try:
        # SPY news often carries macro/market tape; no paid NewsAPI required.
        items = yf.Ticker("SPY").news or []
        for item in items:
            title = (item.get("title") or "").strip()
            if title and title not in headlines:
                headlines.append(title)
            if len(headlines) >= limit:
                break
    except Exception as exc:
        logger.warning("Macro headlines fetch failed: %s", exc)
    return headlines


def compute_macro_signal(
    regime: str,
    spy_price: float | None,
    spy_ema_50: float | None,
    spy_ema_200: float | None,
    vix: float | None,
) -> str:
    """
    Deterministic signal. Headlines must not override this.

    - bullish: RISK_ON and SPY > 50d EMA and VIX < 20
    - cautious: RISK_OFF or SPY < 200d EMA or VIX > 30
    - else neutral
    """
    regime_u = (regime or "NEUTRAL").upper()

    if regime_u == "RISK_OFF":
        return "cautious"
    if spy_ema_200 is not None and spy_price is not None and spy_price < spy_ema_200:
        return "cautious"
    if vix is not None and vix > 30:
        return "cautious"

    if (
        regime_u == "RISK_ON"
        and spy_price is not None
        and spy_ema_50 is not None
        and spy_price > spy_ema_50
        and (vix is None or vix < 20)
    ):
        return "bullish"

    return "neutral"


def _fallback_summary(signal: str, regime: str, snap: dict, headlines: list[str]) -> str:
    parts = [
        f"Macro signal is {signal} (pipeline regime {regime}).",
    ]
    if snap.get("spy_price") is not None:
        parts.append(
            f"SPY at {snap['spy_price']}"
            + (f" vs 50d EMA {snap['spy_ema_50']}" if snap.get("spy_ema_50") else "")
            + (f", VIX {snap['vix']}" if snap.get("vix") is not None else "")
            + "."
        )
    if headlines:
        parts.append(f"Recent tape: {headlines[0]}")
    if signal == "bullish":
        parts.append("Environment supports new risk positions if they fit the portfolio.")
    elif signal == "cautious":
        parts.append("Prefer defense: review exits and size new entries down.")
    else:
        parts.append("Stay selective; wait for clearer regime confirmation.")
    return " ".join(parts)


def _haiku_summary(
    signal: str,
    regime: str,
    snap: dict,
    headlines: list[str],
) -> str:
    client = get_anthropic_client()
    headline_block = "\n".join(f"- {h}" for h in headlines) or "- (none)"
    prompt = f"""You are the Macro Agent for an investment dashboard.
Write exactly 2 short sentences in English for a retail investor's morning brief.

Signal (authoritative — do not contradict): {signal}
Pipeline regime: {regime}
SPY: {snap.get('spy_price')} | 50d EMA: {snap.get('spy_ema_50')} | 200d EMA: {snap.get('spy_ema_200')}
VIX: {snap.get('vix')}

Recent headlines (context only):
{headline_block}

{ENGLISH_OUTPUT_RULE}
Be concrete about whether new buys are favored, neutral, or discouraged.
Do not invent numbers. Do not use bullet points."""

    message = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()
    return text or _fallback_summary(signal, regime, snap, headlines)


def run(db: Any) -> dict:
    """Load inputs, compute signal, write agents/macro_signal. Returns payload."""
    today = date.today().isoformat()

    regime_doc = db.collection("macro_regime").document("current").get()
    regime_data = regime_doc.to_dict() if regime_doc.exists else {}
    regime = (regime_data or {}).get("regime", "NEUTRAL")

    snap = _fetch_market_snapshot()
    headlines = _fetch_macro_headlines()
    signal = compute_macro_signal(
        regime,
        snap.get("spy_price"),
        snap.get("spy_ema_50"),
        snap.get("spy_ema_200"),
        snap.get("vix"),
    )

    try:
        summary = _haiku_summary(signal, regime, snap, headlines)
    except Exception as exc:
        logger.warning("Haiku summary failed (%s) — using fallback", exc)
        summary = _fallback_summary(signal, regime, snap, headlines)

    payload = {
        "signal": signal,
        "summary": summary,
        "regime": regime,
        "spy_price": snap.get("spy_price"),
        "spy_ema_50": snap.get("spy_ema_50"),
        "spy_ema_200": snap.get("spy_ema_200"),
        "vix": snap.get("vix"),
        "headlines": headlines,
        "updated_at": today,
    }
    write_agent_doc(db, "macro_signal", payload)
    logger.info("Macro signal=%s regime=%s", signal, regime)
    return payload
