"""Copy the evidence of the live model runs into demo-state/llm-runs/<run id>/, scrubbed, with a manifest.

The runners (run_demo.py, run_n.py, run_arms.py) keep their state in temporary folders. This keeps what backs a number: the rendered prompts, the
transcripts and result events of every model session, the graph dumps the scores were computed from, and the summary the runner wrote. Files are
copied unchanged except that the work folder, the repo folder, the home folder and any /tmp path are replaced by placeholders. Nothing is read from
the environment variables of the run, so no key can reach the copy, and scripts/scan_repo.py is run over the result by the caller.

run-info.json is the manifest: run id, when, which model was requested and which model the sessions reported, Claude Code, package and Python
versions, platform, the repo commit and whether the working tree had uncommitted changes, the cost the result events report in total, and the
SHA-256 of every file copied. tests/test_llm_runs.py recomputes the hashes.

Usage:
  python scripts/export_llm_runs.py --run-id ID --out demo-state/llm-runs/ID --smoke STATE_DIR \\
      --n-runs main=/tmp/.../nruns-main --n-runs reviewer-scripted-base=/tmp/.../nruns-rev [--arms-dir demo-state/arms] [--note TEXT]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata as md
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STATE_FILES = [
    "step3/prompt.rendered.md", "step3/citations.json", "step3/decisions-from-graph.json", "step3/decision-edges.json", "step3/agent/result.json", "step3/agent/transcript.jsonl",
    "step4/prompt.rendered.md", "step4/recall-results.json", "step4/agent/result.json", "step4/agent/transcript.jsonl",
    "step5/maintainer-reversal.json", "step5/prompt.rendered.md", "step5/before.json", "step5/after.json", "step5/agent/result.json", "step5/agent/transcript.jsonl",
    "arms/pulse-retrieval.json", "timings.json",
]


def clean(text: str, roots: list[Path]) -> str:
    for base, tag in [(r.resolve(), "<work>") for r in roots] + [(ROOT, "<repo>"), (Path.home(), "<home>")]:
        if str(base) not in ("/", ""):
            text = text.replace(str(base), tag)
    return re.sub(r"/(?:private/)?tmp/[A-Za-z0-9_./-]+", "<tmp>", text)


def copy_tree(src_state: Path, dst: Path, roots: list[Path], files: list[str]) -> list[str]:
    done = []
    for rel in files:
        f = src_state / rel
        if f.exists():
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            (dst / rel).write_text(clean(f.read_text(), roots))
            done.append(rel)
    return done


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--smoke", help="state folder of the run_demo.py --steps 3 4 5 run")
    ap.add_argument("--n-runs", action="append", default=[], metavar="NAME=DIR", help="output folder of run_n.py (holds summary.json and run-K/state)")
    ap.add_argument("--arms-dir", default=str(ROOT / "demo-state" / "arms"))
    ap.add_argument("--arms-from", help="state/arms folder of the run_arms.py run; its llm-* files are copied, scrubbed, into --arms-dir first")
    ap.add_argument("--note", action="append", default=[], help="a fact about the run that the manifest should carry, for example a concurrent job")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    roots: list[Path] = []
    if a.smoke:
        roots.append(Path(a.smoke).parent)
        copy_tree(Path(a.smoke), out / "smoke", roots, STATE_FILES)
    for item in a.n_runs:
        name, _, d = item.partition("=")
        work = Path(d)
        roots.append(work)
        dst = out / f"n-runs-{name}"
        dst.mkdir(parents=True, exist_ok=True)
        summary = json.loads((work / "summary.json").read_text())
        (dst / "summary.json").write_text(clean(json.dumps(summary, indent=2) + "\n", roots))
        for run in sorted(work.glob("run-*")):
            copy_tree(run / "state", dst / run.name, roots, STATE_FILES)
    sessions = []
    for p in sorted(out.rglob("result.json")):
        r = json.loads(p.read_text())
        if r.get("model") and not r["model"].startswith("scripted"):
            f = r.get("final") or {}
            sessions.append({"file": str(p.relative_to(out)), "role": r.get("role"), "model": r["model"], "model_requested": r.get("model_requested"), "cost_usd": f.get("total_cost_usd"),
                             "seconds": r.get("seconds"), "finished_at": r.get("finished_at"), "is_error": f.get("is_error")})
    arms = Path(a.arms_dir)
    if a.arms_from:
        src = Path(a.arms_from)
        roots.append(src.parent.parent)
        for f in sorted(src.glob("llm-*")):
            if f.is_file():
                (arms / f.name).write_text(clean(f.read_text(), roots))
            else:
                for g in sorted(f.rglob("*")):
                    if g.is_file():
                        (arms / f.name / g.relative_to(f)).parent.mkdir(parents=True, exist_ok=True)
                        (arms / f.name / g.relative_to(f)).write_text(clean(g.read_text(), roots))
    arm_sessions = []
    for p in sorted(arms.glob("llm-*/run-*/result.json")):
        r = json.loads(p.read_text())
        f = r.get("final") or {}
        arm_sessions.append({"file": str(p.relative_to(ROOT)), "role": r.get("role"), "model": r.get("model"), "model_requested": r.get("model_requested"), "cost_usd": f.get("total_cost_usd"),
                             "seconds": r.get("seconds"), "finished_at": r.get("finished_at"), "is_error": f.get("is_error")})
    allsess = sessions + arm_sessions
    cc = None
    for p in sorted(out.rglob("transcript.jsonl")):
        first = json.loads(p.read_text().splitlines()[0])
        if first.get("claude_code_version"):
            cc = first["claude_code_version"]
            break
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip())
    cfg = json.loads((ROOT / "config" / "agent.json").read_text())
    times = sorted(s["finished_at"] for s in allsess if s["finished_at"])
    files = {str(p.relative_to(out)): sha256(p) for p in sorted(out.rglob("*")) if p.is_file() and p.name != "run-info.json"}
    arm_files = {str(p.relative_to(ROOT)): sha256(p) for p in sorted(arms.rglob("*")) if p.is_file() and p.relative_to(arms).parts[0].startswith("llm-")}
    info = {
        "run_id": a.run_id,
        "what": "Live runs with a model (Claude Code, headless) against real Pulse and Grafx on fresh data homes: the smoke run (run_demo.py --steps 3 4 5), the variance studies (run_n.py) and, in demo-state/arms/, the LLM arms (run_arms.py).",
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "first_session_finished_at": times[0] if times else None, "last_session_finished_at": times[-1] if times else None,
        "model_pinned_in_config": cfg["model"], "models_reported_by_sessions": sorted({s["model"] for s in allsess}),
        "model_requested_by_sessions": sorted({s["model_requested"] for s in allsess if s["model_requested"]}),
        "claude_code": cc, "python": platform.python_version(), "platform": f"{platform.system()} {platform.machine()}",
        "okto_pulse": md.version("okto-pulse"), "okto_pulse_core": md.version("okto-pulse-core"), "okto_grafx": md.version("okto-grafx"),
        "sentence_transformers": md.version("sentence-transformers"), "torch": md.version("torch"), "fastmcp": md.version("fastmcp"),
        "repo_base_commit": sha, "working_tree_had_uncommitted_changes": dirty,
        "isolation": "Each Pulse data home was new, on two free ports; HOME and CLAUDE_CONFIG_DIR were temporary folders; the API key was passed in the environment of the child processes only.",
        "sessions": {"count": len(allsess), "in_this_folder": len(sessions), "arms": len(arm_sessions), "errors": sum(bool(s["is_error"]) for s in allsess),
                     "total_cost_usd": round(sum(s["cost_usd"] or 0 for s in allsess), 4), "total_wall_seconds": round(sum(s["seconds"] or 0 for s in allsess), 1)},
        "notes": a.note,
        "files": files, "arm_files_not_copied_here_but_hashed": arm_files,
    }
    (out / "run-info.json").write_text(json.dumps(info, indent=2) + "\n")
    print(f"exported {len(files)} files to {out}; {len(allsess)} model sessions, ${info['sessions']['total_cost_usd']} by the result events; models {info['models_reported_by_sessions']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
