#!/usr/bin/env bash
# Print okto-pulse status (human text, then JSON).
set -euo pipefail
source "$(dirname "$0")/_env.sh"
"$PULSE" status --api-port "$PULSE_API_PORT" --mcp-port "$PULSE_MCP_PORT" || true
echo "--- json"
"$PULSE" status --json --api-port "$PULSE_API_PORT" --mcp-port "$PULSE_MCP_PORT" || true
