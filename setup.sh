#!/bin/bash
# Sets up the log-reader MCP server and registers it globally in Claude Code.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Creating virtualenv..."
python3 -m venv "$SCRIPT_DIR/venv"

echo "Installing dependencies..."
"$SCRIPT_DIR/venv/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"

PYTHON="$SCRIPT_DIR/venv/bin/python"
SERVER="$SCRIPT_DIR/server.py"
SETTINGS="$HOME/.claude/settings.json"

echo "Registering MCP server in $SETTINGS ..."

# Use Python to safely merge the mcpServers entry into existing settings.json
python3 - <<EOF
import json, os

path = "$SETTINGS"
os.makedirs(os.path.dirname(path), exist_ok=True)

try:
    with open(path) as f:
        cfg = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    cfg = {}

cfg.setdefault("mcpServers", {})["log-reader"] = {
    "command": "$PYTHON",
    "args": ["$SERVER"]
}

with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")

print("Done. Restart Claude Code to load the MCP.")
EOF
