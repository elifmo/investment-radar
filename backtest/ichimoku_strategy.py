"""
Ichimoku + RSI Diverjans Strateji Motoru
=========================================
Veri kaynağı : Yahoo Finance (yfinance)
Kurulum      : pip install yfinance pandas

Kullanım:
    python3 backtest/ichimoku_strategy.py
    python3 backtest/ichimoku_strategy.py AAPL RKLB ASTS
"""

from __future__ import annotations

import sys

import pandas as pd
import yfinance as yf

# ─────────────────────────────────────────────
# CONFIG — buradan özelleştir
# ─────────────────────────────────────────────
SYMBOL = "BTC-USD"  # örnek: "AAPL", "ETH-USD", "THYAO.IS"
INTERVAL = "1d"  # "1d" günlük | "4h" 4 saatlik | "1h" saatlik
PERIOD = "2y"  # kaç yıllık veri çek (4h için max "60d" kullan)

# Ichimoku parametreleri
TENKAN_PERIOD = 9
KIJUN_PERIOD = 26
SENKOU_B_PERIOD = 52

# RSI parametreleri
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30


# ─────────────────────────────────────────────
# 1. VERİ ÇEK
# ─────────────────────────────────────────────
def fetch_data(symbol: str, interval: str, period: str) -> pd.DataFrame:
    df = yf.download(symbol, interval=interval, period=period, progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    return df


# ─────────────────────────────────────────────
# 2. ICHIMOKU HESAPLA
# ─────────────────────────────────────────────
def mid(high: pd.Series, low: pd.Series, period: int) -> pd.Series:
    """Belirli periyottaki en yüksek ve en düşüğün ortası."""
    return (high.rolling(period).max() + low.rolling(period).min()) / 2


def add_ichimoku(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["tenkan"] = mid(df["High"], df["Low"], TENKAN_PERIOD)
    df["kijun"] = mid(df["High"], df["Low"], KIJUN_PERIOD)
    df["span_a"] = ((df["tenkan"] + df["kijun"]) / 2).shift(KIJUN_PERIOD)
    df["span_b"] = mid(df["High"], df["Low"], SENKOU_B_PERIOD).shift(KIJUN_PERIOD)
    df["chikou"] = df["Close"].shift(-KIJUN_PERIOD)

    # Bulut üst ve alt sınırı (fiyatın şu anki pozisyonu için)
    df["cloud_top"] = df[["span_a", "span_b"]].max(axis=1)
    df["cloud_bottom"] = df[["span_a", "span_b"]].min(axis=1)

    return df


# ─────────────────────────────────────────────
# 3. RSI HESAPLA
# ─────────────────────────────────────────────
def add_rsi(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(RSI_PERIOD).mean()
    loss = (-delta.clip(upper=0)).rolling(RSI_PERIOD).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))
    return df


# ─────────────────────────────────────────────
# 4. RSI DİVERJANS TESPİTİ
# ─────────────────────────────────────────────
def find_divergence(df: pd.DataFrame, lookback: int = 5) -> pd.DataFrame:
    """
    Basit diverjans: son 'lookback' bar içinde
    - Bearish: fiyat yüksek yaptı ama RSI düştü
    - Bullish: fiyat düşük yaptı ama RSI yükseldi
    """
    df = df.copy()
    df["bearish_div"] = False
    df["bullish_div"] = False

    for i in range(lookback * 2, len(df)):
        window_price = df["Close"].iloc[i - lookback : i]
        window_rsi = df["rsi"].iloc[i - lookback : i]

        price_high = window_price.max()
        price_low = window_price.min()
        rsi_high = window_rsi.max()
        rsi_low = window_rsi.min()

        prev_price_high = df["Close"].iloc[i - lookback * 2 : i - lookback].max()
        prev_rsi_high = df["rsi"].iloc[i - lookback * 2 : i - lookback].max()
        prev_price_low = df["Close"].iloc[i - lookback * 2 : i - lookback].min()
        prev_rsi_low = df["rsi"].iloc[i - lookback * 2 : i - lookback].min()

        # Bearish diverjans: fiyat yeni yüksek ama RSI daha düşük tepe
        if price_high > prev_price_high and rsi_high < prev_rsi_high:
            df.iloc[i, df.columns.get_loc("bearish_div")] = True

        # Bullish diverjans: fiyat yeni dip ama RSI daha yüksek dip
        if price_low < prev_price_low and rsi_low > prev_rsi_low:
            df.iloc[i, df.columns.get_loc("bullish_div")] = True

    return df


# ─────────────────────────────────────────────
# 5. SİNYAL MOTORU — 5 CASE
# ─────────────────────────────────────────────
def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["signal"] = None  # "BUY" | "SELL" | "EXIT" | "WAIT"
    df["case"] = None  # hangi case tetiklendi

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]

        price = row["Close"]
        tenkan = row["tenkan"]
        kijun = row["kijun"]
        ctop = row["cloud_top"]
        cbot = row["cloud_bottom"]
        rsi = row["rsi"]
        bear_div = row["bearish_div"]
        bull_div = row["bullish_div"]

        tk_cross_up = prev["tenkan"] <= prev["kijun"] and tenkan > kijun
        tk_cross_down = prev["tenkan"] >= prev["kijun"] and tenkan < kijun
        above_cloud = price > ctop
        below_cloud = price < cbot
        in_cloud = cbot <= price <= ctop

        # ── CASE 1: Güçlü AL (üç koşul birden)
        if above_cloud and tk_cross_up and rsi < RSI_OVERBOUGHT:
            df.iloc[i, df.columns.get_loc("signal")] = "BUY"
            df.iloc[i, df.columns.get_loc("case")] = "Case1_Guclu_AL"

        # ── CASE 2: Güçlü SAT
        elif below_cloud and tk_cross_down:
            df.iloc[i, df.columns.get_loc("signal")] = "SELL"
            df.iloc[i, df.columns.get_loc("case")] = "Case2_Guclu_SAT"

        # ── CASE 3: Kijun Bounce — yükselen trendde geri çekilme
        elif above_cloud and abs(price - kijun) / kijun < 0.005 and rsi > 40:
            df.iloc[i, df.columns.get_loc("signal")] = "BUY"
            df.iloc[i, df.columns.get_loc("case")] = "Case3_Kijun_Bounce"

        # ── CASE 4: Bulut kırılımı (breakout)
        elif prev["Close"] < prev["cloud_top"] and price > ctop:
            df.iloc[i, df.columns.get_loc("signal")] = "BUY"
            df.iloc[i, df.columns.get_loc("case")] = "Case4_Bulut_Kirilim"

        # ── CASE 5: Bulut içi — bekle
        elif in_cloud:
            df.iloc[i, df.columns.get_loc("signal")] = "WAIT"
            df.iloc[i, df.columns.get_loc("case")] = "Case5_Bulut_Ici"

        # ── RSI Bearish Diverjans — çık
        if bear_div and above_cloud:
            df.iloc[i, df.columns.get_loc("signal")] = "EXIT"
            df.iloc[i, df.columns.get_loc("case")] = "RSI_Bearish_Div"

        # ── RSI Bullish Diverjans — erken uyarı (Ichimoku teyidi bekle)
        if bull_div and below_cloud:
            df.iloc[i, df.columns.get_loc("signal")] = "WATCH"
            df.iloc[i, df.columns.get_loc("case")] = "RSI_Bullish_Div_Bekle"

    return df


