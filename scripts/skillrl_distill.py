#!/usr/bin/env python3
"""
Dumbi-JARVIS — SkillRL Failure Distillation Script
Run manually or via cron at 03:00 BG time to scan failure trajectories
and write "Lessons Learned" to the SKILLBANK.

Usage:
    python scripts/skillrl_distill.py [--limit 30]
"""
import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.core.trajectory_logger import get_failure_trajectories, init_trajectory_db
from app.core.eval_harness import run_evals_on_trajectory
from app.memory.reflection import _skillbank, save_skillbank, load_skillbank

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("JARVIS.SkillRL.Distill")


def distill_lesson(traj: dict, eval_report: dict) -> str:
    """Generate a concise lesson from a failure trajectory."""
    query   = (traj.get("query") or "")[:100]
    opinion = traj.get("gvu_opinion", "execute")
    monolog = (traj.get("inner_monologue") or "")[:200]

    # Collect which evals failed
    failed_evals = [
        name for name, r in eval_report.get("evals", {}).items()
        if not r["passed"]
    ]

    parts = [f"Query: '{query}'"]
    if opinion in ("oppose", "refine"):
        parts.append(f"JARVIS opposed — reason: {monolog[:80]}")
    if failed_evals:
        parts.append(f"Failed evals: {', '.join(failed_evals)}")

    return " | ".join(parts)


def run_distillation(limit: int = 30) -> int:
    """
    Main distillation loop.
    Returns number of new lessons written.
    """
    load_skillbank()
    init_trajectory_db()

    failures = get_failure_trajectories(limit=limit)
    if not failures:
        logger.info("No failure trajectories found — nothing to distill.")
        return 0

    new_lessons = 0
    for traj in failures:
        eval_report = run_evals_on_trajectory(traj)
        if eval_report["all_pass"]:
            continue  # Already passing — skip

        lesson_text = distill_lesson(traj, eval_report)
        key = f"skillrl_failure_{traj['id']}"

        if key in _skillbank:
            continue  # Already distilled

        _skillbank[key] = {
            "lesson":  lesson_text,
            "type":    "frustration",
            "source":  "skillrl_distillation",
            "traj_id": traj["id"],
            "ts":      datetime.utcnow().isoformat(),
        }
        new_lessons += 1
        logger.info(f"  + Lesson {traj['id']}: {lesson_text[:80]}")

    if new_lessons > 0:
        save_skillbank()
        logger.info(f"SkillRL distillation complete: {new_lessons} new lesson(s) written to SKILLBANK.")
    else:
        logger.info("No new lessons to distill.")

    return new_lessons


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JARVIS SkillRL Failure Distillation")
    parser.add_argument("--limit", type=int, default=30, help="Max trajectories to scan")
    args = parser.parse_args()

    count = run_distillation(limit=args.limit)
    sys.exit(0 if count >= 0 else 1)
