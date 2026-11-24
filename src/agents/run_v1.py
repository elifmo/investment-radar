"""
Beta V1 nightly runner.

Runs after the existing USA pipeline. Soft-fail: always exit 0 so scoring CI stays green.
Per-step timing is written to agents/_run_log.

Usage:
  python -m src.agents.run_v1

Env:
  ANTHROPIC_API_KEY  — required for LLM agents
  RADAR_USER_ID      — Firebase Auth uid for radar_items
  RUN_AGENTS         — set to "false" to no-op (default: true)
"""

from __future__ import annotations

import logging
import os
import sys
import time
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agents.run_v1")


def _step(name: str, fn) -> dict:
    t0 = time.time()
    logger.info("START %s", name)
    try:
        fn()
        elapsed = round(time.time() - t0, 2)
        logger.info("OK    %s (%.1fs)", name, elapsed)
        return {"name": name, "ok": True, "seconds": elapsed, "error": None}
    except Exception as exc:
        elapsed = round(time.time() - t0, 2)
        logger.exception("FAIL  %s (%.1fs)", name, elapsed)
        return {
            "name": name,
            "ok": False,
            "seconds": elapsed,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc()[-1500:],
        }


def main() -> int:
    """Always returns 0 (Phase 4 soft-fail). Pipeline must not die on agent errors."""
    if os.environ.get("RUN_AGENTS", "true").strip().lower() in {"0", "false", "no"}:
        logger.info("RUN_AGENTS=false — skipping Beta V1 agents")
        return 0

    try:
        from src.firebase_writer import init_firebase

        db = init_firebase()
    except Exception:
        logger.exception("Firebase init failed — agents aborted (pipeline still OK)")
        return 0

    logger.info("Firebase ready · Beta V1 runner")
    run_started = datetime.now(timezone.utc)

    def _run_macro():
        from src.agents import macro_agent

        macro_agent.run(db)

    def _run_sector():
        from src.agents import sector_agent

        sector_agent.run(db)

    def _run_earnings():
        from src.agents import earnings_preview

        earnings_preview.run(db)

    def _run_exit():
        from src.agents import exit_signal_agent

        exit_signal_agent.run(db)

    def _run_candidates():
        from src.agents import candidates_runner

        candidates_runner.run(db)

    def _run_risk():
        from src.agents import risk_summary_agent

        risk_summary_agent.run(db)

    def _run_avg_down():
        from src.agents import avg_down_agent

        avg_down_agent.run(db)

    def _run_orchestrator():
        from src.agents import orchestrator_agent

        orchestrator_agent.run(db)

    def _run_logger():
        from src.tracking import decision_logger

        decision_logger.run(db)

    def _run_outcomes():
        from src.tracking import outcome_tracker

        outcome_tracker.run(db)

    steps = [
        ("macro_agent", _run_macro),
        ("sector_agent", _run_sector),
        ("earnings_preview", _run_earnings),
        ("exit_signal_agent", _run_exit),
        ("candidates_runner", _run_candidates),
        ("risk_summary", _run_risk),
        ("avg_down", _run_avg_down),
        ("orchestrator", _run_orchestrator),
        ("decision_logger", _run_logger),
        ("outcome_tracker", _run_outcomes),
    ]

    results = []
    for name, fn in steps:
        results.append(_step(name, fn))

    failures = sum(1 for r in results if not r["ok"])
    total_s = round(sum(r["seconds"] for r in results), 2)
    brief_ok = False
    try:
        brief_ok = db.collection("agents").document("daily_brief").get().exists
    except Exception:
        pass

    if failures:
        logger.warning(
            "%d agent step(s) failed · total %.1fs · brief_present=%s",
            failures,
            total_s,
            brief_ok,
        )
    else:
        logger.info("Beta V1 runner finished OK · total %.1fs", total_s)

    # Timing / status docs for dashboard + ops
    try:
        today = date.today().isoformat()
        payload = {
            "date": today,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "started_at": run_started.isoformat(),
            "status": "ok" if failures == 0 else "partial_failure",
            "failures": failures,
            "total_seconds": total_s,
            "brief_present": brief_ok,
            "steps": [
                {
                    "name": r["name"],
                    "ok": r["ok"],
                    "seconds": r["seconds"],
                    "error": r.get("error"),
                }
                for r in results
            ],
            "layer": "beta_full",
            "note": (
                "Beta learning loop needs 14+ days of outcomes before hit-rate is meaningful. "
                "Includes risk_summary + avg_down (Full phases 5–6)."
            ),
        }
        db.collection("agents").document("_runner_heartbeat").set(payload, merge=True)
        db.collection("agents").document("_run_log").collection("by_date").document(today).set(
            payload, merge=True
        )
    except Exception:
        logger.exception("Could not write agents/_runner_heartbeat or _run_log")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