# ─────────────────────────────────────────────
# 6. BASİT BACKTEST
# ─────────────────────────────────────────────
def backtest(df: pd.DataFrame) -> dict:
    """
    Basit long-only backtest.
    BUY sinyalinde gir, SELL/EXIT sinyalinde çık.
    Stop-loss: Kijun altına düşünce çık.
    """
    trades = []
    position = None  # {"entry_price": x, "entry_date": t, "case": c}

    for i, row in df.iterrows():
        if row["signal"] in ("BUY",) and position is None:
            position = {
                "entry_date": i,
                "entry_price": row["Close"],
                "stop": row["kijun"],
                "case": row["case"],
            }

        elif position is not None:
            # Stop-loss tetiklendi mi?
            hit_stop = row["Close"] < position["stop"]
            exit_signal = row["signal"] in ("SELL", "EXIT")

            if hit_stop or exit_signal:
                pnl = (row["Close"] - position["entry_price"]) / position["entry_price"] * 100
                trades.append(
                    {
                        "Giriş tarihi": position["entry_date"],
                        "Çıkış tarihi": i,
                        "Giriş fiyatı": round(float(position["entry_price"]), 2),
                        "Çıkış fiyatı": round(float(row["Close"]), 2),
                        "PnL %": round(float(pnl), 2),
                        "Case": position["case"],
                        "Çıkış nedeni": "Stop-loss" if hit_stop else row["case"],
                    }
                )
                position = None

    result_df = pd.DataFrame(trades)
    if result_df.empty:
        return {"trades": result_df, "win_rate": 0, "avg_pnl": 0, "total_pnl": 0, "buy_hold": 0}

    win_rate = (result_df["PnL %"] > 0).mean() * 100
    avg_pnl = result_df["PnL %"].mean()
    total_pnl = result_df["PnL %"].sum()

    # Buy & hold same window (first close → last close) for context
    buy_hold = (float(df["Close"].iloc[-1]) / float(df["Close"].iloc[0]) - 1) * 100

    return {
        "trades": result_df,
        "win_rate": round(float(win_rate), 1),
        "avg_pnl": round(float(avg_pnl), 2),
        "total_pnl": round(float(total_pnl), 2),
        "buy_hold": round(buy_hold, 2),
    }


