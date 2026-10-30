"""Re-score the STORED outputs with a human-reviewed key (v2) and compare with the original key (v1). Calls no model, no Pulse, no network.

What a v2 key is: corpus/validation/README.md. The reviewer writes it, nobody else. This script never creates one.
  --questions-key FILE   {"version": 2, "reviewer": ..., "review_date": ..., "questions": [{"id": "d1", "kind": "answerable|unanswerable",
                         "accepted_slugs": ["jwt-algorithm", "token-expiry"], "answer_keywords": [...]}, ...],
                         "conflict_tasks": [{"id": "t1", "accepted_slugs": [...]}, ...]}
                         Every field except id is optional. A question that is not listed keeps its v1 key. accepted_slugs are the decision ids
                         that count as right, in addition to the v1 expected slug (a reviewer who rejects the v1 slug removes it with "expected_slug").
                         kind "unanswerable" makes abstaining the right answer; kind "answerable" needs an expected_slug or accepted_slugs.
  --reference-key FILE   {"version": 2, "reviewer": ..., "entries": [{"id", "files", "lines", "keywords"}, ...]}, the same entry shape as
                         corpus/reference_decisions.json. It replaces the reference list for the Recorder recall.

Stored outputs it re-scores (all under --state, default demo-state):
  arms/*.json                          every arm file, every run (answers record the named decision slug and the abstention)
  llm-runs/*/<study>/run-N/step4/recall-results.json   the Recaller of a run (per_question.agent_choice records slug, answer, abstained)
  llm-runs/*/<study>/run-N/arms/pulse-retrieval.json   the scripted retrieval arm of a run
  llm-runs/*/<study>/run-N/step3/decisions-from-graph.json   the nodes the Recorder wrote, for the recall against the reference list
  step3/decisions-from-graph.json      the first recorded Recorder run
It cannot change: the Reviewer outcomes (edges and superseded state do not depend on a key), costs and tokens, and any answer to a question
whose wording or evidence the reviewer changed (that needs a new model run). Whether a stored answer used enough evidence is not recorded.

Usage: python scripts/rescore_with_key.py --questions-key K.json [--reference-key R.json] [--state demo-state] [--out-json F] [--out-md F]
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import corpus  # noqa: E402
import score_arms  # noqa: E402

DEFAULT_OUT = ROOT / "corpus" / "validation" / "rescore"
TOTAL_FIELDS = ("answerable", "correct", "wrong", "missed_by_abstaining", "unanswerable", "correct_abstentions", "fabricated",
                "graph_only_total", "graph_only_correct", "near_duplicate_total", "near_duplicate_correct")
HEADLINE = ("correct", "answerable", "correct_abstentions", "unanswerable", "fabricated", "wrong", "missed_by_abstaining")


def load_key(path: Path | None, what: str) -> dict | None:
    if path is None:
        return None
    key = json.loads(Path(path).read_text())
    if key.get("version") != 2:
        raise SystemExit(f"{path}: a {what} key must have \"version\": 2 (v1 is the original corpus and is never edited)")
    return key


def apply_questions_key(questions: list[dict], tasks: list[dict], key: dict | None) -> tuple[list[dict], list[dict], dict]:
    """Copies of the questions and conflict tasks with the reviewed key applied, and a report of what changed."""
    qs, ts = copy.deepcopy(questions), copy.deepcopy(tasks)
    report = {"questions_changed": [], "tasks_changed": [], "unknown_ids": []}
    if not key:
        return qs, ts, report
    for kind, items, listing in (("questions", qs, "questions_changed"), ("conflict_tasks", ts, "tasks_changed")):
        by_id = {x["id"]: x for x in items}
        for e in key.get(kind, []):
            q = by_id.get(e["id"])
            if q is None:
                report["unknown_ids"].append(e["id"])
                continue
            def view(x):
                return {k: (x.get(k) or None) for k in ("kind", "expected_slug", "accepted_slugs", "answer_keywords", "reason_keywords")}
            before = view(q)
            if "expected_slug" in e:
                q["expected_slug"] = e["expected_slug"]
            if "accepted_slugs" in e:
                q["accepted_slugs"] = list(e["accepted_slugs"])
            if kind == "questions":
                if "kind" in e:
                    if e["kind"] not in ("answerable", "unanswerable"):
                        raise SystemExit(f"{e['id']}: kind must be answerable or unanswerable")
                    q["kind"] = e["kind"]
                if "answer_keywords" in e:
                    q["answer_keywords"] = list(e["answer_keywords"])
                if q["kind"] == "unanswerable":
                    q["expected_slug"], q["accepted_slugs"] = None, []
                elif not (q.get("expected_slug") or q.get("accepted_slugs")):
                    raise SystemExit(f"{e['id']}: an answerable question needs expected_slug or accepted_slugs")
                elif not q.get("expected_slug"):
                    q["expected_slug"] = q["accepted_slugs"][0]
            elif "reason_keywords" in e:
                q["reason_keywords"] = list(e["reason_keywords"])
            if before != view(q):
                report[listing].append(e["id"])
    return qs, ts, report


def totals(scores: dict) -> dict:
    """Sums over splits, plus the per split headline numbers."""
    out = {f: sum(s[f] for s in scores.values()) for f in TOTAL_FIELDS}
    out["by_split"] = {sp: {f: s[f] for f in HEADLINE} for sp, s in scores.items()}
    return out


def _both(qs1, qs2, ts1, ts2, answers: list[dict], tasks: list[dict] | None = None) -> dict:
    res = {"v1": totals(score_arms.score(qs1, answers)), "v2": totals(score_arms.score(qs2, answers))}
    if tasks is not None:
        res["tasks_v1"], res["tasks_v2"] = score_arms.score_tasks(ts1, tasks), score_arms.score_tasks(ts2, tasks)
    return res


def _only_asked(qs: list[dict], ids) -> list[dict]:
    ids = set(ids)
    return [q for q in qs if q["id"] in ids]


def recall_answers(per_question: list[dict]) -> list[dict]:
    """The arm-style answers behind a stored step4 result: what step04_recaller.score() put in its scores_by_split."""
    out = []
    for row in per_question:
        a = row.get("agent_choice") or {}
        if a.get("answer") or a.get("slug") or a.get("abstained") or a.get("decision_id"):
            out.append({"id": row["id"], "decision": a.get("slug"), "abstain": bool(a.get("abstained")), "answer": a.get("answer") or ""})
    return out


def recorder_recall(rows: list[dict], entries: list[dict]) -> dict:
    taken: set[str] = set()
    matched: dict[str, str] = {}
    for r in rows:
        ref = corpus.match_reference(r.get("title") or "", r.get("content") or "", taken, entries)
        if ref:
            taken.add(ref)
            matched[ref] = r.get("slug")
    return {"nodes": len(rows), "reference_entries": len(entries), "reference_covered": len(matched), "covered": sorted(matched),
            "not_covered": [e["id"] for e in entries if e["id"] not in matched]}


def study_dirs(state: Path) -> list[Path]:
    """Every folder of llm-runs that holds run-N folders or step folders of one run."""
    found = []
    base = state / "llm-runs"
    for d in sorted(base.glob("*/*")) if base.exists() else []:
        if d.is_dir() and (any(d.glob("run-*")) or (d / "step3").exists()):
            found.append(d)
    return found


def rescore(state: Path, qkey: dict | None, rkey: dict | None) -> dict:
    qs1 = corpus.questions()
    ts1 = corpus.conflict_tasks()
    qs2, ts2, changed = apply_questions_key(qs1, ts1, qkey)
    e1 = corpus.reference_entries()
    e2 = rkey["entries"] if rkey else e1
    sources: list[dict] = []

    def add(group: str, name: str, **kw):
        sources.append({"group": group, "source": name, **kw})

    arms_dir = state / "arms"
    for f in sorted(arms_dir.glob("*.json")) if arms_dir.exists() else []:
        arm = json.loads(f.read_text())
        if "answers" not in arm and "runs" not in arm:
            continue  # not an answering arm (question-overlap.json is an analysis of the questions)
        runs = arm.get("runs") or [arm]
        for i, r in enumerate(runs, 1):
            ids = r.get("questions_asked") or [q["id"] for q in qs1]
            add(f"arm:{arm.get('arm', f.stem)}", f"{f.relative_to(state)}" + (f" run {r.get('run', i)}" if len(runs) > 1 else ""),
                **_both(_only_asked(qs1, ids), _only_asked(qs2, ids), ts1, ts2, r.get("answers", []), r.get("tasks", [])))
    for d in study_dirs(state):
        runs = sorted(d.glob("run-*")) or [d]
        label = f"llm-runs/{d.parent.name}/{d.name}"
        for run in runs:
            tag = f"{label}/{run.name}" if run != d else label
            rec = run / "step4" / "recall-results.json"
            if rec.exists():
                pq = json.loads(rec.read_text())["per_question"]
                ids = [r["id"] for r in pq]
                res = _both(_only_asked(qs1, ids), _only_asked(qs2, ids), ts1, ts2, recall_answers(pq))
                stored = json.loads(rec.read_text())["summary"].get("scores_by_split")
                res["v1_matches_stored_scores_by_split"] = stored == score_arms.score(_only_asked(qs1, ids), recall_answers(pq)) if stored else None
                add(f"recaller:{d.name}", tag, **res)
            pr = run / "arms" / "pulse-retrieval.json"
            if pr.exists():
                add(f"pulse-retrieval:{d.name}", tag, **_both(qs1, qs2, ts1, ts2, json.loads(pr.read_text()).get("answers", [])))
            dec = run / "step3" / "decisions-from-graph.json"
            if dec.exists():
                rows = json.loads(dec.read_text())
                add(f"recorder:{d.name}", tag, recorder_v1=recorder_recall(rows, e1), recorder_v2=recorder_recall(rows, e2))
    first = state / "step3" / "decisions-from-graph.json"
    if first.exists():
        rows = json.loads(first.read_text())
        add("recorder:first-run", "step3/decisions-from-graph.json", recorder_v1=recorder_recall(rows, e1), recorder_v2=recorder_recall(rows, e2))
    return {"questions_key": {k: qkey.get(k) for k in ("version", "reviewer", "review_date")} if qkey else None,
            "reference_key": {k: rkey.get(k) for k in ("version", "reviewer", "review_date")} if rkey else None,
            "changed": changed, "reference_entries_v1": len(e1), "reference_entries_v2": len(e2), "sources": sources, "groups": summarise(sources)}


def summarise(sources: list[dict]) -> list[dict]:
    """Per group (an arm, or a study's Recaller or Recorder): the headline metric of every run under v1 and v2, mean, min and max."""
    groups: dict[str, list[dict]] = {}
    for s in sources:
        groups.setdefault(s["group"], []).append(s)
    out = []
    for g, items in groups.items():
        row: dict = {"group": g, "runs": len(items)}
        if "v1" in items[0]:
            for f in ("correct", "correct_abstentions", "fabricated"):
                row[f"{f}_v1"] = score_arms.spread_of([i["v1"][f] for i in items])
                row[f"{f}_v2"] = score_arms.spread_of([i["v2"][f] for i in items])
            row["answerable"] = {"v1": items[0]["v1"]["answerable"], "v2": items[0]["v2"]["answerable"]}
            row["unanswerable"] = {"v1": items[0]["v1"]["unanswerable"], "v2": items[0]["v2"]["unanswerable"]}
            if "tasks_v1" in items[0]:
                row["tasks_respected_v1"] = score_arms.spread_of([i["tasks_v1"]["respected"] for i in items])
                row["tasks_respected_v2"] = score_arms.spread_of([i["tasks_v2"]["respected"] for i in items])
        else:
            row["reference_covered_v1"] = score_arms.spread_of([i["recorder_v1"]["reference_covered"] for i in items])
            row["reference_covered_v2"] = score_arms.spread_of([i["recorder_v2"]["reference_covered"] for i in items])
            row["reference_entries"] = {"v1": items[0]["recorder_v1"]["reference_entries"], "v2": items[0]["recorder_v2"]["reference_entries"]}
        out.append(row)
    return out


def _sp(s: dict) -> str:
    return "n/a" if s["n"] == 0 else (f"{s['mean']:g}" if s["min"] == s["max"] else f"{s['mean']:g} ({s['min']}-{s['max']})")


def render_md(res: dict) -> str:
    lines = ["# Re-scoring of stored outputs: key v1 against key v2", "",
             "Generated by scripts/rescore_with_key.py. No model was called. Cells with several runs show mean (min-max) over the runs.", ""]
    for name in ("questions_key", "reference_key"):
        k = res[name]
        lines.append(f"- {name.replace('_', ' ')}: " + (f"version {k['version']}, reviewer {k['reviewer']}, review date {k['review_date']}" if k else "not given (v1 used)"))
    ch = res["changed"]
    lines += [f"- questions whose key differs from v1: {len(ch['questions_changed'])} ({', '.join(ch['questions_changed']) or 'none'})",
              f"- conflict tasks whose key differs from v1: {len(ch['tasks_changed'])} ({', '.join(ch['tasks_changed']) or 'none'})",
              f"- ids in the key that match no question or task: {', '.join(ch['unknown_ids']) or 'none'}",
              f"- reference entries: v1 {res['reference_entries_v1']}, v2 {res['reference_entries_v2']}", "",
              "## Answer metrics", "", "| Group | Runs | Correct v1 | Correct v2 | of answerable (v1/v2) | Correct abstentions v1 | v2 | Fabricated v1 | v2 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for g in res["groups"]:
        if "correct_v1" in g:
            lines.append(f"| {g['group']} | {g['runs']} | {_sp(g['correct_v1'])} | {_sp(g['correct_v2'])} | {g['answerable']['v1']}/{g['answerable']['v2']} | "
                         f"{_sp(g['correct_abstentions_v1'])} | {_sp(g['correct_abstentions_v2'])} | {_sp(g['fabricated_v1'])} | {_sp(g['fabricated_v2'])} |")
    lines += ["", "## Recorder recall against the reference list", "", "| Group | Runs | Covered v1 | Covered v2 | Entries v1/v2 |", "|---|---:|---:|---:|---:|"]
    for g in res["groups"]:
        if "reference_covered_v1" in g:
            lines.append(f"| {g['group']} | {g['runs']} | {_sp(g['reference_covered_v1'])} | {_sp(g['reference_covered_v2'])} | {g['reference_entries']['v1']}/{g['reference_entries']['v2']} |")
    bad = [s["source"] for s in res["sources"] if s.get("v1_matches_stored_scores_by_split") is False]
    lines += ["", f"Check: v1 re-scored from the stored Recaller answers equals the scores stored with them in every run: {'yes' if not bad else 'NO, differs for ' + ', '.join(bad)}.", "",
              "## Not re-scorable from the stored outputs", "",
              "- Reviewer outcomes (edges, superseded state) do not depend on the key and are not re-scored.",
              "- Costs, tokens and run times do not depend on the key.",
              "- A question whose wording, accessible evidence or task the reviewer changed needs a new model run; stored answers answer the old wording.",
              "- Stored answers record the named decision, the abstention and the answer text, not which evidence the agent used, so \"which evidence is sufficient\" cannot be checked.", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--questions-key", type=Path)
    ap.add_argument("--reference-key", type=Path)
    ap.add_argument("--state", type=Path, default=ROOT / "demo-state")
    ap.add_argument("--out-json", type=Path, default=DEFAULT_OUT / "v1-vs-v2.json")
    ap.add_argument("--out-md", type=Path, default=DEFAULT_OUT / "v1-vs-v2.md")
    a = ap.parse_args()
    if not (a.questions_key or a.reference_key):
        print("give --questions-key and/or --reference-key (a v2 key written by the human reviewer; none exists yet)")
        return 2
    res = rescore(a.state, load_key(a.questions_key, "questions"), load_key(a.reference_key, "reference"))
    a.out_json.parent.mkdir(parents=True, exist_ok=True)
    a.out_json.write_text(json.dumps(res, indent=2) + "\n")
    a.out_md.write_text(render_md(res))
    print(f"wrote {a.out_json} and {a.out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
