"""
Dumbi-JARVIS — BORISLAV_PROFILE Manager
Persistent persona profile for Borislav Ignatov Marinov.
Extracts facts from conversations and stores them as a JSON knowledge base.
"""
import json
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger("JARVIS.Profile")

_PROFILE_PATH = Path(__file__).parent.parent.parent.parent / "BORISLAV_PROFILE.json"

_DEFAULT_PROFILE = {
    "user": {
        "name": "Borislav Ignatov Marinov",
        "preferred_address": "Mr. Marinov",
        "location": "Bulgaria",
        "timezone": "Europe/Sofia",
        "utc_offset": "+03:00",
    },
    "hardware": {
        "cpu": "Ryzen 7730U",
        "ram_gb": 16,
        "inference_engine": "Ollama",
        "quantization": "Q4_K_M",
        "thermal_limit_c": 80,
    },
    "preferences": {
        "language": "English",
        "response_style": "concise_with_detail_on_request",
        "preferred_languages_code": ["Python", "JavaScript"],
        "coding_style": "clean, readable, well-commented",
        "regions_of_interest": ["Bulgaria", "EU", "Technology"],
    },
    "projects": [],
    "learned_facts": [],
    "corrections": [],
    "last_updated": None,
}

_FACT_PATTERNS = [
    (r"\bi (?:prefer|like|use|always use|work with)\s+(.+?)(?:\.|,|$)", "preference"),
    (r"\bmy (?:project|app|system|website|server)\s+(?:is called|is named|is)\s+(.+?)(?:\.|,|$)", "project"),
    (r"\bi(?:'m| am) (?:working on|building|developing)\s+(.+?)(?:\.|,|$)", "project"),
    (r"\bmy (?:name is|name's)\s+(.+?)(?:\.|,|$)", "identity"),
    (r"\bi(?:'m| am) from\s+(.+?)(?:\.|,|$)", "location"),
    (r"\bi(?:'m| am) (?:a|an)\s+(.+?)(?:\.|,|$)", "role"),
]

_CORRECTION_PATTERNS = [
    r"\b(no,?\s+(?:actually|jarvis)|that'?s?\s+(?:wrong|incorrect|not right)|i prefer|i meant|not quite|the correct way)\b",
]


def load_profile() -> Dict[str, Any]:
    if _PROFILE_PATH.exists():
        try:
            return json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Profile load error: {e}")
    # Initialize fresh
    _PROFILE_PATH.write_text(json.dumps(_DEFAULT_PROFILE, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("BORISLAV_PROFILE.json initialized.")
    return dict(_DEFAULT_PROFILE)


def save_profile(profile: Dict[str, Any]):
    profile["last_updated"] = datetime.utcnow().isoformat()
    _PROFILE_PATH.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")


def extract_facts_from_message(message: str) -> list:
    """Extract learnable facts from a user message."""
    facts = []
    msg = message.strip().lower()
    for pattern, category in _FACT_PATTERNS:
        m = re.search(pattern, msg, re.IGNORECASE)
        if m:
            fact_value = m.group(1).strip()[:120]
            if len(fact_value) > 3:
                facts.append({"category": category, "value": fact_value, "ts": datetime.utcnow().isoformat()})
    return facts


def update_profile_from_message(message: str):
    """Auto-extract and persist facts from a user message."""
    facts = extract_facts_from_message(message)
    if not facts:
        return

    profile = load_profile()
    existing = {f["value"] for f in profile.get("learned_facts", [])}
    new_facts = [f for f in facts if f["value"] not in existing]

    if new_facts:
        profile.setdefault("learned_facts", []).extend(new_facts)
        save_profile(profile)
        logger.info(f"Profile updated: +{len(new_facts)} fact(s)")


def record_correction(correction_text: str):
    """Record a user correction into the profile."""
    profile = load_profile()
    profile.setdefault("corrections", []).append({
        "text": correction_text[:300],
        "ts": datetime.utcnow().isoformat()
    })
    if len(profile["corrections"]) > 100:
        profile["corrections"] = profile["corrections"][-100:]
    save_profile(profile)


def get_profile_context() -> str:
    """Build a profile context string for prompt injection."""
    profile = load_profile()
    lines = [
        f"## Primary User: {profile['user']['name']}",
        f"- Location: {profile['user']['location']} (UTC{profile['user']['utc_offset']})",
        f"- Address as: {profile['user']['preferred_address']}",
        f"- Hardware: {profile['hardware']['cpu']} | {profile['hardware']['ram_gb']}GB RAM",
        f"- Thermal limit: {profile['hardware']['thermal_limit_c']}°C",
    ]
    prefs = profile.get("preferences", {})
    if prefs.get("preferred_languages_code"):
        lines.append(f"- Preferred coding languages: {', '.join(prefs['preferred_languages_code'])}")
    if prefs.get("regions_of_interest"):
        lines.append(f"- Regions of interest: {', '.join(prefs['regions_of_interest'])}")

    facts = profile.get("learned_facts", [])[-10:]  # Last 10 facts
    if facts:
        lines.append("## Learned Facts")
        for f in facts:
            lines.append(f"  - [{f['category']}] {f['value']}")

    projects = profile.get("projects", [])[-5:]
    if projects:
        lines.append("## Known Projects")
        for p in projects:
            lines.append(f"  - {p}")

    return "\n".join(lines)


def get_user_name() -> str:
    profile = load_profile()
    return profile["user"]["preferred_address"]
