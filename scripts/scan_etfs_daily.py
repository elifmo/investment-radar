#!/usr/bin/env python3
"""
Daily ETF scan — technical overview + Excel report + Firestore.

Usage:
  python3 scripts/scan_etfs_daily.py
  python3 scripts/scan_etfs_daily.py --no-firestore
  python3 scripts/scan_etfs_daily.py --output reports/custom.xlsx
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from etf_scanner import results_to_dataframe, scan_all_etfs
from firebase_writer import init_firebase, write_etf_scan

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_REPORTS = Path(__file__).parent.parent / "reports"


def _export_excel(results: list[dict], out_path: Path) -> None:
    import pandas as pd

    df = results_to_dataframe(results)
    overview_cols = [
        "Bux Sembol", "Bux'ta Ara", "Ticker + İsim", "Tarih",
        "Fiyat (EUR)", "1 Gün %", "5 Gün %", "1 Ay (21G) %", "3 Ay (63G) %",
        "52H (EUR)", "52L (EUR)", "RSI", "Trend", "Sinyal", "Hacim Oranı", "Alım Önerisi",
    ]
    detail_cols = [
        "Bux Sembol", "Bux'ta Ara", "Ticker + İsim", "Fiyat (EUR)",
        "EMA20 (EUR)", "EMA50 (EUR)", "EMA200 (EUR)",
        "EMA20 Üstü?", "EMA50 Üstü?", "Destek 1 (EUR)", "Destek 2 (EUR)",
        "Direnç 1 (EUR)", "Direnç 2 (EUR)", "Limit Giriş (EUR)", "Stop (EUR)", "Hedef 1 (EUR)",
    ]
    profile_cols = [
        "Ticker + İsim", "Kısa İsim", "Tam Fon Adı", "Rol", "Risk", "Trend", "Sinyal", "Alım Önerisi",
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df[overview_cols].to_excel(writer, sheet_name="Overview", index=False)
        df[detail_cols].to_excel(writer, sheet_name="Detay S-R Strateji", index=False)
        df[profile_cols].to_excel(writer, sheet_name="Profil & Öneri", index=False)
        df.to_excel(writer, sheet_name="Tüm Veriler", index=False)
        for sheet in writer.sheets.values():
            for col in sheet.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                sheet.column_dimensions[col[0].column_letter].width = min(max_len + 2, 55)

    logger.info("Excel written: %s", out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily ETF technical scan")
    parser.add_argument("--no-firestore", action="store_true", help="Skip Firestore upload")
    parser.add_argument("--output", type=str, help="Custom Excel output path")
    args = parser.parse_args()

    results = scan_all_etfs()
    if not results:
        logger.error("No ETF data scanned — check config/etfs.yaml and network")
        sys.exit(1)

    scan_date = results[0].get("as_of_date") or date.today().isoformat()
    out_path = Path(args.output) if args.output else _REPORTS / f"ETF_Scan_{scan_date}.xlsx"
    _export_excel(results, out_path)

    if not args.no_firestore:
        db = init_firebase()
        write_etf_scan(db, results, scan_date=scan_date)

    logger.info("ETF scan complete — %d ETFs", len(results))


if __name__ == "__main__":
    main()
