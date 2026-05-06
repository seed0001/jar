"""
Windows system snapshot via PowerShell / WMI — aligned with seed0001/claude machine.get_system_state.
On non-Windows, returns a short psutil summary instead.
"""
from __future__ import annotations

import logging
import platform
from typing import List

from app.core.local_tools import build_extended_system_info
from app.core.system_shell import run_powershell, system_shell_enabled

logger = logging.getLogger("JAR.WindowsState")


def _append(parts: List[str], title: str, stdout: str) -> None:
    s = (stdout or "").strip()
    if s:
        parts.append(f"--- {title} ---")
        parts.append(s)


def get_full_windows_state() -> str:
    """
    OS, hostname, disks, battery/power, top processes, user, cwd — same spirit as claude/machine.py.
    """
    if platform.system() != "Windows":
        try:
            return "### System state (non-Windows)\n\n" + build_extended_system_info()
        except Exception as e:
            return f"### System state unavailable\n{e}\n"

    if not system_shell_enabled():
        try:
            return (
                "### System state (psutil fallback; shell disabled)\n\n"
                + build_extended_system_info()
            )
        except Exception as e:
            return f"### System state unavailable\n{e}\n"

    parts: List[str] = []

    try:
        r = run_powershell(
            "(Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, OSArchitecture) | Format-List"
        )
        _append(parts, "Operating system", r.stdout)
        r = run_powershell("hostname")
        _append(parts, "Hostname", r.stdout)
    except Exception as e:
        parts.append(f"OS/hostname error: {e}")

    try:
        r = run_powershell(
            "Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DriveType -eq 3 } | "
            "Select-Object DeviceID, @{N='SizeGB';E={[math]::Round($_.Size/1GB,2)}}, "
            "@{N='FreeGB';E={[math]::Round($_.FreeSpace/1GB,2)}} | Format-Table -AutoSize"
        )
        _append(parts, "Disks", r.stdout)
    except Exception as e:
        parts.append(f"Disk error: {e}")

    try:
        r = run_powershell(
            "Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue | "
            "Select-Object BatteryStatus, EstimatedChargeRemaining, EstimatedRunTime | Format-List"
        )
        if r.stdout.strip():
            _append(parts, "Battery", r.stdout)
        else:
            r = run_powershell(
                "powercfg /list 2>$null; "
                "Get-WmiObject -Class Win32_PowerPlan -Namespace root\\cimv2\\power -ErrorAction SilentlyContinue | "
                "Select-Object ElementName, IsActive | Format-Table -AutoSize"
            )
            _append(parts, "Power", r.stdout)
    except Exception as e:
        parts.append(f"Power error: {e}")

    try:
        r = run_powershell(
            "Get-Process | Sort-Object CPU -Descending | Select-Object -First 60 Name, Id, CPU, WorkingSet64 | "
            "Format-Table -AutoSize"
        )
        _append(parts, "Top processes (by CPU)", r.stdout)
    except Exception as e:
        parts.append(f"Process error: {e}")

    try:
        r = run_powershell("whoami")
        _append(parts, "Current user", r.stdout)
        from pathlib import Path

        parts.append("--- Current working directory ---")
        parts.append(str(Path.cwd()))
    except Exception as e:
        parts.append(f"User/cwd error: {e}")

    body = "\n\n".join(parts) if parts else "No system state could be gathered."
    return "### Full Windows machine state\n\n" + body + "\n"
