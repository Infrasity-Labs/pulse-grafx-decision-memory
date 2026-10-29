"""Step 7: crash tests. SIGKILL of the okto-pulse serve process on Linux or macOS.

Kill A: begin a consolidation on the decision board, add candidates, SIGKILL before commit, restart.
        Expect: the draft is absent, earlier decisions remain.
Kill B: three workers each commit one Decision per consolidation on a separate crash-test board and logs each
        acknowledgement. SIGKILL at a random moment, restart, compare acknowledged commits with the graph.
        Expect: every acknowledged commit is present. Unacknowledged ones may or may not be.

Exit code 3 if an acknowledged commit is missing after restart (a stop-and-ask condition).
Output in demo-state/step7/: killA.json, killB.json, restart-log-killA.txt, restart-log-killB.txt, burst-ack-w1..w3.log
"""
from __future__ import annotations

import json
import os
import random
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


def kill_a(info: dict) -> dict:
    b, spec = info["board_id"], info["anchor_spec_id"]
    prefix = f"final_report:{spec}:decision:"
    with sl.Mcp("MAINTAINER") as m:
        before = decisions(m, b, prefix)
        ses = m.call("okto_pulse_kg_begin_consolidation", {"board_id": b, "artifact_type": "spec", "artifact_id": spec,
                                                           "raw_content": "kill A draft", "deterministic_candidates": []})
        sid = ses["data"]["session_id"]
        adds = [m.call("okto_pulse_kg_add_node_candidate", {"session_id": sid, "candidate": {
            "candidate_id": f"killa-{n}", "node_type": "Decision", "title": f"Kill A draft decision {n}", "content": "never committed",
            "context": "crash test", "justification": "synthetic", "source_artifact_ref": f"{prefix}killa-{n}", "source_confidence": 0.9}}) for n in (1, 2, 3)]
        candidates_accepted = sum(1 for a in adds if a["ok"])
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
    res = {
        "decisions_before": len(before), "decisions_after": len(after), "earlier_decisions_all_present": set(before) <= set(after),
        "draft_candidates_accepted_before_kill": candidates_accepted,
        "draft_present_after_restart": [s for s in after if s.startswith("killa-")],
        "draft_absent": not any(s.startswith("killa-") for s in after),
        "late_commit_of_old_session": late_commit["envelope"],
        "draft_present_after_late_commit_attempt": [s for s in after_commit_attempt if s.startswith("killa-")],
        "kill_output": kill_out, "restart": restart_info,
        "health_before_kill": health_before["envelope"], "health_after_restart": health["envelope"], "status_after_restart": status,
        "write_probe_after_restart": write_probe,
    }
    sl.save_json(OUT / "killA.json", res)
    return res


def kill_b(info: dict) -> dict:
    maint = next(a["agent_id"] for a in info["agents"] if a["role"] == "MAINTAINER")
    board = sl.rest("POST", "/boards", {"name": "Crash test board (burst)", "description": "Kill B commits land here so the decision board stays clean."})
    b = board["id"]
    sl.rest("POST", f"/agents/{maint}/boards/{b}")
    spec = sl.rest("POST", f"/boards/{b}/specs", {"title": "Burst commits", "description": "Anchor for the Kill B burst.", "delivery_context": "greenfield"})["id"]
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
    write_probe = probe(b, timeout=600, interval=10, kill_epoch=kill_epoch, quiet=True)
    with sl.Mcp("MAINTAINER") as m:
        health_after_writes = m.call("okto_pulse_kg_health", {"board_id": b, "profile": "full"})
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
    }
    sl.save_json(OUT / "killB.json", res)
    return res


def main() -> int:
    info = sl.board_info()
    OUT.mkdir(parents=True, exist_ok=True)
    with sl.StepTimer("step7"):
        a = kill_a(info)
        print(f"Kill A: draft_absent={a['draft_absent']} earlier_present={a['earlier_decisions_all_present']} "
              f"decisions {a['decisions_before']} -> {a['decisions_after']}")
        b = kill_b(info)
        print(f"Kill B: acked={b['acknowledged_commits']} acked_present={b['acknowledged_and_present']} "
              f"acked_missing={len(b['acknowledged_missing'])} unacked_present={len(b['unacknowledged_but_present'])}")
    return 3 if b["acknowledged_missing"] else 0


if __name__ == "__main__":
    sys.exit(main())
