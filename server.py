#!/usr/bin/env python3
"""Read-only MCP server for monitoring terminal/application logs across any project."""

import json
import os
import re
import signal
import subprocess
import time
import datetime
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("log-reader")

# Tracks background processes started via run_and_capture
_PROCS_FILE = "/tmp/mcp-log-reader-procs.json"


def _load_procs() -> dict:
    try:
        with open(_PROCS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_procs(procs: dict) -> None:
    with open(_PROCS_FILE, "w") as f:
        json.dump(procs, f, indent=2)


def _tail_lines(path: str, n: int) -> list[str]:
    """Efficiently read last N lines without loading the whole file into memory."""
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        if size == 0:
            return []
        buf = b""
        pos = size
        while pos > 0 and buf.count(b"\n") < n + 1:
            step = min(8192, pos)
            pos -= step
            f.seek(pos)
            buf = f.read(step) + buf
        lines = buf.decode("utf-8", errors="replace").splitlines()
        return lines[-n:]


# ── Process capture tools ────────────────────────────────────────────────────

@mcp.tool()
def run_and_capture(command: str, log_file: str = "") -> str:
    """
    Run any shell command in the background and capture its stdout+stderr to a log file.
    Use this for projects that don't write log files — just run their server through this.

    Args:
        command:  Shell command to run (e.g. "python manage.py runserver", "node server.js", "npm start", "./mybinary")
        log_file: Where to write output. If empty, auto-creates a file in /tmp based on command name.
    """
    if not log_file:
        cmd_name = command.split()[0].replace("/", "_").replace(".", "_")
        ts = int(time.time())
        log_file = f"/tmp/mcp-{cmd_name}-{ts}.log"

    log_path = Path(log_file).expanduser().resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with open(str(log_path), "w") as f:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=f,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # detach so it survives MCP restarts
        )

    procs = _load_procs()
    procs[str(proc.pid)] = {
        "command": command,
        "log_file": str(log_path),
        "started": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_procs(procs)

    return (
        f"Started:  {command}\n"
        f"PID:      {proc.pid}\n"
        f"Log file: {log_path}\n\n"
        f"Read output:  tail_file('{log_path}')\n"
        f"Stop server:  stop_process({proc.pid})"
    )


@mcp.tool()
def list_captured_processes() -> str:
    """List all background processes started via run_and_capture, with their status and log file path."""
    procs = _load_procs()
    if not procs:
        return "No captured processes recorded."

    lines = []
    dead = []
    for pid_str, info in procs.items():
        pid = int(pid_str)
        try:
            os.kill(pid, 0)
            status = "RUNNING"
        except ProcessLookupError:
            status = "stopped"
            dead.append(pid_str)
        lines.append(
            f"PID {pid:>6}  [{status}]\n"
            f"  command: {info['command']}\n"
            f"  started: {info['started']}\n"
            f"  log:     {info['log_file']}"
        )

    for pid_str in dead:
        del procs[pid_str]
    if dead:
        _save_procs(procs)

    return "\n\n".join(lines)


@mcp.tool()
def stop_process(pid: int) -> str:
    """
    Stop a background process started via run_and_capture.

    Args:
        pid: Process ID shown by run_and_capture or list_captured_processes
    """
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
        try:
            os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)
            result = f"PID {pid} force-killed (SIGKILL)"
        except ProcessLookupError:
            result = f"PID {pid} stopped cleanly (SIGTERM)"
    except ProcessLookupError:
        result = f"PID {pid} was not running"

    procs = _load_procs()
    procs.pop(str(pid), None)
    _save_procs(procs)
    return result


# ── File reading tools ───────────────────────────────────────────────────────

@mcp.tool()
def tail_file(path: str, lines: int = 80) -> str:
    """
    Get the last N lines of any log or text file.

    Args:
        path:  Absolute or relative path to the file
        lines: Number of lines to return (default 80)
    """
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"ERROR: file not found: {p}"
    if not p.is_file():
        return f"ERROR: not a file: {p}"
    result = _tail_lines(str(p), lines)
    header = f"=== {p} — last {len(result)} lines ===\n"
    numbered = "\n".join(f"{i + 1:>6}: {ln}" for i, ln in enumerate(result))
    return header + numbered


@mcp.tool()
def get_new_lines(path: str, after_line: int = 0) -> str:
    """
    Poll a log file for new output since a given line number.
    Use this to monitor a running server without re-reading the whole file.

    Workflow:
      1. Call with after_line=0 — note the total line count returned.
      2. Call again with after_line=<that count> to get only new lines since then.

    Args:
        path:       Path to the log file
        after_line: Return only lines after this line number (0 = return all)
    """
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"ERROR: file not found: {p}"
    new_lines = []
    with open(str(p), "r", errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            if lineno > after_line:
                new_lines.append(f"{lineno:>6}: {line.rstrip()}")
    total = after_line + len(new_lines)
    header = f"=== {p} — lines {after_line + 1}–{total} (total so far: {total}) ===\n"
    if not new_lines:
        return header + "(no new lines)"
    return header + "\n".join(new_lines)


@mcp.tool()
def search_log(path: str, pattern: str, max_matches: int = 50, case_sensitive: bool = False) -> str:
    """
    Search a log file for lines matching a regex or plain string.

    Args:
        path:          File to search
        pattern:       Regex or plain string (e.g. "ERROR", "500", "Traceback")
        max_matches:   Cap on results (default 50)
        case_sensitive: Default False
    """
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"ERROR: file not found: {p}"
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return f"ERROR: invalid regex '{pattern}': {e}"
    matches = []
    with open(str(p), "r", errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            if regex.search(line):
                matches.append(f"{lineno:>6}: {line.rstrip()}")
                if len(matches) >= max_matches:
                    matches.append(f"... capped at {max_matches} matches, refine your pattern to see more")
                    break
    if not matches:
        return f"No matches for '{pattern}' in {p}"
    return f"=== {len(matches)} matches for '{pattern}' in {p} ===\n" + "\n".join(matches)


@mcp.tool()
def list_log_files(directory: str, pattern: str = "*.log") -> str:
    """
    List log files in a directory. Works with any project's log folder.

    Args:
        directory: Directory to scan
        pattern:   Glob pattern (default *.log). Use ** for recursive, e.g. "**/*.log"
    """
    d = Path(directory).expanduser().resolve()
    if not d.exists():
        return f"ERROR: directory not found: {d}"
    if not d.is_dir():
        return f"ERROR: not a directory: {d}"
    matches = sorted(d.glob(pattern))
    if not matches:
        return f"No files matching '{pattern}' in {d}"
    rows = []
    for m in matches:
        try:
            stat = m.stat()
            mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            rows.append(f"{stat.st_size / 1024:>10.1f} KB  {mtime}  {m}")
        except OSError:
            rows.append(f"{'?':>13}  {'?':>16}  {m}")
    return f"=== {len(matches)} file(s) in {d} ===\n" + "\n".join(rows)


@mcp.tool()
def file_info(path: str) -> str:
    """
    Get size, modification time, and line count for a log file.
    Quick way to check if a file has grown since your last look.

    Args:
        path: Path to the file
    """
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"ERROR: not found: {p}"
    stat = p.stat()
    mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    with open(str(p), "rb") as f:
        line_count = sum(1 for _ in f)
    return (
        f"path:     {p}\n"
        f"size:     {stat.st_size:,} bytes ({stat.st_size / 1024:.1f} KB)\n"
        f"modified: {mtime}\n"
        f"lines:    {line_count:,}"
    )


if __name__ == "__main__":
    mcp.run()
