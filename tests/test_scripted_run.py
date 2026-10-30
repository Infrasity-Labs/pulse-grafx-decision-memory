"""Recorded evidence of the scripted run (no LLM): Pulse gate, role denials, crash recovery, arms. Files in demo-state/scripted-run/.

These tests read what was recorded. The same claims are checked against live Pulse and Grafx by scripts/assert_runtime.py in the integration workflow.
"""
import json
import sys

from conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import build_closeout  # noqa: E402
import corpus  # noqa: E402
import score_arms  # noqa: E402

RUN = "scripted-run/"


def test_run_info_says_what_the_run_was_and_what_it_was_not(loadj):
    i = loadj(RUN + "run-info.json")
    assert "no LLM" in i["what"] and "Not an agent run" in i["what"]
    assert i["assertions"]["failed"] == 0 and i["assertions"]["checks"] >= 40
    assert i["okto_pulse"] == "0.4.2" and i["okto_grafx"] == "0.0.8" and len(i["repo_base_commit"]) == 40
    assert i["files_missing_in_the_run"] == []
    assert i["not_run"] and "step 9" in i["not_run"][0]


def test_every_recorded_assertion_of_the_run_passed(loadj):
    rep = loadj(RUN + "assert-report.json")
    assert rep["failed"] == 0
    assert all(r["ok"] for r in rep["results"])


def test_scripted_transcripts_say_they_are_scripted(loadj):
    for step in ("step3", "step5/maintainer-reversal-no-rationale"):
        assert loadj(f"{RUN}{step}/agent/result.json")["model"] == "scripted-agent (no LLM)"


def test_gate_refused_then_passed_on_the_same_spec(loadj):
    g = loadj(RUN + "step3b/spec-flow.json")["gate"]
    assert g["refusal"]["ok"] is False and g["refusal"]["error_code"] == "spec_validation_gate_not_ready"
    assert "decision_verification_plan_incomplete" in g["refusal"]["message"]
    assert {c["key"] for c in g["blocked_components_before_fix"]} >= {"decision_verification", "spec_validation"}
    assert g["pass"]["ok"] and g["spec_status_at_end"] == "validated" and g["spec_edition_at_end"] == 2
    assert "decision_verification" not in {c["key"] for c in g["blocked_components_after_fix"]}


def test_spec_decisions_are_invisible_to_search_until_the_closeout(loadj):
    f = loadj(RUN + "step3b/spec-flow.json")
    assert f["graph_before_closeout"]["decision_nodes_by_layer"] == {"working": 10}
    assert f["graph_before_closeout"]["recaller_found_a_register_decision_by_similarity"] == "0 of 10"
    assert f["closeout"]["refused_without_edge"]["error_code"] == "kg_node_connectivity_violation"
    assert f["recaller_finds_after_closeout"] == "10 of 10"
    assert f["system_consolidation_settle"]["active_decision_nodes_by_layer_after_settle"] == {"canonical": 10}


def test_the_spec_decisions_are_the_graph_only_ones_of_the_corpus(loadj):
    f = loadj(RUN + "step3b/spec-flow.json")
    assert f["decisions"] == 10
    adds = [e for e in f["events"] if e["tool"] == "okto_pulse_add_decision"]
    assert len(adds) == 10 and all(e["actor"] == "RECORDER" and e["ok"] for e in adds)
    assert sum("no verification plan" in e["note"] for e in adds) == 1


def test_spec_preset_was_refused_a_move_outside_its_preset(loadj):
    d = loadj(RUN + "step3b/spec-flow.json")["role_denial"]
    assert d["preset"] == "Spec" and d["ok"] is False and d["error_code"] == "permission_denied" and "spec.move.approved_to_draft" in d["message"]


