#!/usr/bin/env bash
# SIGKILL the server. Used by the crash tests. Prints the pid and a UTC timestamp.
set -euo pipefail
source "$(dirname "$0")/_env.sh"
pid=$(cat "$PIDFILE")
echo "SIGKILL pid=$pid at $(date -u +%FT%T.%3NZ 2>/dev/null || date -u +%FT%TZ)"
kill -KILL "$pid"
for _ in $(seq 1 30); do kill -0 "$pid" 2>/dev/null || break; sleep 0.2; done
kill -0 "$pid" 2>/dev/null && { echo "still alive" >&2; exit 1; }
rm -f "$PIDFILE"; echo "dead"
