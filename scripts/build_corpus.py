"""Build the 32-decision corpus board with the scripted client. No LLM.

Run it on a board made by step 2. It replays the 12 recorded decisions (scripted recorder), records the 10 code-derived decisions
(scripted code extras) and the 10 graph-only decisions through the Pulse spec flow with its gate (spec_flow.py), then checks the
board: exactly 32 canonical Decision nodes, each mapped to one corpus slug. The LLM arms of run_arms.py and the retrieval arm read this board.

Usage: python scripts/build_corpus.py
Output: demo-state/corpus-board.json
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import corpus  # noqa: E402
import stepslib as sl  # noqa: E402
from step04_recaller import build_node_map  # noqa: E402


def main() -> int:
    for cmd in (["step03_recorder.py", "--scripted"], ["scripted_steps.py", "code-extras"], ["spec_flow.py"]):
        rc = subprocess.call([sys.executable, str(ROOT / "scripts" / cmd[0]), *cmd[1:]])
        if rc != 0:
            print(f"{' '.join(cmd)} stopped with exit code {rc}", file=sys.stderr)
            return rc
    info = sl.board_info()
    node_map = build_node_map(info["board_id"])
    slugs = sorted(s for s in node_map.values() if s)
    expected = sorted(d["slug"] for d in corpus.all_decisions())
    res = {"board_id": info["board_id"], "canonical_decision_nodes": len(node_map), "mapped_to_a_corpus_slug": len(slugs), "expected": len(expected),
           "missing": sorted(set(expected) - set(slugs)), "duplicates": sorted({s for s in slugs if slugs.count(s) > 1}), "unmapped_nodes": [k for k, v in node_map.items() if not v]}
    res["ok"] = slugs == expected
    sl.save_json(sl.STATE / "corpus-board.json", res)
    print(f"corpus board: {res['canonical_decision_nodes']} canonical decision nodes, {res['mapped_to_a_corpus_slug']} mapped, missing {res['missing']}, duplicates {res['duplicates']}")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
