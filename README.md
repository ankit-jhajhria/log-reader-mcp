# log-reader-mcp

Read-only MCP server for Claude Code that lets Claude tail, search, and monitor logs from any project — even projects that don't write log files.

## One-line install

```bash
git clone git@github.com:ankit-jhajhria/log-reader-mcp.git ~/.claude/mcp-servers/log-reader && bash ~/.claude/mcp-servers/log-reader/setup.sh
```

Then **restart Claude Code**. Done.

## Tools

### For projects that don't write log files

| Tool | What it does |
|---|---|
| `run_and_capture(command)` | Runs any server command in background and captures its terminal output to a file |
| `list_captured_processes()` | Shows all running processes started via `run_and_capture` |
| `stop_process(pid)` | Stops a background process |

### For projects that already write log files

| Tool | What it does |
|---|---|
| `tail_file(path, lines=80)` | Last N lines of any log file |
| `get_new_lines(path, after_line)` | Poll for new output since line N |
| `search_log(path, pattern)` | Regex/string search in a log file |
| `list_log_files(directory, pattern)` | List all log files in a folder with sizes |
| `file_info(path)` | Size, modified time, line count |

## Usage

### Project with no log files (Node, Go, Rust, etc.)

Tell Claude:
> *"run node server.js and capture the logs"*

Claude will call `run_and_capture("node server.js")`, get back the auto-created log file path, and can tail it immediately.

### Project that already writes logs (Django, etc.)

Tell Claude:
> *"tail logs/debug.log"*
> *"search logs/debug.log for Traceback"*
> *"what's new in run.log since line 400"*

Works with any project — no per-project setup needed.
