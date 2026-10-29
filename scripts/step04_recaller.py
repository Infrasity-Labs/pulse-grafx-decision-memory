"""Step 4: run the Recaller (fresh session, read-only identity) on ten fixed questions and score it.

Scoring uses the raw tool results in the transcript, not the agent's own report:
  - per tool: is the top-ranked decision the expected one (by slug in source_artifact_ref)?
  - agent choice: is the decision the Recaller finally picked the expected one?
Output in demo-state/step4/: prompt.rendered.md, agent/, recall-results.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import stepslib as sl  # noqa: E402
from questions import QUESTIONS  # noqa: E402

OUT = sl.STATE / "step4"
TOOLS = {
    "mcp__pulse__okto_pulse_kg_find_similar_decisions": ("similar", lambda d: d.get("decisions", [])),
    "mcp__pulse__okto_pulse_kg_query_natural": ("natural", lambda d: d.get("nodes", [])),
    "mcp__pulse__okto_pulse_kg_get_decision_history": ("history", lambda d: d.get("decisions", [])),
}


def slug_of(item: dict) -> str | None:
    ref = item.get("source_artifact_ref") or ""
    return ref.rsplit(":", 1)[-1] if ":decision:" in ref else None


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


def score(transcript: Path) -> dict:
    calls, final = parse_transcript(transcript)
    per_q = []
    for qn, text, expected in QUESTIONS:
        row = {"q": qn, "question": text, "expected_slug": expected, "tools": {}}
        for c in calls:
            short = TOOLS.get("mcp__pulse__" + c["name"].split("__")[-1]) if c["name"].startswith("mcp__pulse__") else None
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
                "top_slug": slug_of(top) if top else None,
                "top_similarity": (top.get("similarity") if top else None),
                "results_returned": len(items),
                "top_is_expected": bool(top) and slug_of(top) == expected,
                "expected_in_results": any(slug_of(i) == expected for i in items),
                "outcome": env.get("outcome") if isinstance(env, dict) else None,
            }
        per_q.append(row)
    answers = {}
    try:
        txt = (final or "").strip()
        txt = txt[txt.find("{"): txt.rfind("}") + 1]
        agent = json.loads(txt)
        answers = {a["q"]: a for a in agent.get("answers", [])}
        write_probe = agent.get("write_probe")
    except (ValueError, KeyError, TypeError):
        write_probe = None
    # map agent-chosen decision id to a slug using any tool result that mentioned it
    id_to_slug = {}
    for c in calls:
        env = c["result"] or {}
        data = env.get("data") if isinstance(env, dict) and "data" in env else env
        if isinstance(data, dict):
            for key in ("decisions", "nodes"):
                for it in data.get(key, []) or []:
                    iid = it.get("id") or it.get("node_id")
                    if iid and slug_of(it):
                        id_to_slug[iid] = slug_of(it)
    for row in per_q:
        a = answers.get(row["q"], {})
        row["agent_choice"] = {
            "tool_used": a.get("tool_used"), "decision_id": a.get("decision_id"), "decision_title": a.get("decision_title"),
            "slug": id_to_slug.get(a.get("decision_id")), "answer": a.get("answer"),
        }
        row["agent_choice"]["correct"] = row["agent_choice"]["slug"] == row["expected_slug"]
    summary = {
        "questions": len(per_q),
        "agent_choice_correct": sum(r["agent_choice"]["correct"] for r in per_q),
        **{f"{t}_top1_correct": sum(bool(r["tools"].get(t, {}).get("top_is_expected")) for r in per_q) for t in ("similar", "natural", "history")},
        **{f"{t}_expected_in_results": sum(bool(r["tools"].get(t, {}).get("expected_in_results")) for r in per_q) for t in ("similar", "natural", "history")},
        "write_probe": write_probe,
        "tool_call_names": sorted({c["name"] for c in calls}),
    }
    return {"summary": summary, "per_question": per_q}


def main() -> int:
    info = sl.board_info()
    with sl.StepTimer("step4"):
        qtext = "\n".join(f"{n}. {t}" for n, t, _ in QUESTIONS)
        prompt_file = OUT / "prompt.rendered.md"
        sl.render_prompt(ROOT / "docs/prompts/step4-recaller.md", prompt_file, BOARD_ID=info["board_id"], QUESTIONS=qtext)
        rc = subprocess.call([sys.executable, str(ROOT / "scripts/run_agent.py"), "recaller", str(prompt_file),
                              str(OUT / "agent"), "--tools", ""])
        result = score(OUT / "agent" / "transcript.jsonl")
        sl.save_json(OUT / "recall-results.json", result)
    print(json.dumps(result["summary"], indent=1))
    return rc


if __name__ == "__main__":
    sys.exit(main())
