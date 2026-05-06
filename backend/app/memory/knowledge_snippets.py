"""
Dumbi-JARVIS — Knowledge Snippets (Hybrid Memory)
Summarizes old sessions into compact snippets, injected into the
prompt only when semantically relevant to the current query.
Also runs the midnight SkillRL distillation job.
"""
import re
import json
import logging
import asyncio
import threading
from datetime import datetime, timedelta
from typing import List

import aiosqlite

from app.config import DB_PATH, SKILLS_DIR
from app.memory.skills import save_skill

logger = logging.getLogger("JARVIS.Snippets")


async def get_recent_context(session_id: str, query: str) -> str:
    """
    Pull the last 3 relevant snippets from OTHER sessions
    to inject cross-session awareness.
    Uses simple keyword matching (no vector needed for 7B efficiency).
    """
    keywords = [w for w in re.split(r'\W+', query.lower()) if len(w) > 3]
    if not keywords:
        return ""

    snippets = []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            # Exclude current session, grab recent messages that share keywords
            for kw in keywords[:3]:
                async with db.execute(
                    """SELECT content, role, ts FROM messages
                       WHERE session != ? AND content LIKE ?
                       ORDER BY id DESC LIMIT 2""",
                    (session_id, f"%{kw}%")
                ) as cur:
                    rows = await cur.fetchall()
                    for r in rows:
                        snip = f"[{r['ts'][:10]} · {r['role']}] {r['content'][:200]}"
                        if snip not in snippets:
                            snippets.append(snip)
    except Exception as e:
        logger.warning(f"Snippet retrieval error: {e}")

    if not snippets:
        return ""
    return "## Knowledge Snippets (from previous sessions)\n" + "\n".join(snippets[:4])


async def summarize_old_sessions():
    """
    Summarize sessions older than 24h into compact Knowledge Snippets.
    Stores summary in sessions.summary column.
    """
    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id FROM sessions WHERE updated < ? AND summary IS NULL", (cutoff,)
            ) as cur:
                old = [r["id"] for r in await cur.fetchall()]

            for sid in old:
                async with db.execute(
                    "SELECT role, content FROM messages WHERE session=? ORDER BY id LIMIT 30",
                    (sid,)
                ) as cur:
                    msgs = await cur.fetchall()

                if not msgs:
                    continue

                # Build a compact summary
                exchange = " | ".join(
                    f"{m['role']}: {m['content'][:80]}" for m in msgs[:8]
                )
                summary = f"Session {sid[:8]}: {exchange}"[:300]

                await db.execute(
                    "UPDATE sessions SET summary=? WHERE id=?", (summary, sid)
                )
            await db.commit()
        logger.info(f"Summarized {len(old)} old session(s).")
    except Exception as e:
        logger.error(f"Session summarization error: {e}")


# ── SkillRL Midnight Distillation ──────────────────────────────────────────────

async def run_skillrl_distillation():
    """
    SkillRL: Scan recent messages for correction patterns.
    If a user corrected JARVIS, extract the rule and save as a skill file.
    Runs every 24 hours.
    """
    logger.info("SkillRL: Starting nightly distillation...")
    correction_patterns = [
        r"\b(actually|no,?\s+that'?s?\s+wrong|incorrect|not quite|you missed|you forgot|correction|wrong)\b",
        r"\b(should be|it is actually|the correct answer|let me correct)\b",
    ]

    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT content, ts FROM messages WHERE role='user' AND ts > ? LIMIT 100",
                (cutoff,)
            ) as cur:
                rows = await cur.fetchall()

        corrections_found = 0
        for row in rows:
            content = row["content"]
            for pat in correction_patterns:
                if re.search(pat, content, re.IGNORECASE) and len(content) > 20:
                    # Extract the correction as a heuristic
                    slug = content[:40].strip().replace(" ", "_").lower()
                    slug = re.sub(r'[^a-z0-9_]', '', slug)[:30]
                    if slug:
                        save_skill(
                            name=f"User Correction: {content[:50]}",
                            heuristic=content[:300],
                            origin=f"SkillRL_{row['ts'][:10]}"
                        )
                        corrections_found += 1
                    break

        logger.info(f"SkillRL: Distilled {corrections_found} correction(s) into skill files.")
    except Exception as e:
        logger.error(f"SkillRL error: {e}")

    # Also summarize old sessions
    await summarize_old_sessions()


def schedule_skillrl():
    """Background thread — SkillRL runs at 03:00 BG time (UTC+3) every night."""
    async def _loop():
        while True:
            from datetime import timezone, timedelta
            bg_tz = timezone(timedelta(hours=3))
            now = datetime.now(bg_tz)
            # Target 03:00 BG time
            target = now.replace(hour=3, minute=0, second=0, microsecond=0)
            if now >= target:
                target = target.replace(day=target.day + 1)
            wait_secs = (target - now).total_seconds()
            logger.info(f"SkillRL: Next distillation in {wait_secs/3600:.1f} hours (03:00 BG time).")
            await asyncio.sleep(wait_secs)
            await run_skillrl_distillation()

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_loop())

    t = threading.Thread(target=_run, daemon=True, name="SkillRL-3AM-BG")
    t.start()
    logger.info("SkillRL 03:00 BG scheduler started.")
