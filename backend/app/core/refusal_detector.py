"""
Refusal / safety-block detection for routing fallback (local LLMs).
Configurable substrings, regexes, and score threshold.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import List, Pattern

from app.config import ROUTING_REFUSAL_EXTRA_PATTERNS_PATH, ROUTING_REFUSAL_THRESHOLD

logger = logging.getLogger("JAR.RefusalDetector")

# High-precision phrases (mid-stream safe — avoid "can't believe" false positives)
_STRONG_SUBSTRINGS: tuple[str, ...] = (
    "i cannot comply",
    "i can't comply",
    "i cannot assist with",
    "i can't assist with",
    "i cannot help with",
    "i can't help with",
    "i'm not able to assist",
    "i am not able to assist",
    "i'm not able to help",
    "i am not able to help",
    "i cannot fulfill",
    "i can't fulfill",
    "i cannot provide",
    "i can't provide",
    "i must refuse",
    "i'll have to refuse",
    "i will have to refuse",
    "violates our policy",
    "violates my policy",
    "violates policy",
    "against my guidelines",
    "against my usage guidelines",
    "against openai's",
    "against the content policy",
    "content policy prohibits",
    "i cannot continue",
    "i can't continue",
    "unable to comply with",
    "not able to comply",
    "i cannot engage",
    "i can't engage",
    "as an ai language model, i cannot",
    "i'm programmed to",
    "i am programmed to decline",
    "i have to decline",
    "i need to decline",
    "cannot assist with that request",
    "can't assist with that request",
)

# Weaker signals (count toward score; alone rarely enough)
_WEAK_SUBSTRINGS: tuple[str, ...] = (
    "i'm sorry, but i can't",
    "i am sorry, but i can't",
    "i'm sorry, but i cannot",
    "i apologize, but i cannot",
    "i apologize, but i can't",
    "not able to provide",
    "unable to provide",
    "cannot assist",
    "can't assist",
    "safety guidelines",
    "ethical guidelines",
    "harmful request",
    "inappropriate request",
)

_DEFAULT_REGEX: tuple[str, ...] = (
    r"\bi\s+can(?:'t|not)\s+(?:help|assist|comply|fulfill|provide)\b",
    r"\bunable\s+to\s+(?:help|assist|comply|fulfill)\b",
    r"\b(?:must|cannot)\s+refuse\b",
    r"\bcontent\s+policy\b",
)

_refusal_regexes: List[Pattern[str]] = [re.compile(p, re.I) for p in _DEFAULT_REGEX]
_extra_loaded = False


def _load_extra_patterns() -> None:
    global _refusal_regexes, _extra_loaded
    if _extra_loaded:
        return
    _extra_loaded = True
    path = ROUTING_REFUSAL_EXTRA_PATTERNS_PATH
    if not path:
        return
    p = Path(path)
    if not p.is_file():
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        subs = data.get("substrings") or []
        rxs = data.get("regexes") or []
        extra_subs: List[str] = [s.strip().lower() for s in subs if isinstance(s, str) and s.strip()]
        extra_rx: List[Pattern[str]] = []
        for r in rxs:
            if isinstance(r, str) and r.strip():
                try:
                    extra_rx.append(re.compile(r, re.I))
                except re.error as e:
                    logger.warning("Invalid refusal regex %r: %s", r, e)
        if extra_rx:
            _refusal_regexes.extend(extra_rx)
        if extra_subs:
            refusal_detector_extra_substrings.extend(extra_subs)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not load extra refusal patterns from %s: %s", path, e)


# Mutable extension from JSON file (substrings)
refusal_detector_extra_substrings: List[str] = []


def refusal_score(text: str) -> float:
    """
    Return 0.0–1.0 likelihood that `text` is a refusal / block. 1.0 = empty or clear refusal.
    """
    _load_extra_patterns()
    raw = text or ""
    t = raw.strip().lower()
    if not t:
        return 1.0

    score = 0.0

    for phrase in _STRONG_SUBSTRINGS:
        if phrase in t:
            score = max(score, 0.88)
            break

    for phrase in _WEAK_SUBSTRINGS:
        if phrase in t:
            score = max(score, score + 0.18)

    for phrase in refusal_detector_extra_substrings:
        if phrase in t:
            score = max(score, score + 0.2)

    for rx in _refusal_regexes:
        if rx.search(t):
            score = max(score, 0.9)

    # Very short boilerplate refusals
    if len(t) < 220 and ("sorry" in t or "apologize" in t) and ("can't" in t or "cannot" in t or "unable" in t):
        score = max(score, 0.72)

    return min(1.0, score)


def detect_refusal(text: str, *, threshold: float | None = None) -> bool:
    """
    True if the assistant output should be treated as a refusal for routing purposes.
    """
    th = ROUTING_REFUSAL_THRESHOLD if threshold is None else float(threshold)
    th = max(0.0, min(1.0, th))
    s = refusal_score(text)
    return s >= th


def detect_refusal_midstream(buffer: str) -> bool:
    """
    Conservative early detection while streaming (high precision only).
    """
    if not buffer or len(buffer) < 24:
        return False
    t = buffer.lower()
    for phrase in _STRONG_SUBSTRINGS:
        if phrase in t:
            return True
    for rx in _refusal_regexes:
        if rx.search(t):
            return True
    return False
