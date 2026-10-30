"""Scripted replacements for the three agent steps. Fixed tool calls, no LLM, no network beyond the local Pulse.

  scripted recorder     step 3: the same 12 decisions and 3 depends_on edges the recorded Recorder committed, in one consolidation
  scripted code extras  step 3b: the 10 code-derived decisions of corpus/decisions.json, in a second consolidation
  scripted recaller     step 4: the ten legacy questions, three tools each, then the write probe of the read-only identity
  scripted reviewer     step 5: the supersede override and the explicit contradicts edge, with the reads around them

Each run writes a transcript.jsonl and result.json in the shape of a real agent run (see scripted_agent.py), so the
scorers and tests run on it unchanged. These runs show what Pulse and Grafx do with a fixed call sequence. They do not
show what an agent would choose to do.

Usage: python scripts/scripted_steps.py {recorder|code-extras|recaller|reviewer} [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import corpus  # noqa: E402
import stepslib as sl  # noqa: E402
from scripted_agent import ScriptedSession  # noqa: E402


def _candidate(spec_id: str, d: dict) -> dict:
    src = d["source"]
    return {"candidate_id": d["slug"], "node_type": "Decision", "title": d["title"], "content": d["content"], "context": d["group"],
            "justification": "not stated in code", "source_artifact_ref": f"final_report:{spec_id}:decision:{d['slug']}",
            "source_confidence": 0.9, "source_span_quote": src["quote"]}


def _consolidate(s: ScriptedSession, board_id: str, spec_id: str, decisions: list[dict], raw: str, summary: str, edges: list[tuple[str, str]] = ()) -> dict:
    begin = s.call("okto_pulse_kg_begin_consolidation", {"board_id": board_id, "artifact_type": "spec", "artifact_id": spec_id, "raw_content": raw, "deterministic_candidates": []})
    if not begin["ok"]:
        return {"session_id": None, "commit_status": "begin_failed", "nodes_added": 0, "edges_added": 0, "problems": [json.dumps(begin["envelope"])[:300]]}
    sid = begin["data"]["session_id"]
    problems, similar_hits = [], 0
    for d in decisions:
        add = s.call("okto_pulse_kg_add_node_candidate", {"session_id": sid, "candidate": _candidate(spec_id, d)})
        if not add["ok"]:
            problems.append(f"add {d['slug']}: {json.dumps(add['envelope'])[:200]}")
            continue
        sim = s.call("okto_pulse_kg_get_similar_nodes", {"session_id": sid, "candidate_id": d["slug"], "top_k": 5, "min_similarity": 0.85})
        similar_hits += len((sim["data"] or {}).get("similar") or []) if sim["ok"] else 0
    for a, b in edges:
        e = s.call("okto_pulse_kg_add_edge_candidate", {"session_id": sid, "candidate": {"candidate_id": f"edge-{a}-{b}", "edge_type": "depends_on",
                   "from_candidate_id": a, "to_candidate_id": b, "confidence": 0.9}})
        if not e["ok"]:
            problems.append(f"edge {a}->{b}: {json.dumps(e['envelope'])[:200]}")
    s.call("okto_pulse_kg_propose_reconciliation", {"session_id": sid})
    commit = s.call("okto_pulse_kg_commit_consolidation", {"session_id": sid, "summary_text": summary})
    if not commit["ok"]:
        s.call("okto_pulse_kg_abort_consolidation", {"session_id": sid, "reason": "commit refused"})
        problems.append(f"commit: {json.dumps(commit['envelope'])[:300]}")
    data = commit["data"] if commit["ok"] and isinstance(commit["data"], dict) else {}
    return {"session_id": sid, "commit_status": data.get("status", "failed"), "nodes_added": data.get("nodes_added", 0), "edges_added": data.get("edges_added", 0),
            "similar_node_matches_seen": similar_hits, "problems": problems}


def recorded_edges() -> list[tuple[str, str]]:
    """The three depends_on edges of the recorded run, as (from slug, to slug)."""
    titles = {d["title"]: d["slug"] for d in corpus.recorded_decisions()}
    rows = json.loads((ROOT / "demo-state" / "step3" / "decision-edges.json").read_text())
    return [(titles[a], titles[b]) for _t, a, b in rows]


def recorder(info: dict, out: Path) -> dict:
    decisions = corpus.recorded_decisions()
    s = ScriptedSession("RECORDER", out)
    final = _consolidate(s, info["board_id"], info["anchor_spec_id"], decisions,
                         "twelve decisions: " + ", ".join(d["slug"] for d in decisions), "Twelve design decisions recorded by the scripted recorder.", recorded_edges())
    s.call("okto_pulse_kg_query_cypher", {"board_id": info["board_id"], "cypher": "MATCH (n:Decision) WHERE n.source_artifact_ref STARTS WITH $p RETURN n.id, n.title, n.source_artifact_ref",
                                          "params": {"p": f"final_report:{info['anchor_spec_id']}:decision:"}})
    final["decisions"] = [{"slug": d["slug"], "title": d["title"], "file": d["source"]["path"], "line": d["source"]["line"], "quote": d["source"]["quote"]} for d in decisions]
    return s.finish(final)


def code_extras(info: dict, out: Path) -> dict:
    decisions = [d for d in corpus.extra_decisions() if d["origin"] == "code-derived"]
    s = ScriptedSession("RECORDER", out)
    final = _consolidate(s, info["board_id"], info["anchor_spec_id"], decisions,
                         "ten more code-derived decisions: " + ", ".join(d["slug"] for d in decisions), "Ten code-derived decisions recorded by the scripted recorder.")
    final["decisions"] = [{"slug": d["slug"], "title": d["title"], "file": d["source"]["path"], "line": d["source"]["line"], "quote": d["source"]["quote"]} for d in decisions]
    return s.finish(final)


def recaller(info: dict, out: Path, questions: list[dict] | None = None) -> dict:
    qs = questions or corpus.questions("legacy")
    s = ScriptedSession("RECALLER", out)
    board = info["board_id"]
    answers = []
    for q in qs:
        sim = s.call("okto_pulse_kg_find_similar_decisions", {"board_id": board, "topic": q["text"], "top_k": 5})
        s.call("okto_pulse_kg_query_natural", {"board_id": board, "nl_query": q["text"], "limit": 5})
        s.call("okto_pulse_kg_get_decision_history", {"board_id": board, "topic": q["text"], "max_rows": 5})
        items = (sim["data"] or {}).get("decisions", []) if sim["ok"] else []
        top = items[0] if items else None
        num = int(q["id"][1:]) if q["id"].startswith("l") else q["id"]
        answers.append({"q": num, "id": q["id"], "tool_used": "okto_pulse_kg_find_similar_decisions", "decision_id": top["id"] if top else None,
                        "decision_title": top["title"] if top else None, "answer": top["title"] if top else "", "abstain": top is None})
    probe = s.call("okto_pulse_kg_begin_consolidation", {"board_id": board, "artifact_type": "spec", "artifact_id": "probe", "raw_content": "probe", "deterministic_candidates": []})
    refusal = json.dumps(probe["envelope"], default=str) if not probe["ok"] else "NOT REFUSED"
    return s.finish({"answers": answers, "write_probe": refusal})


def reviewer(info: dict, out: Path, note: dict) -> dict:
    board, spec = info["board_id"], info["anchor_spec_id"]
    old_ref = f"final_report:{spec}:decision:{note['reverses_slug']}"
    new_ref = f"final_report:{spec}:decision:{note['new_slug']}"
    s = ScriptedSession("REVIEWER", out)

    def cyc(ref: str):
        r = s.call("okto_pulse_kg_query_cypher", {"board_id": board, "cypher": f"MATCH (n:Decision) WHERE n.source_artifact_ref = '{ref}' RETURN n.id AS id, n.title AS title"})
        return r["data"]["rows"][0][0] if r["ok"] and r["data"]["rows"] else None

    def pairs() -> int:
        r = s.call("okto_pulse_kg_find_contradictions", {"board_id": board})
        return r["data"]["count"] if r["ok"] else -1

    old_id = cyc(old_ref)
    before = pairs()
    if not (note.get("reason") or "").strip():  # the failing path: no reason, so nothing is written
        return s.finish({"recorded": False, "reason_for_decision": "the note gives no reason", "old_decision_id": old_id, "new_decision_id": None,
                         "what_i_did": [], "contradiction_pairs_before": before, "problems": ["The Maintainer note has an empty reason. Nothing was recorded."]})
    s.call("okto_pulse_kg_get_supersedence_chain", {"board_id": board, "decision_id": old_id})
    begin = s.call("okto_pulse_kg_begin_consolidation", {"board_id": board, "artifact_type": "spec", "artifact_id": spec,
                   "raw_content": f"Maintainer reversal: {note['old_choice']} -> {note['new_choice']}", "deterministic_candidates": []})
    sid = begin["data"]["session_id"]
    s.call("okto_pulse_kg_add_node_candidate", {"session_id": sid, "candidate": {
        "candidate_id": note["new_slug"], "node_type": "Decision", "title": note["new_title"],
        "content": f"{note['new_choice']}\n{note['reason']}\nSource: maintainer-reversal.json", "context": "error response shape",
        "justification": note["reason"], "source_artifact_ref": new_ref, "source_confidence": 0.9}})
    s.call("okto_pulse_kg_get_similar_nodes", {"session_id": sid, "candidate_id": note["new_slug"], "top_k": 5, "min_similarity": 0.3})
    s.call("okto_pulse_kg_propose_reconciliation", {"session_id": sid})
    commit = s.call("okto_pulse_kg_commit_consolidation", {"session_id": sid, "summary_text": "Maintainer reversal recorded as superseding the old decision.",
                    "agent_overrides": {note["new_slug"]: {"candidate_id": note["new_slug"], "operation": "SUPERSEDE", "target_node_id": old_id, "confidence": 0.9, "reason": "Maintainer reversal"}}})
    after_supersede = pairs()
    new_id = cyc(new_ref)
    flag = s.call("okto_pulse_kg_begin_consolidation", {"board_id": board, "artifact_type": "spec", "artifact_id": spec, "raw_content": "flag contradiction", "deterministic_candidates": []})
    fid = flag["data"]["session_id"]
    s.call("okto_pulse_kg_add_edge_candidate", {"session_id": fid, "candidate": {"candidate_id": "flag-contradiction", "edge_type": "contradicts",
           "from_candidate_id": f"kg:{new_id}", "to_candidate_id": f"kg:{old_id}", "confidence": 0.9}})
    s.call("okto_pulse_kg_commit_consolidation", {"session_id": fid, "summary_text": "Flag the new decision as contradicting the superseded one."})
    after_flag = pairs()
    new_chain = s.call("okto_pulse_kg_get_supersedence_chain", {"board_id": board, "decision_id": new_id})
    old_chain = s.call("okto_pulse_kg_get_supersedence_chain", {"board_id": board, "decision_id": old_id})
    s.call("okto_pulse_kg_get_decision_history", {"board_id": board, "topic": "error response shape"})
    s.call("okto_pulse_kg_get_decision_history", {"board_id": board, "topic": "error response shape", "use_semantic": False, "min_confidence": 0})
    return s.finish({"old_decision_id": old_id, "new_decision_id": new_id, "contradiction_pairs_before": before, "contradiction_pairs_after_supersede": after_supersede,
                     "contradiction_pairs_after_flag": after_flag, "chain_from_new_depth": (new_chain["data"] or {}).get("depth"),
                     "chain_from_old_depth": (old_chain["data"] or {}).get("depth"), "commit_status": (commit["data"] or {}).get("status"), "problems": []})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["recorder", "code-extras", "recaller", "reviewer"])
    ap.add_argument("--out")
    a = ap.parse_args()
    info = sl.board_info()
    steps = {"recorder": ("step3", recorder), "code-extras": ("step3b", code_extras), "recaller": ("step4", recaller)}
    if a.which == "reviewer":
        note = sl.load_json(sl.STATE / "step5" / "maintainer-reversal.json")
        out = Path(a.out) if a.out else sl.STATE / "step5" / "agent"
        res = reviewer(info, out, note)
    else:
        step, fn = steps[a.which]
        out = Path(a.out) if a.out else sl.STATE / step / "agent"
        res = fn(info, out)
    print(f"{a.which}: scripted, tool_calls={res['tool_call_count']} seconds={res['seconds']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
