#!/usr/bin/env python3
"""
J.A.R. / JARVIS — Python launcher

Starts the FastAPI backend (Uvicorn), the Vite frontend dev server, optionally
opens the UI in a browser app window (Edge/Chrome on Windows), then waits until
Ctrl+C and terminates child processes.

Usage:
  python launch.py
  python launch.py --no-browser
  python launch.py --no-install
  python launch.py --backend-port 8765 --wait 8
  python launch.py --force   # if port 8765 is busy, try to stop the listener (Windows/macOS/Linux)
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parent


def _log_line(path: Path, message: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {message}\n")


def _popen_kwargs() -> dict:
    """Hide console windows for children on Windows when supported."""
    if sys.platform != "win32":
        return {}
    # subprocess.CREATE_NO_WINDOW == 0x08000000 (Python 3.7+)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if flags:
        return {"creationflags": flags}
    return {}


def _tcp_port_in_use(host: str, port: int) -> bool:
    """True if something accepts TCP connections on host:port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(0.35)
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


def _try_kill_listeners_windows(port: int) -> None:
    """Kill PIDs in LISTENING state for this TCP port (best-effort)."""
    try:
        r = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            timeout=25,
        )
    except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
        return
    text = r.stdout or ""
    pids: set[int] = set()
    port_s = str(port)
    for line in text.splitlines():
        line = line.strip()
        if not line.upper().startswith("TCP"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        if parts[3].upper() != "LISTENING":
            continue
        local = parts[1]
        _host, _, port_part = local.rpartition(":")
        if port_part != port_s:
            continue
        tail = parts[-1]
        if tail.isdigit():
            pids.add(int(tail))
    me = os.getpid()
    for pid in pids:
        if pid == me:
            continue
        try:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


def _try_kill_listeners_posix(port: int) -> None:
    """Unix: use lsof -ti if available."""
    lsof = shutil.which("lsof")
    if not lsof:
        return
    try:
        r = subprocess.run(
            [lsof, f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return
    me = os.getpid()
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line.isdigit():
            continue
        pid = int(line)
        if pid == me:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass


def _try_free_tcp_port(host: str, port: int) -> bool:
    """Try to terminate listeners on port; return True if port appears free after a short wait."""
    if sys.platform == "win32":
        _try_kill_listeners_windows(port)
    else:
        _try_kill_listeners_posix(port)
    for _ in range(12):
        time.sleep(0.25)
        if not _tcp_port_in_use(host, port):
            return True
    return not _tcp_port_in_use(host, port)


def _which_or_die(name: str, hint: str) -> str:
    path = shutil.which(name)
    if not path:
        print(f"[ERROR] '{name}' not found in PATH. {hint}", file=sys.stderr)
        sys.exit(1)
    return path


def _pip_install_requirements(root: Path, python_exe: str) -> None:
    req = root / "requirements.txt"
    if not req.is_file():
        print("[WARN] requirements.txt missing — skipping pip install.")
        return
    print("[1/3] Installing / updating Python dependencies (quiet)…")
    r = subprocess.run(
        [python_exe, "-m", "pip", "install", "-q", "-r", str(req)],
        cwd=str(root),
    )
    if r.returncode != 0:
        print("[ERROR] pip install failed.", file=sys.stderr)
        sys.exit(r.returncode)


def _npm_install_if_needed(frontend: Path, npm_exe: str) -> None:
    nm = frontend / "node_modules"
    if nm.is_dir():
        return
    print("[1/3] Installing frontend packages (may take a minute)…")
    r = subprocess.run([npm_exe, "install"], cwd=str(frontend), shell=sys.platform == "win32")
    if r.returncode != 0:
        print("[ERROR] npm install failed.", file=sys.stderr)
        sys.exit(r.returncode)


def _open_app_window(url: str) -> None:
    """Prefer Edge/Chrome --app= on Windows; fall back to default browser."""
    if sys.platform == "win32":
        for browser in ("msedge", "chrome"):
            exe = shutil.which(browser)
            if exe:
                try:
                    subprocess.Popen(
                        [exe, f"--app={url}"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        **_popen_kwargs(),
                    )
                    print(f"Opened app window via {browser}.")
                    return
                except OSError as e:
                    print(f"[WARN] Could not start {browser}: {e}")
        webbrowser.open(url)
        print("Opened URL in default browser.")
        return

    if sys.platform == "linux":
        for name in ("google-chrome", "chrome", "chromium", "chromium-browser", "brave-browser"):
            exe = shutil.which(name)
            if exe:
                try:
                    subprocess.Popen(
                        [exe, f"--app={url}"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    print(f"Opened app window via {name}.")
                    return
                except OSError:
                    continue

    if sys.platform == "darwin":
        exe = shutil.which("google-chrome") or shutil.which("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if exe:
            try:
                subprocess.Popen([exe, f"--app={url}"])
                print("Opened app window via Chrome.")
                return
            except OSError:
                pass

    webbrowser.open(url)
    print("Opened URL in default browser.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch J.A.R. backend + Vite frontend.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window.")
    parser.add_argument("--no-install", action="store_true", help="Skip pip install and npm install.")
    parser.add_argument("--backend-host", default="127.0.0.1", help="Uvicorn bind host (default 127.0.0.1).")
    parser.add_argument("--backend-port", type=int, default=8765, help="Uvicorn port (default 8765).")
    parser.add_argument(
        "--frontend-url",
        default="http://localhost:5173",
        help="URL to open after startup (default http://localhost:5173).",
    )
    parser.add_argument("--wait", type=float, default=6.0, help="Seconds to wait before opening browser (default 6).")
    parser.add_argument(
        "--force",
        action="store_true",
        help="If the backend port is busy, try to stop the process listening on it, then start.",
    )
    args = parser.parse_args()

    root = _root()
    backend = root / "backend"
    frontend = root / "frontend"
    launcher_log = root / "jarvis_launcher.log"
    backend_log = root / "backend.log"
    frontend_log = root / "frontend.log"

    if not (backend / "app" / "main.py").is_file():
        print(f"[ERROR] Backend not found at {backend}", file=sys.stderr)
        sys.exit(1)
    if not (frontend / "package.json").is_file():
        print(f"[ERROR] Frontend not found at {frontend}", file=sys.stderr)
        sys.exit(1)

    _which_or_die("npm", "Install Node.js from https://nodejs.org/")

    python_exe = sys.executable
    npm_exe = _which_or_die("npm", "Install Node.js from https://nodejs.org/")

    if not args.no_install:
        _pip_install_requirements(root, python_exe)
        _npm_install_if_needed(frontend, npm_exe)

    popen_kw = _popen_kwargs()
    procs: list[subprocess.Popen] = []

    def cleanup() -> None:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=3)

    def _on_signal(signum: int, frame) -> None:  # noqa: ARG001
        print("\nStopping services…")
        cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, _on_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda s, f: _on_signal(s, f))

    _log_line(launcher_log, "Python launcher starting services…")

    print("[2/3] Launching backend & frontend (logs: backend.log, frontend.log)…")
    try:
        blog = backend_log.open("a", encoding="utf-8")
        flog = frontend_log.open("a", encoding="utf-8")
    except OSError as e:
        print(f"[ERROR] Cannot open log files: {e}", file=sys.stderr)
        sys.exit(1)

    if _tcp_port_in_use(args.backend_host, args.backend_port):
        if args.force:
            print(
                f"[INFO] Port {args.backend_port} is in use — trying to free it (--force)…",
                file=sys.stderr,
            )
            if _try_free_tcp_port(args.backend_host, args.backend_port):
                print(f"[INFO] Port {args.backend_port} is free now.", file=sys.stderr)
            else:
                print(
                    f"[ERROR] Could not free port {args.backend_port}. "
                    "Close the app using it manually, or run Task Manager and end the Python/uvicorn process.",
                    file=sys.stderr,
                )
                sys.exit(1)
        else:
            print(
                f"[ERROR] Port {args.backend_port} is already in use on {args.backend_host}.\n"
                f"       Stop the other backend (old terminal / uvicorn), or run:\n"
                f"         python launch.py --force",
                file=sys.stderr,
            )
            sys.exit(1)

    be = subprocess.Popen(
        [
            python_exe,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            args.backend_host,
            "--port",
            str(args.backend_port),
        ],
        cwd=str(backend),
        stdout=blog,
        stderr=subprocess.STDOUT,
        **popen_kw,
    )
    procs.append(be)

    # npm on Windows is often a .cmd; shell=True avoids spawn issues
    fe_shell = sys.platform == "win32"
    fe_cmd = "npm run dev" if fe_shell else [npm_exe, "run", "dev"]
    fe = subprocess.Popen(
        fe_cmd,
        cwd=str(frontend),
        stdout=flog,
        stderr=subprocess.STDOUT,
        shell=fe_shell,
        **popen_kw,
    )
    procs.append(fe)
    proc_labels = ["backend (uvicorn)", "frontend (vite)"]

    if not args.no_browser:
        print(f"[3/3] Waiting {args.wait}s for servers, then opening UI…")
        time.sleep(args.wait)
        _open_app_window(args.frontend_url)
        _log_line(launcher_log, "Browser launched.")
    else:
        print("[3/3] Skipping browser (--no-browser).")

    print()
    print("=" * 60)
    print("  J.A.R. is running.")
    print(f"  Frontend: {args.frontend_url}")
    print(f"  Backend:  http://{args.backend_host}:{args.backend_port}")
    print("  Press Ctrl+C to stop backend and frontend.")
    print("=" * 60)

    try:
        while True:
            time.sleep(2)
            dead = [(i, p) for i, p in enumerate(procs) if p.poll() is not None]
            if dead:
                parts = [f"{proc_labels[i]} → exit {p.poll()}" for i, p in dead]
                print(f"[WARN] A service exited: {'; '.join(parts)}")
                print(f"       Logs: {backend_log.name} and {frontend_log.name} in {root}")
                cleanup()
                sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopping services…")
        cleanup()
        sys.exit(0)


if __name__ == "__main__":
    main()
