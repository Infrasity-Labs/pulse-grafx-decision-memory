"""Step 7: crash tests. SIGKILL of the okto-pulse serve process on Linux or macOS.

Every crash write goes to its own crash board. The decision board is never written to, and the step records that it is unchanged.

Kill A: on crash board A, commit three baseline decisions, then begin a consolidation, add three draft candidates and SIGKILL
        before commit. Restart. Expect: the draft is absent, the baseline remains.
        Resume (application recovery, not a Pulse feature): a new Recorder session replays all six decisions in one consolidation.
        Expect: each decision exists exactly once afterwards.
Kill B: three workers each commit one Decision per consolidation on crash board B and log each acknowledgement. SIGKILL at a
        random moment, restart, compare acknowledged commits with the graph. Expect: every acknowledged commit is present.
        Unacknowledged ones may or may not be.
        Retry (application recovery): each commit that was in flight at the kill is committed again by a new session.
        Expect: no slug exists twice afterwards.

Exit code 3 if an acknowledged commit is missing after restart (a stop-and-ask condition). Exit code 4 if a resume or retry
left a duplicate, or if the decision board changed.
Output in demo-state/step7/: killA.json, killB.json, decision-board-check.json, restart-log-killA.txt, restart-log-killB.txt, burst-ack-w1..w3.log
Env: KILLB_WORKERS (default 3), CRASH_PROBE_TIMEOUT (seconds to wait for writes after Kill B, default 600)
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import stepslib as sl  # noqa: E402
from probe_writable import probe  # noqa: E402
from setup_board import wait_until_healthy  # noqa: E402

OUT = sl.STATE / "step7"
PORT = os.environ.get("PULSE_API_PORT", "8100")
LOG = ROOT / ".work" / "logs" / f"pulse-{PORT}.log"


def sh(script: str) -> str:
    r = subprocess.run([str(ROOT / "scripts" / script)], capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


def log_size() -> int:
    return LOG.stat().st_size if LOG.exists() else 0


def log_since(offset: int) -> str:
    with open(LOG, "rb") as f:
        f.seek(offset)
        return sl.scrub(f.read().decode(errors="replace"))


def restart(label: str, offset: int) -> dict:
    t0 = time.time()
    out = sh("start_pulse.sh")
    secs = round(time.time() - t0, 1)
    text = log_since(offset)
    keep = [ln for ln in text.splitlines() if not ln.startswith(("Loading weights", "INFO:     127.0.0.1")) and "HF Hub" not in ln]
    (OUT / f"restart-log-{label}.txt").write_text("\n".join(keep) + "\n")
    flagged = [ln for ln in keep if any(w in ln.lower() for w in ("recover", "wal", "checkpoint", "quarantine", "stale", "lock", "error", "warn"))]
    return {"start_script_output": out, "seconds_to_ready": secs, "log_lines": len(keep), "flagged_log_lines": flagged[:40]}


def decisions(m: sl.Mcp, board_id: str, prefix: str) -> list[str]:
    rows = sl.cypher(m, board_id, "MATCH (n:Decision) WHERE n.source_artifact_ref STARTS WITH $p RETURN n.source_artifact_ref AS ref", {"p": prefix})
    return sorted(r[0].rsplit(":", 1)[-1] for r in rows)


def slug_counts(m: sl.Mcp, board_id: str, prefix: str) -> dict[str, dict]:
    """Per slug: how many Decision nodes carry it, how many of them are not superseded, and which slug superseded it."""
    rows = sl.cypher(m, board_id, "MATCH (n:Decision) WHERE n.source_artifact_ref STARTS WITH $p RETURN n.id AS id, n.source_artifact_ref AS ref, n.superseded_by AS sup", {"p": prefix})
    slug_of_id = {r[0]: r[1].rsplit(":", 1)[-1] for r in rows}
    out: dict[str, dict] = {}
    for _id, ref, sup in rows:
        e = out.setdefault(ref.rsplit(":", 1)[-1], {"nodes": 0, "active": 0, "superseded_by": None})
        e["nodes"] += 1
        e["active"] += 0 if sup else 1
        if sup:
            e["superseded_by"] = slug_of_id.get(sup, sup)
    return out


def make_crash_board(info: dict, name: str, description: str, spec_title: str) -> tuple[str, str]:
    """A separate board for crash writes. The Maintainer and the Recorder identities get access."""
    board = sl.rest("POST", "/boards", {"name": name, "description": description})
    for role in ("MAINTAINER", "RECORDER"):
        agent = next(a["agent_id"] for a in info["agents"] if a["role"] == role)
        sl.rest("POST", f"/agents/{agent}/boards/{board['id']}")
    spec = sl.rest("POST", f"/boards/{board['id']}/specs", {"title": spec_title, "description": "Anchor for crash-test commits.", "delivery_context": "greenfield"})["id"]
    return board["id"], spec


def candidate(spec: str, slug: str, title: str, content: str) -> dict:
    return {"candidate_id": slug, "node_type": "Decision", "title": title, "content": content, "context": "crash test", "justification": "synthetic",
            "source_artifact_ref": f"final_report:{spec}:decision:{slug}", "source_confidence": 0.9}


def commit_decisions(role: str, board: str, spec: str, items: list[tuple[str, str, str]], summary: str) -> dict:
    """A new session as role: begin, add every (slug, title, content), propose, commit. Retries while Pulse answers with a lock or a settling graph."""
    last: dict = {}
    for attempt in range(1, 31):
        with sl.Mcp(role) as m:
            b = m.call("okto_pulse_kg_begin_consolidation", {"board_id": board, "artifact_type": "spec", "artifact_id": spec, "raw_content": summary, "deterministic_candidates": []})
            if not b["ok"]:
                last = {"stage": "begin", "envelope": b["envelope"]}
            else:
                sid = b["data"]["session_id"]
                for slug, title, content in items:
                    m.call("okto_pulse_kg_add_node_candidate", {"session_id": sid, "candidate": candidate(spec, slug, title, content)})
                hints = m.call("okto_pulse_kg_propose_reconciliation", {"session_id": sid})
                c = m.call("okto_pulse_kg_commit_consolidation", {"session_id": sid, "summary_text": summary})
                hint_ops = {h["candidate_id"]: h["operation"] for h in (hints["data"] or {}).get("hints", [])} if hints["ok"] else {}
                if c["ok"]:
                    return {"attempts": attempt, "hint_operation_by_slug": hint_ops, "commit": {k: (c["data"] or {}).get(k) for k in ("status", "nodes_added", "nodes_updated", "nodes_superseded", "nodes_noop", "nodes_merged")}}
                last = {"stage": "commit", "envelope": c["envelope"], "hint_operation_by_slug": hint_ops}
                m.call("okto_pulse_kg_abort_consolidation", {"session_id": sid, "reason": "commit refused, retrying"})
        text = json.dumps(last, default=str)
        if not any(t in text for t in ("lock_contention", "kg_graph_degraded", "recovery_needed")):
            break
        time.sleep(10)
    return {"attempts": attempt, "failed": last}


BASELINE = [(f"killa-base-{n}", f"Kill A baseline decision {n}", f"Committed before the kill. Synthetic decision {n} for the crash test.") for n in (1, 2, 3)]
DRAFTS = [(f"killa-draft-{n}", f"Kill A draft decision {n}", f"Added to an open session before the kill. Synthetic decision {n}.") for n in (1, 2, 3)]


def kill_a(info: dict) -> dict:
    b, spec = make_crash_board(info, "Crash test board A (open session)", "Kill A writes land here so the decision board stays clean.", "Kill A baseline and drafts")
    health_log = wait_until_healthy(b)
    prefix = f"final_report:{spec}:decision:"
    base = commit_decisions("RECORDER", b, spec, BASELINE, "Kill A baseline: three committed decisions.")
    with sl.Mcp("RECORDER") as m:
        before = decisions(m, b, prefix)
        ses = m.call("okto_pulse_kg_begin_consolidation", {"board_id": b, "artifact_type": "spec", "artifact_id": spec, "raw_content": "kill A draft", "deterministic_candidates": []})
        sid = ses["data"]["session_id"]
        adds = [m.call("okto_pulse_kg_add_node_candidate", {"session_id": sid, "candidate": candidate(spec, slug, title, content)}) for slug, title, content in DRAFTS]
        candidates_accepted = sum(1 for a in adds if a["ok"])
    with sl.Mcp("MAINTAINER") as m:
        health_before = m.call("okto_pulse_kg_health", {"board_id": b})
    offset = log_size()
    kill_epoch = time.time()
    kill_out = sh("kill9_pulse.sh")
    time.sleep(1)
    restart_info = restart("killA", offset)
    with sl.Mcp("MAINTAINER") as m:
        after = decisions(m, b, prefix)
        late_commit = m.call("okto_pulse_kg_commit_consolidation", {"session_id": sid, "summary_text": "late commit after restart"})
        health = m.call("okto_pulse_kg_health", {"board_id": b, "profile": "full"})
        after_commit_attempt = decisions(m, b, prefix)
    status = sh("status.sh")
    write_probe = probe(b, timeout=120, interval=5, kill_epoch=kill_epoch, quiet=True)
    # Resume. Pulse discards the open session. A new Recorder session replays all six decisions. Whether that leaves each one exactly once is
    # decided by Pulse's reconciliation, and it is recorded as found.
    resume = commit_decisions("RECORDER", b, spec, BASELINE + DRAFTS, "Resume after Kill A: all six decisions replayed by a new session.")
    with sl.Mcp("MAINTAINER") as m:
        counts = slug_counts(m, b, prefix)
    wanted = [slug for slug, _, _ in BASELINE + DRAFTS]
    res = {
        "board_id": b, "baseline_commit": base,
        "decisions_before": len(before), "decisions_after": len(after), "earlier_decisions_all_present": set(before) <= set(after),
        "draft_candidates_accepted_before_kill": candidates_accepted,
        "draft_present_after_restart": [s for s in after if s.startswith("killa-draft")],
        "draft_absent": not any(s.startswith("killa-draft") for s in after),
        "late_commit_of_old_session": late_commit["envelope"],
        "draft_present_after_late_commit_attempt": [s for s in after_commit_attempt if s.startswith("killa-draft")],
        "kill_output": kill_out, "restart": restart_info,
        "health_log_new_board": health_log,
        "health_before_kill": health_before["envelope"], "health_after_restart": health["envelope"], "status_after_restart": status,
        "write_probe_after_restart": write_probe,
        "resume": {
            "who": "a new RECORDER session (application logic, not a Pulse feature)", "replayed": wanted, "result": resume,
            "nodes_per_slug_after": {s: counts.get(s) for s in wanted},
            "every_slug_exactly_once": all(counts.get(s, {}).get("nodes") == 1 for s in wanted),
            "every_slug_has_one_active_node": all(counts.get(s, {}).get("active") == 1 for s in wanted),
            "superseded_by_another_decision": {s: counts[s]["superseded_by"] for s in wanted if counts.get(s, {}).get("superseded_by")},
            "duplicates": sorted(s for s in wanted if counts.get(s, {}).get("nodes", 0) > 1),
        },
    }
    sl.save_json(OUT / "killA.json", res)
    return res


def burst_text(slug: str) -> tuple[str, str]:
    """Title and content the Kill B workers wrote for a slug, so a retry is the same decision."""
    worker, i = re.fullmatch(r"burst-(w\d+)-(\d+)", slug).groups()
    return f"Burst decision {worker} {int(i):04d}", f"Synthetic decision {worker} {int(i)} for the crash test."


def decision_board_slugs(info: dict) -> list[str]:
    with sl.Mcp("MAINTAINER") as m:
        return decisions(m, info["board_id"], f"final_report:{info['anchor_spec_id']}:decision:")


def kill_b(info: dict) -> dict:
    b, spec = make_crash_board(info, "Crash test board B (burst)", "Kill B commits land here so the decision board stays clean.", "Burst commits")
    health_log = wait_until_healthy(b)
    workers_n = int(os.environ.get("KILLB_WORKERS", "3"))
    logs = [OUT / f"burst-ack-w{n}.log" for n in range(1, workers_n + 1)]
    for lg in logs:
        lg.unlink(missing_ok=True)
        lg.touch()
    procs = [subprocess.Popen([sys.executable, str(ROOT / "scripts/kill_b_burst.py"), b, spec, str(lg), f"w{n}", "500"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(os.environ))
             for n, lg in enumerate(logs, 1)]
    t0 = time.time()
    while not any('"ev": "ack"' in lg.read_text() for lg in logs):
        if time.time() - t0 > 120 or all(pr.poll() is not None for pr in procs):
            break
        time.sleep(0.2)
    delay = round(random.SystemRandom().uniform(8.0, 30.0), 2)
    time.sleep(delay)
    offset = log_size()
    kill_epoch = time.time()
    kill_out = sh("kill9_pulse.sh")
    terminated = 0
    for pr in procs:
        try:
            pr.wait(timeout=20)
        except subprocess.TimeoutExpired:  # the worker is blocked on the dead connection and never logs an error
            pr.kill()
            terminated += 1
    time.sleep(1)
    restart_info = restart("killB", offset)
    events = [json.loads(ln) for lg in logs for ln in lg.read_text().splitlines() if ln.strip()]
    acked = [e["slug"] for e in events if e["ev"] == "ack"]
    started = [e["slug"] for e in events if e["ev"] == "start"]
    errors = [e for e in events if e["ev"] == "error"]
    retries = sum(1 for e in events if e["ev"] == "retry")
    with sl.Mcp("MAINTAINER") as m:
        present = decisions(m, b, f"final_report:{spec}:decision:")
        health = m.call("okto_pulse_kg_health", {"board_id": b, "profile": "full"})
    in_flight = [s for s in started if s not in acked]
    write_probe = probe(b, timeout=int(os.environ.get("CRASH_PROBE_TIMEOUT", "600")), interval=10, kill_epoch=kill_epoch, quiet=True)
    with sl.Mcp("MAINTAINER") as m:
        health_after_writes = m.call("okto_pulse_kg_health", {"board_id": b, "profile": "full"})
    # Retry. Every commit that was in flight at the kill is committed again by a new session. Whether that leaves each slug exactly once
    # is decided by Pulse's reconciliation, and it is recorded as found.
    prefix = f"final_report:{spec}:decision:"
    with sl.Mcp("MAINTAINER") as m:
        present_before_retry = set(decisions(m, b, prefix))
    retry_items = [(slug, *burst_text(slug)) for slug in in_flight]
    retry = commit_decisions("RECORDER", b, spec, retry_items, "Retry after Kill B: the commits that were in flight.") if retry_items else {"skipped": "nothing was in flight"}
    with sl.Mcp("MAINTAINER") as m:
        counts = slug_counts(m, b, prefix)
    res = {
        "board_id": b, "workers": workers_n, "retries_on_busy": retries, "workers_terminated_by_script_after_20s": terminated, "random_delay_s_after_first_ack": delay, "acknowledged_commits": len(acked), "commits_started": len(started),
        "present_after_restart": len(present),
        "acknowledged_and_present": len(set(acked) & set(present)),
        "acknowledged_missing": sorted(set(acked) - set(present)),
        "unacknowledged_but_present": sorted(set(present) - set(acked)),
        "in_flight_at_kill": in_flight, "in_flight_present": sorted(set(in_flight) & set(present)),
        "worker_errors": errors, "kill_output": kill_out, "restart": restart_info,
        "health_after_restart": health["envelope"], "health_log_new_board": health_log, "write_probe_after_restart": write_probe,
        "health_after_writes_resumed": health_after_writes["envelope"],
        "retry": {
            "who": "a new RECORDER session (application logic, not a Pulse feature)", "retried": in_flight, "in_flight_already_present_before_retry": sorted(set(in_flight) & present_before_retry),
            "result": retry, "nodes_per_slug_after": {s: counts.get(s) for s in started},
            "every_started_slug_exactly_once": all(counts.get(s, {}).get("nodes") == 1 for s in started),
            "every_started_slug_has_one_active_node": all(counts.get(s, {}).get("active") == 1 for s in started),
            "superseded_by_another_decision": {s: counts[s]["superseded_by"] for s in started if counts.get(s, {}).get("superseded_by")},
            "duplicates": sorted(s for s in started if counts.get(s, {}).get("nodes", 0) > 1),
        },
    }
    sl.save_json(OUT / "killB.json", res)
    return res


def main() -> int:
    info = sl.board_info()
    OUT.mkdir(parents=True, exist_ok=True)
    with sl.StepTimer("step7"):
        before_board = decision_board_slugs(info)
        a = kill_a(info)
        print(f"Kill A: draft_absent={a['draft_absent']} earlier_present={a['earlier_decisions_all_present']} "
              f"decisions {a['decisions_before']} -> {a['decisions_after']}; resume: every slug once={a['resume']['every_slug_exactly_once']}")
        b = kill_b(info)
        print(f"Kill B: acked={b['acknowledged_commits']} acked_present={b['acknowledged_and_present']} "
              f"acked_missing={len(b['acknowledged_missing'])} unacked_present={len(b['unacknowledged_but_present'])}; retry: every slug once={b['retry']['every_started_slug_exactly_once']}")
        after_board = decision_board_slugs(info)
        synthetic = [s for s in after_board if re.match(r"(kill|burst|write-probe)", s)]
        check = {"decision_board_id": info["board_id"], "decisions_before_step7": len(before_board), "decisions_after_step7": len(after_board),
                 "unchanged": before_board == after_board, "synthetic_slugs_on_decision_board": synthetic}
        sl.save_json(OUT / "decision-board-check.json", check)
        print(f"decision board: {check['decisions_before_step7']} before, {check['decisions_after_step7']} after, unchanged={check['unchanged']}")
    if b["acknowledged_missing"]:
        return 3
    return 4 if (a["resume"]["duplicates"] or b["retry"]["duplicates"] or not check["unchanged"]) else 0


if __name__ == "__main__":
    sys.exit(main())
