"""
Stochastic Candidates Backtest
==============================
Walk-forward replay of the daily candidates funnel (event filter → scorer → top 10)
to compare baseline RSI-only vs stochastic-enhanced scenarios.

Usage:
    python backtest/stoch_candidates_backtest.py              # S0 baseline
    python backtest/stoch_candidates_backtest.py --all        # S0,S2,S4,S6,S7
    python backtest/stoch_candidates_backtest.py --scenario S2_stoch_health

Output:
    backtest/stoch_candidates_backtest.md
    backtest/cache/stoch_bt_{scenario}.pkl
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import yaml
import yfinance as yf

warnings.filterwarnings("ignore")

BACKTEST_DIR = Path(__file__).parent
SRC_DIR = BACKTEST_DIR.parent / "src"
CONFIG_DIR = BACKTEST_DIR.parent / "config"
CACHE_DIR = BACKTEST_DIR / "cache"
REPORT_PATH = BACKTEST_DIR / "stoch_candidates_backtest.md"

sys.path.insert(0, str(SRC_DIR))

from detailed_scorer import score_ticker  # noqa: E402
from event_filter import (  # noqa: E402
    detect_52w_high_break,
    detect_ema_crossover,
    detect_price_move,
    detect_rsi_bounce,
    detect_support_proximity,
    detect_volume_spike,
)
from ta_engine import Timeframe, analyze_ticker, calculate_stochastic  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

START_DATE = (date.today() - timedelta(days=2 * 365 + 30)).isoformat()
END_DATE = date.today().isoformat()
MIN_SCORE = 55
TOP_N = 10
HOLD_DAYS = (5, 20, 60)
WARMUP_DAYS = 200

TriggerMode = Literal["baseline", "stoch_add", "stoch_only", "dual_required"]
ScoreMode = Literal["baseline", "stoch_health", "dual_bonus"]


@dataclass(frozen=True)
class Scenario:
    id: str
    label: str
    trigger_mode: TriggerMode
    score_mode: ScoreMode
    stoch_oversold: float = 20.0
    stoch_overbought: float = 80.0
    stoch_lookback: int = 5


SCENARIOS: dict[str, Scenario] = {
    "S0_baseline": Scenario(
        id="S0_baseline",
        label="Baseline (RSI-only, current weights)",
        trigger_mode="baseline",
        score_mode="baseline",
    ),
    "S2_stoch_health": Scenario(
        id="S2_stoch_health",
        label="Stoch health weight (rsi 10 + stoch 10)",
        trigger_mode="baseline",
        score_mode="stoch_health",
    ),
    "S4_stoch_trig": Scenario(
        id="S4_stoch_trig",
        label="Stoch triggers added (bounce + cross)",
        trigger_mode="stoch_add",
        score_mode="stoch_health",
    ),
    "S6_dual_gate": Scenario(
        id="S6_dual_gate",
        label="Dual gate (RSI bounce AND stoch bounce)",
        trigger_mode="dual_required",
        score_mode="stoch_health",
    ),
    "S7_contrarian": Scenario(
        id="S7_contrarian",
        label="Stoch health + contrarian zone tag",
        trigger_mode="baseline",
        score_mode="stoch_health",
    ),
}


# ── Data ──────────────────────────────────────────────────────────────────────


def load_usa_universe() -> list[str]:
    universe = yaml.safe_load((CONFIG_DIR / "universe.yaml").read_text())
    tickers = [e["ticker"] for e in universe.get("usa", []) if isinstance(e, dict)]
    if "SPY" not in tickers:
        tickers.append("SPY")
    return tickers


def fetch_ohlcv(tickers: list[str]) -> dict[str, pd.DataFrame]:
    cache_path = CACHE_DIR / "stoch_ohlcv_usa.pkl"
    CACHE_DIR.mkdir(exist_ok=True)

    if cache_path.exists():
        cached = pd.read_pickle(cache_path)
        sample = next(iter(cached.values()), None)
        if sample is not None and sample.index[-1].date() >= date.today() - timedelta(days=3):
            logger.info("OHLCV loaded from cache (%d tickers, last=%s)", len(cached), sample.index[-1].date())
            return cached

    logger.info("Downloading OHLCV for %d tickers …", len(tickers))
    result: dict[str, pd.DataFrame] = {}
    for i, ticker in enumerate(tickers):
        if i % 25 == 0:
            logger.info("  %d / %d", i, len(tickers))
        try:
            raw = yf.download(
                ticker,
                start=START_DATE,
                end=END_DATE,
                interval="1d",
                auto_adjust=True,
                progress=False,
            )
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.droplevel(1)
            if len(raw) >= 60:
                result[ticker] = raw
        except Exception as exc:
            logger.debug("Fetch failed %s: %s", ticker, exc)

    pd.to_pickle(result, cache_path)
    logger.info("OHLCV cached: %d tickers", len(result))
    return result


def load_factors() -> dict:
    return yaml.safe_load((CONFIG_DIR / "factors.yaml").read_text())


# ── Stochastic event detectors ────────────────────────────────────────────────


def detect_stoch_oversold_bounce(
    df: pd.DataFrame,
    oversold: float = 20.0,
    lookback: int = 5,
) -> bool:
    if len(df) < 25:
        return False
    k, _ = calculate_stochastic(df)
    k = k.dropna()
    if len(k) < lookback + 2:
        return False
    recent = k.iloc[-lookback:]
    return bool(recent.min() < oversold and k.iloc[-1] > k.iloc[-2])


def detect_stoch_cross_up(df: pd.DataFrame) -> bool:
    if len(df) < 25:
        return False
    k, d = calculate_stochastic(df)
    k, d = k.dropna(), d.dropna()
    if len(k) < 3 or len(d) < 3:
        return False
    return bool(k.iloc[-2] <= d.iloc[-2] and k.iloc[-1] > d.iloc[-1])


def detect_stoch_oversold(df: pd.DataFrame, oversold: float = 20.0) -> bool:
    if len(df) < 25:
        return False
    k, _ = calculate_stochastic(df)
    k = k.dropna()
    return bool(len(k) >= 1 and k.iloc[-1] < oversold)


# ── Event filter (scenario-aware) ─────────────────────────────────────────────


def run_event_filter_scenario(
    daily_data: dict[str, pd.DataFrame],
    scenario: Scenario,
    thresholds: dict,
) -> dict[str, list[str]]:
    trigger_map: dict[str, list[str]] = {}

    for ticker, df in daily_data.items():
        if ticker == "SPY":
            continue
        triggers: list[str] = []
        try:
            rsi_hit = detect_rsi_bounce(
                df,
                thresholds["rsi_oversold"],
                thresholds["rsi_lookback"],
            )
            stoch_bounce = detect_stoch_oversold_bounce(
                df,
                scenario.stoch_oversold,
                scenario.stoch_lookback,
            )
            stoch_cross = detect_stoch_cross_up(df)

            if scenario.trigger_mode == "dual_required":
                if rsi_hit and stoch_bounce:
                    triggers.append("rsi_bounce")
                    triggers.append("stoch_oversold_bounce")
            else:
                if detect_volume_spike(df, thresholds["volume_threshold"]):
                    triggers.append("volume_spike")
                if detect_ema_crossover(df):
                    triggers.append("ema_crossover")

                if scenario.trigger_mode == "baseline":
                    if rsi_hit:
                        triggers.append("rsi_bounce")
                elif scenario.trigger_mode == "stoch_add":
                    if rsi_hit:
                        triggers.append("rsi_bounce")
                    if stoch_bounce:
                        triggers.append("stoch_oversold_bounce")
                    if stoch_cross:
                        triggers.append("stoch_cross_up")
                elif scenario.trigger_mode == "stoch_only":
                    if stoch_bounce:
                        triggers.append("stoch_oversold_bounce")
                    if stoch_cross:
                        triggers.append("stoch_cross_up")

                if detect_price_move(df, thresholds["price_move_pct"]):
                    triggers.append("price_move")
                if detect_support_proximity(df, thresholds["support_prox_pct"]):
                    triggers.append("support_proximity")
                if detect_52w_high_break(df):
                    triggers.append("52w_high_break")
        except Exception as exc:
            logger.debug("Event filter failed %s: %s", ticker, exc)
            continue

        if triggers:
            trigger_map[ticker] = triggers

    return trigger_map


# ── Scoring (scenario-aware) ──────────────────────────────────────────────────


def _base_weights(factors: dict, score_mode: ScoreMode) -> dict:
    weights = dict(factors.get("weights") or {})
    if score_mode in ("stoch_health", "dual_bonus"):
        weights["rsi_health"] = 10
        weights["stoch_health"] = 10
    return weights


def score_ticker_scenario(
    ticker: str,
    df: pd.DataFrame,
    scenario: Scenario,
    factors: dict,
    timeframe: Timeframe = "daily",
) -> tuple[int, list[str], dict[str, Any]]:
    """Return (score, signals, extras) where extras has rsi, stoch_k, stoch_d, zone."""
    w = _base_weights(factors, scenario.score_mode)

    if scenario.score_mode == "baseline":
        score, signals = score_ticker(ticker, df, w, timeframe)
        ind = analyze_ticker(ticker, df, timeframe)["indicators"]
        extras = {
            "rsi": round(ind["rsi"]["value"], 1) if ind and ind.get("rsi") else None,
            "stoch_k": round(ind["stochastic"]["k"], 1) if ind and ind.get("stochastic") else None,
            "stoch_d": round(ind["stochastic"]["d"], 1) if ind and ind.get("stochastic") else None,
            "zone": _stoch_zone(ind["stochastic"]["k"] if ind and ind.get("stochastic") else None),
        }
        return score, signals, extras

    analysis = analyze_ticker(ticker, df, timeframe)
    if analysis["error"] or not analysis["indicators"]:
        return 0, [], {}

    ind = analysis["indicators"]
    score = 0
    signals: list[str] = []
    bar_label = "bar"

    ema = ind["ema"]
    if ema["ema5"] > ema["ema20"] > ema["ema50"]:
        score += w.get("ema_alignment", 20)
        signals.append("✅ EMA fully aligned (5>20>50)")
    elif ema["ema5"] > ema["ema20"]:
        score += w.get("ema_alignment", 20) // 2
        signals.append("✅ EMA5 > EMA20")

    rsi = ind.get("rsi")
    if rsi:
        rv = rsi["value"]
        if 40 <= rv <= 70:
            score += w.get("rsi_health", 10)
            signals.append(f"✅ RSI {rv:.0f} = Healthy")
        elif rv < 35:
            signals.append(f"⚠️ RSI {rv:.0f} = Oversold")

    stoch = ind.get("stochastic")
    stoch_k = stoch["k"] if stoch else None
    if stoch:
        sk = stoch["k"]
        if 20 <= sk <= 80:
            score += w.get("stoch_health", 10)
            signals.append(f"✅ Stoch %K {sk:.0f} = Healthy")
        elif sk < scenario.stoch_oversold:
            signals.append(f"⚠️ Stoch %K {sk:.0f} = Oversold")
        elif sk > scenario.stoch_overbought:
            signals.append(f"❌ Stoch %K {sk:.0f} = Overbought")

    if scenario.score_mode == "dual_bonus" and rsi and stoch:
        rv, sk = rsi["value"], stoch["k"]
        rsi_ok = rv < 35 or 40 <= rv <= 70
        stoch_ok = sk < scenario.stoch_oversold or 20 <= sk <= 80
        if rsi_ok and stoch_ok:
            score += 5
            signals.append("✅ RSI + Stoch dual confirm (+5)")

    vol = ind["volume"]
    if vol["volume_ratio"] >= 1.5:
        score += w.get("volume_spike", 20)
        signals.append(f"✅ Volume {vol['volume_ratio']:.1f}x")
    elif vol["volume_ratio"] >= 1.2:
        score += w.get("volume_spike", 20) // 2

    close = ind["latest_close"]
    prev_close = float(df["Close"].iloc[-2])
    if prev_close > 0:
        bar_chg = (close - prev_close) / prev_close * 100
        if bar_chg >= 1.0:
            score += w.get("price_momentum", 15)
            signals.append(f"✅ Price +{bar_chg:.1f}% ({bar_label})")

    bb = ind["bollinger"]
    if close > bb["middle"]:
        score += w.get("bollinger_position", 10)

    sr = ind["support_resistance"]
    if sr["price_vs_support_pct"] <= 5.0:
        score += w.get("sr_proximity", 10)

    if analysis["is_breakout"] and ind["breakout"]["volume_confirmed"]:
        score += w.get("breakout", 10)

    zone = _stoch_zone(stoch_k)
    extras = {
        "rsi": round(rsi["value"], 1) if rsi else None,
        "stoch_k": round(stoch_k, 1) if stoch_k is not None else None,
        "stoch_d": round(stoch["d"], 1) if stoch else None,
        "zone": zone,
        "contrarian": zone == "oversold" and (ind.get("rsi") or {}).get("value", 100) < 35,
    }
    return min(score, 100), signals, extras


def _stoch_zone(k: float | None) -> str:
    if k is None:
        return "unknown"
    if k < 20:
        return "oversold"
    if k > 80:
        return "overbought"
    return "neutral"


# ── Simulation ────────────────────────────────────────────────────────────────


def simulation_dates(ohlcv: dict[str, pd.DataFrame]) -> list[pd.Timestamp]:
    """Trading days with enough warmup history."""
    sample = next(t for t in ohlcv.values() if len(t) > WARMUP_DAYS + 70)
    cutoff = pd.Timestamp(START_DATE) + pd.Timedelta(days=WARMUP_DAYS)
    return [dt for dt in sample.index if dt >= cutoff]


def run_scenario(
    scenario: Scenario,
    ohlcv: dict[str, pd.DataFrame],
    factors: dict,
) -> pd.DataFrame:
    cache_path = CACHE_DIR / f"stoch_bt_{scenario.id}.pkl"
    if cache_path.exists():
        cached = pd.read_pickle(cache_path)
        if not cached.empty:
            logger.info("[%s] loaded from cache (%d picks)", scenario.id, len(cached))
            return cached

    thresholds = {
        "volume_threshold": factors.get("thresholds", {}).get("volume_spike_ratio", 1.5),
        "price_move_pct": factors.get("thresholds", {}).get("price_move_pct", 2.0),
        "rsi_oversold": factors.get("thresholds", {}).get("rsi_oversold", 35),
        "rsi_lookback": factors.get("thresholds", {}).get("rsi_bounce_lookback", 5),
        "support_prox_pct": factors.get("thresholds", {}).get("support_proximity_pct", 2.0),
    }

    sim_dates = simulation_dates(ohlcv)
    logger.info("[%s] simulating %d trading days …", scenario.id, len(sim_dates))

    rows: list[dict] = []
    spy_df = ohlcv.get("SPY")

    for i, sim_date in enumerate(sim_dates):
        if i % 50 == 0:
            logger.info("  [%s] day %d / %d (%s)", scenario.id, i + 1, len(sim_dates), sim_date.date())

        slice_data = {
            t: df.loc[:sim_date].copy()
            for t, df in ohlcv.items()
            if t != "SPY" and sim_date in df.index and len(df.loc[:sim_date]) >= 60
        }
        if not slice_data:
            continue

        trigger_map = run_event_filter_scenario(slice_data, scenario, thresholds)
        if not trigger_map:
            continue

        scored: list[dict] = []
        for ticker in trigger_map:
            df = slice_data[ticker]
            score, signals, extras = score_ticker_scenario(ticker, df, scenario, factors)
            if score < MIN_SCORE:
                continue
            ind = analyze_ticker(ticker, df, "daily")["indicators"]
            scored.append({
                "date": sim_date,
                "ticker": ticker,
                "score": score,
                "triggers": trigger_map[ticker],
                "signals": signals,
                "close": round(float(df["Close"].iloc[-1]), 2),
                "support": ind["support_resistance"]["nearest_support"] if ind else None,
                "resistance": ind["support_resistance"]["nearest_resistance"] if ind else None,
                **extras,
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        for rank, pick in enumerate(scored[:TOP_N], start=1):
            rows.append({**pick, "rank": rank})

    df_out = _attach_forward_returns(rows, ohlcv, spy_df)
    pd.to_pickle(df_out, cache_path)
    logger.info("[%s] done — %d top-%d picks", scenario.id, len(df_out), TOP_N)
    return df_out


def _attach_forward_returns(
    rows: list[dict],
    ohlcv: dict[str, pd.DataFrame],
    spy_df: pd.DataFrame | None,
) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    out: list[dict] = []
    for row in rows:
        ticker = row["ticker"]
        df = ohlcv.get(ticker)
        if df is None:
            continue
        sim_date = row["date"]
        future = df.loc[sim_date:]
        if len(future) < 2:
            continue

        entry_idx = 1
        entry_price = float(future["Open"].iloc[entry_idx]) if "Open" in future.columns else float(future["Close"].iloc[entry_idx])
        if entry_price <= 0:
            continue

        rec = {**row, "entry_price": round(entry_price, 2)}

        for hold in HOLD_DAYS:
            exit_idx = entry_idx + hold
            if len(future) > exit_idx:
                exit_price = float(future["Close"].iloc[exit_idx])
                rec[f"ret_{hold}d"] = round((exit_price / entry_price - 1) * 100, 2)
            else:
                rec[f"ret_{hold}d"] = None

        if spy_df is not None:
            spy_fut = spy_df.loc[sim_date:]
            if len(spy_fut) > entry_idx:
                spy_entry = float(spy_fut["Open"].iloc[entry_idx]) if "Open" in spy_fut.columns else float(spy_fut["Close"].iloc[entry_idx])
                for hold in HOLD_DAYS:
                    exit_idx = entry_idx + hold
                    if spy_entry > 0 and len(spy_fut) > exit_idx:
                        spy_exit = float(spy_fut["Close"].iloc[exit_idx])
                        ticker_ret = rec.get(f"ret_{hold}d")
                        if ticker_ret is not None:
                            rec[f"alpha_{hold}d"] = round(ticker_ret - (spy_exit / spy_entry - 1) * 100, 2)

        out.append(rec)

    return pd.DataFrame(out)


# ── Reporting ─────────────────────────────────────────────────────────────────


def _metric_row(df: pd.DataFrame, hold: int) -> dict:
    col = f"ret_{hold}d"
    alpha_col = f"alpha_{hold}d"
    sub = df.dropna(subset=[col])
    if sub.empty:
        return {"n": 0, "hit": None, "avg_ret": None, "avg_alpha": None}
    return {
        "n": len(sub),
        "hit": round((sub[col] > 0).mean() * 100, 1),
        "avg_ret": round(sub[col].mean(), 2),
        "avg_alpha": round(sub[alpha_col].mean(), 2) if alpha_col in sub.columns else None,
    }


def _zone_breakdown(df: pd.DataFrame, hold: int = 20) -> list[str]:
    col = f"ret_{hold}d"
    sub = df.dropna(subset=[col])
    if sub.empty or "zone" not in sub.columns:
        return []

    lines = [f"**Stoch zone breakdown ({hold}d):**", ""]
    lines.append("| Zone | Picks | Hit% | Avg Ret | Avg Alpha |")
    lines.append("|------|-------|------|---------|-----------|")
    for zone in ("oversold", "neutral", "overbought", "unknown"):
        z = sub[sub["zone"] == zone]
        if z.empty:
            continue
        hit = (z[col] > 0).mean() * 100
        alpha = z[f"alpha_{hold}d"].mean() if f"alpha_{hold}d" in z.columns else float("nan")
        lines.append(
            f"| {zone} | {len(z)} | {hit:.0f}% | {z[col].mean():+.2f}% | {alpha:+.2f}% |"
        )
    lines.append("")
    return lines


def generate_report(results: dict[str, pd.DataFrame]) -> str:
    lines = [
        "# Stochastic Candidates Backtest",
        f"**Period:** {START_DATE} → {END_DATE}",
        f"**Universe:** USA watchlist (daily OHLCV)",
        f"**Method:** Daily walk-forward, entry next-day open, top {TOP_N} @ score ≥ {MIN_SCORE}",
        "",
        "---",
        "",
        "## Scenario Comparison",
        "",
        "| Scenario | Picks | Days w/ picks | Hit% 5d | Avg 5d | Hit% 20d | Avg 20d | Alpha 20d | Hit% 60d | Avg 60d |",
        "|----------|-------|---------------|---------|--------|----------|---------|-----------|----------|---------|",
    ]

    for sid, df in results.items():
        sc = SCENARIOS[sid]
        if df.empty:
            lines.append(f"| {sc.label} | 0 | 0 | — | — | — | — | — | — | — |")
            continue
        days = df["date"].nunique()
        m5 = _metric_row(df, 5)
        m20 = _metric_row(df, 20)
        m60 = _metric_row(df, 60)
        lines.append(
            f"| {sc.label} | {len(df)} | {days} | "
            f"{m5['hit'] or '—'}% | {m5['avg_ret'] or '—'}% | "
            f"{m20['hit'] or '—'}% | {m20['avg_ret'] or '—'}% | {m20['avg_alpha'] or '—'}% | "
            f"{m60['hit'] or '—'}% | {m60['avg_ret'] or '—'}% |"
        )

    lines += ["", "---", ""]

    for sid, df in results.items():
        sc = SCENARIOS[sid]
        lines += [f"## {sc.id}: {sc.label}", ""]
        if df.empty:
            lines += ["_No picks._", ""]
            continue

        m20 = _metric_row(df, 20)
        contrarian = df[df.get("contrarian", False) == True] if "contrarian" in df.columns else pd.DataFrame()
        lines += [
            f"- Total top-{TOP_N} picks: **{len(df)}**",
            f"- Trading days with ≥1 pick: **{df['date'].nunique()}**",
            f"- Avg picks per active day: **{len(df) / max(df['date'].nunique(), 1):.1f}**",
            f"- 20d hit rate: **{m20['hit']}%** | avg return: **{m20['avg_ret']}%** | alpha: **{m20['avg_alpha']}%**",
            "",
        ]
        if not contrarian.empty and "ret_20d" in contrarian.columns:
            c20 = contrarian.dropna(subset=["ret_20d"])
            if not c20.empty:
                lines += [
                    f"**Contrarian zone (stoch<20 + RSI<35):** {len(c20)} picks, "
                    f"hit {(c20['ret_20d'] > 0).mean()*100:.0f}%, "
                    f"avg {c20['ret_20d'].mean():+.2f}%",
                    "",
                ]
        lines += _zone_breakdown(df, 20)

        top = df.dropna(subset=["ret_20d"]).nlargest(5, "ret_20d")
        if not top.empty:
            lines += ["**Top 5 picks (20d return):**", ""]
            lines += ["| Date | Ticker | Score | Stoch K | RSI | 20d Ret | Alpha |"]
            lines += ["|------|--------|-------|---------|-----|---------|-------|"]
            for r in top.itertuples():
                lines.append(
                    f"| {str(r.date)[:10]} | {r.ticker} | {r.score} | "
                    f"{getattr(r, 'stoch_k', '—')} | {getattr(r, 'rsi', '—')} | "
                    f"{r.ret_20d:+.1f}% | {getattr(r, 'alpha_20d', float('nan')):+.1f}% |"
                )
            lines.append("")

    lines += ["---", "", "_Generated by backtest/stoch_candidates_backtest.py_", ""]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Stochastic candidates backtest")
    parser.add_argument("--scenario", default="S0_baseline", choices=list(SCENARIOS.keys()))
    parser.add_argument("--all", action="store_true", help="Run S0,S2,S4,S6,S7")
    parser.add_argument("--refresh", action="store_true", help="Ignore result cache")
    args = parser.parse_args()

    if args.refresh:
        for p in CACHE_DIR.glob("stoch_bt_*.pkl"):
            p.unlink(missing_ok=True)

    tickers = load_usa_universe()
    ohlcv = fetch_ohlcv(tickers)
    factors = load_factors()

    run_ids = list(SCENARIOS.keys()) if args.all else [args.scenario]
    results: dict[str, pd.DataFrame] = {}
    for sid in run_ids:
        results[sid] = run_scenario(SCENARIOS[sid], ohlcv, factors)

    report = generate_report(results)
    REPORT_PATH.write_text(report)
    print(f"\nReport written: {REPORT_PATH}")
    for sid, df in results.items():
        m20 = _metric_row(df, 20)
        print(f"  {sid}: {len(df)} picks | 20d hit {m20['hit']}% | avg {m20['avg_ret']}% | alpha {m20['avg_alpha']}%")


if __name__ == "__main__":
    main()
