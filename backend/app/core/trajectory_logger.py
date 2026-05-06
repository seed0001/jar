"""
Dumbi-JARVIS — Trajectory Logger
Saves every reasoning trace to SQLite for:
  - Debugging and evaluation
  - SkillRL failure distillation
  - Binary eval harness
"""
import json
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("JARVIS.TrajectoryLogger")

TRAJ_DB = Path(__file__).parent.parent.parent.parent / "trajectories.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(TRAJ_DB))
    conn.row_factory = sqlite3.Row
    return conn


def init_trajectory_db():
    """Create trajectories table if not exists."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trajectories (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT    NOT NULL,
                session_id  TEXT,
                query       TEXT,
                tier        INTEGER,
                gvu_opinion TEXT,
                gvu_confidence REAL,
                gvu_entropy    REAL,
                inner_monologue TEXT,
                sat_upgraded   INTEGER DEFAULT 0,
                think_steps    TEXT,    -- JSON array
                prism_score    REAL,
                cove_notes     TEXT,    -- JSON array
                response       TEXT,
                latency_ms     REAL,
                cpu_temp_c     REAL,
                ram_used_gb    REAL,
                passed_eval    INTEGER  -- 1=pass, 0=fail, NULL=not evaluated
            )
        """)
        conn.commit()
    logger.info(f"Trajectory DB ready at {TRAJ_DB}")


def log_trajectory(
    session_id: str,
    query: str,
    tier: int,
    gvu_result: dict,
    think_steps: list,
    response: str,
    latency_ms: float,
    hw: dict,
    prism_score: Optional[float] = None,
    cove_notes: Optional[list] = None,
    sat_upgraded: bool = False,
):
    """Insert one full reasoning trajectory into the DB."""
    try:
        with _get_conn() as conn:
            conn.execute("""
                INSERT INTO trajectories
                (ts, session_id, query, tier,
                 gvu_opinion, gvu_confidence, gvu_entropy, inner_monologue,
                 sat_upgraded, think_steps, prism_score, cove_notes,
                 response, latency_ms, cpu_temp_c, ram_used_gb)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                datetime.utcnow().isoformat(),
                session_id,
                query[:500],
                tier,
                gvu_result.get("opinion", "execute"),
                gvu_result.get("confidence", 100),
                gvu_result.get("entropy", 0.0),
                gvu_result.get("inner_monologue", "")[:1000],
                1 if sat_upgraded else 0,
                json.dumps(think_steps[:20] if think_steps else []),
                prism_score,
                json.dumps(cove_notes[:10] if cove_notes else []),
                response[:2000],
                latency_ms,
                hw.get("cpu_temp_c", 0),
                hw.get("ram_used_gb", 0),
            ))
            conn.commit()
    except Exception as e:
        logger.error(f"Trajectory log error: {e}")


def get_failure_trajectories(limit: int = 50) -> list[dict]:
    """Return trajectories where GVU opposed or PRISM score was low."""
    try:
        with _get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM trajectories
                WHERE gvu_opinion IN ('oppose', 'refine')
                   OR prism_score < 0
                   OR passed_eval = 0
                ORDER BY ts DESC LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Trajectory fetch error: {e}")
        return []


def get_recent_trajectories(limit: int = 20) -> list[dict]:
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trajectories ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Trajectory fetch error: {e}")
        return []


def mark_eval_result(traj_id: int, passed: bool):
    """Mark a trajectory as pass/fail after binary eval."""
    try:
        with _get_conn() as conn:
            conn.execute(
                "UPDATE trajectories SET passed_eval=? WHERE id=?",
                (1 if passed else 0, traj_id)
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Eval mark error: {e}")
