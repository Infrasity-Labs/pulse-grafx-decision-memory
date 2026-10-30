"""The LLM arms: the same questions and change proposals, scored by the same code, with and without the graph.

  memory       the read-only Recaller identity and the Pulse graph on the 32-decision board. No code, no notes.
  no-memory    Read, Grep and Glob on app/. No graph, no notes.
  code-notes   Read, Grep and Glob on app/ and a plain text file with the same 32 decisions. No graph.

Every arm gets the same question set (--splits, default dev held_out) and the same two change proposals, which conflict with a
decision whose reason is written only in the graph (and in the notes). Every arm is scored by scripts/score_arms.py, the code that
also scores the lexical baseline and the scripted Pulse retrieval. The model is pinned in config/agent.json.

--runs N repeats every arm N times (default 1). The memory arm reads one board, which it cannot write to, so its repetitions share the board and
differ only in what the model does. The repetitions of one arm are written into one arm file under "runs". Nothing is pooled.
Running it calls Claude Code once per arm and repetition and costs money.

Prerequisites: a board with the corpus. Run step 2 (setup_board.py) and then scripts/build_corpus.py.
Usage: python scripts/run_arms.py [--arms memory no-memory code-notes] [--splits dev held_out] [--runs N] [--append] [--dry-run]
Output: demo-state/arms/llm-<arm>.json (an arm file for score_arms.py) and demo-state/arms/llm-<arm>/run-<k>/ (prompt, transcript, result)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import corpus  # noqa: E402
import runstats  # noqa: E402
import score_arms  # noqa: E402

PROMPTS = ROOT / "docs" / "prompts" / "arms"
ARM_FILE = {"memory": "llm-memory", "no-memory": "llm-no-memory", "code-notes": "llm-code-notes"}


def notes_text() -> str:
    """The 32 decisions as plain text notes, one heading per decision. The same text the graph holds, without the graph."""
    parts = ["# Design decision notes", ""]
    for d in corpus.all_decisions():
        parts += [f"## {d['slug']}", "", corpus.node_text(d), ""]
    return "\n".join(parts)


def question_lines(questions: list[dict]) -> str:
    return "\n".join(f"{q['id']}. {q['text']}" for q in questions)


def task_lines() -> str:
    return "\n".join(f"{t['id']}. {t['proposal']}" for t in corpus.conflict_tasks())


def parse_final(result: dict) -> dict:
    txt = ((result.get("final") or {}).get("result") or "").strip()
    return json.loads(txt[txt.find("{"): txt.rfind("}") + 1])


def to_arm_answers(arm: str, final: dict, node_map: dict) -> tuple[list[dict], list[dict]]:
    """Turn the agent's JSON into score_arms answers. A graph id or a note heading becomes a corpus slug. No-memory answers carry no decision."""
    def slug(x: dict) -> str | None:
        if arm == "memory":
            return node_map.get(x.get("decision_id"))
        if arm == "code-notes":
            return x.get("decision") or x.get("cited")
        return None
    answers = [{"id": a["id"], "decision": slug(a), "abstain": bool(a.get("abstain")), "answer": a.get("answer") or ""} for a in final.get("answers", [])]
    tasks = [{"id": t["id"], "stance": t.get("stance"), "cited": slug(t), "answer": t.get("answer") or ""} for t in final.get("tasks", [])]
    return answers, tasks


def run_arm(arm: str, run: int, questions: list[dict], dry: bool) -> dict | None:
    import stepslib as sl

    out = score_arms.ARMS_DIR / ARM_FILE[arm] / f"run-{run}"
    out.mkdir(parents=True, exist_ok=True)
    values = {"QUESTIONS": question_lines(questions), "TASKS": task_lines()}
    cmd = [sys.executable, str(ROOT / "scripts" / "run_agent.py")]
    if arm == "memory":
        values["BOARD_ID"] = sl.board_info()["board_id"]
        role, extra = "recaller", ["--tools", ""]
    else:
        notes = ROOT / ".work" / "notes" / "decision-notes.md"
        notes.parent.mkdir(parents=True, exist_ok=True)
        notes.write_text(notes_text())
        role, extra = "answerer", ["--add-dir", "app"]
        if arm == "code-notes":
            values["NOTES_PATH"] = str(Path("..") / ".." / ".work" / "notes" / "decision-notes.md")
            extra += ["--add-dir", ".work/notes"]
    prompt_file = out / "prompt.rendered.md"
    sl.render_prompt(PROMPTS / f"{arm}.md", prompt_file, **values)
    cmd += [role, str(prompt_file), str(out), *extra]
    if dry:
        print(f"[{arm} run {run}] would run: {' '.join(cmd)}")
        return None
    rc = subprocess.call(cmd)
    result = json.loads((out / "result.json").read_text())
    node_map = {}
    if arm == "memory":
        from step04_recaller import build_node_map

        node_map = build_node_map(sl.board_info()["board_id"])
    try:
        answers, tasks = to_arm_answers(arm, parse_final(result), node_map)
        problem = None
    except (ValueError, KeyError, TypeError) as exc:
        # an unparsable final answer is recorded as no answers: every question then counts as missing, never as correct
        answers, tasks, problem = [], [], f"final answer not parsable: {type(exc).__name__}: {exc}"
    run_rec = {"run": run, "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "exit_code": rc, "problem": problem,
               "model_requested": result.get("model_requested"), "model": result.get("model"), "run_stats": runstats.summarise(result),
               "questions_asked": [q["id"] for q in questions], "answers": answers, "tasks": tasks}
    print(f"{arm} run {run}: exit={rc}" + (f" PROBLEM {problem}" if problem else ""))
    print(score_arms.format_scores(score_arms.score(questions, answers)))
    return run_rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="+", default=list(ARM_FILE), choices=list(ARM_FILE))
    ap.add_argument("--splits", nargs="+", default=["dev", "held_out"], choices=["dev", "held_out", "model_authored", "legacy"])
    ap.add_argument("--runs", type=int, default=1, help="repetitions of every arm")
    ap.add_argument("--append", action="store_true", help="add the new runs to the runs already in each arm file (numbered on) instead of replacing them")
    ap.add_argument("--dry-run", action="store_true", help="render the prompts and print the commands, call no model")
    a = ap.parse_args()
    questions = [q for sp in a.splits for q in corpus.questions(sp)]
    rc = 0
    for arm in a.arms:
        f = score_arms.ARMS_DIR / f"{ARM_FILE[arm]}.json"
        runs = json.loads(f.read_text())["runs"] if a.append and f.exists() else []
        first = len(runs) + 1
        for k in range(first, first + a.runs):
            rec = run_arm(arm, k, questions, a.dry_run)
            if rec:
                runs.append(rec)
                rc = max(rc, rec["exit_code"])
                f.write_text(json.dumps(
                    {"arm": ARM_FILE[arm], "kind": "llm", "model_requested": runs[0]["model_requested"], "model": runs[0]["model"], "runs": runs}, indent=2) + "\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
