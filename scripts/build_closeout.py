"""Step 10: build demo-state/closeout-result.json from the recorded outputs of steps 1 to 9.

Nothing is measured here. Every value is read from a file written by an earlier step, and a missing file is an
error, so the scoreboard cannot quietly omit a result. The README prints these numbers and no others.

Usage: python scripts/build_closeout.py [--state DIR] [--out FILE]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ERROR_SLUGS = ("error-response-shape", "error-response-shape-v2")


class MissingOutput(SystemExit):
    pass


def load(state: Path, rel: str):
    p = state / rel
    if not p.exists():
        raise MissingOutput(f"missing recorded output: {rel}. Run the step that writes it first.")
    return json.loads(p.read_text())


def final_json(result: dict) -> dict:
    txt = result["final"]["result"]
    return json.loads(txt[txt.find("{"): txt.rfind("}") + 1])


def find_contradiction_counts(transcript: Path) -> list[int]:
    pending, counts = set(), []
    for ln in transcript.read_text().splitlines():
        ev = json.loads(ln)
        msg = ev.get("message", {})
        if ev.get("type") == "assistant":
            for b in msg.get("content", []):
                if b.get("type") == "tool_use" and b["name"].endswith("find_contradictions"):
                    pending.add(b["id"])
        elif ev.get("type") == "user" and isinstance(msg.get("content"), list):
            for b in msg["content"]:
                if b.get("type") == "tool_result" and b["tool_use_id"] in pending:
                    txt = b["content"] if isinstance(b["content"], str) else "".join(x.get("text", "") for x in b["content"])
                    counts.append(json.loads(txt)["data"]["count"])
    return counts


def health_quote(env: dict) -> dict:
    d = env.get("data") or {}
    keys = ("graph_state", "discovery_state", "overall_state", "metric_status", "classification_reason", "checked_at")
    out = {k: d.get(k) for k in keys}
    out["health_issues"] = [{"code": i.get("code"), "severity": i.get("severity"), "description": i.get("description")} for i in d.get("health_issues", [])]
    out["queue_depth"], out["dead_letter_count"] = d.get("queue_depth"), d.get("dead_letter_count")
    return out


def verify_summary(v: dict) -> dict:
    o = v.get("output") or {}
    return {"exit_code": v.get("exit_code"), "clean": o.get("clean"), "verdict": o.get("verdict"), "findings": len(o.get("findings", []) or []),
            "pages_checked": o.get("pages_checked"), "records_checked": o.get("records_checked"), "index_entries_checked": o.get("index_entries_checked")}


def build(state: Path) -> dict:
    ver, emb = load(state, "step1/versions.json"), load(state, "step1/embedding.json")
    c3, d3 = load(state, "step3/citations.json"), load(state, "step3/agent/result.json")
    counts3 = {k: v for k, v in load(state, "step3/pulse-counts.json")["nodes_by_type"]}
    rec = load(state, "step4/recall-results.json")
    before, after = load(state, "step5/before.json"), load(state, "step5/after.json")
    contra = find_contradiction_counts(state / "step5" / "agent" / "transcript.jsonl")
    chain = after[f"chain_from_{ERROR_SLUGS[1]}"]["data"]
    nodes = {n[2].rsplit(":", 1)[-1]: n for n in after["error_shape_nodes"]}
    g6, b6 = load(state, "step6/global-discovery.json"), load(state, "step6/board2.json")
    ka, kb = load(state, "step7/killA.json"), load(state, "step7/killB.json")
    hp = load(state, "step4/history-probe.json")
    dr = load(state, "step8/direct-read.json")
    step9 = {p.stem.replace("backup-restore-", ""): json.loads(p.read_text()) for p in sorted((state / "step9").glob("backup-restore-*.json"))}
    if not step9:
        raise MissingOutput("missing recorded output: step9/backup-restore-*.json")
    timings = load(state, "timings.json")
    supported = next((k for k, v in step9.items() if v.get("restore", {}).get("ok")), None)

    res = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "scope": "One run on one machine. Not a general accuracy or speed claim.",
        "machine": {"platform": ver["platform"], "python": ver["python"], "claude_code": ver["claude_code"],
                    "agent_model": d3["model"], "embedding_model": emb["configured_model"], "embedding_is_stub": emb["metadata_after_load"]["is_stub"]},
        "versions": {"okto_pulse": ver["okto_pulse"], "okto_pulse_core": ver["okto_pulse_core"], "okto_grafx": ver["okto_grafx"],
                     "requires_dist_grafx_line": ver["requires_dist_grafx_line"],
                     "installed_pulse_requires_installed_grafx": ver["pulse_requires_exact_installed_grafx"]},
        "decisions": {"expected": c3["expected"], "committed_to_graph": counts3.get("Decision"), "found_by_slug": c3["found"],
                      "citations_checked_and_valid": c3["citations_ok"], "recorder_commit": final_json(d3)["commit_status"],
                      "recorder_nodes_added": final_json(d3)["nodes_added"], "recorder_edges_added": final_json(d3)["edges_added"]},
        "recall": {"questions": rec["summary"]["questions"], "agent_choice_correct": rec["summary"]["agent_choice_correct"],
                   "similar_top1_correct": rec["summary"]["similar_top1_correct"], "natural_top1_correct": rec["summary"]["natural_top1_correct"],
                   "history_top1_correct": rec["summary"]["history_top1_correct"],
                   "read_only_identity_write_probe": rec["summary"]["write_probe"],
                   "key_decisions_list_exposed_as_mcp_tool": hp["key_decisions_intent"]["exposed_as_mcp_tool_in_this_install"],
                   "key_decisions_list_rows_via_rest": len(hp["key_decisions_intent"]["rows"]),
                   "decision_history_probes_with_results": f'{sum(1 for x in hp["probes"] if x["count"])} of {len(hp["probes"])}'},
        "reversal": {
            "contradiction_pairs_before": before["contradictions"]["data"]["count"],
            "contradiction_pairs_after_supersede_only": contra[1],
            "contradiction_pairs_after_explicit_flag": contra[2],
            "pulse_flagged_a_contradiction_without_an_agent_edge": contra[1] > 0,
            "supersedence_chain_length_from_new_decision": chain["depth"],
            "chain_end_decision_id": chain["current_active"],
            "chain_end_decision_title": next(n[1] for n in after["error_shape_nodes"] if n[0] == chain["current_active"]),
            "superseded_decision_title": nodes[ERROR_SLUGS[0]][1],
            "supersedence_chain_length_when_queried_from_old_decision": after[f"chain_from_{ERROR_SLUGS[0]}"]["data"]["depth"],
            "decision_history_returned_decisions": after["decision_history_default"]["data"]["count"],
        },
        "global_discovery": {"queries": [{"query": q["query"], "found_on_other_board": q["top_board_is_second_board"], "top_is_expected": q["top_is_expected"],
                                          "attempts": q["attempts"], "seconds_until_result": q["seconds_until_result_or_timeout"]} for q in g6["queries"]],
                             "second_board_decisions": len(b6["decision_nodes"]),
                             "identity_without_access_saw_second_board": any(r["board_id"] == g6["second_board_id"] for r in g6["recaller_first_board_only_view"]["data"]["results"])},
        "kill_a": {"uncommitted_consolidation_absent_after_restart": ka["draft_absent"], "earlier_decisions_all_present": ka["earlier_decisions_all_present"],
                   "decisions_before": ka["decisions_before"], "decisions_after": ka["decisions_after"],
                   "late_commit_of_old_session": (ka["late_commit_of_old_session"].get("error_code") or ka["late_commit_of_old_session"].get("outcome")),
                   "restart_seconds_to_ready": ka["restart"]["seconds_to_ready"],
                   "board_accepted_a_new_commit_seconds_after_kill": ka["write_probe_after_restart"]["writes_resumed_seconds_after_kill"]},
        "kill_b": {"workers": kb["workers"], "acknowledged_before_kill": kb["acknowledged_commits"], "acknowledged_and_present_after_restart": kb["acknowledged_and_present"],
                   "acknowledged_missing_after_restart": len(kb["acknowledged_missing"]), "commits_started": kb["commits_started"],
                   "unacknowledged_but_present": len(kb["unacknowledged_but_present"]), "in_flight_at_kill": len(kb["in_flight_at_kill"]),
                   "retries_on_busy": kb["retries_on_busy"], "random_delay_s_after_first_ack": kb["random_delay_s_after_first_ack"],
                   "restart_seconds_to_ready": kb["restart"]["seconds_to_ready"],
                   "board_accepted_a_new_commit_seconds_after_kill": kb["write_probe_after_restart"]["writes_resumed_seconds_after_kill"],
                   "refusal_seen_while_waiting": sorted({a["error"] for a in kb["write_probe_after_restart"]["attempts"] if a["error"]}),
                   "writer_lock_default_ttl_seconds": kb["write_probe_after_restart"]["writer_lock_default_ttl_seconds"]},
        "health_after_restart_as_returned": {"kill_a": health_quote(ka["health_after_restart"]), "kill_b": health_quote(kb["health_after_restart"])},
        "node_counts": {name: {"pulse": e["comparison"].get("pulse_nodes"), "direct_read": e["comparison"].get("reader_nodes"),
                               "nodes_match": e["comparison"].get("nodes_match"), "pulse_edges": e["comparison"].get("pulse_edges"),
                               "direct_read_edges": e["comparison"].get("reader_edges"), "edges_match": e["comparison"].get("edges_match"),
                               "read_only_open_refused": "refusal" in e["comparison"], "data_files_unchanged_by_read": e["data_files_unchanged_by_read"]}
                        for name, e in dr["boards"].items()},
        "commit_history_enabled_on_board_store": {name: load(state, f"step8/reader-{name}.json").get("commit_history", {}).get("enabled") for name in dr["boards"]},
        "verify": {
            "stopped_original_store": {k: verify_summary(v["verify_original"]) for k, v in step9.items()},
            "copy_before_backup": {k: verify_summary(v["verify_copy_before_backup"]) for k, v in step9.items()},
            "restored_copy": {k: verify_summary(v["verify_restored"]) for k, v in step9.items() if v.get("verify_restored", {}).get("exit_code") is not None},
        },
        "backup_restore": {k: {"platform": v["platform"], "backup_ok": v["backup"]["ok"], "restore_ok": v.get("restore", {}).get("ok"),
                               "backup_refusal": None if v["backup"]["ok"] else v["backup"]["message"],
                               "counts_match_original_vs_restored": v["counts_match"]["original_vs_restored"],
                               "uuid_original_equals_restored": v["uuid_original_equals_restored"], "original_untouched": v["original_untouched"]}
                           for k, v in step9.items()},
        "backup_restore_exercised_on": supported,
        "step_seconds": timings,
    }
    return res


def run_info(res: dict) -> dict:
    """Who and what produced this file: run id, date, commit and tool versions. Taken from the environment of the build, never from memory.

    On GitHub Actions the run id and commit come from GITHUB_RUN_ID, GITHUB_RUN_ATTEMPT and GITHUB_SHA. Locally there is no run id (it stays null)
    and the commit is `git rev-parse HEAD`, with `commit_dirty` true when the working tree has uncommitted changes. This is kept out of build(),
    so the committed-file test compares only the values read from the recorded outputs.
    """
    def git(*args: str) -> str | None:
        p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else None

    sha = os.environ.get("GITHUB_SHA") or git("rev-parse", "HEAD")
    m, v = res["machine"], res["versions"]
    return {"recorded": True, "date": res["generated_at"], "run_id": os.environ.get("GITHUB_RUN_ID"), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "commit": sha, "commit_dirty": None if os.environ.get("GITHUB_SHA") else bool(git("status", "--porcelain")),
            "tool_versions": {"okto_pulse": v["okto_pulse"], "okto_pulse_core": v["okto_pulse_core"], "okto_grafx": v["okto_grafx"], "python": m["python"],
                              "claude_code": m["claude_code"], "agent_model": m["agent_model"], "embedding_model": m["embedding_model"], "platform": m["platform"]}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=str(ROOT / "demo-state"))
    ap.add_argument("--out")
    a = ap.parse_args()
    state = Path(a.state)
    t0 = time.time()
    build(state)  # first pass, only to time this step
    timings = json.loads((state / "timings.json").read_text())
    timings["step10"] = max(0.01, round(time.time() - t0, 2))
    (state / "timings.json").write_text(json.dumps(timings, indent=2) + "\n")
    res = build(state)
    res = {**res, "run": run_info(res)}
    out = Path(a.out) if a.out else state / "closeout-result.json"
    out.write_text(json.dumps(res, indent=2) + "\n")
    print(f"wrote {out.name}: {len(res)} top-level sections")
    return 0


if __name__ == "__main__":
    sys.exit(main())
