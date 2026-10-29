"""After a crash test, retry one small commit on a board until it succeeds or a timeout passes. Logs every attempt.

Usage: python scripts/probe_writable.py BOARD_ID OUT_JSON [TIMEOUT_S] [INTERVAL_S]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import stepslib as sl  # noqa: E402


def attempt(m: sl.Mcp, board: str, spec: str, n: int) -> dict:
    slug = f"write-probe-{n:03d}"
    b = m.call("okto_pulse_kg_begin_consolidation", {"board_id": board, "artifact_type": "spec", "artifact_id": spec,
                                                    "raw_content": f"write probe {n}", "deterministic_candidates": []})
    if not b["ok"]:
        return {"slug": slug, "stage": "begin", "ok": False, "error": (b["envelope"] or {}).get("error_code")}
    sid = b["data"]["session_id"]
    m.call("okto_pulse_kg_add_node_candidate", {"session_id": sid, "candidate": {
        "candidate_id": slug, "node_type": "Decision", "title": f"Write probe {n}", "content": "Probe after a crash test.", "context": "crash test",
        "justification": "synthetic", "source_artifact_ref": f"final_report:{spec}:decision:{slug}", "source_confidence": 0.9}})
    c = m.call("okto_pulse_kg_commit_consolidation", {"session_id": sid, "summary_text": f"write probe {n}"})
    err = (c["envelope"] or {}).get("error_code") if not c["ok"] else None
    if not c["ok"]:
        m.call("okto_pulse_kg_abort_consolidation", {"session_id": sid, "reason": "write probe refused"})
    return {"slug": slug, "stage": "commit", "ok": c["ok"], "error": err, "status": (c["data"] or {}).get("status") if c["ok"] else None}


def probe(board: str, timeout: int = 600, interval: int = 10, kill_epoch: float | None = None, quiet: bool = False) -> dict:
    """Retry one small commit until it succeeds or the timeout passes. Returns the attempt log.

    kill_epoch (time.time() of a SIGKILL) lets the result say how long after the kill writes resumed."""
    specs = sl.rest("GET", f"/boards/{board}/specs")
    spec = (specs if isinstance(specs, list) else specs.get("items"))[0]["id"]
    log, t0, n, success_epoch = [], time.time(), 0, None
    with sl.Mcp("MAINTAINER") as m:
        while time.time() - t0 < timeout:
            n += 1
            r = attempt(m, board, spec, n)
            r["t_s"] = round(time.time() - t0)
            log.append(r)
            if not quiet:
                print(r)
            if r["ok"]:
                success_epoch = time.time()
                break
            time.sleep(interval)
    return {"board_id": board, "timeout_s": timeout, "first_success_after_probe_start_s": next((r["t_s"] for r in log if r["ok"]), None),
            "writes_resumed_seconds_after_kill": round(success_epoch - kill_epoch, 1) if success_epoch and kill_epoch else None,
            "writer_lock_default_ttl_seconds": 300, "attempts": log}


def main() -> int:
    board, out = sys.argv[1], Path(sys.argv[2])
    timeout = int(sys.argv[3]) if len(sys.argv) > 3 else 600
    interval = int(sys.argv[4]) if len(sys.argv) > 4 else 15
    res = probe(board, timeout, interval)
    sl.save_json(out, res)
    return 0 if res["first_success_after_probe_start_s"] is not None else 1


if __name__ == "__main__":
    sys.exit(main())
