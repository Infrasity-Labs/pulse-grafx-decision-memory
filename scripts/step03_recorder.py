"""Step 3: run the Recorder session, then dump what the graph holds and check citations.

Output in demo-state/step3/: prompt.rendered.md, agent/ (transcript.jsonl, result.json), decisions-from-graph.json,
pulse-counts.json, health.json, schema-info.json, citations.json
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import stepslib as sl  # noqa: E402

OUT = sl.STATE / "step3"


def graph_dump(board_id: str, spec_id: str, out: Path) -> list[dict]:
    with sl.Mcp("MAINTAINER") as m:
        rows = sl.cypher(m, board_id,
                         "MATCH (n:Decision) WHERE n.source_artifact_ref STARTS WITH $p "
                         "RETURN n.id AS id, n.title AS title, n.content AS content, n.source_artifact_ref AS ref, "
                         "n.source_span_quote AS quote, n.graph_layer AS layer, n.created_by_agent AS agent",
                         {"p": f"final_report:{spec_id}:decision:"})
        decisions = [{"id": r[0], "title": r[1], "content": r[2], "ref": r[3], "slug": r[3].rsplit(":", 1)[-1],
                      "quote": r[4], "layer": r[5], "agent": r[6]} for r in rows]
        sl.save_json(out / "decisions-from-graph.json", sorted(decisions, key=lambda d: d["slug"]))
        edges = sl.cypher(m, board_id, "MATCH (a:Decision)-[r]->(b:Decision) RETURN type(r) AS t, a.title AS a, b.title AS b")
        sl.save_json(out / "decision-edges.json", edges)
        counts = {
            "nodes_by_type": sl.cypher(m, board_id, "MATCH (n) RETURN labels(n)[0] AS t, count(n) AS c", include_working=True),
            "edges_by_type": sl.cypher(m, board_id, "MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS c", include_working=True),
            "nodes_by_type_canonical_only": sl.cypher(m, board_id, "MATCH (n) RETURN labels(n)[0] AS t, count(n) AS c"),
        }
        sl.save_json(out / "pulse-counts.json", counts)
        sl.save_json(out / "health.json", m.call("okto_pulse_kg_health", {"board_id": board_id, "profile": "full"}))
        sl.save_json(out / "schema-info.json", m.call("okto_pulse_kg_schema_info", {"board_id": board_id}))
    return decisions


def main() -> int:
    info = sl.board_info()
    with sl.StepTimer("step3"):
        prompt_file = OUT / "prompt.rendered.md"
        sl.render_prompt(ROOT / "docs/prompts/step3-recorder.md", prompt_file,
                         BOARD_ID=info["board_id"], SPEC_ID=info["anchor_spec_id"])
        rc = subprocess.call([sys.executable, str(ROOT / "scripts/run_agent.py"), "recorder", str(prompt_file),
                              str(OUT / "agent"), "--add-dir", "app"])
        decisions = graph_dump(info["board_id"], info["anchor_spec_id"], OUT)
        crc = subprocess.call([sys.executable, str(ROOT / "scripts/check_citations.py"),
                               str(OUT / "decisions-from-graph.json"), "--out", str(OUT / "citations.json")])
    print(f"agent_exit={rc} decisions_in_graph={len(decisions)} citations_exit={crc}")
    return 0 if rc == 0 and crc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
