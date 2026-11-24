#!/usr/bin/env python3
"""Plot Fibonacci retracement levels on OHLC chart."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data_fetcher import fetch_ticker_data
from layers.fibonacci import fib_from_lookback

LOOKBACK = 252
FIB_COLORS = {
    "0%": "#f8fafc",
    "23.6%": "#38bdf8",
    "38.2%": "#22c55e",
    "50%": "#eab308",
    "61.8%": "#f97316",
    "78.6%": "#a855f7",
    "100%": "#94a3b8",
    "127.2%": "#64748b",
    "161.8%": "#475569",
    "200%": "#334155",
}


def _draw_ohlc(ax, d) -> None:
    for i in range(len(d)):
        o, hi, lo, c = map(float, (d["Open"].iloc[i], d["High"].iloc[i], d["Low"].iloc[i], d["Close"].iloc[i]))
        color = "#22c55e" if c >= o else "#ef4444"
        ax.vlines(i, lo, hi, color=color, linewidth=1.0, alpha=0.9, zorder=2)
        body_h = max(abs(c - o), 0.02)
        ax.add_patch(
            Rectangle((i - 0.3, min(o, c)), 0.6, body_h, facecolor=color, edgecolor=color, alpha=0.95, zorder=3)
        )


def plot_fib(ticker: str, out_dir: Path) -> Path:
    raw = fetch_ticker_data([ticker]).get(ticker)
    if raw is None or raw.empty:
        raise SystemExit(f"No data for {ticker}")

    df = raw.dropna().iloc[-LOOKBACK:].copy()
    dates = [str(x.date()) for x in df.index]
    d = df.reset_index(drop=True)
    fib = fib_from_lookback(raw, lookback=LOOKBACK, include_extensions=False)
    if fib is None:
        raise SystemExit("Could not compute Fibonacci")

    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{ticker.lower()}_fibonacci.png"

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(14, 7), facecolor="#0f172a")
    ax.set_facecolor("#0f172a")
    _draw_ohlc(ax, d)

    for label, price in fib.levels.items():
        color = FIB_COLORS.get(label, "#64748b")
        lw = 2.0 if label in ("38.2%", "50%", "61.8%") else 1.2
        ax.axhline(price, color=color, linewidth=lw, alpha=0.85, linestyle="--", zorder=4)
        ax.text(len(d) + 0.5, price, f" {label}  ${price:.2f}", color=color, va="center", fontsize=9)

    ax.scatter(len(d) - 1, fib.close, s=120, color="#38bdf8", edgecolors="white", zorder=6, label="Kapanış")
    ax.annotate(
        f"${fib.close:.2f}  ·  nearest {fib.nearest_level}",
        (len(d) - 1, fib.close),
        textcoords="offset points",
        xytext=(-90, 18),
        color="#7dd3fc",
        fontsize=10,
        arrowprops=dict(arrowstyle="->", color="#7dd3fc"),
    )

    tick_step = max(1, len(d) // 10)
    ticks = list(range(0, len(d), tick_step))
    if ticks[-1] != len(d) - 1:
        ticks.append(len(d) - 1)
    ax.set_xticks(ticks)
    ax.set_xticklabels([dates[i][5:] for i in ticks], color="#94a3b8", fontsize=9)
    ax.set_xlim(-0.8, len(d) + 18)

    swing = (
        f"Low ${fib.swing_low:.2f} ({fib.low_date}) → High ${fib.swing_high:.2f} ({fib.high_date})"
        if fib.direction == "up"
        else f"High ${fib.swing_high:.2f} ({fib.high_date}) → Low ${fib.swing_low:.2f} ({fib.low_date})"
    )
    ax.set_title(
        f"{ticker} — Fibonacci Retracement (1 yıl)\n{swing}  ·  direction={fib.direction}",
        color="#f8fafc",
        fontsize=13,
        pad=12,
    )
    ax.set_ylabel("Fiyat ($)", color="#cbd5e1")
    ax.tick_params(axis="y", colors="#94a3b8")
    ax.grid(True, color="#1e293b", alpha=0.8)
    ax.legend(loc="upper left", framealpha=0.2)
    plt.tight_layout()
    fig.savefig(png, dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    print(f"PNG: {png}")
    return png


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("ticker", nargs="?", default="WY")
    p.add_argument("--out", default=str(Path(__file__).parent / "output"))
    args = p.parse_args()
    plot_fib(args.ticker.upper(), Path(args.out))
