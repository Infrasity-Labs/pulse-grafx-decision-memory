"""Record the evidence for the claim "a real run never touches ~/.okto-pulse".

The claim rests on Pulse reading the DATA_DIR environment variable. This script tests it instead of trusting it:
  1. it makes a temporary HOME and puts a sentinel file in HOME/.okto-pulse, so an untouched folder cannot be mistaken for a missing one
  2. it lists HOME/.okto-pulse (every path, size and SHA-256) and the top level of HOME
  3. it runs, with that HOME and a DATA_DIR in a work folder and two free ports: init, start, create the board (step 2),
     the scripted recorder (step 3, a real graph commit), and a clean stop. No LLM.
  4. it lists both again and compares

Result in demo-state/home-guard/data-dir-claim.json: whether HOME/.okto-pulse is byte for byte the same, and what else the run wrote under HOME
(Hugging Face caches for the embedding model, for example), because "never touches ~/.okto-pulse" is not "writes nothing outside the repo".
It uses the real HOME of nobody: the HOME in this script is a temporary folder that is deleted at the end unless --keep is given.

Usage: python scripts/check_data_dir_claim.py [--keep] [--out FILE]
Exit code 0 if HOME/.okto-pulse is unchanged, 1 if it changed, 2 if the run itself failed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def listing(folder: Path) -> dict:
    """Every file under folder: path relative to it, size and SHA-256. Empty if the folder does not exist."""
    out: dict = {}
    if not folder.exists():
        return out
    for p in sorted(folder.rglob("*")):
        if p.is_file() and not p.is_symlink():
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            out[str(p.relative_to(folder))] = {"bytes": p.stat().st_size, "sha256": h.hexdigest()}
    return out


def top_level(home: Path) -> dict:
    """Each top-level entry of HOME with the number of files and bytes below it."""
    out = {}
    for e in sorted(home.iterdir()):
        files = [p for p in ([e] if e.is_file() else e.rglob("*")) if p.is_file() and not p.is_symlink()]
        out[e.name] = {"files": len(files), "bytes": sum(p.stat().st_size for p in files)}
    return out


def compare(before: dict, after: dict) -> dict:
    return {"added": sorted(set(after) - set(before)), "removed": sorted(set(before) - set(after)),
            "changed": sorted(k for k in set(before) & set(after) if before[k] != after[k])}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="keep the temporary HOME and work folder")
    ap.add_argument("--out", default=str(ROOT / "demo-state" / "home-guard" / "data-dir-claim.json"))
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="pulse-home-guard-"))
    home, work = tmp / "home", tmp / "work"
    (home / ".okto-pulse").mkdir(parents=True)
    work.mkdir()
    (home / ".okto-pulse" / "sentinel.txt").write_text("a file that a real run must leave alone\n")
    api, mcp = free_port(), free_port()
    env = dict(os.environ, HOME=str(home), PULSE_HOME=str(work / "pulse-home"), DATA_DIR=str(work / "pulse-home"), DEMO_STATE=str(work / "state"),
               PULSE_KEYS_FILE=str(work / "keys"), PULSE_API_PORT=str(api), PULSE_MCP_PORT=str(mcp), PULSE_MCP_URL=f"http://127.0.0.1:{mcp}/mcp", PYTHONWARNINGS="ignore")
    py = str(ROOT / ".venv" / "bin" / "python")
    before_okto, before_top = listing(home / ".okto-pulse"), top_level(home)
    steps = [[str(ROOT / "scripts" / "init_pulse.sh"), "MAINTAINER", str(work / "keys")], [str(ROOT / "scripts" / "start_pulse.sh")],
             [py, str(ROOT / "scripts" / "setup_board.py")], [py, str(ROOT / "scripts" / "step03_recorder.py"), "--scripted"]]
    failed = None
    try:
        for cmd in steps:
            p = subprocess.run(cmd, env=env, cwd=ROOT, capture_output=True, text=True)
            if p.returncode != 0:
                failed = {"command": [Path(c).name for c in cmd], "exit_code": p.returncode, "stderr_tail": p.stderr[-600:]}
                break
    finally:
        stop = subprocess.run([str(ROOT / "scripts" / "stop_pulse.sh")], env=env, cwd=ROOT, capture_output=True, text=True)
    after_okto, after_top = listing(home / ".okto-pulse"), top_level(home)
    diff = compare(before_okto, after_okto)
    data_home_files = sum(1 for p in (work / "pulse-home").rglob("*") if p.is_file()) if (work / "pulse-home").exists() else 0
    res = {
        "note": "HOME was a temporary folder with a sentinel in HOME/.okto-pulse. No LLM was called.",
        "ran": ["init", "start", "setup_board (step 2)", "scripted recorder (step 3, one graph commit)", "stop"], "run_failed": failed, "stop_output": (stop.stdout + stop.stderr).strip()[-200:],
        "okto_pulse_dir": {"files_before": len(before_okto), "files_after": len(after_okto), **diff, "unchanged": not (diff["added"] or diff["removed"] or diff["changed"])},
        "files_written_to_the_data_dir": data_home_files,
        "home_top_level_before": before_top, "home_top_level_after": after_top,
        "new_top_level_entries_in_home": sorted(set(after_top) - set(before_top)),
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2) + "\n")
    if not a.keep:
        shutil.rmtree(tmp, ignore_errors=True)
    if failed:
        print(f"run failed: {failed}", file=sys.stderr)
        return 2
    print(f"HOME/.okto-pulse unchanged: {res['okto_pulse_dir']['unchanged']} ({res['okto_pulse_dir']['files_before']} file before, {res['okto_pulse_dir']['files_after']} after); "
          f"data dir files: {data_home_files}; new top-level entries in HOME: {res['new_top_level_entries_in_home']}")
    return 0 if res["okto_pulse_dir"]["unchanged"] else 1


if __name__ == "__main__":
    sys.exit(main())
