#!/bin/bash
# Sets up the log-reader MCP server and registers it globally in Claude Code.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check Python 3 is available
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install Python 3.8+ and try again."
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(sys.version_info.minor)")
if [ "$PYTHON_VERSION" -lt 8 ]; then
    echo "ERROR: Python 3.8+ required. Found: $(python3 --version)"
    exit 1
fi

# Check venv is available (missing on Ubuntu/Debian without python3-venv)
if ! python3 -m venv --help &>/dev/null; then
    echo "ERROR: python3-venv is not installed."
    echo ""
    echo "Fix it with:"
    echo "  Ubuntu/Debian: sudo apt install python3-venv"
    echo "  Fedora/RHEL:   sudo dnf install python3"
    echo "  macOS:         venv is included with Python from python.org or Homebrew"
    exit 1
fi

echo "Creating virtualenv..."
python3 -m venv "$SCRIPT_DIR/venv"

echo "Installing dependencies..."
"$SCRIPT_DIR/venv/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"

PYTHON="$SCRIPT_DIR/venv/bin/python"
SERVER="$SCRIPT_DIR/server.py"
SETTINGS="$HOME/.claude/settings.json"

echo "Registering MCP server in $SETTINGS ..."

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

print("Registered successfully.")
EOF

echo ""
echo "Done! Restart Claude Code to load the MCP server."
