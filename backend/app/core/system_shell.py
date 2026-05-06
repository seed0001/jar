"""
Run arbitrary PowerShell on Windows — same capability pattern as seed0001/claude machine.py.
Disabled unless JAR_SYSTEM_SHELL=1 (opt-in; full machine access when enabled).
"""
from __future__ import annotations

import logging
import platform
import subprocess
from dataclasses import dataclass

from app.config import JAR_SYSTEM_SHELL_ENABLED, JAR_SYSTEM_SHELL_TIMEOUT

logger = logging.getLogger("JAR.SystemShell")


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


def system_shell_enabled() -> bool:
    return JAR_SYSTEM_SHELL_ENABLED and platform.system() == "Windows"


def run_powershell(
    command: str,
    *,
    timeout_seconds: int | None = None,
) -> CommandResult:
    """
    Run a single command in PowerShell -NoProfile -Command, like claude/machine.py.
    """
    if not system_shell_enabled():
        return CommandResult(
            stdout="",
            stderr="System shell is disabled. Set JAR_SYSTEM_SHELL=1 in .env to allow [[JAR_RUN: ...]] (Windows only).",
            exit_code=-1,
            timed_out=False,
        )
    cmd = (command or "").strip()
    if not cmd:
        return CommandResult(stdout="", stderr="No command given.", exit_code=-1, timed_out=False)

    timeout = timeout_seconds if timeout_seconds is not None else JAR_SYSTEM_SHELL_TIMEOUT
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=None,
            env=None,
        )
        return CommandResult(
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            exit_code=int(proc.returncode or 0),
            timed_out=False,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(
            stdout="",
            stderr=f"Command timed out after {timeout} seconds.",
            exit_code=-1,
            timed_out=True,
        )
    except Exception as e:
        logger.warning("run_powershell failed: %s", e)
        return CommandResult(stdout="", stderr=str(e), exit_code=-1, timed_out=False)


def format_command_result(result: CommandResult, *, label: str = "PowerShell") -> str:
    lines = [
        f"### {label} result",
        "",
        f"- **Exit code:** {result.exit_code}",
        f"- **Timed out:** {result.timed_out}",
        "",
    ]
    if result.stdout.strip():
        lines.extend(["**Stdout:**", "```", result.stdout.strip(), "```", ""])
    if result.stderr.strip():
        lines.extend(["**Stderr:**", "```", result.stderr.strip(), "```", ""])
    return "\n".join(lines).rstrip() + "\n"
