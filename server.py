#!/usr/bin/env python3
"""MCP server for monitoring terminal/application logs across any project."""

import json
import os
import re
import signal
import subprocess
import tempfile
import time
import datetime
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("log-reader")

_TMP = tempfile.gettempdir()
_PROCS_FILE = os.path.join(_TMP, "mcp-log-reader-procs.json")

ERROR_PATTERNS = re.compile(
    r"error|exception|traceback|critical|fatal|fail|panic|segfault|killed|oom",
    re.IGNORECASE,
)
WARNING_PATTERNS = re.compile(r"warning|warn|deprecated", re.IGNORECASE)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_procs() -> dict:
    try:
        with open(_PROCS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_procs(procs: dict) -> None:
    with open(_PROCS_FILE, "w") as f:
        json.dump(procs, f, indent=2)


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _tail_lines(path: str, n: int) -> list[str]:
    """Efficiently read last N lines without loading the whole file."""
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
        return buf.decode("utf-8", errors="replace").splitlines()[-n:]


def _safe_open(path: Path, mode: str = "r"):
    """Open a file with a clean error for permission issues."""
    try:
        return open(str(path), mode, errors="replace")
    except PermissionError:
        raise PermissionError(f"Permission denied reading {path}. Try running Claude Code with elevated permissions.")


# ── Process capture tools ────────────────────────────────────────────────────

@mcp.tool()
def run_and_capture(command: str, cwd: str = "", log_file: str = "") -> str:
    """
    Run any shell command in the background and capture its stdout+stderr to a log file.
    Use for projects that don't write log files — just run their server through this.

    Args:
        command:  Shell command (e.g. "python manage.py runserver", "node server.js", "npm start")
        cwd:      Working directory to run the command from. Defaults to the current directory.
                  Always set this when the project is in a specific folder.
        log_file: Where to write output. Auto-generated in temp dir if not specified.
    """
    work_dir = Path(cwd).expanduser().resolve() if cwd else Path.cwd()
    if not work_dir.exists():
        return f"ERROR: working directory not found: {work_dir}"

    if not log_file:
        cmd_name = re.sub(r"[^\w]", "_", command.split()[0])[:20]
        ts = int(time.time())
        log_file = os.path.join(_TMP, f"mcp-{cmd_name}-{ts}.log")

    log_path = Path(log_file).expanduser().resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(str(log_path), "w") as f:
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=f,
                stderr=subprocess.STDOUT,
                cwd=str(work_dir),
                start_new_session=True,
            )
    except Exception as e:
        return f"ERROR: failed to start process: {e}"

    # Health check — wait briefly to catch instant failures (wrong command, port conflict, etc.)
    time.sleep(1.5)
    if not _is_alive(proc.pid):
        try:
            output = log_path.read_text(errors="replace").strip()
        except OSError:
            output = "(no output captured)"
        return (
            f"FAILED: process exited immediately.\n"
            f"Command: {command}\n"
            f"Working dir: {work_dir}\n\n"
            f"Output:\n{output or '(empty)'}"
        )

    procs = _load_procs()
    procs[str(proc.pid)] = {
        "command": command,
        "cwd": str(work_dir),
        "log_file": str(log_path),
        "started": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_procs(procs)

    return (
        f"Started:     {command}\n"
        f"Working dir: {work_dir}\n"
        f"PID:         {proc.pid}\n"
        f"Log file:    {log_path}\n\n"
        f"Read output: tail_file('{log_path}')\n"
        f"Stop server: stop_process({proc.pid})"
    )


@mcp.tool()
def list_captured_processes() -> str:
    """List all background processes started via run_and_capture, with status and log paths."""
    procs = _load_procs()
    if not procs:
        return "No captured processes recorded."

    lines = []
    dead = []
    for pid_str, info in procs.items():
        pid = int(pid_str)
        alive = _is_alive(pid)
        status = "RUNNING" if alive else "stopped"
        if not alive:
            dead.append(pid_str)
        lines.append(
            f"PID {pid:>6}  [{status}]\n"
            f"  command: {info['command']}\n"
            f"  cwd:     {info.get('cwd', '?')}\n"
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
        pid: Process ID from run_and_capture or list_captured_processes
    """
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
        if _is_alive(pid):
            os.kill(pid, signal.SIGKILL)
            result = f"PID {pid} force-killed (SIGKILL)"
        else:
            result = f"PID {pid} stopped cleanly (SIGTERM)"
    except ProcessLookupError:
        result = f"PID {pid} was not running"

    procs = _load_procs()
    procs.pop(str(pid), None)
    _save_procs(procs)
    return result


@mcp.tool()
def restart_process(pid: int) -> str:
    """
    Stop a running process and restart it with the same command and working directory.
    Useful after a code change.

    Args:
        pid: Process ID from list_captured_processes
    """
    procs = _load_procs()
    info = procs.get(str(pid))
    if not info:
        return f"ERROR: PID {pid} not found in captured processes. Use list_captured_processes() to check."

    command = info["command"]
    cwd = info.get("cwd", "")
    log_file = info["log_file"]

    # Stop old process
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
        if _is_alive(pid):
            os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

    procs.pop(str(pid), None)
    _save_procs(procs)

    # Small gap so ports are released
    time.sleep(1)

    return run_and_capture(command=command, cwd=cwd, log_file=log_file)


# ── tmux tools ──────────────────────────────────────────────────────────────

def _tmux_check() -> str | None:
    """Return error string if tmux is not available, else None."""
    if subprocess.run(["which", "tmux"], capture_output=True).returncode != 0:
        return "ERROR: tmux is not installed. Run: sudo apt install tmux (Ubuntu) or brew install tmux (macOS)"
    return None


def _tmux_target(session: str, pane: int) -> str:
    return f"{session}:{pane}"


@mcp.tool()
def tmux_sessions() -> str:
    """
    List all running tmux sessions and their panes.
    Run this first to find the session name to use in other tmux tools.
    """
    err = _tmux_check()
    if err:
        return err
    result = subprocess.run(
        ["tmux", "list-panes", "-a", "-F",
         "#{session_name}:#{window_index}.#{pane_index}  [#{pane_width}x#{pane_height}]  cmd=#{pane_current_command}  path=#{pane_current_path}"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return "No tmux sessions running. Start one with: tmux new -s mysession"
    return "=== Running tmux panes ===\n" + result.stdout.strip()


@mcp.tool()
def tmux_read(session: str, pane: int = 0, lines: int = 80) -> str:
    """
    Read output directly from a tmux pane — no log file needed.
    This sees exactly what is printed in your terminal.

    Args:
        session: tmux session name (get it from tmux_sessions())
        pane:    pane index (default 0 — the first/only pane)
        lines:   how many lines of scrollback to capture (default 80)
    """
    err = _tmux_check()
    if err:
        return err
    target = _tmux_target(session, pane)
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", target, "-p", "-S", f"-{lines}"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return f"ERROR: pane '{target}' not found. Use tmux_sessions() to list available panes."
    output = result.stdout.rstrip()
    if not output:
        return f"Pane '{target}' is empty or has no output yet."
    return f"=== tmux {target} — last {lines} lines ===\n{output}"


@mcp.tool()
def tmux_run(session: str, command: str, pane: int = 0, wait: float = 1.5) -> str:
    """
    Send a command to a tmux pane and read back the output.
    The command runs visibly in your terminal — you can watch it execute.

    Args:
        session: tmux session name
        command: shell command to run (e.g. "docker compose up --build", "git status")
        pane:    pane index (default 0)
        wait:    seconds to wait before reading output (default 1.5 — increase for slow commands)
    """
    err = _tmux_check()
    if err:
        return err
    target = _tmux_target(session, pane)
    send = subprocess.run(
        ["tmux", "send-keys", "-t", target, command, "Enter"],
        capture_output=True, text=True
    )
    if send.returncode != 0:
        return f"ERROR: could not send to pane '{target}'. Use tmux_sessions() to check available panes."
    if wait > 0:
        time.sleep(wait)
    return tmux_read(session=session, pane=pane, lines=80)


@mcp.tool()
def tmux_send_keys(session: str, keys: str, pane: int = 0) -> str:
    """
    Send raw keys to a tmux pane. Use this for special keys like Ctrl+C, Ctrl+D, Enter, arrow keys.

    Common values:
      "C-c"     → Ctrl+C  (stop a running process)
      "C-d"     → Ctrl+D  (exit a shell/REPL)
      "q"       → quit (e.g. for less/vim)
      "Enter"   → press Enter
      "Up"      → arrow up (previous command)

    Args:
        session: tmux session name
        keys:    key sequence to send
        pane:    pane index (default 0)
    """
    err = _tmux_check()
    if err:
        return err
    target = _tmux_target(session, pane)
    result = subprocess.run(
        ["tmux", "send-keys", "-t", target, keys, ""],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return f"ERROR: could not send keys to '{target}'. Use tmux_sessions() to check available panes."
    time.sleep(0.3)
    return tmux_read(session=session, pane=pane, lines=30)


@mcp.tool()
def tmux_new_session(session: str, command: str = "", cwd: str = "") -> str:
    """
    Create a new tmux session (optionally run a command in it immediately).
    After this you can watch the terminal and Claude can read it via tmux_read.

    Args:
        session: name for the new session (e.g. "myserver", "docker")
        command: command to run immediately inside the session (optional)
        cwd:     working directory for the session (optional)
    """
    err = _tmux_check()
    if err:
        return err

    cmd = ["tmux", "new-session", "-d", "-s", session]
    if cwd:
        work_dir = str(Path(cwd).expanduser().resolve())
        cmd += ["-c", work_dir]
    if command:
        cmd += [command]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "duplicate session" in stderr:
            return f"ERROR: session '{session}' already exists. Use tmux_sessions() to see running sessions."
        return f"ERROR: {stderr}"

    msg = f"Session '{session}' created."
    if command:
        time.sleep(1.5)
        output = tmux_read(session=session, pane=0, lines=50)
        return f"{msg}\n\n{output}"
    return f"{msg}\nAttach to see it: tmux attach -t {session}\nOr use tmux_run('{session}', 'your command') to run commands in it."


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
    try:
        result = _tail_lines(str(p), lines)
    except PermissionError:
        return f"ERROR: permission denied reading {p}"
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
        after_line: Return only lines after this number (0 = return all)
    """
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"ERROR: file not found: {p}"
    try:
        new_lines = []
        with _safe_open(p) as f:
            for lineno, line in enumerate(f, 1):
                if lineno > after_line:
                    new_lines.append(f"{lineno:>6}: {line.rstrip()}")
    except PermissionError as e:
        return f"ERROR: {e}"
    total = after_line + len(new_lines)
    header = f"=== {p} — lines {after_line + 1}–{total} (total so far: {total}) ===\n"
    return header + ("\n".join(new_lines) if new_lines else "(no new lines)")


@mcp.tool()
def search_log(path: str, pattern: str, context_lines: int = 0, max_matches: int = 50, case_sensitive: bool = False) -> str:
    """
    Search a log file for lines matching a regex or plain string.

    Args:
        path:          File to search
        pattern:       Regex or plain string (e.g. "ERROR", "500", "Traceback")
        context_lines: Lines to show before and after each match, like grep -C (default 0)
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

    try:
        with _safe_open(p) as f:
            all_lines = f.readlines()
    except PermissionError as e:
        return f"ERROR: {e}"

    match_indices = [i for i, ln in enumerate(all_lines) if regex.search(ln)]
    if not match_indices:
        return f"No matches for '{pattern}' in {p}"

    capped = len(match_indices) > max_matches
    match_indices = match_indices[:max_matches]

    # Collect line ranges to display (with context), merging overlapping windows
    ranges = []
    for i in match_indices:
        start = max(0, i - context_lines)
        end = min(len(all_lines) - 1, i + context_lines)
        if ranges and start <= ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], end)
        else:
            ranges.append((start, end))

    blocks = []
    for start, end in ranges:
        block = []
        for i in range(start, end + 1):
            lineno = i + 1
            marker = ">>>" if regex.search(all_lines[i]) else "   "
            block.append(f"{marker} {lineno:>6}: {all_lines[i].rstrip()}")
        blocks.append("\n".join(block))

    header = f"=== {len(match_indices)} match(es) for '{pattern}' in {p}"
    if capped:
        header += f" (capped at {max_matches})"
    header += " ===\n"
    return header + "\n\n".join(blocks)


@mcp.tool()
def detect_errors(path: str, last_lines: int = 0) -> str:
    """
    Scan a log file for errors, exceptions, warnings, and crashes.
    The fastest way to check if something went wrong.

    Args:
        path:       File to scan
        last_lines: Only scan the last N lines (0 = scan entire file)
    """
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"ERROR: file not found: {p}"
    try:
        if last_lines:
            lines = _tail_lines(str(p), last_lines)
            offset = 0
        else:
            with _safe_open(p) as f:
                lines = [ln.rstrip() for ln in f]
            offset = 0
    except PermissionError as e:
        return f"ERROR: {e}"

    errors = []
    warnings = []
    for i, line in enumerate(lines):
        lineno = i + 1 + offset
        if ERROR_PATTERNS.search(line):
            errors.append(f"  {lineno:>6}: {line}")
        elif WARNING_PATTERNS.search(line):
            warnings.append(f"  {lineno:>6}: {line}")

    if not errors and not warnings:
        scope = f"last {last_lines} lines of " if last_lines else ""
        return f"No errors or warnings found in {scope}{p}"

    parts = []
    if errors:
        parts.append(f"ERRORS / EXCEPTIONS ({len(errors)} found):\n" + "\n".join(errors[:30]))
        if len(errors) > 30:
            parts[0] += f"\n  ... and {len(errors) - 30} more"
    if warnings:
        parts.append(f"WARNINGS ({len(warnings)} found):\n" + "\n".join(warnings[:20]))
        if len(warnings) > 20:
            parts[-1] += f"\n  ... and {len(warnings) - 20} more"

    return f"=== {p} ===\n\n" + "\n\n".join(parts)


@mcp.tool()
def list_log_files(directory: str, pattern: str = "*.log") -> str:
    """
    List log files in a directory.

    Args:
        directory: Directory to scan
        pattern:   Glob pattern (default *.log). Use ** for recursive, e.g. "**/*.log"
    """
    d = Path(directory).expanduser().resolve()
    if not d.exists():
        return f"ERROR: directory not found: {d}"
    if not d.is_dir():
        return f"ERROR: not a directory: {d}"
    try:
        matches = sorted(d.glob(pattern))
    except PermissionError:
        return f"ERROR: permission denied listing {d}"
    if not matches:
        return f"No files matching '{pattern}' in {d}"
    now = time.time()
    rows = []
    for m in matches:
        try:
            stat = m.stat()
            mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            age_s = now - stat.st_mtime
            active = " [active]" if age_s < 60 else ""
            rows.append(f"{stat.st_size / 1024:>10.1f} KB  {mtime}{active}  {m}")
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
    try:
        stat = p.stat()
    except PermissionError:
        return f"ERROR: permission denied: {p}"
    mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(str(p), "rb") as f:
            line_count = sum(1 for _ in f)
    except PermissionError:
        line_count = "?"
    return (
        f"path:     {p}\n"
        f"size:     {stat.st_size:,} bytes ({stat.st_size / 1024:.1f} KB)\n"
        f"modified: {mtime}\n"
        f"lines:    {line_count:,}" if isinstance(line_count, int) else
        f"path:     {p}\n"
        f"size:     {stat.st_size:,} bytes ({stat.st_size / 1024:.1f} KB)\n"
        f"modified: {mtime}\n"
        f"lines:    {line_count}"
    )


if __name__ == "__main__":
    mcp.run()
