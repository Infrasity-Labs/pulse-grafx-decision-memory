"""CI helper for the manual LLM workflow: start Pulse on a temporary data home and free ports, build the 32-decision corpus board,
run the three LLM arms (scripts/run_arms.py), stop Pulse.

run_arms.py needs a running Pulse with the corpus board, and it calls Claude Code, which costs money. This script only wires the
environment the other scripts already read (PULSE_HOME, ports, keys file, DEMO_STATE). It adds no logic of its own and records
nothing in demo-state/. Nothing touches the default data home or ports 8100 and 8101.

Usage: python scripts/ci_llm_arms.py [--work DIR] [run_arms.py arguments]
Output: DIR/state/arms/llm-<arm>.json and DIR/state/arms/llm-<arm>/ (prompt, transcript, result), DIR/keys is never uploaded
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default=str(ROOT / ".work" / "llm-arms"))
    a, rest = ap.parse_known_args()
    work = Path(a.work)
    if work.exists():
        shutil.rmtree(work)
    (work / "state").mkdir(parents=True)
    api, mcp = free_port(), free_port()
    (work / "ports.json").write_text(json.dumps({"api": api, "mcp": mcp}))
    env = dict(os.environ, PULSE_HOME=str(work / "pulse-home"), DATA_DIR=str(work / "pulse-home"), DEMO_STATE=str(work / "state"),
               PULSE_KEYS_FILE=str(work / "keys"), PULSE_API_PORT=str(api), PULSE_MCP_PORT=str(mcp),
               PULSE_MCP_URL=f"http://127.0.0.1:{mcp}/mcp", PYTHONWARNINGS="ignore")

    def run(*cmd: str, check: bool = True) -> int:
        rc = subprocess.call(list(cmd), env=env, cwd=ROOT)
        if check and rc:
            raise SystemExit(rc)
        return rc

    try:
        run(str(ROOT / "scripts" / "init_pulse.sh"), "MAINTAINER", str(work / "keys"))
        run(str(ROOT / "scripts" / "start_pulse.sh"))
        run(PY, str(ROOT / "scripts" / "setup_board.py"))
        run(PY, str(ROOT / "scripts" / "build_corpus.py"))
        return run(PY, str(ROOT / "scripts" / "run_arms.py"), *rest, check=False)
    finally:
        subprocess.call([str(ROOT / "scripts" / "stop_pulse.sh")], env=env, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
