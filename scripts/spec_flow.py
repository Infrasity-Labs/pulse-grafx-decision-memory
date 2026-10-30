"""Step 3b: record the graph-only decisions the way a team does, through the Pulse spec flow. No LLM.

The 10 graph-only decisions of corpus/decisions.json carry a reason that exists nowhere except in the graph. They are
written as spec decisions with okto_pulse_add_decision (rationale, alternatives, a verification plan), not as raw graph nodes.

What this script exercises, in order, and records in demo-state/step3b/spec-flow.json:
  1. author     RECORDER (Spec preset) adds the decisions to a new decision-register spec and moves it to approved.
                One decision has no verification plan on purpose.
  2. role       RECORDER tries a move it has no permission for (approved to draft) and is refused.
  3. gate       REVIEWER (Validator preset) records requirement lint and a decomposition evaluation, then submits the spec validation.
                Pulse refuses it: decision_verification_plan_incomplete. A direct move to validated is refused too.
  4. fix        MAINTAINER reopens the spec to draft (a new edition). RECORDER adds the missing plan and moves it back to approved.
  5. pass       REVIEWER submits lint, evaluation and validation again. Pulse promotes the spec to validated.
  6. graph      The approved spec's decisions are Decision nodes in the working layer. A reader (RECALLER) sees none of them,
                because search reads the canonical layer only.
  7. closeout   RECORDER commits a consolidation for the spec: each decision becomes a canonical Decision node with Alternative
                nodes and relates_to edges, which Pulse's connectivity rule asks for. A Decision with no such edge is refused
                first, and that refusal is recorded too.
  8. read       RECALLER now finds them.

The lint, evaluation and validation scores are FIXED values written by this script and say so in their justification.
They exercise the gate. They are not a judgement of the decisions by a model.

Usage: python scripts/spec_flow.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import corpus  # noqa: E402
import stepslib as sl  # noqa: E402
from setup_board import wait_until_healthy  # noqa: E402

OUT = sl.STATE / "step3b"
JUST = "Scripted run with a fixed score. It exercises the gate and is not a judgement by a model."
GATE_TOOL = "okto_pulse_submit_spec_validation"
# Pulse answers these while its own workers hold a lock or the board graph is still settling. They are retried and counted.
TRANSIENT = ("database is locked", "lock_contention", "kg_graph_degraded", "recovery_needed")


class Flow:
    """Calls Pulse as a given role and keeps one record of every call."""

    def __init__(self, board_id: str):
        self.board_id = board_id
        self.events: list[dict] = []
        self.sessions: dict[str, sl.Mcp] = {}

    def mcp(self, role: str) -> sl.Mcp:
        if role not in self.sessions:
            self.sessions[role] = sl.Mcp(role)
        return self.sessions[role]

    def call(self, role: str, phase: str, tool: str, args: dict, note: str = "") -> dict:
        retries = 0
        while True:
            r = self.mcp(role).call(tool, args)
            text = json.dumps(r["envelope"], default=str)
            if r["ok"] or retries >= 12 or not any(t in text for t in TRANSIENT):
                break
            retries += 1
            time.sleep(5)
        env = r["envelope"] if isinstance(r["envelope"], dict) else {}
        err = (env.get("data") or {}).get("error") if isinstance(env.get("data"), dict) else None
        self.events.append({"n": len(self.events) + 1, "phase": phase, "actor": role, "tool": tool, "note": note, "retries_on_transient_error": retries, "ok": r["ok"],
                            "error_code": None if r["ok"] else (env.get("error_code") or (err.get("code") if isinstance(err, dict) else err)),
                            "message": None if r["ok"] else str(env.get("message") or err)[:400]})
        return r

    def close(self) -> None:
        for m in self.sessions.values():
            m.close()


def plan(spec_id: str, text: str) -> dict:
    return {"obligation_refs": [], "inspection": {"condition": text, "scope_refs": [{"kind": "spec", "id": spec_id}]}}


def lint_eval_validate(f: Flow, phase: str, spec_id: str, key: str) -> dict:
    """REVIEWER: requirement lint, decomposition evaluation, spec validation. Returns the validation result."""
    b = f.board_id
    pf = f.call("REVIEWER", phase, "okto_pulse_get_requirement_lint_preflight", {"board_id": b, "spec_id": spec_id})["data"]
    fence = pf["submission_fence"]
    f.call("REVIEWER", phase, "okto_pulse_record_requirement_lint", {
        "board_id": b, "spec_id": spec_id, "idempotency_key": f"{key}-lint", "expected_subject_version": fence["expected_subject_version"],
        "expected_subject_edition": fence["expected_subject_edition"], "expected_head_revision": fence["expected_head_revision"],
        "ruleset_digest": pf["ruleset_digest"], "score": 0, "summary": "No findings. " + JUST, "findings": []})
    f.call("REVIEWER", phase, "okto_pulse_submit_spec_evaluation", {
        "board_id": b, "spec_id": spec_id, "breakdown_completeness": 80, "breakdown_justification": JUST, "granularity": 80, "granularity_justification": JUST,
        "dependency_coherence": 80, "dependency_justification": JUST, "test_coverage_quality": 80, "test_coverage_justification": JUST,
        "overall_score": 80, "overall_justification": JUST, "recommendation": "approve"})
    cyc = f.call("REVIEWER", phase, "okto_pulse_get_spec_validation_cycle", {"board_id": b, "spec_id": spec_id, "include_planning": True})["data"]
    fe = cyc["submission_fence"]
    return f.call("REVIEWER", phase, GATE_TOOL, {
        "board_id": b, "spec_id": spec_id, "idempotency_key": key, "expected_validation_edition": fe["expected_validation_edition"],
        "expected_spec_version": fe["expected_subject_version"], "expected_head_revision": fe["expected_head_revision"], "expected_planning_manifest": cyc["planning_manifest"],
        "confidence": 80, "confidence_justification": JUST, "clarity": 85, "clarity_justification": JUST, "assertiveness": 85, "assertiveness_justification": JUST,
        "decidability": 85, "decidability_justification": JUST, "ambiguity": 10, "ambiguity_justification": JUST, "recommendation": "approve"})


def blocked_components(f: Flow, spec_id: str) -> list[dict]:
    d = f.mcp("REVIEWER").call("okto_pulse_get_spec_validation_cycle", {"board_id": f.board_id, "spec_id": spec_id, "include_planning": True})["data"]
    comps = d["planning_readiness"]["components"]
    return [{"key": c["key"], "state": c["state"], "reason_codes": c["reason_codes"], "message": c["message"]} for c in comps if c["state"] == "blocked"]


def system_sessions(board_id: str, spec_id: str) -> list[str]:
    """Commit times of the sessions Pulse's own worker (system:historical_consolidation) committed for a spec."""
    entries = sl.rest("GET", f"/kg/boards/{board_id}/audit")["entries"]
    return sorted(e["committed_at"] for e in entries if e["artifact_id"] == spec_id and e["agent_id"] == "system:historical_consolidation")


