import json
import os
from datetime import date, datetime, timezone, timedelta

import anthropic
import firebase_admin
import numpy as np
import pandas as pd
import requests
import yfinance as yf
from firebase_admin import firestore
from firebase_functions import https_fn, options

from ticker_resolver import resolve_ticker

# ── Helpers ───────────────────────────────────────────────────────────────────

def _rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff().dropna()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return round(float(val), 1) if not np.isnan(val) else 50.0


def _ema(series: pd.Series, period: int) -> float:
    val = series.ewm(span=period, adjust=False).mean().iloc[-1]
    return round(float(val), 2)


def _volume_ratio(volume: pd.Series, period: int = 20) -> float:
    avg = volume.rolling(period).mean().iloc[-1]
    cur = volume.iloc[-1]
    return round(float(cur / avg), 2) if avg and avg > 0 else 1.0


def _support_resistance(hist: pd.DataFrame) -> tuple[float, float]:
    recent = hist.tail(20)
    return round(float(recent["Low"].min()), 2), round(float(recent["High"].max()), 2)


def _fmt_large(n: float, currency: str = "USD") -> str:
    sym = "€" if currency == "EUR" else "$"
    if n >= 1e12:
        return f"{sym}{n/1e12:.2f}T"
    if n >= 1e9:
        return f"{sym}{n/1e9:.2f}B"
    if n >= 1e6:
        return f"{sym}{n/1e6:.2f}M"
    return f"{sym}{n:,.0f}"


def _money(amount: float, currency: str = "USD") -> str:
    sym = "€" if currency == "EUR" else "$"
    return f"{sym}{amount:.2f}"


def _fmt_volume(n: float) -> str:
    if n >= 1e6:
        return f"{n/1e6:.1f}M"
    if n >= 1e3:
        return f"{n/1e3:.1f}K"
    return str(int(n))


def _fetch_news(ticker: str, av_key: str, market: str = "US") -> list[dict]:
    news_ticker = ticker.split(".")[0] if market == "NL" else ticker
    if av_key and market == "US":
        try:
            url = (
                f"https://www.alphavantage.co/query"
                f"?function=NEWS_SENTIMENT&tickers={news_ticker}&limit=5&apikey={av_key}"
            )
            data = requests.get(url, timeout=10).json()
            result = []
            for a in data.get("feed", [])[:5]:
                label = a.get("overall_sentiment_label", "Neutral")
                if "Bullish" in label:
                    emoji, sentiment = "🟢", "Positive"
                elif "Bearish" in label:
                    emoji, sentiment = "🔴", "Negative"
                else:
                    emoji, sentiment = "🟡", "Neutral"
                result.append({
                    "emoji": emoji,
                    "title": a.get("title", ""),
                    "sentiment": sentiment,
                    "published": a.get("time_published") or "",
                })
            if result:
                return result
        except Exception:
            pass
    # fallback: yfinance news (no reliable sentiment — mark as Info)
    try:
        stock = yf.Ticker(ticker)
        yf_news = stock.news or []
        out = []
        for n in yf_news[:5]:
            content = n.get("content") if isinstance(n.get("content"), dict) else {}
            title = content.get("title") or n.get("title") or ""
            if not title:
                continue
            published = ""
            # yfinance shapes vary
            for key in ("pubDate", "providerPublishTime", "published"):
                val = content.get(key) or n.get(key)
                if val:
                    published = str(val)
                    break
            ts = content.get("pubDate") or n.get("providerPublishTime")
            if isinstance(ts, (int, float)) and ts > 0:
                published = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
            out.append({
                "emoji": "🟡",
                "title": title,
                "sentiment": "Info",
                "published": published,
            })
        return out
    except Exception:
        return []


# ── Claude prompt ─────────────────────────────────────────────────────────────

