"""Assert the outcomes of a live integration run (scripts/run_integration.py). Reads only the run's own state folder.

These checks fail when Pulse or Grafx return a different outcome from the one the demo claims: a lost acknowledged commit, a gate that
no longer refuses, a role that is no longer denied, a restore that does not give back the decisions. They never read the committed
demo-state/ of the reference run, except to compare a number with the same number there, and they say so when they do.

Two kinds of check:
  claim         a statement the README makes. A failure means the claim is false for this run.
  observation   a behaviour of Pulse or Grafx that the demo documents as a limit or a defect (the decision-history tool returning nothing,
                no contradiction without an explicit edge). A failure means the product changed. Review docs/PRODUCT-OBSERVATIONS.md.

Usage: python scripts/assert_runtime.py --state DIR [--require-step9]
Exit code 0 if every check passes, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_closeout  # noqa: E402
import corpus  # noqa: E402
import score_arms  # noqa: E402

TTL_S = 300
results: list[dict] = []


def chk(kind: str, name: str, cond, detail: str = "") -> None:
    results.append({"kind": kind, "name": name, "ok": bool(cond), "detail": detail})


def load(state: Path, rel: str):
    p = state / rel
    if not p.exists():
        chk("claim", f"{rel} exists", False, "the step that writes it did not run")
        return None
    return json.loads(p.read_text())


def check_setup(state: Path) -> None:
    v = load(state, "step1/versions.json")
    if v:
        pins = {ln.split("==")[0].split("[")[0]: ln.split("==")[1] for ln in (ROOT / "requirements.txt").read_text().splitlines() if "==" in ln and not ln.startswith("#")}
        chk("claim", "installed versions equal the pins in requirements.txt", v["okto_pulse"] == pins["okto-pulse"] and v["okto_grafx"] == pins["okto-grafx"], f"pulse {v['okto_pulse']}, grafx {v['okto_grafx']}")
        chk("claim", "the installed Pulse requires exactly the installed Grafx", v["pulse_requires_exact_installed_grafx"] is True, str(v["requires_dist_grafx_line"]))
    e = load(state, "step1/embedding.json")
    if e:
        chk("claim", "Pulse loads the real embedding model, not the stub", e["metadata_after_load"]["is_stub"] is False and e["similarity_related_pair"] > e["similarity_unrelated_pair"] + 0.2, e["configured_model"])
    b = load(state, "step2/board.json")
    if b:
        chk("claim", "step 2: four identities and a board graph that reaches healthy", len(b["agents"]) == 4 and b["health_after_create"][-1]["graph_state"] == "healthy",
            ", ".join(f"{a['role']}={a['preset']}" for a in b["agents"]))


def check_recording(state: Path) -> None:
    c = load(state, "step3/citations.json")
    rows = load(state, "step3/decisions-from-graph.json")
    if c and rows:
        chk("claim", "step 3 (scripted): 12 decisions committed, every cited file and line exists", c["all_ok"] and c["found"] == 12 == c["citations_ok"] and len(rows) == 12, f"found {c['found']}, citations ok {c['citations_ok']}")
    edges = load(state, "step3/decision-edges.json")
    if edges is not None:
        chk("claim", "step 3: the three depends_on edges are in the graph", len(edges) == 3 and {e[0] for e in edges} == {"depends_on__Decision__Decision"}, f"{len(edges)} edges")
    r = load(state, "step4/recall-results.json")
    if r:
        s = r["summary"]
        chk("claim", "step 4 (scripted, 12-decision board): similarity and natural-language search put the right decision first for all ten questions",
            s["similar_top1_correct"] == 10 and s["natural_top1_correct"] == 10 and s["agent_choice_correct"] == 10, f"similar {s['similar_top1_correct']}/10, natural {s['natural_top1_correct']}/10")
        chk("claim", "step 4: the read-only identity is refused a write session", "permission_denied" in (s["write_probe"] or "") and "kg.session.begin" in (s["write_probe"] or ""), "kg.session.begin")
        rec = json.loads((ROOT / "demo-state" / "step4" / "recall-results.json").read_text())["summary"]
        chk("observation", "step 4: the numbers equal the numbers of the recorded agent run (similar, natural, history top-1)",
            (s["similar_top1_correct"], s["natural_top1_correct"], s["history_top1_correct"]) == (rec["similar_top1_correct"], rec["natural_top1_correct"], rec["history_top1_correct"]),
            f"live {s['similar_top1_correct']}/{s['natural_top1_correct']}/{s['history_top1_correct']}, recorded {rec['similar_top1_correct']}/{rec['natural_top1_correct']}/{rec['history_top1_correct']}. A different history number means the decision-history tool changed.")


def check_spec_flow(state: Path) -> None:
    f = load(state, "step3b/spec-flow.json")
    if not f:
        return
    g = f["gate"]
    chk("claim", "Pulse gate: the spec validation is refused while a decision has no verification plan", not g["refusal"]["ok"] and "decision_verification_plan_incomplete" in (g["refusal"]["message"] or ""),
        f"{g['refusal']['error_code']}: {g['refusal']['message']}")
    chk("claim", "Pulse gate: after the plan is added the same spec is promoted to validated", g["pass"]["ok"] and g["spec_status_at_end"] == "validated", f"status {g['spec_status_at_end']}, edition {g['spec_edition_at_end']}")
    chk("claim", "role: the Spec preset is refused a move it has no permission for", not f["role_denial"]["ok"] and f["role_denial"]["error_code"] == "permission_denied", str(f["role_denial"]["message"])[:120])
    chk("claim", "spec decisions: 10 Decision nodes exist in the working layer and the Recaller finds none of them", f["graph_before_closeout"]["decision_nodes_by_layer"] == {"working": 10}
        and f["graph_before_closeout"]["recaller_found_a_register_decision_by_similarity"] == "0 of 10", str(f["graph_before_closeout"]["decision_nodes_by_layer"]))
    chk("claim", "closeout: a Decision with no Alternative or judgement edge is refused by the connectivity rule", f["closeout"]["refused_without_edge"]["error_code"] == "kg_node_connectivity_violation", str(f["closeout"]["refused_without_edge"]["error_code"]))
    chk("claim", "closeout: one consolidation makes the 10 decisions canonical and the Recaller finds all of them", f["closeout"]["commit"].get("status") == "committed" and f["recaller_finds_after_closeout"] == "10 of 10",
        f"{f['recaller_finds_after_closeout']}, layers {f['decision_nodes_by_layer_after_closeout']}")
    settle = f["system_consolidation_settle"]
    chk("observation", "closeout: after Pulse's own consolidation worker goes quiet, the 10 canonical nodes are still active and none was superseded by a working-layer node",
        settle["active_decision_nodes_by_layer_after_settle"].get("canonical") == 10 and not settle["after_closeout"]["timed_out"],
        f"active by layer {settle['active_decision_nodes_by_layer_after_settle']}; waited {settle['before_closeout']['waited_s']} s before and {settle['after_closeout']['waited_s']} s after the closeout")


def check_roles(state: Path) -> None:
    r = load(state, "roles/role-denials.json")
    if not r:
        return
    for role, s in r["summary"].items():
        chk("claim", f"role {role} ({s['preset']}): at least 2 permission denials, all denials as expected, controls succeed",
            s["by_kind"]["permission"] >= 2 and s["denied_as_expected"] == s["denied_actions_tried"] and s["controls_succeeded"] == s["controls_tried"],
            f"denied {s['denied_as_expected']}/{s['denied_actions_tried']} (permission {s['by_kind']['permission']}, ownership {s['by_kind']['ownership']}), controls {s['controls_succeeded']}/{s['controls_tried']}")


def check_arms(state: Path) -> None:
    for name in ("lexical-tfidf", "pulse-retrieval"):
        f = state / "arms" / f"{name}.json"
        if not f.exists():
            chk("claim", f"arm {name} was scored", False, "arms/%s.json is missing" % name)
            continue
        arm = score_arms.load_arm(f)
        total = sum(s["answered_by_arm"] for s in arm["scores"].values())
        chk("claim", f"arm {name}: every question was answered or abstained and scored by the shared scorer", total == len(corpus.questions()), f"{total} of {len(corpus.questions())} questions")
        print(f"  [arm] {name}\n{score_arms.format_scores(arm['scores'])}")
    p = state / "arms" / "pulse-retrieval.json"
    if p.exists():
        chk("claim", "the corpus board holds 32 decisions that the retrieval arm could map to corpus slugs", json.loads(p.read_text())["decisions_on_board"] == 32, "")


def check_reversal(state: Path) -> None:
    b, a = load(state, "step5/before.json"), load(state, "step5/after.json")
    if b and a:
        chk("claim", "step 5: one decision is added by the reversal", a["decisions_total"] == b["decisions_total"] + 1, f"{b['decisions_total']} -> {a['decisions_total']}")
        counts = build_closeout.find_contradiction_counts(state / "step5" / "agent" / "transcript.jsonl")
        chk("observation", "step 5: Pulse flags no contradiction after the supersede alone, and one pair after the explicit contradicts edge", counts == [0, 0, 1], f"find_contradictions counts {counts}")
        chain = a["chain_from_error-response-shape-v2"]["data"]
        chk("claim", "step 5: the supersedence chain from the new decision has length 1 and ends at it", chain["depth"] == 1, f"depth {chain['depth']}")
        chk("observation", "step 5: the chain from the old decision has length 0 and still names the old decision", a["chain_from_error-response-shape"]["data"]["depth"] == 0, "")
        chk("claim", "step 5: one supersedes edge and one contradicts edge", len(a["supersedes_edges"]) == 1 and len(a["contradicts_edges"]) == 1, "")
    nb, na = load(state, "step5/maintainer-reversal-no-rationale/before.json"), load(state, "step5/maintainer-reversal-no-rationale/after.json")
    if nb and na:
        chk("claim", "failing path: a note without a reason leaves the graph unchanged", nb["decisions_total"] == na["decisions_total"] and len(nb["supersedes_edges"]) == len(na["supersedes_edges"]), f"{nb['decisions_total']} -> {na['decisions_total']}")


def check_global(state: Path) -> None:
    g = load(state, "step6/global-discovery.json")
    if g:
        chk("claim", "step 6: both queries find the expected convention on the other board", all(q["top_is_expected"] and q["top_board_is_second_board"] for q in g["queries"]), ", ".join(f"{q['attempts']} attempts" for q in g["queries"]))
        chk("claim", "step 6: an identity without access to the second board does not see it", not any(r["board_id"] == g["second_board_id"] for r in g["recaller_first_board_only_view"]["data"]["results"]), "")


def check_crash(state: Path) -> None:
    a, b, d = load(state, "step7/killA.json"), load(state, "step7/killB.json"), load(state, "step7/decision-board-check.json")
    if a:
        chk("claim", "Kill A: the uncommitted draft is gone and the committed baseline is present", a["draft_absent"] and a["earlier_decisions_all_present"] and a["decisions_before"] == a["decisions_after"] == 3, f"{a['decisions_before']} -> {a['decisions_after']}")
        chk("observation", "Kill A: the old session cannot be committed after the restart (session_not_found)", a["late_commit_of_old_session"].get("error_code") == "session_not_found", str(a["late_commit_of_old_session"].get("error_code")))
        chk("claim", "Kill A resume: after a new session replays all six decisions, each exists exactly once", a["resume"]["every_slug_exactly_once"] and not a["resume"]["duplicates"], str(a["resume"]["result"].get("hint_operation_by_slug")))
        chk("claim", "Kill A: the board accepted a write within the writer-lock TTL plus 90 s", a["write_probe_after_restart"]["first_success_after_probe_start_s"] is not None and a["write_probe_after_restart"]["writes_resumed_seconds_after_kill"] <= TTL_S + 90, str(a["write_probe_after_restart"]["writes_resumed_seconds_after_kill"]))
    if b:
        chk("claim", "Kill B: every acknowledged commit is present after the restart", b["acknowledged_missing"] == [] and b["acknowledged_and_present"] == b["acknowledged_commits"] > 0, f"{b['acknowledged_and_present']} of {b['acknowledged_commits']} present")
        chk("claim", "Kill B: commits were in flight at the kill (parallel workers)", b["workers"] >= 2, f"{len(b['in_flight_at_kill'])} in flight")
        chk("claim", "Kill B retry: after the in-flight commits are committed again, no slug exists twice", b["retry"]["every_started_slug_exactly_once"] and not b["retry"]["duplicates"], f"retried {len(b['retry']['retried'])}")
        chk("claim", "Kill B: the board accepted a write within the writer-lock TTL plus 90 s", b["write_probe_after_restart"]["first_success_after_probe_start_s"] is not None and b["write_probe_after_restart"]["writes_resumed_seconds_after_kill"] <= TTL_S + 90, str(b["write_probe_after_restart"]["writes_resumed_seconds_after_kill"]))
    if d:
        chk("claim", "the decision board holds no synthetic crash-test decision and was not changed by step 7", d["unchanged"] and not d["synthetic_slugs_on_decision_board"], f"{d['decisions_before_step7']} before, {d['decisions_after_step7']} after")


def check_read(state: Path) -> None:
    dr = load(state, "step8/direct-read.json")
    if dr:
        names = set(dr["boards"])
        chk("claim", "step 8: the decision board and both crash boards were read", {"decision_board", "crash_test_board_a", "crash_test_board"} <= names, ", ".join(sorted(names)))
        for name, e in dr["boards"].items():
            c = e["comparison"]
            chk("claim", f"step 8 {name}: the direct read opens read-only, matches Pulse's counts and writes nothing", "skipped" not in c and c["nodes_match"] and c["edges_match"] and e["data_files_unchanged_by_read"], f"nodes {sum(c.get('reader_nodes', {}).values())}")


def check_restore(state: Path, required: bool) -> None:
    files = sorted((state / "step9").glob("backup-restore-*.json")) if (state / "step9").exists() else []
    if not files:
        if required:
            chk("claim", "step 9 ran", False, "required and missing")
        else:
            results.append({"kind": "skip", "name": "step 9 (backup and restore) did not run", "ok": True, "detail": "NOT RUN: it needs Linux, or macOS with Docker. Nothing about backup or restore is asserted."})
        return
    runs = {f.stem.replace("backup-restore-", ""): json.loads(f.read_text()) for f in files}
    done = {k: r for k, r in runs.items() if r["backup"]["ok"] and r["restore"]["ok"]}
    chk("claim", "step 9: one platform completed backup and restore", bool(done), ", ".join(f"{k}: backup {r['backup']['ok']}" for k, r in runs.items()))
    for k, r in done.items():
        chk("claim", f"step 9 {k}: original, copy and restored folder verify clean", all(r[x]["exit_code"] == 0 and r[x]["output"]["clean"] for x in ("verify_original", "verify_copy_before_backup", "verify_restored")), "")
        chk("claim", f"step 9 {k}: counts match and the original was not touched", r["counts_match"] == {"original_vs_copy": True, "original_vs_restored": True} and r["original_untouched"], "")
        dec = r.get("decisions", {})
        chk("claim", f"step 9 {k}: the restored store holds the same decisions, with the same text and citations, as the original", dec.get("original_vs_restored") is True and dec.get("original_vs_copy") is True and dec.get("original_count", 0) > 0,
            f"{dec.get('restored_count')} decisions compared by title, text, source reference and quote")


def check_closeout(state: Path, required: bool) -> None:
    if not required and not list((state / "step9").glob("backup-restore-*.json")):
        return  # the scoreboard builder needs the step 9 result. Without it the closeout was skipped, and check_restore reports that.
    c = load(state, "closeout-result.json")
    if c:
        chk("claim", "the scoreboard builder reads the live outputs of all steps", {"versions", "decisions", "recall", "reversal", "kill_a", "kill_b", "node_counts"} <= set(c), f"{len(c)} sections")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--require-step9", action="store_true")
    a = ap.parse_args()
    state = Path(a.state)
    for fn in (check_setup, check_recording, check_spec_flow, check_roles, check_arms, check_reversal, check_global, check_crash, check_read):
        fn(state)
    check_restore(state, a.require_step9)
    check_closeout(state, a.require_step9)
    width = max(len(r["name"]) for r in results)
    for r in results:
        print(f"{'SKIP' if r['kind'] == 'skip' else 'PASS' if r['ok'] else 'FAIL'}  {r['kind']:<11} {r['name']:<{width}}  {r['detail']}")
    failed = [r for r in results if not r["ok"]]
    (state / "assert-report.json").write_text(json.dumps({"checks": len(results), "failed": len(failed), "results": results}, indent=2) + "\n")
    skipped = sum(r["kind"] == "skip" for r in results)
    print(f"{len(results) - len(failed) - skipped} of {len(results) - skipped} checks passed" + (f", {skipped} skipped" if skipped else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
