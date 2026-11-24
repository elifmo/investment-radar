#!/usr/bin/env python3
"""Plot auto trendline breakout for a single ticker (PNG + HTML)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Rectangle

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data_fetcher import fetch_ticker_data
from layers.trendline_breakout import (
    LOOKBACK_BARS,
    _line_at,
    _pivot_highs,
    find_descending_resistance_geometry,
)

LOOKBACK = LOOKBACK_BARS
PIVOT_WINDOW = 5


def _draw_ohlc_bars(ax, d: pd.DataFrame, *, up_color: str = "#22c55e", down_color: str = "#ef4444") -> None:
    """Draw daily OHLC bars on integer x-axis."""
    n = len(d)
    bar_w = 0.62
    for i in range(n):
        o = float(d["Open"].iloc[i])
        hi = float(d["High"].iloc[i])
        lo = float(d["Low"].iloc[i])
        c = float(d["Close"].iloc[i])
        up = c >= o
        color = up_color if up else down_color
        ax.vlines(i, lo, hi, color=color, linewidth=1.0, alpha=0.9, zorder=2)
        body_bottom = min(o, c)
        body_h = max(abs(c - o), 0.015)
        ax.add_patch(
            Rectangle(
                (i - bar_w / 2, body_bottom),
                bar_w,
                body_h,
                facecolor=color,
                edgecolor=color,
                linewidth=0.8,
                alpha=0.95,
                zorder=3,
            )
        )


def _svg_candles(d: pd.DataFrame, sx, sy, bar_w: float = 6.0) -> str:
    parts: list[str] = []
    for i in range(len(d)):
        o = float(d["Open"].iloc[i])
        hi = float(d["High"].iloc[i])
        lo = float(d["Low"].iloc[i])
        c = float(d["Close"].iloc[i])
        color = "#22c55e" if c >= o else "#ef4444"
        x = sx(i)
        y_hi, y_lo = sy(hi), sy(lo)
        y_o, y_c = sy(o), sy(c)
        y_top, y_bot = min(y_o, y_c), max(y_o, y_c)
        body_h = max(y_bot - y_top, 1.2)
        parts.append(f'<line x1="{x:.1f}" y1="{y_hi:.1f}" x2="{x:.1f}" y2="{y_lo:.1f}" stroke="{color}" stroke-width="1"/>')
        parts.append(
            f'<rect x="{x - bar_w/2:.1f}" y="{y_top:.1f}" width="{bar_w:.1f}" height="{body_h:.1f}" fill="{color}"/>'
        )
    return "\n".join(parts)


def plot_ticker(ticker: str, out_dir: Path) -> Path:
    raw = fetch_ticker_data([ticker]).get(ticker)
    if raw is None or raw.empty:
        raise SystemExit(f"No data for {ticker}")

    df = raw.dropna()
    dates_full = [str(x.date()) for x in df.iloc[-LOOKBACK:].index]
    d = df.iloc[-LOOKBACK:].copy().reset_index(drop=True)

    line = find_descending_resistance_geometry(raw, lookback=LOOKBACK, require_breakout=False)
    if line is None:
        raise SystemExit(f"No descending resistance trendline for {ticker}")
    dates = dates_full

    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / f"{ticker.lower()}_trendline_breakout.png"
    html_path = out_dir / f"{ticker.lower()}_trendline_breakout.html"

    # ── Matplotlib chart (OHLC bars) ──────────────────────────────────────────
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(14, 7), facecolor="#0f172a")
    ax.set_facecolor("#0f172a")

    x = list(range(len(d)))
    _draw_ohlc_bars(ax, d)

    # X-axis date labels
    tick_step = max(1, len(d) // 10)
    tick_idx = list(range(0, len(d), tick_step))
    if tick_idx[-1] != len(d) - 1:
        tick_idx.append(len(d) - 1)
    ax.set_xticks(tick_idx)
    ax.set_xticklabels([dates[i][5:] for i in tick_idx], color="#94a3b8", fontsize=9)
    ax.set_xlim(-0.8, len(d) - 0.2)

    # All pivot highs (small)
    highs = _pivot_highs(d, dates, PIVOT_WINDOW)
    for idx, price, _ in highs:
        ax.scatter(idx, price, s=28, color="#64748b", zorder=4, alpha=0.7)

    # Anchor pivots
    ax.scatter(
        [line["p1_idx"], line["p2_idx"]],
        [line["p1_price"], line["p2_price"]],
        s=120,
        color="#fbbf24",
        edgecolors="white",
        linewidths=1.5,
        zorder=6,
        label="Trendline pivotları",
    )
    ax.annotate(
        f"P1  ${line['p1_price']:.2f}\n{line['p1_date']}",
        (line["p1_idx"], line["p1_price"]),
        textcoords="offset points",
        xytext=(0, 14),
        ha="center",
        color="#fbbf24",
        fontsize=9,
    )
    ax.annotate(
        f"P2  ${line['p2_price']:.2f}\n{line['p2_date']}",
        (line["p2_idx"], line["p2_price"]),
        textcoords="offset points",
        xytext=(0, 14),
        ha="center",
        color="#fbbf24",
        fontsize=9,
    )

    # Trendline extended P1 → today
    x_line = list(range(line["p1_idx"], len(d)))
    y_line = [_line_at(line["slope"], line["intercept"], i) for i in x_line]
    ax.plot(x_line, y_line, color="#ef4444", linewidth=2.2, linestyle="--", label="Düşen direnç (auto)", zorder=5)

    # Breakout bar highlight (only if breakout)
    if line.get("has_breakout"):
        ax.scatter(
            len(d) - 1,
            line["close"],
            s=160,
            color="#38bdf8",
            edgecolors="white",
            linewidths=1.5,
            zorder=7,
            label="Breakout bar",
        )
    ax.axhline(line["line_today"], color="#22c55e", linewidth=1, alpha=0.5, linestyle=":")
    ax.annotate(
        f"Trendline: ${line['line_today']:.2f}\nKapanış: ${line['close']:.2f} ({line['break_pct']:+.2f}%)",
        (len(d) - 1, line["close"]),
        textcoords="offset points",
        xytext=(-120, 20),
        color="#86efac",
        fontsize=10,
        arrowprops=dict(arrowstyle="->", color="#86efac"),
    )

    breakout_note = (
        f"Breakout +{line['break_pct']:.2f}%"
        if line.get("has_breakout")
        else f"Henüz kırılmadı ({line['break_pct']:+.2f}% vs çizgi)"
    )

    title = (
        f"{ticker} — Auto Trendline (1 yıl / {line.get('lookback_bars', len(d))} bar)\n"
        f"Düşen direnç: {line['p1_date']} → {line['p2_date']}  |  "
        f"{line['touches']} dokunuş  |  {breakout_note}  |  Bar: {dates[-1]}"
    )
    ax.set_title(title, color="#f8fafc", fontsize=13, pad=12)
    ax.set_ylabel("Fiyat ($)", color="#cbd5e1")
    ax.tick_params(axis="y", colors="#94a3b8")
    ax.grid(True, color="#1e293b", alpha=0.8)
    ax.legend(loc="upper left", framealpha=0.2)
    plt.tight_layout()
    fig.savefig(png_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close()

    # ── Simple interactive HTML (SVG) ─────────────────────────────────────────
    w, h = 900, 480
    pad_l, pad_r, pad_t, pad_b = 56, 24, 48, 40
    chart_w = w - pad_l - pad_r
    chart_h = h - pad_t - pad_b
    y_min = float(d["Low"].min()) * 0.98
    y_max = float(d["High"].max()) * 1.02

    def sx(i: int) -> float:
        return pad_l + (i / max(len(d) - 1, 1)) * chart_w

    def sy(price: float) -> float:
        return pad_t + (1 - (price - y_min) / max(y_max - y_min, 0.01)) * chart_h

    close_pts = ""  # replaced by candles
    candle_svg = _svg_candles(d, sx, sy)
    line_pts = " ".join(
        f"{sx(i):.1f},{sy(_line_at(line['slope'], line['intercept'], i)):.1f}"
        for i in range(line["p1_idx"], len(d))
    )

    html = f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8"><title>{ticker} Trendline</title>
<style>
body{{margin:0;background:#0f172a;color:#e2e8f0;font-family:system-ui,sans-serif;padding:20px}}
h1{{font-size:20px;margin:0 0 4px}} p{{color:#94a3b8;font-size:13px;margin:0 0 16px}}
.card{{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:16px;max-width:960px}}
.legend{{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;margin-top:12px;color:#cbd5e1}}
.dot{{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:6px}}
img{{max-width:100%;border-radius:8px;margin-top:12px}}
</style></head><body>
<div class="card">
<h1>{ticker} — Auto Trendline Breakout</h1>
<p>Algoritma son <b>1 yıllık</b> (~252 bar) veride swing tepeleri tarar, <b>düşen direnç</b> çizer.
<b>{dates[-1]}</b> kapanışı çizginin üstündeyse breakout sayılır.</p>
<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<rect width="100%" height="100%" fill="#0f172a"/>
{candle_svg}
<polyline points="{line_pts}" fill="none" stroke="#ef4444" stroke-width="2.2" stroke-dasharray="6 4"/>
<circle cx="{sx(line['p1_idx']):.1f}" cy="{sy(line['p1_price']):.1f}" r="7" fill="#fbbf24" stroke="#fff"/>
<circle cx="{sx(line['p2_idx']):.1f}" cy="{sy(line['p2_price']):.1f}" r="7" fill="#fbbf24" stroke="#fff"/>
<circle cx="{sx(len(d)-1):.1f}" cy="{sy(line['close']):.1f}" r="8" fill="#22c55e" stroke="#fff"/>
<text x="{pad_l}" y="24" fill="#f8fafc" font-size="12">P1 ${line['p1_price']:.2f} ({line['p1_date']}) → P2 ${line['p2_price']:.2f} ({line['p2_date']})</text>
<text x="{pad_l}" y="{h-12}" fill="#86efac" font-size="12">Breakout: kapanış ${line['close']:.2f} &gt; trendline ${line['line_today']:.2f} (+{line['break_pct']:.2f}%)</text>
</svg>
<div class="legend">
<span><span class="dot" style="background:#fbbf24"></span>Pivot tepe (çizgi anchor)</span>
<span><span class="dot" style="background:#ef4444"></span>Düşen direnç</span>
<span><span class="dot" style="background:#22c55e"></span>Breakout kapanış</span>
<span><span class="dot" style="background:#22c55e"></span>Yükselen bar</span>
<span><span class="dot" style="background:#ef4444"></span>Düşen bar</span>
</div>
<img src="{png_path.name}" alt="{ticker} chart"/>
<pre style="margin-top:12px;font-size:11px;color:#64748b;overflow:auto">{json.dumps(line, indent=2)}</pre>
</div></body></html>"""
    html_path.write_text(html, encoding="utf-8")

    print(f"PNG:  {png_path}")
    print(f"HTML: {html_path}")
    return png_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", nargs="?", default="WY")
    parser.add_argument("--out", default=str(Path(__file__).parent / "output"))
    args = parser.parse_args()
    plot_ticker(args.ticker.upper(), Path(args.out))


if __name__ == "__main__":
    main()
