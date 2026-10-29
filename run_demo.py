#!/usr/bin/env python3
"""Replay the ten steps of the Pulse + Grafx decision memory demo.

  python run_demo.py --dry-run                 print every command and prompt for all ten steps, run nothing
  python run_demo.py --steps 5 7 8             run only these steps
  python run_demo.py --start 3                 run steps 3 to 10
  python run_demo.py --list                    list the steps

A dry run uses only the Python standard library. It needs no Pulse or Grafx install and starts nothing.
A real run needs Mac or Linux, Python 3.11 to 3.13, free ports 8100 and 8101, Claude Code logged in,
and network access. Step 7 sends SIGKILL to the okto-pulse server it started. Step 5 runs the Maintainer
reversal script for you. Steps 8 and 9 stop Pulse and leave it stopped.

Every step writes to demo-state/. Agent keys go to agents/.keys.local (mode 600, ignored by git) and are
never printed.
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = ".venv/bin/python"

STEPS = [
    {"n": 1, "title": "Setup: environment, install, init, start, status",
     "shows": "the pairing: okto-pulse 0.4.2 requires okto-grafx 0.0.8; the real embedding model is loaded",
     "commands": ["python3.12 -m venv .venv", ".venv/bin/pip install -r requirements.txt", f"{PY} scripts/capture_versions.py",
                  "scripts/init_pulse.sh MAINTAINER agents/.keys.local", "scripts/start_pulse.sh", "scripts/status.sh",
                  f"{PY} scripts/check_embedding.py"], "prompts": []},
    {"n": 2, "title": "Board, identities, anchor spec",
     "shows": "one board, four identities from Pulse presets, and the board's Grafx store folder",
     "commands": [f"{PY} scripts/setup_board.py"], "prompts": []},
    {"n": 3, "title": "Recorder: twelve decisions in one consolidation",
     "shows": "decisions in the board graph, each with a file and line that exist",
     "commands": [f"{PY} scripts/step03_recorder.py"], "prompts": ["docs/prompts/step3-recorder.md"]},
    {"n": 4, "title": "Recaller: ten questions in a fresh session",
     "shows": "recall by similarity, natural-language search and decision history; a read-only identity cannot write",
     "commands": [f"{PY} scripts/step04_recaller.py", f"{PY} scripts/probe_history.py"], "prompts": ["docs/prompts/step4-recaller.md"]},
    {"n": 5, "title": "Reversal: Maintainer reverses one decision, Reviewer records it",
     "shows": "supersedence chain, contradiction pairs, decision history",
     "commands": [f"{PY} scripts/maintainer_reverse.py", f"{PY} scripts/step05_reversal.py"], "prompts": ["docs/prompts/step5-reviewer.md"]},
    {"n": 6, "title": "Second board and Global Discovery",
     "shows": "a convention on another board found from the first board's context",
     "commands": [f"{PY} scripts/step06_second_board.py"], "prompts": []},
    {"n": 7, "title": "Crash tests: Kill A and Kill B (SIGKILL)",
     "shows": "committed decisions survive, an unfinished consolidation does not",
     "commands": [f"{PY} scripts/step07_crash.py"], "prompts": []},
    {"n": 8, "title": "Direct read: stop Pulse, read the stores from outside",
     "shows": "oktografx and a read-only Python reader see the same counts as Pulse",
     "commands": [f"{PY} scripts/step08_direct_read.py"], "prompts": []},
    {"n": 9, "title": "Backup and restore on a copy of the stopped store",
     "shows": "Grafx backup, restore to a new folder, verify, counts match",
     "commands": [f"{PY} scripts/step09_backup_restore.py"], "prompts": []},
    {"n": 10, "title": "Close-out: build the scoreboard",
     "shows": "demo-state/closeout-result.json built only from recorded outputs",
     "commands": [f"{PY} scripts/build_closeout.py"], "prompts": []},
]


def show(step: dict, dry: bool) -> None:
    print(f"\n=== Step {step['n']}: {step['title']}")
    print(f"    shows: {step['shows']}")
    for c in step["commands"]:
        print(f"    $ {c}")
    for p in step["prompts"]:
        print(f"    --- prompt: {p} (placeholders like {{{{BOARD_ID}}}} are filled from demo-state/step2/board.json at run time)")
        for line in (ROOT / p).read_text().splitlines():
            print(f"    | {line}")


def run(step: dict) -> int:
    for c in step["commands"]:
        print(f"\n$ {c}", flush=True)
        rc = subprocess.call(shlex.split(c), cwd=ROOT)
        if rc != 0:
            print(f"step {step['n']} stopped: command exited {rc}", file=sys.stderr)
            return rc
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--steps", type=int, nargs="+", metavar="N", help="run only these steps (1 to 10)")
    ap.add_argument("--start", type=int, metavar="N", help="run from step N to step 10")
    ap.add_argument("--dry-run", action="store_true", help="print every command and prompt, run nothing")
    ap.add_argument("--list", action="store_true", help="list the steps and exit")
    a = ap.parse_args()

    if a.list:
        for s in STEPS:
            print(f"{s['n']:>2}  {s['title']}")
        return 0
    if a.steps and a.start:
        ap.error("use --steps or --start, not both")
    chosen = [s for s in STEPS if (s["n"] in a.steps if a.steps else s["n"] >= (a.start or 1))]
    bad = [n for n in (a.steps or []) if n not in {s["n"] for s in STEPS}]
    if bad or not chosen:
        ap.error(f"no such step: {bad or a.start}. Steps are 1 to 10.")

    if a.dry_run:
        print("DRY RUN. Nothing is installed, started or changed.")
        for s in chosen:
            show(s, dry=True)
        print(f"\nDry run complete: {len(chosen)} step(s) listed.")
        return 0

    if chosen[0]["n"] > 1 and not (ROOT / PY).exists():
        print("No .venv found. Run step 1 first: python run_demo.py --steps 1", file=sys.stderr)
        return 2
    for s in chosen:
        print(f"\n=== Step {s['n']}: {s['title']}")
        rc = run(s)
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
