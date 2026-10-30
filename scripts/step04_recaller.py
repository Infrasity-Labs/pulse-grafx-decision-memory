"""Step 4: run the Recaller (fresh session, read-only identity) on a question set and score it.

Two ways to run it:
  default    the goal-based Recaller prompt (docs/prompts/step4-recaller.md) in a headless Claude Code session. The prompt gives
             the goal and the tools, not a tool order. Questions come from corpus/questions.json: --splits dev held_out by default.
             The committed demo-state/step4 was recorded with the earlier fixed-order prompt in docs/prompts/recorded-run-1/.
  --scripted a scripted client asks the ten legacy questions with the same three tools each. No LLM.

Scoring uses the raw tool results in the transcript and the graph, not the agent's own report:
  - per tool: is the top-ranked decision the expected one? Only for calls whose search text is the question text.
  - agent choice: is the decision the Recaller finally picked the expected one, or did it abstain on an unanswerable question?
  - the same answers go through scripts/score_arms.py, so the numbers per split use the scorer every arm uses
  - tool usage: which tools the agent chose, counted from the transcript
Output in demo-state/step4/: prompt.rendered.md, agent/, recall-results.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import corpus  # noqa: E402
import score_arms  # noqa: E402
import stepslib as sl  # noqa: E402

OUT = sl.STATE / "step4"
TOOLS = {
    "mcp__pulse__okto_pulse_kg_find_similar_decisions": ("similar", lambda d: d.get("decisions", [])),
    "mcp__pulse__okto_pulse_kg_query_natural": ("natural", lambda d: d.get("nodes", [])),
    "mcp__pulse__okto_pulse_kg_get_decision_history": ("history", lambda d: d.get("decisions", [])),
}


def slug_of(item: dict, node_map: dict | None = None) -> str | None:
    """The corpus slug of a decision in a tool result. node_map (graph id to slug, from the graph) wins over the slug in the ref."""
    iid = item.get("id") or item.get("node_id")
    if node_map and iid in node_map:
        return node_map[iid]
    ref = item.get("source_artifact_ref") or ""
    return ref.rsplit(":", 1)[-1] if ":decision:" in ref else None


def build_node_map(board_id: str) -> dict:
    """Graph id of every canonical Decision node mapped to the corpus slug it stands for, read by the Maintainer identity."""
    with sl.Mcp("MAINTAINER") as m:
        rows = sl.cypher(m, board_id, "MATCH (n:Decision) RETURN n.id AS id, n.title AS title, n.content AS content, n.source_artifact_ref AS ref")
    return {r[0]: corpus.slug_for_node(r[1], r[2], r[3]) for r in rows}


def parse_transcript(path: Path) -> tuple[list[dict], str | None]:
    """Return tool calls (name, input, parsed result) in order, and the final result text."""
    calls: dict[str, dict] = {}
    order: list[str] = []
    final = None
    for ln in path.read_text().splitlines():
        ev = json.loads(ln)
        if ev.get("type") == "assistant":
            for b in ev["message"].get("content", []):
                if b.get("type") == "tool_use":
                    calls[b["id"]] = {"name": b["name"], "input": b["input"], "result": None}
                    order.append(b["id"])
        elif ev.get("type") == "user":
            content = ev["message"].get("content")
            for b in content if isinstance(content, list) else []:
                if b.get("type") == "tool_result" and b.get("tool_use_id") in calls:
                    txt = b.get("content")
                    if isinstance(txt, list):
                        txt = "".join(x.get("text", "") for x in txt)
                    try:
                        calls[b["tool_use_id"]]["result"] = json.loads(txt)
                    except (TypeError, json.JSONDecodeError):
                        calls[b["tool_use_id"]]["result"] = {"raw": txt}
        elif ev.get("type") == "result":
            final = ev.get("result")
    return [calls[i] for i in order], final


def on_board_counts(per_q: list[dict], questions: list[dict], node_map: dict | None) -> dict:
    """How many answerable questions have their expected decision on the board at all.

    When the Recorder chose its own topics, the board may hold no decision for a question. The scorer then counts a right-looking answer as wrong,
    and the gap is a recording miss, not a recall miss. Each row gets expected_on_board, and the summary counts the choices that were right where it was."""
    if node_map is None:
        return {}
    present = {s for s in node_map.values() if s}
    answerable = [(r, q) for r, q in zip(per_q, questions) if q["expected_slug"] is not None]
    for r, q in answerable:
        r["expected_on_board"] = q["expected_slug"] in present
    on = [(r, q) for r, q in answerable if r["expected_on_board"]]
    return {"answerable_expected_on_board": len(on), "answerable_expected_missing_from_board": [q["id"] for r, q in answerable if not r["expected_on_board"]],
            "agent_choice_correct_where_expected_on_board": sum(r["agent_choice"]["correct"] for r, _ in on)}


def score(transcript: Path, questions: list[dict] | None = None, node_map: dict | None = None) -> dict:
    questions = questions if questions is not None else corpus.questions("legacy")
    calls, final = parse_transcript(transcript)
    per_q = []
    for q in questions:
        text, expected = q["text"], q["expected_slug"]
        row = {"q": int(q["id"][1:]) if q["id"].startswith("l") else q["id"], "id": q["id"], "split": q["split"], "kind": q["kind"],
               "question": text, "expected_slug": expected, "tools": {}}
        for c in calls:
            short = TOOLS.get(c["name"]) if c["name"].startswith("mcp__pulse__") else None
            if not short:
                continue
            args = c["input"]
            asked = args.get("topic") or args.get("nl_query")
            if asked != text:
                continue
            name, getter = short
            env = c["result"] or {}
            data = env.get("data") if isinstance(env, dict) and "data" in env else env
            items = getter(data) if isinstance(data, dict) else []
            top = items[0] if items else None
            row["tools"][name] = {
                "top_id": top.get("id") or top.get("node_id") if top else None,
                "top_title": top.get("title") if top else None,
                "top_slug": slug_of(top, node_map) if top else None,
                "top_similarity": (top.get("similarity") if top else None),
                "results_returned": len(items),
                "top_is_expected": bool(top) and slug_of(top, node_map) == expected,
                "expected_in_results": any(slug_of(i, node_map) == expected for i in items),
                "outcome": env.get("outcome") if isinstance(env, dict) else None,
            }
        per_q.append(row)
    answers, write_probe = {}, None
    try:
        txt = (final or "").strip()
        txt = txt[txt.find("{"): txt.rfind("}") + 1]
        agent = json.loads(txt)
        answers = {str(a.get("id", a.get("q"))): a for a in agent.get("answers", [])}
        write_probe = agent.get("write_probe")
    except (ValueError, KeyError, TypeError):
        pass
    # map the agent's decision id to a slug: the graph map first, then any tool result that mentioned the id
    id_to_slug = dict(node_map or {})
    for c in calls:
        env = c["result"] or {}
        data = env.get("data") if isinstance(env, dict) and "data" in env else env
        if isinstance(data, dict):
            for key in ("decisions", "nodes"):
                for it in data.get(key, []) or []:
                    iid = it.get("id") or it.get("node_id")
                    if iid and iid not in id_to_slug and slug_of(it):
                        id_to_slug[iid] = slug_of(it)
    arm_answers = []
    for row, q in zip(per_q, questions):
        a = answers.get(row["id"]) or answers.get(str(row["q"])) or {}
        slug = id_to_slug.get(a.get("decision_id"))
        row["agent_choice"] = {
            "tool_used": a.get("tool_used") or a.get("tools_used"), "decision_id": a.get("decision_id"), "decision_title": a.get("decision_title"),
            "slug": slug, "answer": a.get("answer"), "abstained": bool(a.get("abstain")),
        }
        # right means: the expected decision for an answerable question, an abstention for an unanswerable one
        row["agent_choice"]["correct"] = bool(a.get("abstain")) if q["expected_slug"] is None else (slug == q["expected_slug"] and not a.get("abstain"))
        if a:
            arm_answers.append({"id": row["id"], "decision": slug, "abstain": bool(a.get("abstain")), "answer": a.get("answer") or ""})
    usage: dict[str, int] = {}
    for c in calls:
        usage[c["name"]] = usage.get(c["name"], 0) + 1
    summary = {
        "questions": len(per_q),
        "agent_choice_correct": sum(r["agent_choice"]["correct"] for r in per_q),
        **{f"{t}_top1_correct": sum(bool(r["tools"].get(t, {}).get("top_is_expected")) for r in per_q) for t in ("similar", "natural", "history")},
        **{f"{t}_expected_in_results": sum(bool(r["tools"].get(t, {}).get("expected_in_results")) for r in per_q) for t in ("similar", "natural", "history")},
        "write_probe": write_probe,
        **on_board_counts(per_q, questions, node_map),
        "tool_call_names": sorted({c["name"] for c in calls}),
        "tool_usage": dict(sorted(usage.items())),
        "scores_by_split": score_arms.score(questions, arm_answers),
    }
    return {"summary": summary, "per_question": per_q}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scripted", action="store_true", help="ask the legacy questions with a scripted client instead of running an agent")
    ap.add_argument("--splits", nargs="+", choices=["dev", "held_out", "model_authored", "legacy"], help="question splits (default: dev held_out; with --scripted: legacy)")
    a = ap.parse_args()
    splits = a.splits or (["legacy"] if a.scripted else ["dev", "held_out"])
    questions = [q for sp in splits for q in corpus.questions(sp)]
    info = sl.board_info()
    with sl.StepTimer("step4"):
        if a.scripted:
            import scripted_steps

            scripted_steps.recaller(info, OUT / "agent", questions)
            rc = 0
        else:
            qtext = "\n".join(f"{q['id']}. {q['text']}" for q in questions)
            prompt_file = OUT / "prompt.rendered.md"
            sl.render_prompt(ROOT / "docs/prompts/step4-recaller.md", prompt_file, BOARD_ID=info["board_id"], QUESTIONS=qtext)
            rc = subprocess.call([sys.executable, str(ROOT / "scripts/run_agent.py"), "recaller", str(prompt_file),
                                  str(OUT / "agent"), "--tools", ""])
        result = score(OUT / "agent" / "transcript.jsonl", questions, build_node_map(info["board_id"]))
        sl.save_json(OUT / "recall-results.json", result)
    print(json.dumps({k: v for k, v in result["summary"].items() if k != "tool_usage"}, indent=1))
    return rc


if __name__ == "__main__":
    sys.exit(main())
