"""
Refusal-based rerouting: buffer primary Ollama completion → detect block → stream fallback with same messages.
Invisible to the client except final `model_used` and structured logs.
"""
from __future__ import annotations

import logging
import time
from typing import Any, AsyncGenerator, Dict, List

from app.core.model_registry import effective_fallback_for_tier
from app.core.refusal_detector import detect_refusal

logger = logging.getLogger("JAR.Router")


async def stream_chat_with_refusal_routing(
    llm: Any,
    messages: List[Dict],
    *,
    tier: int,
    max_tokens: int = 2048,
    temperature: float = 0.7,
    routing_meta: Dict[str, Any],
) -> AsyncGenerator[str, None]:
    """
    Yields token strings. Mutates `routing_meta` with keys:
    primary_model, fallback_model, model_used, refusal_detected, rerouted, primary_ms, fallback_ms, error
    """
    routing_meta.clear()
    t0 = time.perf_counter()
    primary = llm.get_model_for_tier(tier)
    fallback = effective_fallback_for_tier(primary)
    routing_meta["primary_model"] = primary
    routing_meta["fallback_model"] = fallback
    routing_meta["refusal_detected"] = False
    routing_meta["rerouted"] = False
    routing_meta["model_used"] = primary
    routing_meta["fallback_ms"] = 0.0

    primary_tokens: List[str] = []
    t_primary = time.perf_counter()
    try:
        async for token in llm.stream_chat_with_model(
            messages, primary, max_tokens=max_tokens, temperature=temperature
        ):
            primary_tokens.append(token)
    except Exception as e:
        logger.exception("[ROUTER] Primary stream error: %s", e)
        routing_meta["error"] = str(e)
        routing_meta["primary_ms"] = round((time.perf_counter() - t_primary) * 1000, 1)
        raise

    acc = "".join(primary_tokens)
    routing_meta["primary_ms"] = round((time.perf_counter() - t_primary) * 1000, 1)

    if not fallback:
        for t in primary_tokens:
            yield t
        logger.info("[ROUTER] no fallback configured; primary=%s %.0fms", primary, routing_meta["primary_ms"])
        return

    refused = detect_refusal(acc) or not (acc or "").strip()
    if not refused:
        for t in primary_tokens:
            yield t
        logger.info(
            "[ROUTER] primary=%s ok in %.0fms (no reroute)",
            primary,
            routing_meta["primary_ms"],
        )
        return

    routing_meta["refusal_detected"] = True
    logger.warning("[ROUTER] Primary refused or empty; switching to fallback=%s", fallback)
    t_fb = time.perf_counter()
    try:
        async for token in llm.stream_chat_with_model(
            messages, fallback, max_tokens=max_tokens, temperature=temperature
        ):
            yield token
        routing_meta["rerouted"] = True
        routing_meta["model_used"] = fallback
    finally:
        routing_meta["fallback_ms"] = round((time.perf_counter() - t_fb) * 1000, 1)
        logger.info(
            "[ROUTER] reroute done primary_ms=%s fallback_ms=%s model_used=%s",
            routing_meta.get("primary_ms"),
            routing_meta.get("fallback_ms"),
            routing_meta.get("model_used"),
        )
