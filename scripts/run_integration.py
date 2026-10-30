"""Run the non-LLM steps against real Pulse and Grafx on a fresh data home, then assert what came back. No LLM, no secret.

This is what CI runs (.github/workflows/integration.yml). The fast `validate` workflow only checks committed files. This runs the products.

Phases, in order:
  setup     step 1 (versions, init, start, status, embedding check) and step 2 (board, four identities, anchor spec)
  memory    step 3 (scripted Recorder), step 4 (scripted Recaller, legacy questions), step 3b (10 code-derived decisions, then the
            Pulse spec flow with its gate for 10 graph-only decisions), role probes, the lexical baseline, the Pulse retrieval arm and the decision-history probe
  reversal  step 5 (scripted Reviewer: supersede, then the explicit contradicts edge) and the no-rationale failing path
  global    step 6 (second board, Global Discovery)
  crash     step 7 (Kill A with resume, Kill B with retry, decision board unchanged)
  read      step 8 (stop Pulse, read the stores directly)
  restore   step 9 (backup and restore of a copy, decision-level comparison). Needs Linux, or macOS with Docker.
  closeout  build_closeout.py on the new outputs
  assert    scripts/assert_runtime.py on everything above

Everything runs in --work (default .work/integration): its own data home, keys, state, logs and two free ports. Nothing is written to
demo-state/ and nothing is read from or written to the default Pulse data home. A phase that fails stops the run; logs and state stay in --work.
Run a later phase again with --phases after a fix. The `setup` phase deletes --work first, so leave it out to resume.

Usage: python scripts/run_integration.py [--work DIR] [--phases setup memory ...] [--require-step9]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHASES = ["setup", "memory", "reversal", "global", "crash", "read", "restore", "closeout", "assert"]
PY = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Run:
    def __init__(self, work: Path, fresh: bool):
        if fresh and work.exists():
            shutil.rmtree(work)
        (work / "logs").mkdir(parents=True, exist_ok=True)
        (work / "state").mkdir(exist_ok=True)
        self.work = work
        ports = work / "ports.json"
        if not ports.exists():
            ports.write_text(json.dumps({"api": free_port(), "mcp": free_port()}))
        p = json.loads(ports.read_text())
        self.env = dict(os.environ, PULSE_HOME=str(work / "pulse-home"), DATA_DIR=str(work / "pulse-home"), DEMO_STATE=str(work / "state"), PULSE_KEYS_FILE=str(work / "keys"),
                        PULSE_API_PORT=str(p["api"]), PULSE_MCP_PORT=str(p["mcp"]), PULSE_MCP_URL=f"http://127.0.0.1:{p['mcp']}/mcp", PYTHONWARNINGS="ignore")
        self.n = len(list((work / "logs").glob("*.log")))

    def step(self, label: str, cmd: list[str], ok_codes=(0,)) -> int:
        self.n += 1
        log = self.work / "logs" / f"{self.n:02d}-{label}.log"
        t0 = time.time()
        with open(log, "w") as f:
            f.write(f"$ {' '.join(Path(c).name if os.sep in c else c for c in cmd)}\n")
            f.flush()
            rc = subprocess.call(cmd, env=self.env, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
        print(f"  [{'ok' if rc in ok_codes else 'FAIL'}] {label} ({time.time() - t0:.0f} s, exit {rc}) log: {log.relative_to(self.work.parent) if self.work.parent in log.parents else log}", flush=True)
        if rc not in ok_codes:
            tail = log.read_text().splitlines()[-15:]
            print("\n".join("      " + ln for ln in tail), flush=True)
            raise SystemExit(rc or 1)
        return rc

    def py(self, label: str, script: str, *args: str, ok_codes=(0,)) -> int:
        return self.step(label, [PY, str(ROOT / "scripts" / script), *args], ok_codes)

    def sh(self, label: str, script: str, *args: str, ok_codes=(0,)) -> int:
        return self.step(label, [str(ROOT / "scripts" / script), *args], ok_codes)


def phase_setup(r: Run) -> None:
    r.py("versions", "capture_versions.py")
    r.sh("init", "init_pulse.sh", "MAINTAINER", str(r.work / "keys"))
    r.sh("start", "start_pulse.sh")
    r.sh("status", "status.sh")
    r.py("embedding", "check_embedding.py")
    r.py("board", "setup_board.py")


def phase_memory(r: Run) -> None:
    r.py("step3-scripted-recorder", "step03_recorder.py", "--scripted")
    r.py("step4-scripted-recaller", "step04_recaller.py", "--scripted")
    r.py("step3b-code-extras", "scripted_steps.py", "code-extras")
    r.py("step3b-spec-flow", "spec_flow.py")
    r.py("roles", "probe_roles.py")
    r.py("arm-lexical", "lexical_baseline.py")
    r.py("arm-pulse-retrieval", "arm_pulse_retrieval.py")
    r.py("history-probe", "probe_history.py")


def phase_reversal(r: Run) -> None:
    r.py("step5-note", "maintainer_reverse.py")
    r.py("step5-scripted-reviewer", "step05_reversal.py", "--scripted")
    r.py("step5-note-no-rationale", "maintainer_reverse.py", "--no-rationale")
    r.py("step5-scripted-reviewer-no-rationale", "step05_reversal.py", "--scripted", "--note", "maintainer-reversal-no-rationale.json")


def phase_global(r: Run) -> None:
    r.py("step6", "step06_second_board.py")


def phase_crash(r: Run) -> None:
    r.py("step7", "step07_crash.py")


def phase_read(r: Run) -> None:
    r.py("step8", "step08_direct_read.py")


def phase_restore(r: Run, require: bool) -> None:
    host_ok = platform.system() == "Linux" or shutil.which("docker") and subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    if not host_ok and not require:
        print("  [skip] step 9: it needs Linux, or Docker on macOS, and neither is available. assert_runtime.py will report it as not run.", flush=True)
        return
    r.py("step9", "step09_backup_restore.py")


def phase_closeout(r: Run) -> None:
    if not list((r.work / "state" / "step9").glob("backup-restore-*.json")):
        print("  [skip] closeout: it needs the step 9 result, and step 9 did not run.", flush=True)
        return
    r.py("closeout", "build_closeout.py", "--state", str(r.work / "state"), "--out", str(r.work / "state" / "closeout-result.json"))


def phase_assert(r: Run, require_step9: bool) -> None:
    r.py("assert", "assert_runtime.py", "--state", str(r.work / "state"), *(["--require-step9"] if require_step9 else []))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default=str(ROOT / ".work" / "integration"))
    ap.add_argument("--phases", nargs="+", choices=PHASES, default=PHASES)
    ap.add_argument("--require-step9", action="store_true", help="fail instead of skipping step 9 when neither Linux nor Docker is available")
    a = ap.parse_args()
    r = Run(Path(a.work), fresh="setup" in a.phases)
    print(f"integration run in {a.work}: pulse ports {r.env['PULSE_API_PORT']}/{r.env['PULSE_MCP_PORT']}, data home {r.env['PULSE_HOME']}", flush=True)
    try:
        for ph in PHASES:
            if ph not in a.phases:
                continue
            print(f"phase {ph}", flush=True)
            if ph == "restore":
                phase_restore(r, a.require_step9)
            elif ph == "assert":
                phase_assert(r, a.require_step9)
            else:
                globals()[f"phase_{ph}"](r)
    finally:
        # leave nothing running: a failed phase must not leave a server on the port. stop_pulse.sh is a no-op when the pidfile is gone
        subprocess.call([str(ROOT / "scripts" / "stop_pulse.sh")], env=r.env, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        src = ROOT / ".work" / "logs"
        if src.exists():
            for f in src.glob(f"pulse-{r.env['PULSE_API_PORT']}.log"):
                shutil.copy(f, r.work / "logs" / f.name)
    print("integration run complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