def _build_prompt(ticker, info, hist, rsi, ema8, ema21, ema50, vol_ratio,
                  support, resistance, price, price_pct_range, currency="USD",
                  market="US") -> str:
    pe           = info.get("trailingPE") or info.get("forwardPE")
    rev_growth   = info.get("revenueGrowth")
    margins      = info.get("profitMargins")
    debt_eq      = info.get("debtToEquity")
    inst_pct     = info.get("heldPercentInstitutions")
    week52_high  = info.get("fiftyTwoWeekHigh", hist["High"].max())
    week52_low   = info.get("fiftyTwoWeekLow",  hist["Low"].min())
    m = _money

    ema_trend = (
        "EMAs aligned upward — uptrend" if ema8 > ema21 > ema50
        else "EMAs aligned downward — downtrend" if ema8 < ema21 < ema50
        else "EMAs mixed — sideways / no clear trend"
    )
    rsi_note = "(overbought)" if rsi > 70 else "(oversold)" if rsi < 30 else "(neutral zone)"
    vol_note = "(high)" if vol_ratio > 1.5 else "(light)" if vol_ratio < 0.7 else "(normal)"

    market_label = (
        "Dutch / Euronext Amsterdam equity analyst"
        if market == "NL"
        else "US equity analyst"
    )
    listing_note = "Listed on Euronext Amsterdam (AEX / Dutch market). Prices in EUR." if market == "NL" else ""

    return f"""You are a senior {market_label} writing a plain-language stock deep dive for a retail investor who wants clear, actionable guidance — not jargon. Write as if explaining to a smart friend who is new to investing. Be direct. No filler.
{listing_note}

STOCK DATA:
- Ticker: {ticker}
- Price: {m(price, currency)}
- 52W range position: {price_pct_range:.0f}% ({m(float(week52_low), currency)} low → {m(float(week52_high), currency)} high)
- RSI(14): {rsi} {rsi_note}
- EMA 8/21/50: {m(ema8, currency)} / {m(ema21, currency)} / {m(ema50, currency)} — {ema_trend}
- Volume vs 20d avg: {vol_ratio}x {vol_note}
- 20d support: {m(support, currency)}  |  20d resistance: {m(resistance, currency)}
- P/E: {f"{pe:.1f}x" if pe else "N/A"}
- Revenue growth (YoY): {f"+{rev_growth*100:.1f}%" if rev_growth else "N/A"}
- Profit margin: {f"{margins*100:.1f}%" if margins else "N/A"}
- Debt/Equity: {f"{debt_eq:.2f}" if debt_eq else "N/A"}
- Institutional ownership: {f"{inst_pct*100:.1f}%" if inst_pct else "N/A"}

Return ONLY a valid JSON object with these exact fields:

{{
  "one_line": "What does this company do? Max 12 words.",
  "snapshot_price": "Where is the price right now in simple terms? (e.g. 'Near all-time highs, extended' or 'Middle of yearly range, balanced')",
  "snapshot_momentum": "What does RSI + EMA tell us in plain English?",
  "snapshot_volume": "What does current volume tell us?",
  "snapshot_strength": "One sentence on institutional ownership trend.",
  "situation": "2-3 sentences explaining the current setup to a friend. Be honest about risks too.",
  "decision": "BUY or WATCH or AVOID",
  "decision_reason": "One sentence why.",
  "level_entry": {{"price": number, "note": "plain note — when to enter"}},
  "level_breakout": {{"price": number, "note": "plain note — breakout target"}},
  "level_stop": {{"price": number, "note": "plain note — when to exit / stop"}},
  "bull_points": ["point 1", "point 2", "point 3"],
  "bear_points": ["point 1", "point 2", "point 3"],
  "fundamentals_pe": "Is the valuation cheap, fair or expensive vs sector? Plain language.",
  "fundamentals_growth": "Revenue growth — what does it mean?",
  "fundamentals_margins": "Profit margin — good or bad?",
  "fundamentals_debt": "Debt — is it a concern?",
  "risks": ["risk 1 and what it means for the stock", "risk 2", "risk 3"]
}}"""


