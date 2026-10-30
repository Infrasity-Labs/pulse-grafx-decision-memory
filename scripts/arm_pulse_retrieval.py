"""Arm: Pulse and Grafx retrieval, asked by a scripted client. No LLM.

For every question the read-only identity calls okto_pulse_kg_find_similar_decisions with the question as the topic and
takes the top-1 decision. A question whose top similarity is below a threshold is an abstention. The threshold is chosen on
the dev split only (score_arms.calibrate_threshold) and applied to the rest, the same rule the lexical baseline uses.
Each conflict task is the proposal text sent through the same search, to see whether the decision it conflicts with is the top hit.
Stance (stop, adapt, proceed) needs an agent, so a retrieval arm records none.

This measures what the graph search returns on the 32-decision board. It does not measure an agent that reads the results.

Usage: python scripts/arm_pulse_retrieval.py [--out FILE]
Output: demo-state/arms/pulse-retrieval.json (an arm file for scripts/score_arms.py)
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import corpus  # noqa: E402
import score_arms  # noqa: E402
import stepslib as sl  # noqa: E402


def pkg(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def top_decision(m: sl.Mcp, board_id: str, text: str, node_map: dict) -> tuple[str | None, float, list[str]]:
    r = m.call("okto_pulse_kg_find_similar_decisions", {"board_id": board_id, "topic": text, "top_k": 5})
    items = (r["data"] or {}).get("decisions", []) if r["ok"] else []
    slugs = [node_map.get(i["id"]) for i in items]
    return (slugs[0] if slugs else None), (items[0]["similarity"] if items else 0.0), [s for s in slugs if s]


def run(board_id: str) -> dict:
    from step04_recaller import build_node_map

    node_map = build_node_map(board_id)
    by_slug = {d["slug"]: d for d in corpus.all_decisions()}
    questions = corpus.questions()
    rows = []
    with sl.Mcp("RECALLER") as m:
        for q in questions:
            top, sim, ranked = top_decision(m, board_id, q["text"], node_map)
            rows.append({"id": q["id"], "top": top, "score": round(sim, 4), "top5": ranked})
        task_rows = []
        for t in corpus.conflict_tasks():
            top, sim, ranked = top_decision(m, board_id, t["proposal"], node_map)
            task_rows.append({"id": t["id"], "top": top, "score": round(sim, 4), "top5": ranked})
    by_id = {r["id"]: r for r in rows}
    threshold = score_arms.calibrate_threshold([(by_id[q["id"]]["score"], by_id[q["id"]]["top"], q["expected_slug"]) for q in questions if q["split"] == "dev"])
    answers = []
    for q in questions:
        r = by_id[q["id"]]
        keep = r["score"] >= threshold and r["top"] is not None
        answers.append({"id": q["id"], "decision": r["top"] if keep else None, "abstain": not keep,
                        "answer": corpus.node_text(by_slug[r["top"]]) if keep else "", "score": r["score"]})
    tasks = [{"id": r["id"], "stance": None, "cited": r["top"], "answer": corpus.node_text(by_slug[r["top"]]) if r["top"] else "", "score": r["score"]} for r in task_rows]
    return {
        "arm": "pulse-retrieval", "kind": "retrieval",
        "description": "Scripted client, no LLM. find_similar_decisions top-1 on the 32-decision board, abstaining below a similarity threshold chosen on dev.",
        "environment": {"platform": f"{platform.system()} {platform.machine()}", "python": platform.python_version(), "okto_pulse": pkg("okto-pulse"),
                        "okto_grafx": pkg("okto-grafx"), "sentence_transformers": pkg("sentence-transformers")},
        "decisions_on_board": sum(1 for v in node_map.values() if v), "abstention_threshold_chosen_on_dev": threshold,
        "answers": answers, "tasks": tasks, "rows": rows, "task_rows": task_rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(score_arms.ARMS_DIR / "pulse-retrieval.json"))
    a = ap.parse_args()
    arm = run(sl.board_info()["board_id"])
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sl.scrub(json.dumps(arm, indent=2)) + "\n")
    print(f"decisions on board {arm['decisions_on_board']}, abstention threshold {arm['abstention_threshold_chosen_on_dev']} (chosen on dev)")
    print(score_arms.format_scores(score_arms.score(corpus.questions(), arm["answers"])))
    ts = score_arms.score_tasks(corpus.conflict_tasks(), arm["tasks"])
    print(f"conflict tasks: the conflicting decision was the top hit for {ts['cited']} of {ts['tasks']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