def wait_for_system_sessions(board_id: str, spec_id: str, quiet_s: int = 30, timeout_s: int = 240) -> dict:
    """Wait until Pulse's own consolidation worker has had no new session on the spec for quiet_s seconds.

    Pulse re-projects a spec's decisions into the working layer in a system session that lags the spec's status moves by 20 s or more.
    A system session that lands after a cognitive closeout superseded the canonical Decision nodes in the first run of this script (see
    demo-state/notes/closeout-superseded-by-system-session.json). The closeout therefore waits for that worker to go quiet. The wait is recorded."""
    t0, last_change, seen = time.time(), time.time(), system_sessions(board_id, spec_id)
    while time.time() - t0 < timeout_s:
        time.sleep(5)
        now = system_sessions(board_id, spec_id)
        if now != seen:
            seen, last_change = now, time.time()
        if seen and time.time() - last_change >= quiet_s:
            break
    return {"waited_s": round(time.time() - t0, 1), "system_sessions_seen": len(seen), "quiet_for_s": round(time.time() - last_change, 1), "timed_out": time.time() - t0 >= timeout_s}


def node_text(d: dict) -> str:
    return corpus.node_text(d)


def closeout(f: Flow, spec_id: str, ids: dict[str, str], decisions: list[dict]) -> dict:
    """One consolidation turns the approved spec decisions into canonical Decision nodes with Alternative nodes."""
    b = f.board_id
    # a Decision with no judgement edge is refused first
    first = decisions[0]
    ses = f.call("RECORDER", "closeout", "okto_pulse_kg_begin_consolidation", {"board_id": b, "artifact_type": "spec", "artifact_id": spec_id,
                 "raw_content": "probe: a decision without a judgement edge", "deterministic_candidates": []})["data"]["session_id"]
    f.call("RECORDER", "closeout", "okto_pulse_kg_add_node_candidate", {"session_id": ses, "candidate": {
        "candidate_id": "probe", "node_type": "Decision", "title": first["title"], "content": node_text(first), "context": first["group"],
        "justification": first["rationale"], "source_artifact_ref": f"spec:{spec_id}:decision:{ids[first['slug']]}", "source_confidence": 0.9}})
    refused = f.call("RECORDER", "closeout", "okto_pulse_kg_commit_consolidation", {"session_id": ses, "summary_text": "probe"}, "expected refusal: no Alternative or Decision edge")
    f.call("RECORDER", "closeout", "okto_pulse_kg_abort_consolidation", {"session_id": ses, "reason": "probe done"})

    ses = f.call("RECORDER", "closeout", "okto_pulse_kg_begin_consolidation", {"board_id": b, "artifact_type": "spec", "artifact_id": spec_id,
                 "raw_content": "closeout of the decision register: " + ", ".join(d["slug"] for d in decisions), "deterministic_candidates": []})["data"]["session_id"]
    for d in decisions:
        did = ids[d["slug"]]
        f.call("RECORDER", "closeout", "okto_pulse_kg_add_node_candidate", {"session_id": ses, "candidate": {
            "candidate_id": d["slug"], "node_type": "Decision", "title": d["title"], "content": node_text(d), "context": d["group"],
            "justification": d["rationale"], "source_artifact_ref": f"spec:{spec_id}:decision:{did}", "source_confidence": 0.9}})
        for n, alt in enumerate(d["alternatives"], 1):
            f.call("RECORDER", "closeout", "okto_pulse_kg_add_node_candidate", {"session_id": ses, "candidate": {
                "candidate_id": f"{d['slug']}-alt{n}", "node_type": "Alternative", "title": f"Alternative to {d['slug']}: {alt}", "content": f"Considered and not chosen: {alt}.",
                "context": d["group"], "justification": "listed as an alternative in the spec decision", "source_artifact_ref": f"spec:{spec_id}:alternative:{did}-{n}", "source_confidence": 0.9}})
            f.call("RECORDER", "closeout", "okto_pulse_kg_add_edge_candidate", {"session_id": ses, "candidate": {
                "candidate_id": f"edge-{d['slug']}-alt{n}", "edge_type": "relates_to", "from_candidate_id": d["slug"], "to_candidate_id": f"{d['slug']}-alt{n}", "confidence": 0.9}})
    hints = f.call("RECORDER", "closeout", "okto_pulse_kg_propose_reconciliation", {"session_id": ses})["data"]["hints"]
    commit = f.call("RECORDER", "closeout", "okto_pulse_kg_commit_consolidation", {"session_id": ses, "summary_text": "Decision register closeout: spec decisions with their alternatives."})
    return {"refused_without_edge": {"ok": refused["ok"], "error_code": refused["envelope"].get("error_code"), "message": refused["envelope"].get("message")},
            "hints_by_operation": {op: sum(1 for h in hints if h["operation"] == op) for op in sorted({h["operation"] for h in hints})},
            "commit": {k: (commit["data"] or {}).get(k) for k in ("status", "nodes_added", "nodes_updated", "nodes_superseded", "edges_added")} if commit["ok"] else commit["envelope"]}


