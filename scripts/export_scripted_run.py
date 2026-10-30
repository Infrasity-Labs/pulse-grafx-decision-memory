"""Copy the evidence of one scripted integration run into demo-state/scripted-run/, with machine paths replaced.

run_integration.py writes everything under its --work folder. That folder is temporary. This script keeps the part that backs a
claim: the spec-flow gate record, the role denials, the crash-recovery results, the arm results and the assertion report. It copies
files unchanged except that the work folder, the repo folder and the home folder are replaced by <work>, <repo> and <home>. It also writes
run-info.json: when, on what machine, with which versions, from which commit, and what the assertions said.

The direct-read output of step 8 (hundreds of KB of schema listings) is not copied. A short summary of it is written instead.
The scripted run is not an agent run. Nothing here says what an agent would choose to do.

A dated copy is made with --out demo-state/integration-<run id> --run-id <run id>. Then run-info.json also carries the run id and a SHA-256 manifest
of every copied file. --update-arms also writes the Pulse retrieval arm file into demo-state/arms/ (do not use it for a container run: the arm file
there is the macOS one). --what and --label name a run that is not the plain macOS integration run, for example the Linux container run.

Usage: python scripts/export_scripted_run.py --work .work/integration [--out demo-state/scripted-run] [--run-id ID] [--update-arms] [--what TEXT]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    "step1/versions.json", "step1/embedding.json",
    "step3/citations.json", "step3/decisions-from-graph.json", "step3/decision-edges.json", "step3/agent/result.json", "step3/agent/transcript.jsonl",
    "step3b/spec-flow.json", "step3b/node-map.json",
    "step4/recall-results.json", "step4/agent/transcript.jsonl", "step4/history-probe.json",
    "step5/maintainer-reversal.json", "step5/before.json", "step5/after.json", "step5/agent/transcript.jsonl",
    "step5/maintainer-reversal-no-rationale/before.json", "step5/maintainer-reversal-no-rationale/after.json", "step5/maintainer-reversal-no-rationale/agent/result.json",
    "step6/global-discovery.json",
    "step7/killA.json", "step7/killB.json", "step7/decision-board-check.json", "step7/burst-ack-w1.log", "step7/burst-ack-w2.log", "step7/burst-ack-w3.log",
    "roles/role-denials.json", "arms/pulse-retrieval.json", "arms/lexical-tfidf.json", "assert-report.json", "closeout-result.json", "timings.json",
    "step2/board.json",
]
GLOBS = ["step9/backup-restore-*.json", "step9/reader-*.json", "step8/reader-*.json", "logs/*.log"]


def clean(text: str, work: Path) -> str:
    for base, tag in (((ROOT / ".venv").resolve(), "<venv>"), (work.resolve(), "<work>"), (ROOT, "<repo>"), (Path.home(), "<home>")):
        text = text.replace(str(base), tag)
    return re.sub(r"/(?:private/)?tmp/[A-Za-z0-9_./-]+", "<tmp>", text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", default=str(ROOT / "demo-state" / "scripted-run"))
    ap.add_argument("--run-id")
    ap.add_argument("--update-arms", action="store_true", help="also write the Pulse retrieval arm file into demo-state/arms/")
    ap.add_argument("--what")
    ap.add_argument("--started-at", help="UTC time the run was started (from the command that started it); recorded_at is only the time of this export")
    ap.add_argument("--logs-dir", help="folder with the step logs of the run (default: WORK/logs); copied into the export as logs/")
    a = ap.parse_args()
    work, out = Path(a.work), Path(a.out)
    state = work / "state"
    out.mkdir(parents=True, exist_ok=True)
    copied, missing = [], []
    rels = list(FILES)
    for g in GLOBS:
        if g.startswith("logs/"):
            continue
        rels += sorted(str(p.relative_to(state)) for p in state.glob(g))
    for rel in rels:
        src = state / rel
        if not src.exists():
            missing.append(rel)
            continue
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(clean(src.read_text(), work))
        copied.append(rel)
    logs = Path(a.logs_dir) if a.logs_dir else work / "logs"
    for f in sorted(logs.glob("*.log")) if logs.exists() else []:
        dst = out / "logs" / f.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(clean(f.read_text(errors="replace"), work))
        copied.append(f"logs/{f.name}")
    arm = state / "arms" / "pulse-retrieval.json"
    if arm.exists() and a.update_arms:
        (ROOT / "demo-state" / "arms").mkdir(parents=True, exist_ok=True)
        (ROOT / "demo-state" / "arms" / "pulse-retrieval.json").write_text(clean(arm.read_text(), work))
    dr = state / "step8" / "direct-read.json"
    summary8 = None
    if dr.exists():
        boards = json.loads(dr.read_text())["boards"]
        summary8 = {name: {"nodes_match": e["comparison"].get("nodes_match"), "edges_match": e["comparison"].get("edges_match"), "reader_nodes": e["comparison"].get("reader_nodes"),
                           "data_files_unchanged_by_read": e["data_files_unchanged_by_read"]} for name, e in boards.items()}
    report = json.loads((state / "assert-report.json").read_text())
    ver = json.loads((state / "step1" / "versions.json").read_text())
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip())
    info = {
        "what": a.what or "One scripted integration run (scripts/run_integration.py): fixed tool calls, no LLM, a fresh Pulse data home. Not an agent run.",
        **({"run_id": a.run_id} if a.run_id else {}),
        **({"started_at": a.started_at} if a.started_at else {}),
        "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "platform": ver["platform"], "python": ver["python"], "okto_pulse": ver["okto_pulse"], "okto_grafx": ver["okto_grafx"],
        "sentence_transformers": ver["sentence_transformers"], "torch": ver["torch"],
        "repo_base_commit": sha, "working_tree_had_uncommitted_changes": dirty,
        "assertions": {"checks": report["checks"] - sum(r["kind"] == "skip" for r in report["results"]), "failed": report["failed"], "skipped": [r["name"] for r in report["results"] if r["kind"] == "skip"]},
        "step_8_summary": summary8, "files": copied, "files_missing_in_the_run": [m for m in missing if not m.startswith("step9/") or (state / "step9").exists()],
        "not_run": [r["name"] for r in report["results"] if r["kind"] == "skip"],
    }
    if a.run_id:
        info["sha256"] = {rel: hashlib.sha256((out / rel).read_bytes()).hexdigest() for rel in copied}
    (out / "run-info.json").write_text(json.dumps(info, indent=2) + "\n")
    print(f"copied {len(copied)} files to {out}; missing {missing}; assertions {info['assertions']['checks'] - info['assertions']['failed']} of {info['assertions']['checks']} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
