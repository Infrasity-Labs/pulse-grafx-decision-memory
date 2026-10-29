#!/usr/bin/env bash
# Start okto-pulse serve in the background and wait until both servers answer.
# Env: PULSE_HOME (data home), PULSE_API_PORT, PULSE_MCP_PORT. Prints the pid and seconds to ready.
set -euo pipefail
source "$(dirname "$0")/_env.sh"
if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "already running pid $(cat "$PIDFILE")"; exit 0
fi
LOG="$LOG_DIR/pulse-$PULSE_API_PORT.log"
echo "=== start $(date -u +%FT%TZ) ===" >> "$LOG"
start=$(date +%s)
nohup "$PULSE" serve --api-port "$PULSE_API_PORT" --mcp-port "$PULSE_MCP_PORT" --accept-terms >> "$LOG" 2>&1 &
echo $! > "$PIDFILE"
for _ in $(seq 1 240); do
  if "$PULSE" status --json --api-port "$PULSE_API_PORT" --mcp-port "$PULSE_MCP_PORT" 2>/dev/null \
     | "$PY" -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d["api_up"] and d["mcp_up"] else 1)' 2>/dev/null; then
    echo "pulse up pid $(cat "$PIDFILE") ready_after_s=$(( $(date +%s) - start )) api=$PULSE_API_PORT mcp=$PULSE_MCP_PORT"
    exit 0
  fi
  kill -0 "$(cat "$PIDFILE")" 2>/dev/null || { echo "pulse exited during start, see $LOG" >&2; exit 1; }
  sleep 1
done
echo "pulse not ready after 240s, see $LOG" >&2; exit 1
