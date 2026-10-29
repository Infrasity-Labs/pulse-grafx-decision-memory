"""Kill B burst worker. Commits one tiny Decision per consolidation in a loop and logs every step.

Log lines (JSON, one per line, flushed and fsynced so the log survives the server being killed):
  {"ev": "start", "i": N, "slug": "...", "t": ...}   before the commit call
  {"ev": "ack",   "i": N, "slug": "...", "t": ..., "committed_at": "..."}   commit returned success + status committed
  {"ev": "error", "i": N, "slug": "...", "t": ..., "error": "..."}   any failure, then the worker stops

Several workers run at once (one process each, own MCP session), so a kill can land while commits are in flight.
A busy or retryable answer from Pulse is retried after the delay it gives; retries are counted in the log.

Usage: python scripts/kill_b_burst.py BOARD_ID SPEC_ID LOG_FILE WORKER_ID [MAX_COMMITS]
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import stepslib as sl  # noqa: E402


def main() -> int:
    board_id, spec_id, log_file = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    worker = sys.argv[4]
    max_commits = int(sys.argv[5]) if len(sys.argv) > 5 else 500
    log = open(log_file, "a", buffering=1)

    def emit(**kw):
        log.write(json.dumps({**kw, "t": time.time()}) + "\n")
        log.flush()
        os.fsync(log.fileno())

    def call(m, tool, args, i, slug):
        """Call a tool, retrying a retryable envelope a bounded number of times."""
        for attempt in range(40):
            r = m.call(tool, args)
            env = r["envelope"] if isinstance(r["envelope"], dict) else {}
            if r["ok"] or not env.get("retryable"):
                return r
            emit(ev="retry", i=i, slug=slug, tool=tool, attempt=attempt + 1)
            time.sleep(max(0.2, float((env.get("meta") or {}).get("retry_after_ms", 500)) / 1000))
        return r

    i = 0
    try:
        m = sl.Mcp("MAINTAINER")
        for i in range(1, max_commits + 1):
            slug = f"burst-{worker}-{i:04d}"
            b = call(m, "okto_pulse_kg_begin_consolidation", {"board_id": board_id, "artifact_type": "spec", "artifact_id": spec_id,
                                                            "raw_content": f"burst commit {worker} {i}", "deterministic_candidates": []}, i, slug)
            if not b["ok"]:
                emit(ev="error", i=i, slug=slug, error=f"begin: {json.dumps(b['envelope'])[:300]}")
                return 1
            sid = b["data"]["session_id"]
            a = call(m, "okto_pulse_kg_add_node_candidate", {"session_id": sid, "candidate": {
                "candidate_id": slug, "node_type": "Decision", "title": f"Burst decision {worker} {i:04d}",
                "content": f"Synthetic decision {worker} {i} for the crash test.", "context": "crash test", "justification": "synthetic",
                "source_artifact_ref": f"final_report:{spec_id}:decision:{slug}", "source_confidence": 0.9}}, i, slug)
            if not a["ok"]:
                emit(ev="error", i=i, slug=slug, error=f"add: {json.dumps(a['envelope'])[:300]}")
                return 1
            emit(ev="start", i=i, slug=slug)
            c = call(m, "okto_pulse_kg_commit_consolidation", {"session_id": sid, "summary_text": f"burst {worker} {i}"}, i, slug)
            if c["ok"] and (c["data"] or {}).get("status") == "committed":
                emit(ev="ack", i=i, slug=slug, committed_at=c["data"].get("committed_at"))
            else:
                emit(ev="error", i=i, slug=slug, error=f"commit: {json.dumps(c['envelope'])[:300]}")
                return 1
    except Exception as exc:  # connection lost when the server is killed lands here
        emit(ev="error", i=i, slug=f"burst-{worker}-{i:04d}", error=f"{type(exc).__name__}: {str(exc)[:300]}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