def test_each_restricted_role_is_refused_at_least_twice_and_still_does_its_work(loadj):
    r = loadj(RUN + "roles/role-denials.json")
    assert set(r["summary"]) == {"RECALLER", "RECORDER", "REVIEWER"}
    for role, s in r["summary"].items():
        assert s["by_kind"]["permission"] >= 2, role
        assert s["denied_as_expected"] == s["denied_actions_tried"] and s["controls_succeeded"] == s["controls_tried"] >= 2, role
    assert all(x["as_expected"] for x in r["results"])
    permission = [x for x in r["results"] if x["role"] == "RECALLER" and x["kind"] == "permission"]
    assert {x["required_permission"] for x in permission} >= {"kg.session.begin", "spec.structured_entity.decision.create", "spec.entity.create"}


def test_reporter_is_refused_every_graph_write_tool_but_five_of_them_by_session_ownership(loadj):
    rows = [x for x in loadj(RUN + "roles/role-denials.json")["results"] if x["role"] == "RECALLER" and x["tool"].startswith("okto_pulse_kg_") and x["kind"] != "control (allowed)"]
    tools = {x["tool"].replace("okto_pulse_kg_", "") for x in rows if x["tool"] != "okto_pulse_kg_query_cypher"}
    assert tools == {"begin_consolidation", "add_node_candidate", "add_edge_candidate", "propose_reconciliation", "commit_consolidation", "abort_consolidation"}
    own = [x for x in rows if x["kind"].startswith("ownership")]
    assert len(own) == 5 and all(x["error_code"] == "session_ownership_mismatch" and x["required_permission"] is None for x in own)


def test_kill_a_resume_leaves_each_decision_once(loadj):
    a = loadj(RUN + "step7/killA.json")
    assert a["draft_absent"] and a["earlier_decisions_all_present"] and a["decisions_before"] == a["decisions_after"] == 3
    r = a["resume"]
    assert r["every_slug_exactly_once"] and r["duplicates"] == [] and len(r["replayed"]) == 6
    ops = r["result"]["hint_operation_by_slug"]
    assert {ops[f"killa-base-{n}"] for n in (1, 2, 3)} == {"UPDATE"} and {ops[f"killa-draft-{n}"] for n in (1, 2, 3)} == {"ADD"}


def test_kill_b_retry_leaves_no_slug_twice_and_acknowledged_commits_survive(loadj, state):
    b = loadj(RUN + "step7/killB.json")
    assert b["acknowledged_missing"] == [] and b["acknowledged_and_present"] == b["acknowledged_commits"] > 0
    events = [json.loads(ln) for n in (1, 2, 3) for ln in (state / RUN / "step7" / f"burst-ack-w{n}.log").read_text().splitlines() if ln.strip()]
    acked = {e["slug"] for e in events if e["ev"] == "ack"}
    started = {e["slug"] for e in events if e["ev"] == "start"}
    assert len(acked) == b["acknowledged_commits"] and set(b["in_flight_at_kill"]) == started - acked
    r = b["retry"]
    assert set(r["retried"]) == set(b["in_flight_at_kill"]) and r["every_started_slug_exactly_once"] and r["duplicates"] == []


def test_crash_writes_never_touched_the_decision_board(loadj):
    c = loadj(RUN + "step7/decision-board-check.json")
    assert c["unchanged"] and c["synthetic_slugs_on_decision_board"] == []
    assert loadj(RUN + "step7/killA.json")["board_id"] != loadj(RUN + "step7/killB.json")["board_id"]


def test_scripted_recall_equals_the_numbers_of_the_recorded_agent_run(loadj):
    live, rec = loadj(RUN + "step4/recall-results.json")["summary"], loadj("step4/recall-results.json")["summary"]
    for k in ("similar_top1_correct", "natural_top1_correct", "history_top1_correct", "agent_choice_correct"):
        assert live[k] == rec[k], k


def test_scripted_reversal_shows_pulse_alone_flags_nothing(loadj):
    counts = build_closeout.find_contradiction_counts(ROOT / "demo-state" / "scripted-run" / "step5" / "agent" / "transcript.jsonl")
    assert counts == [0, 0, 1]
    b, a = loadj(RUN + "step5/before.json"), loadj(RUN + "step5/after.json")
    assert a["decisions_total"] == b["decisions_total"] + 1


