# log-reader-mcp

MCP server for Claude Code — lets Claude start, monitor, and search logs from any project, even ones that don't write log files.

## Install (one-line, any machine)

```bash
git clone git@github.com:ankit-jhajhria/log-reader-mcp.git ~/.claude/mcp-servers/log-reader && bash ~/.claude/mcp-servers/log-reader/setup.sh
```

Restart Claude Code after install.

---

## How to use in a new session

### Case 1 — Project that does NOT write log files (Node, Go, Rust, plain Python, etc.)

Open Claude Code in your project folder and say:

```
run "node server.js" and capture the logs
```

or

```
run "npm start" and show me the logs
```

Claude will start the server in the background, capture all terminal output to a temp file, and immediately start showing you the logs. You never touch the terminal.

To check for errors later in the same session:

```
check the captured logs for errors
```

To stop the server:

```
stop the server
```

---

### Case 2 — Project that already writes log files (Django, etc.)

Open Claude Code and say:

```
tail logs/debug.log
```

or

```
search logs/debug.log for Traceback
```

or to watch new output as the server runs:

```
show me new lines in logs/debug.log since line 400
```

---

### Case 3 — You don't know where the logs are

```
list log files in the logs folder
```

Claude will show all `.log` files with sizes and modification times so you can pick the right one.

---

## All available tools

| Tool | What it does |
|---|---|
| `run_and_capture(command)` | Start any server command in background, capture all output to a temp file |
| `list_captured_processes()` | Show all running processes started via this MCP |
| `stop_process(pid)` | Stop a running process |
| `tail_file(path, lines=80)` | Last N lines of any log file |
| `get_new_lines(path, after_line)` | New lines since line N — use to poll a running server |
| `search_log(path, pattern)` | Regex/string search inside a log file |
| `list_log_files(directory)` | List all log files in a folder |
| `file_info(path)` | Size, modified time, line count |
