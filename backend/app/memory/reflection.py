"""
J.A.R. — Immediate Reflection Hook + SKILLBANK + Adaptive Heuristics
Runs after EVERY turn to extract lessons about Borislav.
Corrections/preferences are persisted to BORISLAV_PROFILE.json as
Adaptive Heuristics for long-term cross-session retention.
"""
import re
import json
import logging
from pathlib import Path
from datetime import datetime

from app.core.llm import llm

logger = logging.getLogger("JAR.Reflect")

SKILLBANK_PATH = Path(__file__).parent.parent.parent.parent / "skills" / "skillbank.json"
SKILLBANK_PATH.parent.mkdir(parents=True, exist_ok=True)
PROFILE_PATH = Path(__file__).parent.parent.parent.parent / "BORISLAV_PROFILE.json"

_skillbank: dict = {}

CORRECTION_PATTERNS = [
    r"\bno[,\s]", r"\bthat'?s?\s+wrong\b", r"\bincorrect\b", r"\bactually\b",
    r"\bi\s+prefer\b", r"\bdon'?t\s+(do|say|use)\b", r"\bstop\s+\w+ing\b",
    r"\bnot\s+right\b", r"\bwrong\b", r"\bi\s+want\b", r"\bi\s+like\b",
    r"\bi\s+hate\b", r"\balways\b", r"\bnever\b",
]


def load_skillbank() -> dict:
    global _skillbank
    try:
        if SKILLBANK_PATH.exists():
            _skillbank = json.loads(SKILLBANK_PATH.read_text(encoding="utf-8"))
    except Exception:
        _skillbank = {}
    return _skillbank


def save_skillbank():
    try:
        SKILLBANK_PATH.write_text(
            json.dumps(_skillbank, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:
        logger.error(f"Skillbank save error: {e}")


def _load_profile() -> dict:
    try:
        if PROFILE_PATH.exists():
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_profile(profile: dict):
    try:
        profile["last_updated"] = datetime.utcnow().isoformat() + "Z"
        PROFILE_PATH.write_text(
            json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:
        logger.error(f"Profile save error: {e}")


def _store_adaptive_heuristic(heuristic: str, heuristic_type: str):
    """Persist heuristic to SKILLBANK + BORISLAV_PROFILE.json."""
    key = re.sub(r'\W+', '_', heuristic[:40].lower())
    _skillbank[key] = {
        "lesson": heuristic, "type": heuristic_type,
        "source": "adaptive_heuristic", "ts": datetime.utcnow().isoformat()
    }
    save_skillbank()
    try:
        profile = _load_profile()
        heuristics = profile.get("adaptive_heuristics", [])
        existing = {h.get("heuristic", "")[:40] for h in heuristics}
        if heuristic[:40] not in existing:
            heuristics.append({
                "heuristic": heuristic, "type": heuristic_type,
                "source": "immediate_reflect", "ts": datetime.utcnow().isoformat()
            })
            profile["adaptive_heuristics"] = heuristics
            _save_profile(profile)
            logger.info(f"Adaptive heuristic → profile: {heuristic[:60]}")
    except Exception as e:
        logger.error(f"Heuristic profile persistence error: {e}")


def get_skillbank_context() -> str:
    if not _skillbank:
        return ""
    lines = [
        f"• [{e.get('type','preference')}] {e.get('lesson', k)}"
        for k, e in list(_skillbank.items())[-12:]
    ]
    if not lines:
        return ""
    return "## Borislav's SKILLBANK (Instantly Learned Preferences)\n" + "\n".join(lines)


def _has_correction_signal(query: str) -> bool:
    q = query.lower()
    return any(re.search(p, q) for p in CORRECTION_PATTERNS)


async def immediate_reflect(query: str, response: str) -> list[str]:
    """
    Post-turn reflection: extract preference/correction signals.
    Enhanced: detects Adaptive Heuristics and persists them to profile.
    """
    if len(response) < 40 or len(query) < 5:
        return []

    trivial_patterns = [r'\bhello\b', r'\bhi\b', r'thank', r'ok\b', r'bye\b', r'time\b']
    if any(re.search(p, query, re.I) for p in trivial_patterns):
        return []

    is_correction = _has_correction_signal(query)

    correction_hint = (
        "IMPORTANT: This message contains a correction or preference. "
        "Prioritize extracting it as an Adaptive Heuristic.\n" if is_correction else ""
    )

    prompt = (
        f"You analyze an AI conversation to extract durable lessons about the user's preferences.\n"
        f"User (Developer, Bulgaria): \"{query[:300]}\"\n"
        f"J.A.R. Response: \"{response[:500]}\"\n\n"
        f"{correction_hint}"
        f"Extract 0-2 short lessons. Format as JSON array with keys:\n"
        f"  \"lesson\" (string), \"type\" (preference|frustration|habit|goal|correction),\n"
        f"  \"is_adaptive_heuristic\" (boolean — true if it should change future behavior).\n"
        f"Return [] if nothing meaningful. Return ONLY the JSON array."
    )

    try:
        resp = llm.chat([
            {"role": "system", "content": "Extract user preference lessons. Respond ONLY with a JSON array."},
            {"role": "user", "content": prompt}
        ], tier=2, max_tokens=250, temperature=0.1)

        match = re.search(r'\[.*?\]', resp, re.DOTALL)
        if not match:
            return []

        lessons = json.loads(match.group())
        extracted = []

        for item in lessons[:2]:
            if not isinstance(item, dict) or "lesson" not in item:
                continue
            lesson_text = item["lesson"]
            lesson_type = item.get("type", "preference")
            is_heuristic = item.get("is_adaptive_heuristic", False)

            key = re.sub(r'\W+', '_', lesson_text[:40].lower())
            _skillbank[key] = {
                "lesson": lesson_text, "type": lesson_type,
                "source": "immediate_reflect", "ts": datetime.utcnow().isoformat()
            }
            extracted.append(lesson_text)

            if is_heuristic or lesson_type in ("correction", "frustration"):
                _store_adaptive_heuristic(lesson_text, lesson_type)

        if extracted:
            save_skillbank()
            logger.info(f"SKILLBANK +{len(extracted)} lesson(s): {extracted[0][:60]}")
        return extracted

    except Exception as e:
        logger.debug(f"Reflect error (non-critical): {e}")
        return []


def record_feedback(query: str, response: str, rating: int):
    """DPO-style preference signal. rating: +1 thumbs up, -1 thumbs down."""
    if rating < 0:
        lesson = f"J.A.R.'s response to '{query[:60]}' was unsatisfactory — avoid similar approach"
        key = f"dpo_fail_{hash(query) % 100000}"
        _skillbank[key] = {
            "lesson": lesson, "type": "frustration",
            "source": "user_thumbs_down", "rating": -1,
            "ts": datetime.utcnow().isoformat()
        }
        save_skillbank()
        _store_adaptive_heuristic(lesson, "frustration")
        logger.info(f"DPO 👎 recorded: '{query[:40]}'")
    else:
        key = f"dpo_good_{hash(response) % 100000}"
        _skillbank[key] = {
            "lesson": f"Response style approved for query type: '{query[:60]}'",
            "type": "preference", "source": "user_thumbs_up",
            "rating": +1, "ts": datetime.utcnow().isoformat()
        }
        save_skillbank()
        logger.info(f"DPO 👍 recorded: '{query[:40]}'")


load_skillbank()