def test_a_note_without_a_reason_changes_nothing(loadj):
    b = loadj(RUN + "step5/maintainer-reversal-no-rationale/before.json")
    a = loadj(RUN + "step5/maintainer-reversal-no-rationale/after.json")
    assert b["decisions_total"] == a["decisions_total"] and len(b["supersedes_edges"]) == len(a["supersedes_edges"])
    final = json.loads(loadj(RUN + "step5/maintainer-reversal-no-rationale/agent/result.json")["final"]["result"])
    assert final["recorded"] is False


def test_arms_scoreboard_statements_hold():
    """The prose under the arms table makes three claims. They are checked here, from the arm files, with the shared scorer."""
    arms = score_arms.load_arms(ROOT / "demo-state" / "arms")
    lex, pulse = arms["lexical-tfidf"]["scores"], arms["pulse-retrieval"]["scores"]
    for split in ("dev", "held_out"):
        assert pulse[split]["correct"] > lex[split]["correct"], split
    assert sum(s["fabricated"] for s in pulse.values()) == 3 and pulse["dev"]["fabricated"] == pulse["held_out"]["fabricated"] == pulse["model_authored"]["fabricated"] == 1
    assert pulse["dev"]["graph_only_correct"] == 4 and pulse["held_out"]["graph_only_correct"] == 2
    assert pulse["legacy"]["correct"] == 7  # the same ten questions scored 10 of 10 on the 12-decision board
    assert arms["pulse-retrieval"]["decisions_on_board"] == len(corpus.all_decisions()) == 32


def test_pulse_arm_threshold_was_chosen_on_dev_only():
    arm = json.loads((ROOT / "demo-state" / "arms" / "pulse-retrieval.json").read_text())
    dev = [(r["score"], r["top"], q["expected_slug"]) for r, q in zip(arm["rows"], corpus.questions()) if q["split"] == "dev"]
    assert arm["abstention_threshold_chosen_on_dev"] == score_arms.calibrate_threshold(dev)


def test_previous_session_id_on_a_fresh_data_home_is_pulse_own_system_session(loadj):
    p = loadj("notes/previous-session-id-probe.json")
    first, later = p["begin_consolidation_calls"]
    assert first["previous_session_id"] is None and later["previous_session_id"]
    assert p["previous_session_id_is_a_system_session"] is True
    assert [e["agent"] for e in p["audit_entries_for_the_spec"]] == ["system:historical_consolidation"]


def test_the_closeout_that_pulse_own_worker_later_superseded_is_kept_as_evidence(loadj):
    n = loadj("notes/closeout-superseded-by-system-session.json")
    layers = [(d["layer"], d["superseded"]) for d in n["decision_nodes"]]
    assert layers.count(("canonical", True)) == 10  # the canonical nodes ended up superseded
    assert layers.count(("working", False)) == 10
    assert sum(e["agent_id"] == "system:historical_consolidation" for e in n["audit_entries_for_the_spec"]) >= 3


def test_data_dir_claim_a_run_leaves_the_okto_pulse_folder_alone_but_writes_a_model_cache_to_home(loadj):
    """README claim: a real run never touches ~/.okto-pulse. Recorded by scripts/check_data_dir_claim.py against a temporary HOME with a sentinel file."""
    d = loadj("home-guard/data-dir-claim.json")
    o = d["okto_pulse_dir"]
    assert o["unchanged"] and o["files_before"] == o["files_after"] == 1 and not (o["added"] or o["removed"] or o["changed"])
    assert d["run_failed"] is None and d["files_written_to_the_data_dir"] > 0
    assert d["new_top_level_entries_in_home"] == [".cache"]  # the Hugging Face cache of the embedding model, which is outside .okto-pulse
