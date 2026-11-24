"""Shared clients and helpers for Beta V1 agents.

All user-facing LLM text must be clear English (see beta-version/DEVELOPMENT_PLAN.md).
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Prompt suffix for every Haiku/Sonnet call in this package.
ENGLISH_OUTPUT_RULE = (
    "Respond in clear, plain English only. "
    "Use direct action language a retail investor can act on. "
    "Do not mix languages."
)


def get_radar_user_id() -> str:
    """Firestore Auth uid whose radar_items / trade_entries agents personalize for."""
    uid = os.environ.get("RADAR_USER_ID", "").strip()
    if not uid:
        raise RuntimeError(
            "RADAR_USER_ID is not set. Agents need the portfolio owner's Firebase Auth uid."
        )
    return uid


def get_anthropic_client():
    """Lazy Anthropic client. Requires ANTHROPIC_API_KEY."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")
    from anthropic import Anthropic

    return Anthropic(api_key=api_key)


def write_agent_doc(db: Any, doc_id: str, data: dict) -> None:
    """Write/merge a top-level document under agents/{doc_id}."""
    payload = {**data, "layer": "beta_v1"}
    db.collection("agents").document(doc_id).set(payload, merge=True)
    logger.info("Wrote agents/%s", doc_id)
