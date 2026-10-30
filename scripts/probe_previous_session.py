"""Where does `previous_session_id` come from on a fresh data home? Probe it and record what Pulse says. No LLM.

The Recorder's begin_consolidation returned a previous_session_id for the anchor spec although the data home was new and the Recorder
had opened no earlier session. This probe creates a spec on a scratch board, never opens a consolidation on it before the probe, and
calls begin_consolidation on it twice, once at once and once after a wait, aborting each session. It then lists the audit entries
Pulse keeps for the board (GET /api/v1/kg/boards/{board_id}/audit) to see who committed which session.

Output: demo-state/notes/previous-session-id-probe.json (under DEMO_STATE if set)
Usage: python scripts/probe_previous_session.py [--wait 40]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import stepslib as sl  # noqa: E402
from setup_board import wait_until_healthy  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait", type=int, default=40)
    a = ap.parse_args()
    info = sl.board_info()
    board = sl.rest("POST", "/boards", {"name": "Session probe board (scratch)", "description": "Scratch board for probe_previous_session.py."})
    b = board["id"]
    for role in ("MAINTAINER", "RECORDER"):
        sl.rest("POST", f"/agents/{next(x['agent_id'] for x in info['agents'] if x['role'] == role)}/boards/{b}")
    wait_until_healthy(b)
    spec = sl.rest("POST", f"/boards/{b}/specs", {"title": "Spec never touched before the probe", "description": "Scratch spec.", "delivery_context": "greenfield"})["id"]
    calls = []
    with sl.Mcp("RECORDER") as m:
        for label, delay in (("at once", 0), (f"after {a.wait} s", a.wait)):
            time.sleep(delay)
            r = m.call("okto_pulse_kg_begin_consolidation", {"board_id": b, "artifact_type": "spec", "artifact_id": spec, "raw_content": "probe", "deterministic_candidates": []})
            calls.append({"call": label, "own_session_id": r["data"]["session_id"], "previous_session_id": r["data"].get("previous_session_id")})
            m.call("okto_pulse_kg_abort_consolidation", {"session_id": r["data"]["session_id"], "reason": "probe"})
    entries = [e for e in sl.rest("GET", f"/kg/boards/{b}/audit")["entries"] if e["artifact_id"] == spec]
    recorder = next(x["agent_id"] for x in info["agents"] if x["role"] == "RECORDER")
    out = {
        "note": "The spec had no consolidation opened by this probe before the first call. Sessions the probe aborted never commit, so they are not in the audit list.",
        "begin_consolidation_calls": calls,
        "audit_entries_for_the_spec": [{"session_id": e["session_id"], "agent": "system:historical_consolidation" if e["agent_id"].startswith("system:") else ("the Recorder identity" if e["agent_id"] == recorder else e["agent_id"]),
                                        "committed_at": e["committed_at"]} for e in entries],
    }
    out["previous_session_id_is_a_system_session"] = any(c["previous_session_id"] == e["session_id"] and e["agent_id"].startswith("system:") for c in calls for e in entries)
    sl.save_json(sl.STATE / "notes" / "previous-session-id-probe.json", out)
    for c in calls:
        print(c)
    print("system sessions in the audit list:", [e["session_id"] for e in entries if e["agent_id"].startswith("system:")])
    print("previous_session_id is a system session:", out["previous_session_id_is_a_system_session"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
