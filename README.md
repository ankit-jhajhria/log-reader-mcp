# log-reader-mcp

MCP server for Claude Code — lets Claude start, monitor, search, and detect errors in logs from any project, even ones that don't write log files.

**Requirements:** Python 3.8+, Claude Code

---

## Install (one-line, any machine)

**SSH** (if you have GitHub SSH keys set up):
```bash
git clone git@github.com:ankit-jhajhria/log-reader-mcp.git ~/.claude/mcp-servers/log-reader && bash ~/.claude/mcp-servers/log-reader/setup.sh
```

**HTTPS** (works without SSH keys):
```bash
git clone https://github.com/ankit-jhajhria/log-reader-mcp.git ~/.claude/mcp-servers/log-reader && bash ~/.claude/mcp-servers/log-reader/setup.sh
```

Restart Claude Code after install.

> **Ubuntu/Debian users:** If setup fails with a `venv` error, run `sudo apt install python3-venv` first — the script will tell you this too.

---

## How to use in a new session

### Project with no log files (Node, Go, Rust, plain Python, etc.)

Open Claude Code in your project and say:

```
run "node server.js" and capture the logs
```

Claude starts the server in the background, captures all terminal output, and tails the log immediately. Always set the working directory so the command runs from the right folder:

```
run "npm start" in /home/user/my-node-project and capture the logs
```

To check for problems:
```
detect errors in the captured log
```

To restart after a code change:
```
restart the server
```

To stop it:
```
stop the server
```

---

### Project that already writes log files (Django, Rails, etc.)

```
tail logs/debug.log
```

```
detect errors in logs/debug.log
```

```
search logs/debug.log for "Traceback" with 3 lines of context
```

```
show me new lines in logs/debug.log since line 400
```

---

### Don't know where the logs are

```
list log files in the logs folder
```

Files modified in the last 60 seconds are marked `[active]` so you can spot the right one instantly.

---

## All tools

### Process management
| Tool | What it does |
|---|---|
| `run_and_capture(command, cwd, log_file)` | Start any server in background, capture all output to a file |
| `list_captured_processes()` | Show all running/stopped captured processes |
| `stop_process(pid)` | Stop a process |
| `restart_process(pid)` | Stop and restart with the same command and working directory |

### Log reading
| Tool | What it does |
|---|---|
| `detect_errors(path, last_lines)` | Auto-scan for ERROR, Exception, Traceback, WARNING, CRITICAL, fatal |
| `tail_file(path, lines=80)` | Last N lines of any log file |
| `get_new_lines(path, after_line)` | New lines since line N — use to poll a running server |
| `search_log(path, pattern, context_lines)` | Regex/string search with optional surrounding context lines |
| `list_log_files(directory, pattern)` | List log files with sizes and active status |
| `file_info(path)` | Size, modified time, line count |

---

## Troubleshooting

**`python3-venv` error on Ubuntu/Debian:**
```bash
sudo apt install python3-venv
```

**Permission denied reading a log file:**
Some system logs (e.g. `/var/log/syslog`) require elevated permissions. Run Claude Code with `sudo` or copy the log to a readable location.

**Process exits immediately after `run_and_capture`:**
The tool detects this and shows you the output. Common causes: wrong command, port already in use, missing dependencies. Fix the command and try again.