# ── Cloud Function ─────────────────────────────────────────────────────────────

@https_fn.on_request(
    cors=options.CorsOptions(cors_origins="*", cors_methods=["get", "options"]),
    memory=options.MemoryOption.MB_512,
    timeout_sec=120,
    secrets=["ANTHROPIC_API_KEY"],
)
def deep_dive(req: https_fn.Request) -> https_fn.Response:
    if not firebase_admin._apps:
        firebase_admin.initialize_app()

    ticker = req.args.get("ticker", "").upper().strip()
    if not ticker:
        return https_fn.Response(
            json.dumps({"error": "ticker required"}), status=400, mimetype="application/json"
        )

    resolved   = resolve_ticker(ticker)
    yf_symbol  = resolved["symbol"]
    market     = resolved["market"]
    currency   = resolved["currency"]
    cache_id   = resolved["cache_id"] or yf_symbol

    if not yf_symbol:
        return https_fn.Response(
            json.dumps({"error": "ticker required"}), status=400, mimetype="application/json"
        )

    db        = firestore.client()
    cache_ref = db.collection("deep_dive").document(cache_id)
    levels_only = str(req.args.get("levels_only", "")).lower() in ("1", "true", "yes")

    # ── Cache check (full deep dive only) ─────────────────────────────────────
    if not levels_only:
        cached = cache_ref.get()
        if cached.exists:
            data       = cached.to_dict()
            cached_at  = data.get("cached_at")
            if cached_at and (datetime.now(timezone.utc) - cached_at) < timedelta(hours=24):
                return https_fn.Response(
                    json.dumps({"result": data["result"], "cached": True,
                                "cached_at": cached_at.isoformat()}),
                    mimetype="application/json",
                )

    # ── Fetch market data ─────────────────────────────────────────────────────
    try:
        stock = yf.Ticker(yf_symbol)
        info  = stock.info or {}
        hist  = stock.history(period="1y")

        # Bare symbol with no US data? Try Euronext Amsterdam (.AS)
        if hist.empty and market == "US" and "." not in ticker:
            nl_symbol = f"{ticker}.AS"
            stock_nl  = yf.Ticker(nl_symbol)
            hist_nl   = stock_nl.history(period="1y")
            if not hist_nl.empty:
                stock    = stock_nl
                info     = stock_nl.info or {}
                hist     = hist_nl
                yf_symbol = nl_symbol
                market   = "NL"
                currency = "EUR"
                cache_id = nl_symbol

        if hist.empty:
            hint = " For Dutch listings add .AS (e.g. SIFG.AS)." if "." not in ticker else ""
            return https_fn.Response(
                json.dumps({"error": f"No price data found for {ticker}.{hint}"}),
                status=404, mimetype="application/json",
            )

        currency     = info.get("currency") or currency
        price        = float(info.get("currentPrice") or info.get("regularMarketPrice") or hist["Close"].iloc[-1])
        company_name = info.get("longName") or info.get("shortName") or ticker
        sector       = info.get("sector")   or "—"
        industry     = info.get("industry") or "—"
        exchange     = info.get("exchange") or info.get("exchangeShortName") or ("AMS" if market == "NL" else "NASDAQ")
        market_cap   = info.get("marketCap")
        week52_high  = float(info.get("fiftyTwoWeekHigh") or hist["High"].max())
        week52_low   = float(info.get("fiftyTwoWeekLow")  or hist["Low"].min())
        avg_volume   = float(info.get("averageVolume")    or hist["Volume"].mean())
        inst_pct     = info.get("heldPercentInstitutions")

        # Technicals
        rsi        = _rsi(hist["Close"])
        ema8       = _ema(hist["Close"], 8)
        ema21      = _ema(hist["Close"], 21)
        ema50      = _ema(hist["Close"], 50)
        vol_ratio  = _volume_ratio(hist["Volume"])
        support, resistance = _support_resistance(hist)
        price_pct  = round((price - week52_low) / max(week52_high - week52_low, 0.01) * 100, 0)

        # Institutional data
        try:
            inst_holders = stock.institutional_holders
            top_holder   = None
            if inst_holders is not None and not inst_holders.empty:
                top_holder = str(inst_holders.iloc[0].get("Holder", ""))
        except Exception:
            top_holder = None

        # News
        av_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
        news   = _fetch_news(yf_symbol, av_key, market)

        # Approximate days to earnings when Yahoo exposes it
        days_to_earnings = None
        try:
            cal = getattr(stock, "calendar", None)
            earn_date = None
            if isinstance(cal, dict):
                earn_date = cal.get("Earnings Date") or cal.get("earningsDate")
            elif cal is not None and hasattr(cal, "empty") and not cal.empty:
                if "Earnings Date" in cal.index:
                    earn_date = cal.loc["Earnings Date"]
            if earn_date is not None:
                if hasattr(earn_date, "__iter__") and not isinstance(earn_date, (str, bytes)):
                    earn_date = list(earn_date)[0] if list(earn_date) else None
                if earn_date is not None:
                    if hasattr(earn_date, "date"):
                        ed = earn_date.date()
                    else:
                        ed = date.fromisoformat(str(earn_date)[:10])
                    days_to_earnings = (ed - date.today()).days
        except Exception:
            days_to_earnings = None

    except Exception as e:
        return https_fn.Response(
            json.dumps({"error": f"Data fetch failed: {e}"}),
            status=500, mimetype="application/json",
        )

    # Fast path: levels + news (no Claude) for portfolio enrich
    if levels_only:
        preview = news[0] if news else None
        levels = {
            "ticker": yf_symbol,
            "currency": currency,
            "price": price,
            "support": support,
            "resistance": resistance,
            "days_to_earnings": days_to_earnings,
            "news": news,
            "news_preview": preview,
        }
        return https_fn.Response(
            json.dumps({"result": levels, "cached": False, "levels_only": True}),
            mimetype="application/json",
        )

    # ── Claude analysis ───────────────────────────────────────────────────────
    try:
        prompt = _build_prompt(
            yf_symbol, info, hist, rsi, ema8, ema21, ema50,
            vol_ratio, support, resistance, price, price_pct,
            currency=currency, market=market,
        )
        client  = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            return https_fn.Response(
                json.dumps({
                    "error": "ANTHROPIC_API_KEY is not configured on deep_dive. "
                             "Set the Firebase secret and redeploy."
                }),
                status=500,
                mimetype="application/json",
            )
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1600,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        analysis = json.loads(raw)

    except Exception as e:
        return https_fn.Response(
            json.dumps({"error": f"Analysis failed: {e}"}),
            status=500, mimetype="application/json",
        )

    # ── Build & cache result ──────────────────────────────────────────────────
    result = {
        "ticker":       yf_symbol,
        "input_ticker": ticker,
        "market":       market,
        "currency":     currency,
        "company_name": company_name,
        "sector":       sector,
        "industry":     industry,
        "exchange":     exchange,
        "price":        price,
        "market_cap":   _fmt_large(market_cap, currency) if market_cap else "—",
        "week52_high":  week52_high,
        "week52_low":   week52_low,
        "avg_volume":   _fmt_volume(avg_volume),
        "rsi":          rsi,
        "support":      support,
        "resistance":   resistance,
        "inst_pct":     round(inst_pct * 100, 1) if inst_pct else None,
        "top_holder":   top_holder,
        "news":         news,
        "analysis":     analysis,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    cache_ref.set({"result": result, "cached_at": datetime.now(timezone.utc)})

    return https_fn.Response(
        json.dumps({"result": result, "cached": False}),
        mimetype="application/json",
    )
