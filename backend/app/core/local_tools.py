"""
Local-only tools: constrained file reads, process list, extended system info.
Paths must fall under configured roots (see app.config).
"""
from __future__ import annotations

import logging
import os
import platform
import re
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import psutil

from app.config import (
    JAR_ALLOWED_READ_PATHS,
    JAR_FILE_READ_MAX_BYTES,
    JAR_PROCESS_LIMIT,
    REPO_ROOT,
)

logger = logging.getLogger("JAR.LocalTools")

_TEXT_EXT = re.compile(
    r"\.(?:txt|md|json|ya?ml|toml|ini|cfg|conf|py|js|ts|tsx|jsx|css|html|xml|"
    r"csv|log|env|sh|bat|ps1|sql|rs|go|c|h|cpp|hpp|java|kt|swift|rb|php|vue|svelte)$",
    re.I,
)
_TEXT_BASENAMES_OK = frozenset(
    x.lower()
    for x in (
        "README",
        "LICENSE",
        "Dockerfile",
        "Makefile",
        "Procfile",
        "Gemfile",
        "Rakefile",
        ".gitignore",
        ".dockerignore",
    )
)


def allowed_read_roots() -> List[Path]:
    raw = (JAR_ALLOWED_READ_PATHS or "").strip()
    if not raw:
        return [REPO_ROOT.resolve()]
    roots = []
    for part in raw.split(","):
        p = Path(os.path.expandvars(part.strip())).expanduser()
        try:
            roots.append(p.resolve())
        except OSError:
            continue
    return roots or [REPO_ROOT.resolve()]


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def resolve_safe_read_path(user_path: str) -> Tuple[Optional[Path], Optional[str]]:
    """
    Return (resolved_path, error_message). error_message set if access denied.
    """
    if not user_path or not str(user_path).strip():
        return None, "empty path"
    candidate = Path(os.path.expandvars(str(user_path).strip())).expanduser()
    try:
        resolved = candidate.resolve()
    except OSError as e:
        return None, f"invalid path: {e}"

    roots = allowed_read_roots()
    for root in roots:
        if _is_under(resolved, root):
            return resolved, None
    return None, f"path must be under allowed roots ({len(roots)} configured)"


def read_file_for_context(user_path: str) -> str:
    """Return markdown block for LLM injection, or error string (still one block)."""
    path, err = resolve_safe_read_path(user_path)
    if err or path is None:
        return f"### File read denied\n{err or 'unknown error'}\n"

    max_b = max(4096, min(JAR_FILE_READ_MAX_BYTES, 2_000_000))

    try:
        st = path.stat()
    except OSError as e:
        return f"### File read failed\n`{path}`: {e}\n"

    if st.st_size > max_b:
        return (
            f"### File too large\n`{path}` is {st.st_size} bytes "
            f"(limit {max_b}). Ask for a smaller slice or a different file.\n"
        )

    if path.is_dir():
        try:
            names = sorted(path.iterdir(), key=lambda p: p.name.lower())[:120]
        except OSError as e:
            return f"### Directory listing failed\n`{path}`: {e}\n"
        lines = [f"### Directory listing: `{path}`", ""]
        for ch in names:
            kind = "dir" if ch.is_dir() else "file"
            try:
                sz = ch.stat().st_size if ch.is_file() else 0
            except OSError:
                sz = -1
            lines.append(f"- **{ch.name}** ({kind}, {sz} bytes)")
        if not lines[2:]:
            lines.append("(empty)")
        return "\n".join(lines) + "\n"

    if path.is_file():
        nm = path.name
        if not _TEXT_EXT.search(nm) and nm.lower() not in _TEXT_BASENAMES_OK:
            return (
                f"### File skipped (non-text extension)\n`{path}` — "
                f"allowed text-like extensions only, Sir.\n"
            )

    try:
        raw = path.read_bytes()
    except OSError as e:
        return f"### File read failed\n`{path}`: {e}\n"

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("latin-1", errors="replace")
        except Exception as e:
            return f"### File decode failed\n`{path}`: {e}\n"

    if len(text) > max_b:
        text = text[:max_b] + f"\n\n… truncated to {max_b} characters …"

    return f"### File contents: `{path}`\n\n```\n{text}\n```\n"


def build_process_snapshot(limit: Optional[int] = None) -> str:
    lim = max(10, min(limit or JAR_PROCESS_LIMIT, 200))
    rows: List[Tuple[int, int, str, str]] = []
    for p in psutil.process_iter(["pid", "name", "username", "memory_info"]):
        try:
            info = p.info
            mi = info.get("memory_info")
            rss = mi.rss if mi else 0
            name = (info.get("name") or "")[:48]
            user = (info.get("username") or "")[:40]
            pid = int(info.get("pid") or 0)
            rows.append((rss, pid, name, user))
        except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError):
            continue
    rows.sort(reverse=True)
    lines = [
        f"### Running processes (top {lim} by resident memory)",
        "",
        "| RSS (MB) | PID | Name | User |",
        "| ---: | ---: | --- | --- |",
    ]
    for rss, pid, name, user in rows[:lim]:
        mb = round(rss / (1024 * 1024), 1)
        lines.append(f"| {mb} | {pid} | `{name}` | {user} |")
    lines.append("")
    lines.append("*Some system processes may be hidden due to access permissions.*")
    return "\n".join(lines) + "\n"


def build_extended_system_info() -> str:
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    lines = [
        "### Extended system information",
        "",
        f"- **OS:** {platform.system()} {platform.release()} ({platform.machine()})",
        f"- **Python:** {platform.python_version()}",
        f"- **CPU cores:** logical {psutil.cpu_count(logical=True)}, physical {psutil.cpu_count(logical=False)}",
        f"- **CPU usage (instant):** {psutil.cpu_percent(interval=None)}%",
        f"- **RAM:** {round(vm.used / 1e9, 2)} / {round(vm.total / 1e9, 2)} GB used ({vm.percent}%)",
        f"- **Swap:** {swap.percent}% used",
        "",
    ]
    try:
        bt = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc).astimezone()
        lines.append(f"- **Boot time (local):** {bt.isoformat(timespec='seconds')}")
    except Exception:
        pass

    lines.append("")
    lines.append("#### Disk partitions (usage)")
    for part in psutil.disk_partitions(all=False)[:12]:
        try:
            if "cdrom" in part.opts or not part.fstype:
                continue
            usage = psutil.disk_usage(part.mountpoint)
            lines.append(
                f"- `{part.device}` → `{part.mountpoint}` ({part.fstype}): "
                f"{round(usage.used / 1e9, 2)} / {round(usage.total / 1e9, 2)} GB "
                f"({usage.percent}% used)"
            )
        except PermissionError:
            continue
        except OSError:
            continue

    lines.append("")
    lines.append("#### Network interfaces (addresses, sample)")
    try:
        for name, addrs in list(psutil.net_if_addrs().items())[:14]:
            ips = [a.address for a in addrs if getattr(a, "family", None) == socket.AF_INET]
            if ips:
                lines.append(f"- **{name}:** {', '.join(ips[:4])}")
    except Exception as e:
        lines.append(f"- (interface enumeration failed: {e})")

    lines.append("")
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            lines.append("#### Temperature sensors")
            for key, entries in list(temps.items())[:4]:
                for e in entries[:2]:
                    lines.append(f"- {key}: {e.current}°C ({e.label or 'n/a'})")
    except Exception:
        pass

    return "\n".join(lines) + "\n"
