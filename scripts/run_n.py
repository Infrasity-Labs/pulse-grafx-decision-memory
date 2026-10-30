"""Run the recording and recall steps N times, each on a fresh Pulse data home, and report the spread.

One run is one sample. This runner repeats steps 1 to 4 and the Pulse retrieval arm N times and reports mean, minimum and maximum
of each number, so a reader can tell 10 of 10 from "10 of 10 once".

Per run, in a fresh data home on two free ports:
  init, start Pulse, create the board (step 2)
  step 3   Recorder: the goal-based agent prompt, or (not in --agents) the replay of the 12 recorded decisions. Checked in open mode.
  step 3b  the 10 code-derived and 10 graph-only decisions, scripted: scripted_steps.py code-extras, then spec_flow.py
  step 4   Recaller: the goal-based agent prompt on --splits (default dev held_out), or (not in --agents) the ten legacy questions
           (they are asked before step 3b, on the 12-decision board, as in the recorded run)
  arm      scripts/arm_pulse_retrieval.py on the board as it stands (agent decisions plus the scripted ones, 32 only when the Recorder is scripted)
  step 5   Reviewer, with --agents reviewer: the Maintainer note, then the goal-based Reviewer prompt. Without it the reversal is not run.
  stop Pulse

--agents chooses which sessions call the model: recorder, recaller, reviewer. The default is recorder and recaller. --scripted means none.
The Reviewer can only record a reversal of a decision that is on the board. With a model Recorder the board may not hold the decision the
note reverses, so each run records reversal_target_present and a run without it is a refusal case, not a failed reversal. Use
--agents reviewer alone to run the Reviewer on the scripted base, where the target always exists.

Reported per metric: n, mean, min, max. For an agent run also tokens, cost and wall time per role, from the result event.
With --scripted no model is called and the spread shows how much Pulse and Grafx vary between fresh homes. Every model session costs money: run it only on purpose.

Usage: python scripts/run_n.py --runs 5 [--agents recorder recaller reviewer | --scripted] [--splits dev held_out] [--out DIR]
       python scripts/run_n.py --recompute DIR      rebuild DIR/summary.json from the saved runs, no model
Output: OUT/run-1 ... run-N (state of each run) and OUT/summary.json. Default OUT is .work/n-runs. Copy summary.json into demo-state/n-runs/ to record it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_citations  # noqa: E402
import runstats  # noqa: E402


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def sh(cmd: list[str], env: dict, check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, env=env, cwd=ROOT, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise SystemExit(f"command failed ({p.returncode}): {' '.join(cmd)}\n{p.stdout[-800:]}\n{p.stderr[-800:]}")
    return p


def py(script: str, *args: str) -> list[str]:
    return [str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "scripts" / script), *args]


def one_run(i: int, work: Path, agents: set[str], splits: list[str]) -> dict:
    run = work / f"run-{i}"
    if run.exists():
        shutil.rmtree(run)
    (run / "state").mkdir(parents=True)
    api, mcp = free_port(), free_port()
    env = dict(os.environ, PULSE_HOME=str(run / "pulse-home"), DATA_DIR=str(run / "pulse-home"), DEMO_STATE=str(run / "state"), PULSE_KEYS_FILE=str(run / "keys"),
               PULSE_API_PORT=str(api), PULSE_MCP_PORT=str(mcp), PULSE_MCP_URL=f"http://127.0.0.1:{mcp}/mcp", PYTHONWARNINGS="ignore")
    sh([str(ROOT / "scripts" / "init_pulse.sh"), "MAINTAINER", str(run / "keys")], env)
    sh([str(ROOT / "scripts" / "start_pulse.sh")], env)
    try:
        sh(py("setup_board.py"), env)
        rec_flag = [] if "recorder" in agents else ["--scripted"]
        sh(py("step03_recorder.py", *rec_flag), env, check="recorder" not in agents)
        if "recaller" not in agents:
            sh(py("step04_recaller.py", "--scripted"), env)
        sh(py("scripted_steps.py", "code-extras"), env)
        sh(py("spec_flow.py"), env)
        if "recaller" in agents:
            sh(py("step04_recaller.py", "--splits", *splits), env, check=False)
        sh(py("arm_pulse_retrieval.py"), env)
        if "reviewer" in agents:
            sh(py("maintainer_reverse.py"), env)
            sh(py("step05_reversal.py"), env, check=False)
    finally:
        sh([str(ROOT / "scripts" / "stop_pulse.sh")], env, check=False)
    return collect(i, run, agents, {"api_port": api, "mcp_port": mcp})


def collect(i: int, run: Path, agents: set[str], extra: dict) -> dict:
    """Read the numbers of one run from its saved state. Used right after a run, and by --recompute on runs that are already saved.

    Only sessions that called a model are listed in agent_runs: a scripted session has no cost or tokens."""
    st = run / "state"
    out: dict = {"run": i, **extra}
    rows = json.loads((st / "step3" / "decisions-from-graph.json").read_text())
    opened = check_citations.check_open(rows, ROOT)
    out["recorder"] = {"nodes": opened["found"], "citations_ok": opened["citations_ok"], "reference_covered": opened["reference_covered"], "reference_entries": opened["reference_entries"]}
    rec_file = st / "step4" / "recall-results.json"
    if rec_file.exists():
        rec = json.loads(rec_file.read_text())["summary"]
        out["recaller"] = {k: rec[k] for k in ("agent_choice_correct", "questions", "answerable_expected_on_board", "agent_choice_correct_where_expected_on_board") if k in rec}
        out["recaller"]["scores_by_split"] = rec["scores_by_split"]
        out["recaller"]["expected_missing_from_board"] = len(rec.get("answerable_expected_missing_from_board", []))
    if "reviewer" in agents:
        out["reviewer"] = reviewer_outcome(st)
    arm = json.loads((st / "arms" / "pulse-retrieval.json").read_text())
    import score_arms
    import corpus

    out["pulse_retrieval_arm"] = score_arms.score(corpus.questions(), arm["answers"])
    for role, step in (("recorder", "step3"), ("recaller", "step4"), ("reviewer", "step5")):
        f = st / step / "agent" / "result.json"
        if f.exists():
            res = json.loads(f.read_text())
            if not str(res.get("model", "")).startswith("scripted"):
                out.setdefault("agent_runs", {})[role] = runstats.summarise(res)
    return out


def reviewer_outcome(st: Path) -> dict:
    """What the Reviewer left in the graph, read from the graph snapshots before and after it ran. Its own report is kept next to it, not instead of it.

    The goal-based prompt does not give the Reviewer a slug or a source reference for the new decision, so the new decision is not counted by slug
    or by reference: the edges it added are counted (supersedes, contradicts), and the old decision is found by the slug of the decision the note reverses."""
    f = st / "step5" / "after.json"
    if not f.exists():
        return {"after_snapshot_missing": 1}
    after, before = json.loads(f.read_text()), json.loads((st / "step5" / "before.json").read_text())
    old_before = [n for n in before.get("error_shape_nodes", []) if n[2].rsplit(":", 1)[-1] == "error-response-shape"]
    old_after = [n for n in after.get("error_shape_nodes", []) if n[2].rsplit(":", 1)[-1] == "error-response-shape"]
    reported = None
    try:
        txt = (json.loads((st / "step5" / "agent" / "result.json").read_text()).get("final") or {}).get("result") or ""
        reported = int(bool(json.loads(txt[txt.find("{"): txt.rfind("}") + 1]).get("recorded")))
    except (ValueError, KeyError, TypeError):
        pass
    return {"reversal_target_present": int(bool(old_before)), **({"reviewer_reported_recorded": reported} if reported is not None else {}),
            "old_marked_superseded": int(bool(old_after and old_after[0][3])), "supersedes_edges": len(after["supersedes_edges"]) - len(before["supersedes_edges"]),
            "contradicts_edges": len(after["contradicts_edges"]) - len(before["contradicts_edges"]),
            "pulse_contradiction_pairs_after": after["contradictions"]["data"]["count"] if after["contradictions"].get("ok") else None}


def flatten(prefix: str, obj, into: dict) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(f"{prefix}.{k}" if prefix else k, v, into)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        into.setdefault(prefix, []).append(obj)


def aggregate(runs: list[dict]) -> dict:
    cols: dict[str, list[float]] = {}
    for r in runs:
        flat: dict[str, list] = {}
        for key in ("recorder", "recaller", "reviewer", "pulse_retrieval_arm", "agent_runs"):
            if key in r:
                flatten(key, r[key], flat)
        for k, v in flat.items():
            cols.setdefault(k, []).extend(v)
    return {k: runstats.spread(v) for k, v in sorted(cols.items())}


def recompute(work: Path) -> int:
    """Rebuild summary.json from the run folders that are already saved, with the current collect(). Calls no model and starts nothing."""
    old = json.loads((work / "summary.json").read_text())
    agents = set(old["agents_with_a_model"])
    ports = {r["run"]: {"api_port": r["api_port"], "mcp_port": r["mcp_port"]} for r in old["per_run"]}
    runs = [collect(r["run"], work / f"run-{r['run']}", agents, ports[r["run"]]) for r in old["per_run"]]
    summary = dict(old, spread=aggregate(runs), per_run=runs, recomputed_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                   recomputed_because="summary.json was rebuilt from the saved run folders after collect() changed (scripted sessions left out of agent_runs, reviewer self-report added)")
    (work / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"recomputed {work / 'summary.json'} from {len(runs)} saved runs")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recompute", metavar="DIR", help="rebuild DIR/summary.json from its saved run-K folders; runs nothing")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--agents", nargs="*", default=None, choices=["recorder", "recaller", "reviewer"], help="sessions that call the model (default: recorder recaller)")
    ap.add_argument("--scripted", action="store_true", help="no model at all (same as --agents with no names)")
    ap.add_argument("--splits", nargs="+", default=["dev", "held_out"], choices=["dev", "held_out", "model_authored", "legacy"])
    ap.add_argument("--out", default=str(ROOT / ".work" / "n-runs"))
    a = ap.parse_args()
    if a.recompute:
        return recompute(Path(a.recompute))
    if a.scripted and a.agents:
        ap.error("use --scripted or --agents, not both")
    if not (ROOT / ".venv" / "bin" / "python").exists():
        print("No .venv found. Run step 1 first: python run_demo.py --steps 1", file=sys.stderr)
        return 2
    agents = set() if a.scripted else set(a.agents if a.agents is not None else ["recorder", "recaller"])
    work = Path(a.out)
    work.mkdir(parents=True, exist_ok=True)
    runs = []
    for i in range(1, a.runs + 1):
        print(f"run {i} of {a.runs} ...", flush=True)
        runs.append(one_run(i, work, agents, a.splits))
        print(f"  recorder {runs[-1]['recorder']}", flush=True)
    summary = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "runs": a.runs, "scripted": not agents, "agents_with_a_model": sorted(agents),
        "model": json.loads((ROOT / "config" / "agent.json").read_text())["model"] if agents else None,
        "note": "Each run used a fresh Pulse data home and its own ports. n is the number of values the statistic is over.",
        "spread": aggregate(runs), "per_run": runs,
    }
    (work / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"wrote {work / 'summary.json'}")
    for k, v in summary["spread"].items():
        if k.startswith(("recorder.", "pulse_retrieval_arm.held_out.correct", "pulse_retrieval_arm.dev.correct", "recaller.agent_choice")):
            print(f"  {k}: mean {v['mean']} min {v['min']} max {v['max']} (n={v['n']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
