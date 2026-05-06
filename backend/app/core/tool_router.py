"""
Plan and run local tools for /chat: DuckDuckGo web search, file reads, system/process info.
Uses explicit [[JAR_*]] tags plus optional phrase heuristics (JAR_TOOL_HEURISTICS).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Tuple

from app.config import (
    JAR_INJECT_WINSTATE_EACH_CHAT,
    JAR_TOOL_HEURISTICS,
    REPO_ROOT,
)
from app.core.local_tools import (
    build_extended_system_info,
    build_process_snapshot,
    read_file_for_context,
)
from app.core.system_shell import format_command_result, run_powershell
from app.core.web_search import multi_hop_search, web_search_available
from app.core.windows_state import get_full_windows_state

logger = logging.getLogger("JAR.ToolRouter")

RE_TAG_WEB = re.compile(r"\[\[JAR_WEB:\s*(.+?)\s*\]\]", re.I | re.DOTALL)
RE_TAG_FILE = re.compile(r"\[\[JAR_READ_FILE:\s*(.+?)\s*\]\]", re.I | re.DOTALL)
RE_TAG_SYSINFO = re.compile(r"\[\[JAR_SYSINFO\]\]", re.I)
RE_TAG_PROCESSES = re.compile(r"\[\[JAR_PROCESSES\]\]", re.I)
RE_TAG_WINSTATE = re.compile(r"\[\[JAR_WINSTATE\]\]", re.I)
RE_TAG_RUN = re.compile(r"\[\[JAR_RUN:\s*(.+?)\s*\]\]", re.I | re.DOTALL)

RE_HEUR_FILE = re.compile(
    r"\b(?:read|show|open|display|cat)\s+(?:the\s+)?(?:file\s+)?[`'\"]?([a-zA-Z]:\\[^\n`'\"<>|*?]{2,260})",
    re.I,
)
RE_REPO_REL = re.compile(
    r"\b(?:read|show|open|display|cat)\s+(?:the\s+)?(?:file\s+)?[`'\"]?"
    r"((?:backend|frontend|docs|skills|launch\.py|requirements\.txt|README\.md)"
    r"(?:[/\\][\w.\-][\w.\-/\\]{0,240}))\b",
    re.I,
)


@dataclass
class ToolPlan:
    web_queries: List[str] = field(default_factory=list)
    read_paths: List[str] = field(default_factory=list)
    want_processes: bool = False
    want_sysinfo: bool = False
    want_winstall: bool = False
    powershell_commands: List[str] = field(default_factory=list)


def _dedupe_preserve(seq: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for x in seq:
        k = x.strip()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def plan_tools(user_query: str) -> ToolPlan:
    q = user_query or ""
    plan = ToolPlan()

    for m in RE_TAG_WEB.finditer(q):
        inner = (m.group(1) or "").strip()
        if inner:
            plan.web_queries.append(inner[:900])

    for m in RE_TAG_FILE.finditer(q):
        inner = (m.group(1) or "").strip().strip('"').strip("'")
        if inner:
            plan.read_paths.append(inner[:900])

    if RE_TAG_SYSINFO.search(q):
        plan.want_sysinfo = True
        plan.want_processes = True
    if RE_TAG_PROCESSES.search(q):
        plan.want_processes = True

    if RE_TAG_WINSTATE.search(q):
        plan.want_winstall = True

    for m in RE_TAG_RUN.finditer(q):
        inner = (m.group(1) or "").strip()
        if inner:
            plan.powershell_commands.append(inner[:12000])

    if JAR_INJECT_WINSTATE_EACH_CHAT:
        plan.want_winstall = True

    if JAR_TOOL_HEURISTICS:
        low = q.lower()

        if not plan.web_queries:
            web_markers = (
                "search the web",
                "web search",
                "search online",
                "look up online",
                "duckduckgo",
                "google for",
                "what does the internet",
                "latest news on",
                "wikipedia search for",
            )
            if any(m in low for m in web_markers):
                plan.web_queries.append(q.strip()[:900])

        if not plan.read_paths:
            for m in RE_HEUR_FILE.finditer(q):
                plan.read_paths.append(m.group(1).strip())
            for m in RE_REPO_REL.finditer(q):
                rel = m.group(1).strip().replace("/", "\\")
                try:
                    abs_path = (REPO_ROOT / rel).resolve()
                    plan.read_paths.append(str(abs_path))
                except OSError:
                    continue
            for m in re.finditer(r"`([^`\n]{4,280})`", q):
                inner = m.group(1).strip()
                if re.match(r"^[a-zA-Z]:\\", inner) or inner.startswith(("/", ".", "~")):
                    plan.read_paths.append(inner)

        if not plan.want_processes:
            proc_markers = (
                "list processes",
                "running processes",
                "show processes",
                "task manager",
                "what's running",
                "whats running",
                "top processes",
                "cpu per process",
            )
            if any(m in low for m in proc_markers):
                plan.want_processes = True

        if not plan.want_sysinfo:
            sys_markers = (
                "system information",
                "system info",
                "full system report",
                "hardware report",
                "disk usage",
                "network interfaces",
                "memory breakdown",
                "extended diagnostics",
            )
            if any(m in low for m in sys_markers):
                plan.want_sysinfo = True
                plan.want_processes = True

    plan.web_queries = _dedupe_preserve(plan.web_queries)[:2]
    plan.read_paths = _dedupe_preserve(plan.read_paths)[:6]
    plan.powershell_commands = _dedupe_preserve(plan.powershell_commands)[:3]

    return plan


async def execute_tool_plan(plan: ToolPlan) -> Tuple[List[str], Dict[str, Any]]:
    """
    Returns (markdown blocks for LLM, metadata for SSE / logging).
    """
    blocks: List[str] = []
    meta: Dict[str, Any] = {
        "web_searched": False,
        "search_queries": [],
        "search_count": 0,
        "files_read": [],
        "processes": False,
        "sysinfo": False,
        "winstate": False,
        "shell_ran": 0,
    }

    for wq in plan.web_queries:
        if not web_search_available():
            blocks.append(
                "### Web search unavailable\n"
                "The `duckduckgo-search` package is not installed on the server.\n"
            )
            break
        try:
            result = await multi_hop_search(wq)
            cb = (result.get("context_block") or "").strip()
            if cb:
                blocks.append(cb)
            subs = result.get("sub_queries") or []
            meta["search_queries"].extend(subs)
            nres = len(result.get("results") or [])
            meta["search_count"] += nres
            meta["web_searched"] = meta["web_searched"] or nres > 0
        except Exception as e:
            logger.warning("Web search failed: %s", e)
            blocks.append(f"### Web search error\n{e}\n")

    for path in plan.read_paths:
        text = read_file_for_context(path)
        blocks.append(text)
        if "### File contents:" in text or "### Directory listing:" in text:
            meta["files_read"].append(path)

    if plan.want_winstall:
        try:
            blocks.append(get_full_windows_state())
            meta["winstate"] = True
        except Exception as e:
            logger.warning("Windows state gather failed: %s", e)
            blocks.append(f"### Machine state error\n{e}\n")

    if plan.want_sysinfo:
        try:
            blocks.append(build_extended_system_info())
            meta["sysinfo"] = True
        except Exception as e:
            blocks.append(f"### System info error\n{e}\n")

    if plan.want_processes:
        try:
            blocks.append(build_process_snapshot())
            meta["processes"] = True
        except Exception as e:
            blocks.append(f"### Process list error\n{e}\n")

    for ps_cmd in plan.powershell_commands:
        result = run_powershell(ps_cmd)
        blocks.append(format_command_result(result, label="PowerShell (JAR_RUN)"))
        meta["shell_ran"] += 1

    return blocks, meta
