"""
Dumbi-JARVIS — SkillRL Manager
Loads learned heuristic files from the skills/ directory and injects
them into the system prompt. Scans for new skills on startup.
"""
import json
import logging
from pathlib import Path
from typing import List

from app.config import SKILLS_DIR

logger = logging.getLogger("JARVIS.Skills")

_cache: List[dict] = []


def load_skills() -> List[dict]:
    """Load all skill JSON files from the skills directory."""
    global _cache
    skills = []
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    for f in SKILLS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            skills.append(data)
        except Exception as e:
            logger.warning(f"Could not load skill {f.name}: {e}")
    _cache = skills
    logger.info(f"Loaded {len(skills)} skill(s) from {SKILLS_DIR}")
    return skills


def get_skill_context() -> str:
    """Return a formatted string of active skills for prompt injection."""
    if not _cache:
        load_skills()
    if not _cache:
        return ""
    lines = ["## Injected Skill Heuristics (SkillRL)\n"]
    for s in _cache:
        name = s.get("skill_name", "Unknown Skill")
        heuristic = s.get("heuristic", "")
        lines.append(f"- **{name}**: {heuristic}")
    return "\n".join(lines)


def save_skill(name: str, heuristic: str, origin: str = "user_correction"):
    """Persist a new learned skill to disk."""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    slug = name.lower().replace(" ", "_")
    path = SKILLS_DIR / f"{slug}.json"
    data = {
        "skill_name": name,
        "version": "1.0.0",
        "heuristic": heuristic,
        "origin": origin
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _cache.append(data)
    logger.info(f"New skill saved: {name}")
