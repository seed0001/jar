"""
J.A.R. — Episodic Memory Manager v2
SQLite-backed persistent memory with rich metadata, buffer + archival pattern.
Enhancements:
  - save_message now stores power_level, cognitive_mode metadata
  - Periodic flush of in-memory buffer to DB on a background task
  - Basic compression: messages older than COMPRESS_AFTER_TURNS are summarized
"""
import json
import logging
import asyncio
import shutil
import sqlite3
import zlib
import base64
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

import aiosqlite

from app.config import DB_PATH, BUFFER_LIMIT

logger = logging.getLogger("JAR.Memory")

# One-shot: if FTS is unreadable even after drop/recreate, archive DB and bootstrap a new file.
_memory_db_recovery_attempted = False


class FTSRepairImpossible(Exception):
    """Corrupt FTS5 index cannot be fixed in place; caller may replace jar_memory.db."""

# After how many messages per session do we compress older ones
COMPRESS_AFTER_TURNS = 40
# How many recent messages to keep verbatim before compressing the rest
KEEP_RECENT = 20


def _fts_error(e: BaseException) -> bool:
    msg = str(e).lower()
    return ("fts5" in msg) or ("malformed" in msg) or (("fts" in msg) and ("rebuild" in msg))


async def _recreate_messages_fts_full(db: aiosqlite.Connection) -> None:
    """Drop and recreate FTS5 + backfill from messages (when rebuild is not enough)."""
    await db.execute("DROP TABLE IF EXISTS messages_fts")
    await db.commit()
    await db.execute(
        "CREATE VIRTUAL TABLE messages_fts USING fts5(content, session UNINDEXED, role UNINDEXED, ts UNINDEXED)"
    )
    await db.execute(
        """INSERT INTO messages_fts (content, session, role, ts)
           SELECT content, session, role, ts FROM messages"""
    )
    await db.commit()
    logger.info("messages_fts recreated and repopulated from messages")


async def _rebuild_messages_fts(db: aiosqlite.Connection) -> None:
    """Rebuild FTS5 shadow tables (fixes some invalid fts5 file format cases)."""
    await db.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")


async def _insert_messages_fts(
    db: aiosqlite.Connection,
    content: str,
    session_id: str,
    role: str,
    ts: str,
) -> None:
    """Insert one row into messages_fts; repair FTS on corruption (rebuild, then full recreate)."""
    sql = "INSERT INTO messages_fts (content, session, role, ts) VALUES (?, ?, ?, ?)"
    params = (content, session_id, role, ts)

    try:
        await db.execute(sql, params)
        return
    except Exception as e:
        if not _fts_error(e):
            raise
        logger.warning("messages_fts insert failed (%s) — rebuilding FTS index", e)

    try:
        await _rebuild_messages_fts(db)
        await db.execute(sql, params)
        return
    except Exception as e2:
        if not _fts_error(e2):
            raise
        logger.warning("FTS rebuild failed (%s) — recreating messages_fts from scratch", e2)

    await _recreate_messages_fts_full(db)
    await db.execute(sql, params)


def _archive_corrupt_memory_db() -> None:
    """Rename jar_memory.db so a new file can be created (chat history in old file is lost)."""
    p = Path(DB_PATH)
    if not p.is_file():
        return
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    dest = p.with_name(f"jar_memory.corrupt.{stamp}.db")
    shutil.move(str(p), str(dest))
    logger.warning(
        "Renamed unreadable memory DB to %s (FTS5 corruption). Starting with a new empty database.",
        dest.name,
    )


