"""Step 5: wait for the Maintainer's reversal note, run the Reviewer, then read the graph back directly.

Usage: python scripts/step05_reversal.py [--wait]   (--wait polls up to 1 hour for the reversal note)
Output in demo-state/step5/: maintainer-reversal.json, prompt.rendered.md, agent/, before.json, after.json
The after.json file holds the raw tool results exactly as Pulse returned them to the Maintainer identity.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import stepslib as sl  # noqa: E402

OUT = sl.STATE / "step5"


def snapshot(m: sl.Mcp, board_id: str, spec_id: str, label: str) -> dict:
    ref = f"final_report:{spec_id}:decision:"
    nodes = sl.cypher(m, board_id, "MATCH (n:Decision) WHERE n.source_artifact_ref STARTS WITH $p "
                      "RETURN n.id AS id, n.title AS title, n.source_artifact_ref AS ref, n.superseded_by AS superseded_by, n.superseded_at AS superseded_at",
                      {"p": ref})
    ids = {r[2].rsplit(":", 1)[-1]: r[0] for r in nodes}
    snap = {"label": label, "decisions_total": len(nodes), "error_shape_nodes": [r for r in nodes if "error-response-shape" in r[2]]}
    snap["contradictions"] = m.call("okto_pulse_kg_find_contradictions", {"board_id": board_id})
    snap["supersedes_edges"] = sl.cypher(m, board_id, "MATCH (a:Decision)-[r:supersedes]->(b:Decision) RETURN a.title AS newer, b.title AS older")
    snap["contradicts_edges"] = sl.cypher(m, board_id, "MATCH (a:Decision)-[r:contradicts]->(b:Decision) RETURN a.title AS a, b.title AS b")
    for slug in ("error-response-shape", "error-response-shape-v2"):
        if slug in ids:
            snap[f"chain_from_{slug}"] = m.call("okto_pulse_kg_get_supersedence_chain", {"board_id": board_id, "decision_id": ids[slug]})
            snap[f"related_context_{slug}"] = m.call("okto_pulse_kg_get_related_context", {"board_id": board_id, "artifact_id": f"spec:{spec_id}", "max_depth": 1, "rel_types": "supersedes,contradicts"})
    snap["decision_history_default"] = m.call("okto_pulse_kg_get_decision_history", {"board_id": board_id, "topic": "error response shape"})
    snap["decision_history_no_semantic"] = m.call("okto_pulse_kg_get_decision_history", {"board_id": board_id, "topic": "error response shape", "use_semantic": False, "min_confidence": 0.0})
    snap["health"] = m.call("okto_pulse_kg_health", {"board_id": board_id, "profile": "full"})
    return snap


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait", action="store_true")
    a = ap.parse_args()
    info = sl.board_info()
    note = OUT / "maintainer-reversal.json"
    deadline = time.time() + 3600
    while not note.exists():
        if not a.wait or time.time() > deadline:
            print("waiting: no maintainer-reversal.json yet. Run scripts/maintainer_reverse.py, or pass --wait to poll.")
            return 2
        time.sleep(5)
    with sl.StepTimer("step5"):
        with sl.Mcp("MAINTAINER") as m:
            sl.save_json(OUT / "before.json", snapshot(m, info["board_id"], info["anchor_spec_id"], "before reviewer"))
        prompt_file = OUT / "prompt.rendered.md"
        sl.render_prompt(ROOT / "docs/prompts/step5-reviewer.md", prompt_file, BOARD_ID=info["board_id"], SPEC_ID=info["anchor_spec_id"],
                         NOTE_PATH=os.path.relpath(note, ROOT / "agents" / "reviewer"))
        rc = subprocess.call([sys.executable, str(ROOT / "scripts/run_agent.py"), "reviewer", str(prompt_file),
                              str(OUT / "agent"), "--tools", "Read", "--add-dir", os.path.relpath(OUT, ROOT)])
        with sl.Mcp("MAINTAINER") as m:
            sl.save_json(OUT / "after.json", snapshot(m, info["board_id"], info["anchor_spec_id"], "after reviewer"))
    print(f"reviewer_exit={rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
