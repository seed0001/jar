"""
Resolved Ollama model names for chat routing (tiers + optional refusal fallback).
Reads `jar_tier_models.json` via app.config — no extra cache so UI saves apply immediately.
"""
from __future__ import annotations

from typing import Optional

from app.config import get_routing_from_disk


def get_fallback_model_name() -> Optional[str]:
    fb, _ = get_routing_from_disk()
    return fb if fb else None


def is_refusal_fallback_enabled() -> bool:
    _, en = get_routing_from_disk()
    return bool(en)


def effective_fallback_for_tier(primary: str) -> Optional[str]:
    """
    Fallback tag if routing is on and fallback is set and distinct from primary.
    """
    if not is_refusal_fallback_enabled():
        return None
    fb = get_fallback_model_name()
    if not fb or fb.strip() == primary.strip():
        return None
    return fb.strip()
