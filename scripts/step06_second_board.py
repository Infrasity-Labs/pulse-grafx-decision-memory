"""Step 6: second board with three invented shared conventions, then Global Discovery queries.

The conventions are written by this script through the Maintainer identity (Full Control preset).
Queries run from the first board's context. Because cross-board delivery is asynchronous, each query is
polled until the expected board answers or a timeout passes, and the wait is recorded.
Output in demo-state/step6/: board2.json, global-discovery.json
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import stepslib as sl  # noqa: E402
from setup_board import wait_until_healthy  # noqa: E402

OUT = sl.STATE / "step6"

# Invented for this demo. They are labelled as invented in the node content.
CONVENTIONS = [
    ("health-endpoint", "Every service exposes GET /healthz that returns status ok",
     "Every service in the platform exposes GET /healthz. It returns HTTP 200 with the body {\"status\": \"ok\"} and does not touch the database. Invented shared convention for this demo."),
    ("iso-dates", "API dates are ISO 8601 strings in UTC",
     "Every API sends and accepts dates as ISO 8601 strings in UTC, for example 2026-10-29T06:00:00Z. Invented shared convention for this demo."),
    ("page-size-cap", "List endpoints cap the page size at 100 items",
     "Every list endpoint accepts a limit parameter and caps it at 100 items. A larger value is lowered to 100. Invented shared convention for this demo."),
]

# Fixed before the first run. expected_slug is the convention on board 2 that should answer.
GLOBAL_QUERIES = [
    ("What is the largest number of items a list endpoint may return in one page?", "page-size-cap"),
    ("How can a monitor check that a service is alive?", "health-endpoint"),
]


def global_query(m: sl.Mcp, nl: str, board_id: str = "") -> dict:
    return m.call("okto_pulse_kg_query_global", {"board_id": board_id, "nl_query": nl, "top_k": 5})


def main() -> int:
    info = sl.board_info()
    b1 = info["board_id"]
    maint = next(a["agent_id"] for a in info["agents"] if a["role"] == "MAINTAINER")
    with sl.StepTimer("step6"):
        board2 = sl.rest("POST", "/boards", {"name": "Shared Conventions (invented)", "description": "Second board. Three invented platform conventions for the Global Discovery step."})
        b2 = board2["id"]
        sl.rest("POST", f"/agents/{maint}/boards/{b2}")
        spec2 = sl.rest("POST", f"/boards/{b2}/specs", {"title": "Platform conventions (invented)", "description": "Anchor spec for three invented conventions.", "delivery_context": "greenfield"})
        health_log = wait_until_healthy(b2)
        with sl.Mcp("MAINTAINER") as m:
            sid = spec2["id"]
            ses = m.call("okto_pulse_kg_begin_consolidation", {"board_id": b2, "artifact_type": "spec", "artifact_id": sid,
                                                              "raw_content": "three invented shared conventions", "deterministic_candidates": []})
            session_id = ses["data"]["session_id"]
            adds = []
            for slug, title, content in CONVENTIONS:
                adds.append(m.call("okto_pulse_kg_add_node_candidate", {"session_id": session_id, "candidate": {
                    "candidate_id": slug, "node_type": "Decision", "title": title, "content": content, "context": "platform conventions",
                    "justification": "invented for the demo", "source_artifact_ref": f"final_report:{sid}:decision:{slug}", "source_confidence": 0.9}}))
            commit = m.call("okto_pulse_kg_commit_consolidation", {"session_id": session_id, "summary_text": "three invented shared conventions"})
            nodes_b2 = sl.cypher(m, b2, "MATCH (n:Decision) RETURN n.id AS id, n.title AS title, n.source_artifact_ref AS ref")
            sl.save_json(OUT / "board2.json", {"board_id": b2, "anchor_spec_id": sid, "health_after_create": health_log,
                                               "commit": commit["envelope"], "decision_nodes": nodes_b2})

            results = []
            for nl, expected in GLOBAL_QUERIES:
                t0, attempts, seen = time.time(), 0, None
                while time.time() - t0 < 180:
                    attempts += 1
                    r = global_query(m, nl)
                    items = (r["data"] or {}).get("results", []) if r["ok"] else []
                    seen = r
                    if any(i.get("board_id") == b2 and (i.get("title") or "") for i in items):
                        break
                    time.sleep(5)
                items = (seen["data"] or {}).get("results", []) if seen["ok"] else []
                top = items[0] if items else None
                restricted = global_query(m, nl, board_id=b1)
                results.append({
                    "query": nl, "expected_slug": expected, "attempts": attempts, "seconds_until_result_or_timeout": round(time.time() - t0, 1),
                    "result_all_boards": seen["envelope"], "top_board_is_second_board": bool(top) and top.get("board_id") == b2,
                    "top_title": top.get("title") if top else None,
                    "expected_title": next(t for s, t, _ in CONVENTIONS if s == expected),
                    "top_is_expected": bool(top) and top.get("title") == next(t for s, t, _ in CONVENTIONS if s == expected),
                    "result_restricted_to_first_board": restricted["envelope"],
                })
            health1 = m.call("okto_pulse_kg_health", {"board_id": b1, "profile": "full"})
        with sl.Mcp("RECALLER") as rc:  # read-only identity with access to the first board only
            recaller_view = global_query(rc, GLOBAL_QUERIES[0][0])
        sl.save_json(OUT / "global-discovery.json", {
            "second_board_id": b2, "queries": results, "recaller_first_board_only_view": recaller_view["envelope"],
            "first_board_health_discovery_state": (health1["data"] or {}).get("discovery_state"),
            "first_board_global_outbox": (health1["data"] or {}).get("global_outbox_dead_letter_count"),
        })
    for r in results:
        print(f"{r['query'][:50]!r}: attempts={r['attempts']} top_is_expected={r['top_is_expected']} second_board={r['top_board_is_second_board']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
