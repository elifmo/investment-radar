"""
Sector Agent (Beta V1 — Phase 1).

Reads existing sector_status from Firestore (pipeline). Maps to strengthening /
weakening / neutral. Optional ETF headlines for context. Haiku writes English summary.

Writes: agents/sector_rotation
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import yfinance as yf

from src.agents.client import ENGLISH_OUTPUT_RULE, get_anthropic_client, write_agent_doc
from src.layers.sector_rotation import SECTOR_ETFS

logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Pipeline short_status → agent label
_STATUS_MAP = {
    "LEADING": "strengthening",
    "IMPROVING": "strengthening",
    "WEAKENING": "weakening",
    "LAGGING": "weakening",
}


def _map_status(short_status: str) -> str:
    return _STATUS_MAP.get((short_status or "").upper(), "neutral")


def _load_sector_status(db: Any) -> list[dict]:
    """Load all sector_status docs written by the pipeline."""
    rows: list[dict] = []
    try:
        for doc in db.collection("sector_status").stream():
            data = doc.to_dict() or {}
            data["_id"] = doc.id
            rows.append(data)
    except Exception as exc:
        logger.warning("Failed to read sector_status: %s", exc)
    return rows


def _build_sectors_map(rows: list[dict]) -> dict[str, str]:
    """
    {sector_name_or_slug: strengthening|weakening|neutral}

    Prefer human sector name from doc; fall back to ETF id.
    """
    out: dict[str, str] = {}
    for row in rows:
        name = row.get("sector") or row.get("_id") or row.get("etf")
        if not name:
            continue
        label = _map_status(row.get("short_status", ""))
        # Mixed long/short → soft neutral if they disagree strongly
        short_s = (row.get("short_status") or "").upper()
        long_s = (row.get("long_status") or "").upper()
        if short_s in {"LEADING", "IMPROVING"} and long_s in {"WEAKENING", "LAGGING"}:
            label = "neutral"
        elif short_s in {"WEAKENING", "LAGGING"} and long_s in {"LEADING", "IMPROVING"}:
            label = "neutral"
        out[str(name)] = label
    return out


def _fetch_sector_headlines(etfs: list[str], per_etf: int = 2, max_total: int = 12) -> list[str]:
    headlines: list[str] = []
    for etf in etfs:
        if len(headlines) >= max_total:
            break
        try:
            items = yf.Ticker(etf).news or []
            n = 0
            for item in items:
                title = (item.get("title") or "").strip()
                if not title:
                    continue
                line = f"[{etf}] {title}"
                if line not in headlines:
                    headlines.append(line)
                    n += 1
                if n >= per_etf:
                    break
        except Exception as exc:
            logger.debug("News fetch failed for %s: %s", etf, exc)
    return headlines


def _pick_headline_etfs(rows: list[dict], limit: int = 4) -> list[str]:
    """Prefer non-neutral movers for news context."""
    ranked: list[tuple[int, str]] = []
    for row in rows:
        etf = row.get("etf") or row.get("_id")
        if not etf:
            continue
        short_s = (row.get("short_status") or "").upper()
        score = 2 if short_s in {"LEADING", "WEAKENING"} else 1 if short_s else 0
        ranked.append((score, str(etf)))
    ranked.sort(key=lambda x: -x[0])
    seen: list[str] = []
    for _, etf in ranked:
        if etf not in seen:
            seen.append(etf)
        if len(seen) >= limit:
            break
    # Fallback to defaults if Firestore empty
    if not seen:
        seen = list(SECTOR_ETFS.values())[:limit]
    return seen


def _fallback_summary(sectors: dict[str, str]) -> str:
    strong = [k for k, v in sectors.items() if v == "strengthening"]
    weak = [k for k, v in sectors.items() if v == "weakening"]
    parts = []
    if strong:
        parts.append("Strengthening: " + ", ".join(strong[:4]) + ".")
    if weak:
        parts.append("Weakening: " + ", ".join(weak[:4]) + ".")
    if not parts:
        parts.append("Sector tape is mixed; no clear rotation leader.")
    parts.append("Use this to tag holdings and filter new entries — not as a standalone buy signal.")
    return " ".join(parts)


def _haiku_summary(sectors: dict[str, str], headlines: list[str]) -> str:
    client = get_anthropic_client()
    sector_lines = "\n".join(f"- {k}: {v}" for k, v in sorted(sectors.items())) or "- (none)"
    headline_block = "\n".join(f"- {h}" for h in headlines) or "- (none)"
    prompt = f"""You are the Sector Rotation Agent for an investment dashboard.
Write exactly 2 short sentences in English for a morning brief.

Authoritative sector labels (do not contradict):
{sector_lines}

Recent sector ETF headlines (context only):
{headline_block}

{ENGLISH_OUTPUT_RULE}
Name the strongest and weakest areas. Tell the investor what to watch on existing holdings.
No bullet points. Do not invent sector labels."""

    message = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=220,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()
    return text or _fallback_summary(sectors)


def run(db: Any) -> dict:
    today = date.today().isoformat()
    rows = _load_sector_status(db)
    sectors = _build_sectors_map(rows)

    # If pipeline has not written yet, fall back to empty map (still write doc)
    etfs = _pick_headline_etfs(rows)
    headlines = _fetch_sector_headlines(etfs)

    try:
        summary = _haiku_summary(sectors, headlines) if sectors else (
            "Sector status is not available yet from the nightly pipeline. "
            "Tags will appear after sector_status is populated."
        )
    except Exception as exc:
        logger.warning("Haiku sector summary failed (%s) — fallback", exc)
        summary = _fallback_summary(sectors)

    payload = {
        "sectors": sectors,
        "summary": summary,
        "headlines": headlines,
        "updated_at": today,
    }
    write_agent_doc(db, "sector_rotation", payload)
    logger.info(
        "Sector rotation written (%d sectors, %d headlines)",
        len(sectors),
        len(headlines),
    )
    return payload
