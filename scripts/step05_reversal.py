"""Step 5: wait for the Maintainer's reversal note, run the Reviewer, then read the graph back directly.

Two ways to run the Reviewer:
  default    the goal-based prompt (docs/prompts/step5-reviewer.md): the Reviewer gets the note and the goal and chooses its own
             tools. The committed demo-state/step5 was recorded with the earlier prompt in docs/prompts/recorded-run-1/, which
             handed over the old slug, the query, the override JSON and the edge ids.
  --scripted a scripted client makes the fixed calls of that earlier run (the SUPERSEDE override, then the explicit contradicts
             edge). No LLM. On a note without a reason it writes nothing, which is the failing path.

Usage: python scripts/step05_reversal.py [--wait] [--scripted] [--note NOTE.json]
  --wait polls up to 1 hour for the reversal note. --note names another note, for example the no-rationale note written by
  maintainer_reverse.py --no-rationale. Its outputs go to a folder named after the note.
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


def snapshot(m: sl.Mcp, board_id: str, spec_id: str, label: str, slugs: tuple[str, str] = ("error-response-shape", "error-response-shape-v2")) -> dict:
    ref = f"final_report:{spec_id}:decision:"
    nodes = sl.cypher(m, board_id, "MATCH (n:Decision) WHERE n.source_artifact_ref STARTS WITH $p "
                      "RETURN n.id AS id, n.title AS title, n.source_artifact_ref AS ref, n.superseded_by AS superseded_by, n.superseded_at AS superseded_at",
                      {"p": ref})
    ids = {r[2].rsplit(":", 1)[-1]: r[0] for r in nodes}
    key = "error_shape_nodes" if slugs[0] == "error-response-shape" else "note_nodes"
    snap = {"label": label, "decisions_total": len(nodes), key: [r for r in nodes if r[2].rsplit(":", 1)[-1] in slugs]}
    snap["contradictions"] = m.call("okto_pulse_kg_find_contradictions", {"board_id": board_id})
    snap["supersedes_edges"] = sl.cypher(m, board_id, "MATCH (a:Decision)-[r:supersedes]->(b:Decision) RETURN a.title AS newer, b.title AS older")
    snap["contradicts_edges"] = sl.cypher(m, board_id, "MATCH (a:Decision)-[r:contradicts]->(b:Decision) RETURN a.title AS a, b.title AS b")
    for slug in slugs:
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
    ap.add_argument("--scripted", action="store_true")
    ap.add_argument("--note", default="maintainer-reversal.json")
    a = ap.parse_args()
    info = sl.board_info()
    note = OUT / a.note
    out = OUT if a.note == "maintainer-reversal.json" else OUT / Path(a.note).stem
    deadline = time.time() + 3600
    while not note.exists():
        if not a.wait or time.time() > deadline:
            print(f"waiting: no {a.note} yet. Run scripts/maintainer_reverse.py, or pass --wait to poll.")
            return 2
        time.sleep(5)
    spec = sl.load_json(note)
    slugs = (spec["reverses_slug"], spec["new_slug"])
    with sl.StepTimer("step5" if out == OUT else f"step5-{out.name}"):
        with sl.Mcp("MAINTAINER") as m:
            sl.save_json(out / "before.json", snapshot(m, info["board_id"], info["anchor_spec_id"], "before reviewer", slugs))
        if a.scripted:
            import scripted_steps

            scripted_steps.reviewer(info, out / "agent", spec)
            rc = 0
        else:
            prompt_file = out / "prompt.rendered.md"
            sl.render_prompt(ROOT / "docs/prompts/step5-reviewer.md", prompt_file, BOARD_ID=info["board_id"], SPEC_ID=info["anchor_spec_id"],
                             NOTE_PATH=os.path.relpath(note, ROOT / "agents" / "reviewer"))
            rc = subprocess.call([sys.executable, str(ROOT / "scripts/run_agent.py"), "reviewer", str(prompt_file),
                                  str(out / "agent"), "--tools", "Read", "--add-dir", os.path.relpath(OUT, ROOT), "--mcp-resources"])
        with sl.Mcp("MAINTAINER") as m:
            sl.save_json(out / "after.json", snapshot(m, info["board_id"], info["anchor_spec_id"], "after reviewer", slugs))
    print(f"reviewer_exit={rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
