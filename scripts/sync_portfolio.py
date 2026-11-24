#!/usr/bin/env python3
"""
Sync config/portfolio.yaml → Firestore My Radar (radar_items + trade_entries).

Usage:
  python3 scripts/sync_portfolio.py --uid YOUR_FIREBASE_UID --dry-run
  python3 scripts/sync_portfolio.py --uid YOUR_FIREBASE_UID
  python3 scripts/sync_portfolio.py --uid UID --dsfir-opening-qty 4 --dsfir-opening-price 72.50
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CONFIG = ROOT / "config" / "portfolio.yaml"
SERVICE_ACCOUNT = ROOT / "serviceAccountKey.json"


def compute_position(trades: list[dict]) -> dict:
    """Mirror frontend computePosition() logic."""
    sorted_trades = sorted(trades, key=lambda t: t.get("trade_date") or t.get("date") or "")
    qty = 0.0
    cost_basis = 0.0
    realized_pnl = 0.0
    for t in sorted_trades:
        q = float(t.get("quantity") or t.get("qty") or 0)
        p = float(t.get("price") or 0)
        side = (t.get("side") or "buy").lower()
        if not q or not p:
            continue
        if side == "buy":
            cost_basis += q * p
            qty += q
        elif side == "sell":
            sell_qty = min(q, qty)
            if sell_qty <= 0:
                continue
            avg = cost_basis / qty if qty > 0 else 0
            realized_pnl += (p - avg) * sell_qty
            cost_basis -= avg * sell_qty
            qty -= sell_qty
    return {
        "remaining_qty": qty,
        "avg_cost": cost_basis / qty if qty > 0 else 0,
        "realized_pnl": realized_pnl,
    }


def load_portfolio(config_path: Path | None = None) -> tuple[list[dict], dict[str, list[dict]]]:
    path = config_path or CONFIG
    raw = yaml.safe_load(path.read_text()) or {}
    holdings = list(raw.get("holdings") or [])
    optional = [h for h in (raw.get("optional") or []) if not h.get("skip_without_opening")]
    holdings.extend(optional)
    trades_map = raw.get("trades") or {}
    return holdings, trades_map


def build_trade_list(
    ticker: str,
    trades_map: dict[str, list[dict]],
    opening_qty: float | None = None,
    opening_price: float | None = None,
    opening_date: str = "2026-01-01",
) -> list[dict]:
    rows = list(trades_map.get(ticker) or [])
    out = []
    if opening_qty and opening_price:
        out.append({
            "trade_date": opening_date,
            "side": "buy",
            "quantity": opening_qty,
            "price": opening_price,
        })
    for row in rows:
        out.append({
            "trade_date": row["date"],
            "side": row["side"],
            "quantity": float(row["qty"]),
            "price": float(row["price"]),
        })
    return out


def init_firestore():
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not SERVICE_ACCOUNT.exists():
        raise FileNotFoundError(f"Missing {SERVICE_ACCOUNT}")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(str(SERVICE_ACCOUNT)))
    return firestore.client()


def find_radar_item(db, uid: str, ticker: str):
    from google.cloud.firestore_v1.base_query import FieldFilter

    col = db.collection("radar_items")
    q = col.where(filter=FieldFilter("user_id", "==", uid)).where(
        filter=FieldFilter("ticker", "==", ticker)
    )
    for doc in q.stream():
        data = doc.to_dict()
        if data.get("status") != "exited":
            return doc.id, data
    return None, None


def delete_trades_for_radar(db, uid: str, radar_item_id: str) -> int:
    from google.cloud.firestore_v1.base_query import FieldFilter

    col = db.collection("trade_entries")
    q = col.where(filter=FieldFilter("user_id", "==", uid)).where(
        filter=FieldFilter("radar_item_id", "==", radar_item_id)
    )
    deleted = 0
    for doc in q.stream():
        if not dry_run_global:
            doc.reference.delete()
        deleted += 1
    return deleted


dry_run_global = False


def sync_holding(
    db,
    uid: str,
    holding: dict,
    trades: list[dict],
) -> dict:
    from google.cloud.firestore import SERVER_TIMESTAMP

    ticker = holding["ticker"]
    pos = compute_position(trades)

    if pos["remaining_qty"] <= 0 and not any(t["side"] == "sell" for t in trades):
        logger.warning("[%s] No remaining qty — skipping", ticker)
        return {"ticker": ticker, "skipped": True, "reason": "zero qty"}

    if pos["remaining_qty"] < 0:
        logger.warning("[%s] Negative qty after trades — need opening_trades or --opening flags", ticker)
        return {"ticker": ticker, "skipped": True, "reason": "negative qty"}

    status = holding.get("status") or ("holding" if pos["remaining_qty"] > 0 else "exited")
    radar_id, existing = find_radar_item(db, uid, ticker)

    summary = {
        "ticker": ticker,
        "radar_id": radar_id,
        "qty": pos["remaining_qty"],
        "avg_cost": round(pos["avg_cost"], 4),
        "realized_pnl": round(pos["realized_pnl"], 4),
        "trades": len(trades),
        "status": status,
    }

    if dry_run_global:
        logger.info(
            "[DRY-RUN] %s: %s sh @ %s (%d trades, status=%s)",
            ticker, summary["qty"], summary["avg_cost"], len(trades), status,
        )
        return summary

    col = db.collection("radar_items")
    payload = {
        "user_id": uid,
        "ticker": ticker,
        "thesis": holding.get("thesis") or f"Holding {ticker}",
        "exit_condition": holding.get("exit_condition") or "Review exit plan",
        "status": status,
        "is_active": status != "exited",
        "asset_type": holding.get("asset_type") or ("etf" if holding.get("platform") == "Bux" else "stock"),
        "platform": holding.get("platform"),
        "bucket": holding.get("bucket"),
        "currency": holding.get("currency"),
        "updated_at": SERVER_TIMESTAMP,
    }

    if radar_id:
        col.document(radar_id).update(payload)
        logger.info("Updated radar_items/%s for %s", radar_id, ticker)
    else:
        payload["added_at"] = SERVER_TIMESTAMP
        ref = col.add(payload)
        radar_id = ref[1].id
        summary["radar_id"] = radar_id
        logger.info("Created radar_items/%s for %s", radar_id, ticker)

    deleted = delete_trades_for_radar(db, uid, radar_id)
    if deleted:
        logger.info("  Removed %d old trade_entries", deleted)

    trade_col = db.collection("trade_entries")
    for t in trades:
        trade_col.add({
            "user_id": uid,
            "radar_item_id": radar_id,
            "ticker": ticker,
            "side": t["side"],
            "trade_date": t["trade_date"],
            "quantity": t["quantity"],
            "price": t["price"],
            "created_at": SERVER_TIMESTAMP,
        })
    logger.info("  Wrote %d trade_entries for %s", len(trades), ticker)
    return summary


def main() -> None:
    global dry_run_global
    parser = argparse.ArgumentParser(description="Sync portfolio.yaml to My Radar")
    parser.add_argument("--uid", required=True, help="Firebase Auth UID")
    parser.add_argument("--dry-run", action="store_true", help="Print summary without writing")
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--dsfir-opening-qty", type=float, default=None,
                        help="DSFIR shares held before statement sells")
    parser.add_argument("--dsfir-opening-price", type=float, default=None,
                        help="DSFIR average cost before sells")
    parser.add_argument("--include-dsfir", action="store_true",
                        help="Sync DSFIR optional holding (requires opening qty/price)")
    args = parser.parse_args()

    dry_run_global = args.dry_run
    holdings, trades_map = load_portfolio(args.config)

    optional_raw = yaml.safe_load(args.config.read_text()).get("optional") or []
    optional_tickers = {h["ticker"] for h in optional_raw}

    db = None if args.dry_run else init_firestore()

    summaries = []
    for holding in holdings:
        ticker = holding["ticker"]
        opening_qty = opening_price = None
        if ticker == "DSFIR" and args.include_dsfir:
            opening_qty = args.dsfir_opening_qty
            opening_price = args.dsfir_opening_price
            if not opening_qty or not opening_price:
                logger.warning("DSFIR: provide --dsfir-opening-qty and --dsfir-opening-price")
                continue
        trades = build_trade_list(ticker, trades_map, opening_qty, opening_price)
        if not trades:
            logger.warning("[%s] No trades — skipping", ticker)
            continue
        if args.dry_run:
            pos = compute_position(trades)
            summaries.append({
                "ticker": ticker,
                "qty": pos["remaining_qty"],
                "avg_cost": round(pos["avg_cost"], 4),
                "realized_pnl": round(pos["realized_pnl"], 4),
                "trades": len(trades),
                "status": holding.get("status", "holding"),
            })
            logger.info(
                "[DRY-RUN] %s: %.0f sh @ %.2f (%d trades)",
                ticker, pos["remaining_qty"], pos["avg_cost"], len(trades),
            )
        else:
            summaries.append(sync_holding(db, args.uid, holding, trades))

    # Optional DSFIR not in holdings list unless include-dsfir
    if args.include_dsfir and "DSFIR" in optional_tickers:
        dsfir_h = next(h for h in optional_raw if h["ticker"] == "DSFIR")
        if not any(s.get("ticker") == "DSFIR" for s in summaries):
            trades = build_trade_list(
                "DSFIR", trades_map,
                args.dsfir_opening_qty, args.dsfir_opening_price,
            )
            if trades and not args.dry_run:
                summaries.append(sync_holding(db, args.uid, dsfir_h, trades))
            elif trades and args.dry_run:
                pos = compute_position(trades)
                summaries.append({
                    "ticker": "DSFIR",
                    "qty": pos["remaining_qty"],
                    "avg_cost": round(pos["avg_cost"], 4),
                    "realized_pnl": round(pos["realized_pnl"], 4),
                    "trades": len(trades),
                })

    print("\n=== SYNC SUMMARY ===")
    print(f"{'Ticker':<8} {'Qty':>6} {'AvgCost':>10} {'RealizedPnL':>12} {'Trades':>7}")
    for s in summaries:
        if s.get("skipped"):
            print(f"{s['ticker']:<8} SKIPPED ({s.get('reason')})")
        else:
            cur = "EUR" if s["ticker"] == "DSFIR" else "USD"
            print(
                f"{s['ticker']:<8} {s['qty']:>6.0f} {s['avg_cost']:>9.2f} {cur:<4} "
                f"{s.get('realized_pnl', 0):>11.2f} {s['trades']:>7}"
            )
    if args.dry_run:
        print("\n(dry-run — no Firestore writes)")


if __name__ == "__main__":
    main()
