#!/usr/bin/env bash
set -eu

PROJECT_DIR="${HPC_AGENT_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PROJECT_DIR"

PYTHON="$PROJECT_DIR/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  PYTHON="$(command -v python3)"
fi

if [ -f "$PROJECT_DIR/.env" ]; then
  while IFS= read -r -d '' entry; do
    export "$entry"
  done < <("$PYTHON" - "$PROJECT_DIR/.env" <<'PY'
import os
import sys

from dotenv import dotenv_values

env_path = sys.argv[1]
for key, value in dotenv_values(env_path).items():
    if not key or value is None or key in os.environ:
        continue
    sys.stdout.buffer.write(f"{key}={value}".encode())
    sys.stdout.buffer.write(b"\0")
PY
)
fi

HOST="${HPC_AGENT_MCP_HOST:-127.0.0.1}"
PORT="${HPC_AGENT_MCP_PORT:-8000}"
PATH_VALUE="${HPC_AGENT_MCP_PATH:-/mcp}"
ALLOWED_HOST="${HPC_AGENT_MCP_ALLOWED_HOST:-}"
ALLOWED_ORIGIN="${HPC_AGENT_MCP_ALLOWED_ORIGIN:-}"
LOG_DIR="${HPC_AGENT_LOG_DIR:-$HOME/.local/share/hpc-agent/logs}"

mkdir -p "$LOG_DIR"

export HPC_AGENT_MCP_AUDIT_LOG="${HPC_AGENT_MCP_AUDIT_LOG:-$HOME/.local/share/hpc-agent/mcp_audit.jsonl}"

CMD="$PROJECT_DIR/.venv/bin/hpc-agent-mcp"
if [ ! -x "$CMD" ]; then
  CMD="$(command -v hpc-agent-mcp)"
fi

set -- "$CMD" \
  --transport streamable-http \
  --host "$HOST" \
  --port "$PORT" \
  --path "$PATH_VALUE"

if [ -n "$ALLOWED_HOST" ]; then
  set -- "$@" --allowed-host "$ALLOWED_HOST"
fi

if [ -n "$ALLOWED_ORIGIN" ]; then
  set -- "$@" --allowed-origin "$ALLOWED_ORIGIN"
fi

echo "Starting hpc-agent MCP on http://$HOST:$PORT$PATH_VALUE"
echo "Health check: http://$HOST:$PORT/health"
echo "Audit log: $HPC_AGENT_MCP_AUDIT_LOG"

exec "$@" 2>&1 | tee -a "$LOG_DIR/mcp-http.log"
