# Shared settings for the demo scripts. Source this file, do not run it.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PULSE_HOME="${PULSE_HOME:-$ROOT/.work/pulse-home}"
export PULSE_API_PORT="${PULSE_API_PORT:-8100}"
export PULSE_MCP_PORT="${PULSE_MCP_PORT:-8101}"
export DATA_DIR="$PULSE_HOME"
export OKTO_PULSE_NO_BANNER=1
export PYTHONWARNINGS=ignore
PY="$ROOT/.venv/bin/python"
PULSE="$ROOT/.venv/bin/okto-pulse"
LOG_DIR="$ROOT/.work/logs"
PIDFILE="$ROOT/.work/pulse-$PULSE_API_PORT.pid"
mkdir -p "$LOG_DIR"
