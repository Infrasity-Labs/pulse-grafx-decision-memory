"""Test the role claim in both directions: each restricted role is refused several actions outside its preset, and still does its own work.

Presets (see setup_board.py): RECALLER is Reporter, RECORDER is Spec, REVIEWER is Validator. For each of them this probe tries
actions the preset should not allow, records what Pulse answered, and also runs a control action the preset should allow.

Two kinds of refusal show up, and they are different:
  permission   Pulse names the missing permission (error_code permission_denied or forbidden, field required_permission).
  ownership    a session-bound graph tool is refused because the session belongs to another identity (session_ownership_mismatch).
               The Reporter reaches this check for add, edge, propose, commit and abort. Nothing in the answer says the Reporter lacks
               a permission for those tools. The preset stops it earlier, at begin_consolidation, which is a permission refusal.

All probe writes go to a scratch board, so the decision board is not touched.
Output: demo-state/roles/role-denials.json. Exit code 1 if any denial did not happen or any control failed.

Usage: python scripts/probe_roles.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import stepslib as sl  # noqa: E402
from setup_board import wait_until_healthy  # noqa: E402

OUT = sl.STATE / "roles"


def refusal(r: dict) -> dict:
    env = r["envelope"] if isinstance(r["envelope"], dict) else {}
    msg = str(env.get("message") or "")
    perm = None
    m = re.search(r'"required_permission":\s*"([^"]+)"', msg)
    if m:
        perm = m.group(1)
    return {"ok": r["ok"], "error_code": env.get("error_code"), "required_permission": perm, "message": msg[:240]}


def main() -> int:
    info = sl.board_info()
    agents = {a["role"]: a["agent_id"] for a in info["agents"]}
    board = sl.rest("POST", "/boards", {"name": "Role probe board (scratch)", "description": "Scratch board for role probes. Holds no scenario decisions."})
    b = board["id"]
    for aid in agents.values():
        sl.rest("POST", f"/agents/{aid}/boards/{b}")
    spec = sl.rest("POST", f"/boards/{b}/specs", {"title": "Role probe spec", "description": "Scratch spec.", "delivery_context": "greenfield"})["id"]
    wait_until_healthy(b)
    fake_validation = {"idempotency_key": "k", "expected_validation_edition": 1, "expected_spec_version": 1, "expected_head_revision": 0, "expected_planning_manifest": {}}
    results: list[dict] = []

    def case(role: str, preset: str, tool: str, args: dict, kind: str, expect_code: str | tuple, expect_perm: str | None, m: sl.Mcp) -> None:
        r = refusal(m.call(tool, args))
        codes = (expect_code,) if isinstance(expect_code, str) else expect_code
        passed = (not r["ok"]) and r["error_code"] in codes and (expect_perm is None or r["required_permission"] == expect_perm)
        results.append({"role": role, "preset": preset, "tool": tool, "kind": kind, "expected_error_code": list(codes), "expected_permission": expect_perm, **r, "as_expected": passed})

    def control(role: str, preset: str, tool: str, args: dict, m: sl.Mcp) -> dict:
        r = m.call(tool, args)
        results.append({"role": role, "preset": preset, "tool": tool, "kind": "control (allowed)", "ok": r["ok"], "as_expected": r["ok"],
                        "error_code": None if r["ok"] else (r["envelope"] or {}).get("error_code")})
        return r

    with sl.Mcp("RECORDER") as rec, sl.Mcp("RECALLER") as rcl, sl.Mcp("REVIEWER") as rev, sl.Mcp("MAINTAINER") as mnt:
        # The Recorder authors a decision and approves the scratch spec: its own work, so these are controls.
        control("RECORDER", "Spec", "okto_pulse_add_decision", {"board_id": b, "spec_id": spec, "title": "Probe decision", "rationale": "A scratch decision for the role probe."}, rec)
        for st in ("review", "approved"):
            control("RECORDER", "Spec", "okto_pulse_move_spec", {"board_id": b, "spec_id": spec, "status": st}, rec)
        opened = rec.call("okto_pulse_kg_begin_consolidation", {"board_id": b, "artifact_type": "spec", "artifact_id": spec, "raw_content": "probe", "deterministic_candidates": []})
        results.append({"role": "RECORDER", "preset": "Spec", "tool": "okto_pulse_kg_begin_consolidation", "kind": "control (allowed)", "ok": opened["ok"], "as_expected": opened["ok"]})
        sid = opened["data"]["session_id"]

        # Reporter: refused on write tools
        rb = {"board_id": b}
        case("RECALLER", "Reporter", "okto_pulse_kg_begin_consolidation", {**rb, "artifact_type": "spec", "artifact_id": spec, "raw_content": "x", "deterministic_candidates": []}, "permission", "permission_denied", "kg.session.begin", rcl)
        case("RECALLER", "Reporter", "okto_pulse_add_decision", {**rb, "spec_id": spec, "title": "x", "rationale": "y"}, "permission", "permission_denied", "spec.structured_entity.decision.create", rcl)
        case("RECALLER", "Reporter", "okto_pulse_create_spec", {**rb, "title": "x", "description": "y", "delivery_context": "greenfield"}, "permission", "permission_denied", "spec.entity.create", rcl)
        case("RECALLER", "Reporter", "okto_pulse_move_spec", {**rb, "spec_id": spec, "status": "draft"}, "permission", "permission_denied", "spec.move.approved_to_draft", rcl)
        case("RECALLER", "Reporter", "okto_pulse_kg_query_cypher", {**rb, "cypher": "MATCH (n:Decision) RETURN count(n)"}, "permission", "permission_denied", "kg.power.cypher", rcl)
        cand = {"candidate_id": "z1", "node_type": "Decision", "title": "t", "content": "c", "context": "x", "justification": "j", "source_artifact_ref": f"final_report:{spec}:decision:z1", "source_confidence": 0.9}
        for tool, args in (("okto_pulse_kg_add_node_candidate", {"session_id": sid, "candidate": cand}),
                           ("okto_pulse_kg_add_edge_candidate", {"session_id": sid, "candidate": {"candidate_id": "e", "edge_type": "depends_on", "from_candidate_id": "z1", "to_candidate_id": "z2", "confidence": 0.9}}),
                           ("okto_pulse_kg_propose_reconciliation", {"session_id": sid}),
                           ("okto_pulse_kg_commit_consolidation", {"session_id": sid, "summary_text": "x"}),
                           ("okto_pulse_kg_abort_consolidation", {"session_id": sid, "reason": "x"})):
            case("RECALLER", "Reporter", tool, args, "ownership (another identity's open session)", "session_ownership_mismatch", None, rcl)
        control("RECALLER", "Reporter", "okto_pulse_kg_find_similar_decisions", {**rb, "topic": "token", "top_k": 1}, rcl)
        control("RECALLER", "Reporter", "okto_pulse_kg_query_natural", {**rb, "nl_query": "token", "limit": 1}, rcl)

        # Recorder (Spec): refused outside its preset
        case("RECORDER", "Spec", "okto_pulse_move_spec", {**rb, "spec_id": spec, "status": "draft"}, "permission", "permission_denied", "spec.move.approved_to_draft", rec)
        case("RECORDER", "Spec", "okto_pulse_submit_spec_evaluation", {**rb, "spec_id": spec, "breakdown_completeness": 80, "breakdown_justification": "x" * 20, "granularity": 80,
             "granularity_justification": "x" * 20, "dependency_coherence": 80, "dependency_justification": "x" * 20, "test_coverage_quality": 80,
             "test_coverage_justification": "x" * 20, "overall_score": 80, "overall_justification": "x" * 20, "recommendation": "approve"}, "permission", "permission_denied", "spec.evaluations.submit", rec)
        case("RECORDER", "Spec", "okto_pulse_record_requirement_lint", {**rb, "spec_id": spec, "idempotency_key": "k", "expected_subject_version": 1, "expected_subject_edition": 1,
             "expected_head_revision": 0, "ruleset_digest": "0" * 64, "score": 0, "summary": "x" * 20, "findings": []}, "permission", ("forbidden", "permission_denied"), "spec.quality.assess", rec)
        case("RECORDER", "Spec", "okto_pulse_kg_health", rb, "permission", "permission_denied", "kg.operations.health.read", rec)
        rec.call("okto_pulse_kg_abort_consolidation", {"session_id": sid, "reason": "probe done"})

        # Reviewer (Validator): refused outside its preset
        case("REVIEWER", "Validator", "okto_pulse_add_decision", {**rb, "spec_id": spec, "title": "x", "rationale": "y"}, "permission", "permission_denied", "spec.structured_entity.decision.create", rev)
        case("REVIEWER", "Validator", "okto_pulse_create_spec", {**rb, "title": "x", "description": "y", "delivery_context": "greenfield"}, "permission", "permission_denied", "spec.entity.create", rev)
        case("REVIEWER", "Validator", "okto_pulse_delete_spec", {**rb, "spec_id": spec}, "permission", "permission_denied", "spec.entity.delete", rev)
        case("REVIEWER", "Validator", "okto_pulse_create_card", {**rb, "spec_id": spec, "title": "t", "description": "d"}, "permission", "permission_denied", "card.entity.create", rev)
        case("REVIEWER", "Validator", "okto_pulse_kg_health", rb, "permission", "permission_denied", "kg.operations.health.read", rev)
        vs = rev.call("okto_pulse_kg_begin_consolidation", {**rb, "artifact_type": "spec", "artifact_id": spec, "raw_content": "probe", "deterministic_candidates": []})
        results.append({"role": "REVIEWER", "preset": "Validator", "tool": "okto_pulse_kg_begin_consolidation", "kind": "control (allowed)", "ok": vs["ok"], "as_expected": vs["ok"]})
        if vs["ok"]:
            rev.call("okto_pulse_kg_abort_consolidation", {"session_id": vs["data"]["session_id"], "reason": "probe done"})
        control("REVIEWER", "Validator", "okto_pulse_kg_find_contradictions", rb, rev)

        # the Maintainer (Full Control) can do what the others cannot
        control("MAINTAINER", "Full Control", "okto_pulse_kg_health", rb, mnt)

    summary = {}
    for role in ("RECALLER", "RECORDER", "REVIEWER"):
        rs = [r for r in results if r["role"] == role]
        denials = [r for r in rs if not r["kind"].startswith("control")]
        summary[role] = {"preset": rs[0]["preset"], "denied_actions_tried": len(denials), "denied_as_expected": sum(r["as_expected"] for r in denials),
                         "by_kind": {k: sum(1 for r in denials if r["kind"].startswith(k)) for k in ("permission", "ownership")},
                         "controls_tried": len(rs) - len(denials), "controls_succeeded": sum(r["as_expected"] for r in rs if r["kind"].startswith("control"))}
    record = {"note": "Scripted probe, no LLM. All writes went to a scratch board.", "board_id": b, "summary": summary, "results": results}
    sl.save_json(OUT / "role-denials.json", record)
    bad = [r for r in results if not r["as_expected"]]
    for role, s in summary.items():
        print(f"{role} ({s['preset']}): denied as expected {s['denied_as_expected']} of {s['denied_actions_tried']} (permission {s['by_kind']['permission']}, ownership {s['by_kind']['ownership']}); controls {s['controls_succeeded']} of {s['controls_tried']}")
    for r in bad:
        print("UNEXPECTED:", r["role"], r["tool"], r.get("error_code"), r.get("required_permission"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