def main() -> int:
    info = sl.board_info()
    b = info["board_id"]
    decisions = [d for d in corpus.extra_decisions() if d["origin"] == "graph-only"]
    OUT.mkdir(parents=True, exist_ok=True)
    wait_until_healthy(b)
    f = Flow(b)
    try:
        spec = sl.rest("POST", f"/boards/{b}/specs", {"title": "Decision register: product decisions", "delivery_context": "brownfield",
                       "description": "Product and security decisions whose reasons are not in the code. Invented for this demo."})
        sid = spec["id"]
        # 1. author. The first decision has no verification plan on purpose.
        ids: dict[str, str] = {}
        for n, d in enumerate(decisions):
            args = {"board_id": b, "spec_id": sid, "title": d["title"], "rationale": d["rationale"], "context": d["group"], "alternatives_considered": d["alternatives"]}
            if n > 0:
                args["verification"] = plan(sid, f"Confirm that the code and the configuration still follow the decision: {d['title']}")
            r = f.call("RECORDER", "author", "okto_pulse_add_decision", args, d["slug"] + (" (no verification plan)" if n == 0 else ""))
            ids[d["slug"]] = r["data"]["decision"]["id"]
        for st in ("review", "approved"):
            f.call("RECORDER", "author", "okto_pulse_move_spec", {"board_id": b, "spec_id": sid, "status": st})
        # 2. role: the Spec preset may not send an approved spec back to draft
        denied = f.call("RECORDER", "role", "okto_pulse_move_spec", {"board_id": b, "spec_id": sid, "status": "draft"}, "expected refusal")
        # 3. gate: refusal
        f.call("REVIEWER", "gate", "okto_pulse_move_spec", {"board_id": b, "spec_id": sid, "status": "validated"}, "direct move, expected refusal")
        blocked_before = blocked_components(f, sid)
        refusal = lint_eval_validate(f, "gate", sid, "register-validate-1")
        # 4. fix
        f.call("MAINTAINER", "fix", "okto_pulse_move_spec", {"board_id": b, "spec_id": sid, "status": "draft"}, "reopen: a new edition")
        first = decisions[0]
        f.call("RECORDER", "fix", "okto_pulse_update_spec_entity", {"board_id": b, "spec_id": sid, "entity_type": "decision", "entity_id": ids[first["slug"]], "operation": "update",
               "payload_json": {"verification": plan(sid, f"Confirm that the code and the configuration still follow the decision: {first['title']}")}}, "add the missing plan")
        for st in ("review", "approved"):
            f.call("RECORDER", "fix", "okto_pulse_move_spec", {"board_id": b, "spec_id": sid, "status": st})
        # 5. pass
        passed = lint_eval_validate(f, "pass", sid, "register-validate-2")
        blocked_after = blocked_components(f, sid)
        status = f.mcp("REVIEWER").call("okto_pulse_get_spec", {"board_id": b, "spec_id": sid})["data"]
        # 6. graph, before the closeout
        titles = {d["title"] for d in decisions}
        reader = f.mcp("RECALLER")
        maint = f.mcp("MAINTAINER")
        layer_q = "MATCH (n:Decision) WHERE n.source_artifact_ref STARTS WITH $p RETURN n.graph_layer AS layer, count(n) AS c"
        for _ in range(24):  # the worker that projects spec decisions into the graph runs after the move to approved
            layers = sl.cypher(maint, b, layer_q, {"p": f"spec:{sid}:decision:"}, include_working=True)
            if isinstance(layers, list) and sum(r[1] for r in layers) >= len(decisions):
                break
            time.sleep(5)
        seen_similar = seen_natural = 0
        audit = None
        for d in decisions:
            similar = reader.call("okto_pulse_kg_find_similar_decisions", {"board_id": b, "topic": d["title"], "top_k": 10})
            natural = reader.call("okto_pulse_kg_query_natural", {"board_id": b, "nl_query": d["title"], "limit": 10})
            seen_similar += any(x["title"] in titles for x in (similar["data"] or {}).get("decisions", []))
            seen_natural += any(x.get("title") in titles for x in (natural["data"] or {}).get("nodes", []))
            audit = audit or (natural["data"] or {}).get("layer_audit")
        before = {"decision_nodes_by_layer": {r[0]: r[1] for r in layers}, "recaller_found_a_register_decision_by_similarity": f"{seen_similar} of {len(decisions)}",
                  "recaller_found_a_register_decision_by_natural_search": f"{seen_natural} of {len(decisions)}", "recaller_natural_layer_audit_example": audit}
        # 7. closeout, once Pulse's own consolidation worker has gone quiet on the spec
        settle_before = wait_for_system_sessions(b, sid)
        close = closeout(f, sid, ids, decisions)
        settle_after = wait_for_system_sessions(b, sid)
        active = sl.cypher(maint, b, "MATCH (n:Decision) WHERE n.source_artifact_ref STARTS WITH $p AND n.superseded_by IS NULL RETURN n.graph_layer AS layer, count(n) AS c",
                           {"p": f"spec:{sid}:decision:"}, include_working=True)
        # 8. read
        found = 0
        for d in decisions:
            r = reader.call("okto_pulse_kg_find_similar_decisions", {"board_id": b, "topic": d["title"], "top_k": 5})
            found += any(x["title"] == d["title"] for x in (r["data"] or {}).get("decisions", []))
        layers_after = sl.cypher(maint, b, "MATCH (n:Decision) WHERE n.source_artifact_ref STARTS WITH $p RETURN n.graph_layer AS layer, count(n) AS c",
                                 {"p": f"spec:{sid}:decision:"}, include_working=True)
        canonical = sl.cypher(maint, b, "MATCH (n:Decision) WHERE n.source_artifact_ref STARTS WITH $p RETURN n.id, n.title, n.source_artifact_ref", {"p": f"spec:{sid}:decision:"})
        sl.save_json(OUT / "node-map.json", {r[0]: corpus.slug_for_node(r[1], None, r[2]) for r in canonical})
        record = {
            "note": "Scripted run, no LLM. Scores in lint, evaluation and validation are fixed values that exercise the gate.",
            "spec_id": sid, "decisions": len(decisions), "decision_ids": ids,
            "gate": {
                "tool": GATE_TOOL,
                "blocked_components_before_fix": blocked_before,
                "refusal": {"ok": refusal["ok"], "error_code": refusal["envelope"].get("error_code"), "message": refusal["envelope"].get("message")},
                "pass": {"ok": passed["ok"], **{k: (passed["data"] or {}).get(k) for k in ("outcome", "spec_status", "planning_result", "validation_edition")}},
                "blocked_components_after_fix": blocked_after, "spec_status_at_end": (status or {}).get("status"), "spec_edition_at_end": (status or {}).get("edition"),
            },
            "role_denial": {"actor": "RECORDER", "preset": "Spec", "tool": "okto_pulse_move_spec", "ok": denied["ok"], "error_code": denied["envelope"].get("error_code"), "message": denied["envelope"].get("message")},
            "graph_before_closeout": before, "closeout": close,
            "system_consolidation_settle": {"before_closeout": settle_before, "after_closeout": settle_after,
                                            "active_decision_nodes_by_layer_after_settle": {r[0]: r[1] for r in active}}, "recaller_finds_after_closeout": f"{found} of {len(decisions)}",
            "decision_nodes_by_layer_after_closeout": {r[0]: r[1] for r in layers_after},
            "events": f.events,
        }
        sl.save_json(OUT / "spec-flow.json", record)
    finally:
        f.close()
    g = record["gate"]
    print(f"gate refusal: {g['refusal']['error_code']} | pass: {g['pass'].get('spec_status')} | role denied: {record['role_denial']['error_code']}")
    print(f"before closeout: layers {before['decision_nodes_by_layer']}, recaller finds {before['recaller_found_a_register_decision_by_similarity']}; "
          f"after: {record['recaller_finds_after_closeout']}, layers {record['decision_nodes_by_layer_after_closeout']}")
    ok = (not g["refusal"]["ok"]) and g["pass"]["ok"] and g["spec_status_at_end"] == "validated" and not record["role_denial"]["ok"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
