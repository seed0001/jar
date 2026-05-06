"""
Dumbi-JARVIS — Hybrid Memory Pattern
Keeps last 20 messages in full fidelity.
Older messages are summarized into "Context Profiles" — compact semantic snapshots.
"""
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

import aiosqlite

from app.config import DB_PATH
from app.core.llm import llm

logger = logging.getLogger("JARVIS.Memory.Context")

CONTEXT_PROFILES_PATH = Path(__file__).parent.parent.parent.parent / "context_profiles.json"
HIGH_FIDELITY_LIMIT = 20  # Messages kept verbatim


def _load_profiles() -> dict:
    try:
        if CONTEXT_PROFILES_PATH.exists():
            return json.loads(CONTEXT_PROFILES_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_profiles(profiles: dict):
    try:
        CONTEXT_PROFILES_PATH.write_text(
            json.dumps(profiles, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception as e:
        logger.error(f"Context profile save error: {e}")


async def maybe_compress_session(session_id: str):
    """
    If a session has > HIGH_FIDELITY_LIMIT messages, summarize the older half
    into a Context Profile and trim the DB to only keep recent messages.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, role, content FROM messages WHERE session=? ORDER BY id ASC",
            (session_id,)
        ) as cursor:
            rows = list(await cursor.fetchall())

    total = len(rows)
    if total <= HIGH_FIDELITY_LIMIT:
        return  # Nothing to compress

    old_msgs = rows[:total - HIGH_FIDELITY_LIMIT]
    if not old_msgs:
        return

    # Build text for summarization
    convo_text = "\n".join(
        f"{r['role'].upper()}: {r['content'][:300]}"
        for r in old_msgs
    )

    prompt = f"""Summarize this conversation segment into a compact "Context Profile" — 3-5 bullet points capturing the most important facts, decisions, and preferences revealed. Focus on information useful for future turns.

Conversation:
{convo_text[:2000]}

Output ONLY bullet points starting with •:"""

    try:
        summary = llm.chat([
            {"role": "system", "content": "You create compact context profiles from conversation history."},
            {"role": "user", "content": prompt}
        ], tier=1, max_tokens=300, temperature=0.1)

        # Save profile
        profiles = _load_profiles()
        profiles[session_id] = {
            "summary":     summary.strip(),
            "compressed_count": len(old_msgs),
            "ts":          datetime.utcnow().isoformat()
        }
        _save_profiles(profiles)
        logger.info(f"Context Profile created for session {session_id[:8]}: {len(old_msgs)} msgs compressed.")

        # Delete old messages from DB (keep only recent HIGH_FIDELITY_LIMIT)
        old_ids = [r["id"] for r in old_msgs]
        async with aiosqlite.connect(DB_PATH) as db:
            placeholders = ",".join("?" * len(old_ids))
            await db.execute(f"DELETE FROM messages WHERE id IN ({placeholders})", old_ids)
            await db.commit()

    except Exception as e:
        logger.warning(f"Context compression failed (non-critical): {e}")


def get_context_profile(session_id: str) -> Optional[str]:
    """Return the compressed Context Profile for a session, if it exists."""
    profiles = _load_profiles()
    p = profiles.get(session_id)
    if not p:
        return None
    return (
        f"## Context Profile (from earlier in this session)\n"
        f"{p['summary']}\n"
        f"[{p['compressed_count']} messages compressed on {p['ts'][:10]}]"
    )
