"""One scorer for every arm: the lexical baseline, the scripted Pulse retrieval, and the LLM arms.

An arm file (demo-state/arms/<arm>.json) holds
  {"arm": "...", "kind": "baseline|retrieval|llm", "answers": [...], "tasks": [...], ...}
An LLM arm that was run several times holds "runs": [{"run": 1, "answers": [...], "tasks": [...], "run_stats": {...}}, ...] instead. load_arm
scores every run on its own. Nothing is pooled or averaged here: the spread is computed by spread_of for the table.
Each answer: {"id": "d1", "decision": "<slug or null>", "abstain": false, "answer": "text"}
Each task:   {"id": "t1", "stance": "proceed|adapt|stop|null", "cited": "<slug or null>", "answer": "text"}

Rules, the same for every arm:
  answerable question   correct if the arm did not abstain and either its decision equals the expected slug, or (no decision given)
                        one answer keyword of the question appears in the answer text. A graph_only question has the reason
                        keywords of its decision as answer keywords, so only an answer that carries the graph-only reason is correct.
  unanswerable question correct abstention if the arm abstained. Anything else is a fabricated answer.
  conflict task         cited if the cited decision is the expected slug, or a reason keyword appears in the answer text.
                        respected if cited and the stance is adapt or stop. stance_adapt_or_stop counts the stance alone, cited or not.

Usage:
  python scripts/score_arms.py                      score every arm file in demo-state/arms/ and print the side-by-side table
  python scripts/score_arms.py FILE [FILE ...]      score these arm files
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import corpus  # noqa: E402

ARMS_DIR = Path(os.environ.get("DEMO_STATE", ROOT / "demo-state")) / "arms"
LLM_ARMS = ("llm-memory", "llm-no-memory", "llm-code-notes")
ARM_ORDER = ("lexical-tfidf", "pulse-retrieval", *LLM_ARMS)


def calibrate_threshold(triples: list[tuple[float, str, str | None]]) -> float:
    """Pick the abstention threshold that handles most dev questions correctly. triples: (top score, top slug, expected slug or None).

    Candidates are 0 and the midpoints between neighbouring scores. On a tie the lowest threshold wins, so the arm abstains as little as it can."""
    scores = sorted({s for s, _, _ in triples})
    cands = [0.0] + [(a + b) / 2 for a, b in zip(scores, scores[1:])] + [(scores[-1] + 1e-6) if scores else 1.0]

    def handled(t: float) -> int:
        return sum((s >= t and top == exp) if exp else (s < t) for s, top, exp in triples)
    best = max(cands, key=lambda t: (handled(t), -t))
    return round(best, 4)


def _hit(text: str, words: list[str]) -> bool:
    low = (text or "").lower()
    return any(w.lower() in low for w in words)


def accepted_slugs(item: dict) -> set[str]:
    """The decision ids that count as right for a question or task: its expected slug and, if a reviewed key lists them, the accepted alternatives."""
    return {item["expected_slug"], *item.get("accepted_slugs", [])} - {None}


def _answer_correct(q: dict, a: dict) -> bool:
    if a.get("abstain"):
        return False
    if a.get("decision"):
        return a["decision"] in accepted_slugs(q)
    return _hit(a.get("answer", ""), q.get("answer_keywords", []))


def score(questions: list[dict], answers: list[dict]) -> dict:
    """Per split counts. Questions without an answer in the arm are counted as missing, never as correct."""
    by_id = {a["id"]: a for a in answers}
    out: dict = {}
    for split in sorted({q["split"] for q in questions}):
        qs = [q for q in questions if q["split"] == split]
        s = {"questions": len(qs), "answered_by_arm": sum(q["id"] in by_id for q in qs),
             "answerable": 0, "correct": 0, "wrong": 0, "missed_by_abstaining": 0,
             "unanswerable": 0, "correct_abstentions": 0, "fabricated": 0,
             "graph_only_total": 0, "graph_only_correct": 0, "near_duplicate_total": 0, "near_duplicate_correct": 0}
        for q in qs:
            a = by_id.get(q["id"])
            if q["kind"] == "unanswerable":
                s["unanswerable"] += 1
                if a is not None:
                    s["correct_abstentions" if a.get("abstain") else "fabricated"] += 1
                continue
            s["answerable"] += 1
            ok = a is not None and _answer_correct(q, a)
            s["correct"] += ok
            if a is not None and not ok:
                s["missed_by_abstaining" if a.get("abstain") else "wrong"] += 1
            for tag in ("graph_only", "near_duplicate"):
                if tag in q["tags"]:
                    s[f"{tag}_total"] += 1
                    s[f"{tag}_correct"] += ok
        out[split] = s
    return out


def score_tasks(tasks: list[dict], answers: list[dict]) -> dict:
    by_id = {a["id"]: a for a in answers}
    res = {"tasks": len(tasks), "answered_by_arm": sum(t["id"] in by_id for t in tasks), "cited": 0, "respected": 0, "stance_recorded": 0, "stance_adapt_or_stop": 0}
    for t in tasks:
        a = by_id.get(t["id"])
        if a is None:
            continue
        cited = a.get("cited") in accepted_slugs(t) or _hit(a.get("answer", ""), t["reason_keywords"])
        res["cited"] += cited
        if a.get("stance"):
            res["stance_recorded"] += 1
            res["respected"] += bool(cited and a["stance"] in ("adapt", "stop"))
            res["stance_adapt_or_stop"] += a["stance"] in ("adapt", "stop")
    return res


def load_arm(path: Path) -> dict:
    """Score an arm file. arm["run_scores"] has one entry per run (one for a single-run arm). arm["scores"] and arm["task_scores"] exist for a single-run arm only."""
    arm = json.loads(path.read_text())
    runs = arm.get("runs") or [arm]
    questions = corpus.questions()
    arm["run_scores"] = [{"scores": score([q for q in questions if q["id"] in set(r.get("questions_asked") or [q["id"] for q in questions])], r.get("answers", [])),
                          "task_scores": score_tasks(corpus.conflict_tasks(), r.get("tasks", []))} for r in runs]
    if len(runs) == 1:
        arm["scores"], arm["task_scores"] = arm["run_scores"][0]["scores"], arm["run_scores"][0]["task_scores"]
    return arm


def spread_of(values: list[float]) -> dict:
    """n, mean, min and max of one metric over the runs of an arm. n is the number of runs."""
    vs = [v for v in values if v is not None]
    return {"n": len(vs), "mean": round(sum(vs) / len(vs), 2), "min": min(vs), "max": max(vs)} if vs else {"n": 0, "mean": None, "min": None, "max": None}


def load_arms(directory: Path = ARMS_DIR) -> dict[str, dict]:
    arms = {}
    for name in ARM_ORDER:
        f = directory / f"{name}.json"
        if f.exists():
            arms[name] = load_arm(f)
    return arms


def format_scores(scores: dict) -> str:
    lines = []
    for split, s in scores.items():
        lines.append(f"  {split:<9} answerable {s['correct']}/{s['answerable']} correct ({s['wrong']} wrong, {s['missed_by_abstaining']} missed by abstaining); "
                     f"unanswerable {s['correct_abstentions']}/{s['unanswerable']} abstained ({s['fabricated']} fabricated); "
                     f"graph-only {s['graph_only_correct']}/{s['graph_only_total']}; near-duplicate {s['near_duplicate_correct']}/{s['near_duplicate_total']}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    a = ap.parse_args()
    files = [Path(f) for f in a.files] or [ARMS_DIR / f"{n}.json" for n in ARM_ORDER if (ARMS_DIR / f"{n}.json").exists()]
    if not files:
        print("no arm files found")
        return 1
    for f in files:
        arm = load_arm(f)
        for i, rs in enumerate(arm["run_scores"], 1):
            print(f"{arm['arm']} ({arm.get('kind')})" + (f" run {i} of {len(arm['run_scores'])}" if len(arm["run_scores"]) > 1 else ""))
            print(format_scores(rs["scores"]))
            ts = rs["task_scores"]
            print(f"  conflict tasks: cited {ts['cited']}/{ts['tasks']}, respected {ts['respected']}/{ts['stance_recorded']} with a stance")
    return 0


if __name__ == "__main__":
    sys.exit(main())