async def init_db():
    """Initialize the SQLite schema — extended with metadata columns."""
    global _memory_db_recovery_attempted
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session       TEXT    NOT NULL,
                role          TEXT    NOT NULL,
                content       TEXT    NOT NULL,
                ts            TEXT    NOT NULL,
                power_level   INTEGER DEFAULT 2,
                cognitive_mode TEXT   DEFAULT 'standard',
                compressed    INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id        TEXT PRIMARY KEY,
                title     TEXT,
                summary   TEXT,
                created   TEXT NOT NULL,
                updated   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS found_facts (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                fact      TEXT NOT NULL,
                source    TEXT,
                ts        TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
                USING fts5(content, session UNINDEXED, role UNINDEXED, ts UNINDEXED);
            """)
            # Add columns if they don't exist yet (safe migration)
            for col, typedef in [
                ("power_level",    "INTEGER DEFAULT 2"),
                ("cognitive_mode", "TEXT DEFAULT 'standard'"),
                ("compressed",     "INTEGER DEFAULT 0"),
            ]:
                try:
                    await db.execute(f"ALTER TABLE messages ADD COLUMN {col} {typedef}")
                except Exception:
                    pass  # Column already exists
            # If FTS shadow data is corrupt, repair or replace DB (otherwise startup / chat crash).
            try:
                await db.execute("SELECT 1 FROM messages_fts LIMIT 1")
            except Exception as e:
                if not _fts_error(e):
                    raise
                logger.warning("messages_fts unreadable at startup (%s) — repairing", e)
                try:
                    await _rebuild_messages_fts(db)
                    await db.execute("SELECT 1 FROM messages_fts LIMIT 1")
                except Exception as e2:
                    if not _fts_error(e2):
                        raise
                    logger.warning("FTS rebuild failed (%s) — drop/recreate messages_fts", e2)
                    try:
                        await _recreate_messages_fts_full(db)
                    except Exception as e3:
                        if not _fts_error(e3):
                            raise
                        logger.error("FTS still broken after recreate (%s)", e3)
                        raise FTSRepairImpossible() from e3
            await db.commit()
    except FTSRepairImpossible:
        if _memory_db_recovery_attempted:
            raise RuntimeError(
                "jar_memory.db FTS5 could not be repaired. Delete jar_memory.db manually and restart."
            ) from None
        _memory_db_recovery_attempted = True
        _archive_corrupt_memory_db()
        await init_db()
        return
    logger.info("JAR Memory DB initialized (v2 schema).")


async def save_message(
    session_id: str,
    role: str,
    content: str,
    power_level: int = 2,
    cognitive_mode: str = "standard",
):
    """
    Persist a message with rich metadata (timestamp, power level, cognitive mode).
    Also maintains the FTS index and upserts the session record.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        ts = datetime.utcnow().isoformat()
        await db.execute(
            """INSERT INTO messages
               (session, role, content, ts, power_level, cognitive_mode)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, role, content, ts, power_level, cognitive_mode)
        )
        await _insert_messages_fts(db, content, session_id, role, ts)
        await db.execute(
            """INSERT INTO sessions (id, title, created, updated) VALUES (?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET updated=excluded.updated""",
            (session_id, session_id[:20], ts, ts)
        )
        await db.commit()


async def get_buffer(session_id: str) -> List[Dict]:
    """Return the last BUFFER_LIMIT non-compressed messages for this session."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT role, content FROM messages
               WHERE session=? AND compressed=0
               ORDER BY id DESC LIMIT ?""",
            (session_id, BUFFER_LIMIT)
        ) as cursor:
            rows = await cursor.fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def search_memory(query: str, limit: int = 5) -> List[str]:
    """Full-text search across all sessions. Falls back to LIKE on FTS5 errors."""
    import re as _re
    safe_q = _re.sub(r'[",\(\)\*\:\^\~\!\+\-]', ' ', query).strip()
    words = safe_q.split()[:10]
    fts_query = " ".join(words) if words else "JAR"

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        try:
            async with db.execute(
                "SELECT content, ts FROM messages_fts WHERE messages_fts MATCH ? ORDER BY rank LIMIT ?",
                (fts_query, limit)
            ) as cursor:
                rows = await cursor.fetchall()
        except Exception:
            like_q = f"%{query[:60]}%"
            async with db.execute(
                "SELECT content, ts FROM messages WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
                (like_q, limit)
            ) as cursor:
                rows = await cursor.fetchall()
    return [f"[{r['ts'][:10]}] {r['content']}" for r in rows]


async def get_sessions() -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, title, summary, updated FROM sessions ORDER BY updated DESC LIMIT 50"
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def update_session_title(session_id: str, title: str, summary: Optional[str] = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sessions SET title=?, summary=? WHERE id=?",
            (title, summary, session_id)
        )
        await db.commit()


async def save_fact(fact: str, source: str = "conversation"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO found_facts (fact, source, ts) VALUES (?, ?, ?)",
            (fact, source, datetime.utcnow().isoformat())
        )
        await db.commit()


async def get_buffer_full(session_id: str) -> List[Dict]:
    """Return ALL messages for a session (for sidebar history loading)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT role, content, ts, power_level, cognitive_mode FROM messages WHERE session=? ORDER BY id ASC",
            (session_id,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [
        {
            "role": r["role"], "content": r["content"], "ts": r["ts"],
            "power_level": r["power_level"], "cognitive_mode": r["cognitive_mode"],
        }
        for r in rows
    ]


async def delete_session_db(session_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM messages WHERE session=?", (session_id,))
        await db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        await db.execute("DELETE FROM messages_fts WHERE session=?", (session_id,))
        await db.commit()
    logger.info(f"Session deleted: {session_id[:8]}")


async def clear_all_history():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM messages")
        await db.execute("DELETE FROM sessions")
        await db.execute("DELETE FROM found_facts")
        await db.execute("DELETE FROM messages_fts")
        await db.commit()
    logger.info("All history cleared.")


def _compress_text(text: str) -> str:
    """Compress text using zlib, return base64-encoded string."""
    compressed = zlib.compress(text.encode("utf-8"), level=6)
    return base64.b64encode(compressed).decode("ascii")


def _decompress_text(data: str) -> str:
    """Decompress base64-encoded zlib text."""
    try:
        raw = base64.b64decode(data.encode("ascii"))
        return zlib.decompress(raw).decode("utf-8")
    except Exception:
        return data  # Return as-is if not compressed


async def compress_old_messages(session_id: str):
    """
    Compress messages beyond KEEP_RECENT for long sessions.
    Messages are zlib-compressed and flagged (compressed=1) in the DB.
    This reduces storage without losing conversation history.
    Runs automatically when session exceeds COMPRESS_AFTER_TURNS messages.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Count total uncompressed messages
        async with db.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE session=? AND compressed=0",
            (session_id,)
        ) as cur:
            row = await cur.fetchone()
            total = row["cnt"] if row else 0

        if total <= COMPRESS_AFTER_TURNS:
            return  # Not enough messages to warrant compression

        # Fetch IDs of old messages (exclude KEEP_RECENT newest)
        async with db.execute(
            """SELECT id, content FROM messages
               WHERE session=? AND compressed=0
               ORDER BY id ASC LIMIT ?""",
            (session_id, total - KEEP_RECENT)
        ) as cur:
            old_rows = await cur.fetchall()

        compressed_count = 0
        for row in old_rows:
            msg_id = row["id"]
            original = row["content"]
            if len(original) < 80:
                continue  # Too short to bother compressing
            try:
                c_content = _compress_text(original)
                await db.execute(
                    "UPDATE messages SET content=?, compressed=1 WHERE id=?",
                    (c_content, msg_id)
                )
                compressed_count += 1
            except Exception:
                pass

        if compressed_count:
            await db.commit()
            logger.info(f"Compressed {compressed_count} old messages for session {session_id[:8]}")


async def periodic_flush_task(interval_seconds: int = 300):
    """
    Background task: every N seconds, ensure in-flight messages are safely
    written (SQLite auto-commits, but this flushes WAL and runs compression).
    """
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("PRAGMA wal_checkpoint(PASSIVE)")
                await db.commit()
            logger.debug("Periodic WAL flush complete.")
        except Exception as e:
            logger.warning(f"Periodic flush error: {e}")
