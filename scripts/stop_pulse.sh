#!/usr/bin/env bash
# Clean stop: SIGTERM, wait for exit. There is no `okto-pulse stop` command in 0.4.2.
set -euo pipefail
source "$(dirname "$0")/_env.sh"
[[ -f "$PIDFILE" ]] || { echo "no pidfile"; exit 0; }
pid=$(cat "$PIDFILE")
kill -0 "$pid" 2>/dev/null || { echo "pid $pid not running"; rm -f "$PIDFILE"; exit 0; }
kill -TERM "$pid"
for i in $(seq 1 90); do
  kill -0 "$pid" 2>/dev/null || { echo "clean exit after ${i}s"; rm -f "$PIDFILE"; exit 0; }
  sleep 1
done
echo "still running after 90s" >&2; exit 1
