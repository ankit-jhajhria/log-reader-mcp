# log-reader-mcp

Read-only MCP server for Claude Code that lets Claude tail, search, and monitor log files from any project.

## One-line install

```bash
git clone git@github.com:ankit-jhajhria/log-reader-mcp.git ~/.claude/mcp-servers/log-reader && bash ~/.claude/mcp-servers/log-reader/setup.sh
```

Then **restart Claude Code**. Done.

## Tools

| Tool | What it does |
|---|---|
| `tail_file(path, lines=80)` | Last N lines of any log file |
| `get_new_lines(path, after_line)` | Poll for new output since line N — use while server is running |
| `search_log(path, pattern)` | Regex/string search in a log file |
| `list_log_files(directory, pattern)` | List all log files in a folder with sizes |
| `file_info(path)` | Size, modified time, line count |

## Usage in Claude Code

Just tell Claude naturally:

- *"tail logs/debug.log"*
- *"search logs/debug.log for Traceback"*
- *"what's new in run.log since line 400"*
- *"list log files in /home/user/myproject/logs"*

Works with any project — no per-project setup needed.
