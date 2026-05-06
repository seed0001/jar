"""
Auto-select Ollama tier (1 = express, 2 = standard, 3 = deep) per query + hardware.
Uses heuristics only (no extra LLM call). Downgrades under thermal / battery / CPU load.
"""
from __future__ import annotations


def auto_select_tier(query: str, hw: dict) -> int:
    """
    Pick tier 1–3. Caller maps tier → model name via llm.get_model_for_tier().
    """
    q = (query or "").strip()
    low = q.lower()
    n_words = len(q.split())
    n_chars = len(q)

    tier = 2

    deep_markers = (
        "explain in detail",
        "step-by-step",
        "step by step",
        "prove ",
        "formal proof",
        "refactor",
        "architecture",
        "security audit",
        "line by line",
        "comprehensive",
        "deep dive",
        "mathematical",
        "derive ",
        "analyze in depth",
        "compare and contrast",
        "trade-offs",
        "tradeoffs",
        "optimize this",
        "debug this entire",
        "full code review",
        "edge cases",
    )

    # Tier 3: long / structured / explicit deep-reasoning asks
    if n_chars > 1100 or n_words > 160 or "```" in q or q.count("\n") > 14:
        tier = 3
    elif any(m in low for m in deep_markers) or n_words > 50:
        tier = 3

    # Tier 1: very short conversational / trivial
    elif n_words <= 5 and n_chars < 70 and "```" not in q:
        tier = 1
    elif n_words <= 10 and n_chars < 140:
        trivial = (
            "thanks", "thank you", "hello", "hi jar", "hey jar",
            "good morning", "bye", "what time", "ok", "okay",
        )
        if any(low == t or low.startswith(t + " ") or low.startswith(t + ",") for t in trivial):
            tier = 1
    elif n_words < 16 and n_chars < 320 and "```" not in q:
        tier = 1

    # Hardware-aware downgrades (same spirit as CPU_THROTTLE in .env)
    if hw.get("thermal_alert") or hw.get("battery_low"):
        tier = 1
    elif hw.get("cpu_high"):
        tier = max(1, tier - 1)

    return max(1, min(3, tier))