def run_symbol(symbol: str, interval: str = INTERVAL, period: str = PERIOD) -> dict:
    df = fetch_data(symbol, interval, period)
    if df.empty or len(df) < SENKOU_B_PERIOD + KIJUN_PERIOD + 10:
        raise RuntimeError(f"{symbol}: not enough data ({len(df)} bars)")
    df = add_ichimoku(df)
    df = add_rsi(df)
    df = find_divergence(df)
    df = generate_signals(df)
    result = backtest(df)
    result["symbol"] = symbol
    result["bars"] = len(df)
    result["last"] = df.iloc[-1]
    result["signals_tail"] = df[df["signal"].notna() & (df["signal"] != "WAIT")].tail(8)
    return result


def print_result(result: dict) -> None:
    symbol = result["symbol"]
    print(f"\n{'=' * 55}")
    print(f"  {symbol} | {INTERVAL} | {PERIOD} | bars={result['bars']}")
    print(f"{'=' * 55}")

    signals = result["signals_tail"]
    print("\nSon sinyaller (WAIT hariç):")
    if signals.empty:
        print("  (yok)")
    else:
        print(signals[["Close", "tenkan", "kijun", "rsi", "signal", "case"]].to_string())

    print(f"\n{'-' * 55}")
    print("Backtest (long-only, Kijun stop)")
    print(f"{'-' * 55}")

    if result["trades"].empty:
        print("  Yeterli tamamlanmış trade yok.")
    else:
        print(f"  Toplam trade : {len(result['trades'])}")
        print(f"  Kazanma oranı: %{result['win_rate']}")
        print(f"  Ortalama PnL : %{result['avg_pnl']}")
        print(f"  Toplam PnL*  : %{result['total_pnl']}  (trade'lerin toplamı, compound değil)")
        print(f"  Buy & hold   : %{result['buy_hold']}  (aynı dönemde sadece tut)")
        print("\n  Detay:")
        print(result["trades"].to_string(index=False))
    print(f"\n{'=' * 55}\n")


# ─────────────────────────────────────────────
# 7. ÇALIŞTIR
# ─────────────────────────────────────────────
if __name__ == "__main__":
    symbols = sys.argv[1:] or [SYMBOL]
    summary_rows = []
    for sym in symbols:
        try:
            result = run_symbol(sym.upper() if not sym.endswith((".IS", ".AS")) else sym)
            print_result(result)
            summary_rows.append(
                {
                    "Symbol": result["symbol"],
                    "Trades": len(result["trades"]),
                    "Win%": result["win_rate"],
                    "Avg PnL%": result["avg_pnl"],
                    "Sum PnL%": result["total_pnl"],
                    "BuyHold%": result["buy_hold"],
                }
            )
        except Exception as exc:
            print(f"\nFAIL {sym}: {exc}\n")

    if len(summary_rows) > 1:
        print("\nÖZET")
        print(pd.DataFrame(summary_rows).to_string(index=False))
        print()
