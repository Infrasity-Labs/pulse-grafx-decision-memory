"""Step 8: stop Pulse cleanly, read the board stores directly, compare with Pulse's own counts.

Boards read: the decision board and the crash-test boards of Kill A and Kill B. Nothing here writes into a store.
A SHA-256 of every data file is taken before and after to show that the read-only passes wrote nothing.
Output in demo-state/step8/.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import stepslib as sl  # noqa: E402

OUT = sl.STATE / "step8"
CLI = str(ROOT / ".venv" / "bin" / "oktografx")


def cli(*args: str) -> dict:
    p = subprocess.run([CLI, *args, "--json"], capture_output=True, text=True)
    try:
        body = json.loads(p.stdout)
    except json.JSONDecodeError:
        body = {"unparsed_stdout": p.stdout[:2000]}
    return {"args": [sl.scrub(a) for a in args], "exit_code": p.returncode, "stderr": sl.scrub(p.stderr[-800:]), "output": body}


def pulse_counts(m: sl.Mcp, board_id: str) -> dict:
    return {
        "nodes_by_type": {r[0]: r[1] for r in sl.cypher(m, board_id, "MATCH (n) RETURN labels(n)[0] AS t, count(n) AS c", include_working=True)},
        "edges_by_type": {r[0]: r[1] for r in sl.cypher(m, board_id, "MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS c", include_working=True)},
    }


def main() -> int:
    info = sl.board_info()
    crash = sl.load_json(sl.STATE / "step7" / "killB.json")["board_id"]
    boards = {"decision_board": info["board_id"], "crash_test_board": crash}
    crash_a = sl.load_json(sl.STATE / "step7" / "killA.json").get("board_id")  # absent in a run recorded before Kill A had its own board
    if crash_a:
        boards = {"decision_board": info["board_id"], "crash_test_board_a": crash_a, "crash_test_board": crash}
    OUT.mkdir(parents=True, exist_ok=True)
    with sl.StepTimer("step8"):
        counts_before = {}
        with sl.Mcp("MAINTAINER") as m:
            for name, bid in boards.items():
                counts_before[name] = pulse_counts(m, bid)
        sl.save_json(OUT / "pulse-counts-before-stop.json", counts_before)
        stop = subprocess.run([str(ROOT / "scripts/stop_pulse.sh")], capture_output=True, text=True)
        stop_out = (stop.stdout + stop.stderr).strip()
        report = {"stop_pulse": {"exit_code": stop.returncode, "output": stop_out}, "boards": {}}
        for name, bid in boards.items():
            store = sl.store_path(bid)
            hashes_before = sl.data_file_hashes(store)
            rel = str(store)
            entry = {
                "board_id": bid, "store_folder": str(store.relative_to(sl.HOME)),
                "capabilities": cli("capabilities"),
                "schema": cli("schema", rel, "--limit", "100"),
                "indexes": cli("indexes", rel, "--limit", "100"),
                "status_read_only": cli("status", rel, "--read-only"),
            }
            rdr = subprocess.run([sys.executable, str(ROOT / "scripts/read_store_counts.py"), rel, "--out", str(OUT / f"reader-{name}.json")],
                                 capture_output=True, text=True)
            reader = json.loads((OUT / f"reader-{name}.json").read_text())
            entry["reader_exit_code"] = rdr.returncode
            pulse = counts_before[name]
            if reader.get("opened"):
                rn = {k: v for k, v in reader["node_counts"].items() if v}
                re_ = {k: v for k, v in reader["rel_counts"].items() if v}
                pn = {k: v for k, v in pulse["nodes_by_type"].items() if v}
                pe = {k: v for k, v in pulse["edges_by_type"].items() if v}
                entry["comparison"] = {
                    "nodes_match": rn == pn, "edges_match": re_ == pe,
                    "reader_nodes": rn, "pulse_nodes": pn, "reader_edges": re_, "pulse_edges": pe,
                    "node_diff": {k: [rn.get(k), pn.get(k)] for k in sorted(set(rn) | set(pn)) if rn.get(k) != pn.get(k)},
                    "edge_diff": {k: [re_.get(k), pe.get(k)] for k in sorted(set(re_) | set(pe)) if re_.get(k) != pe.get(k)},
                }
            else:
                entry["comparison"] = {"skipped": "read-only open refused, see reader file", "refusal": reader.get("refused")}
            entry["data_files_unchanged_by_read"] = sl.data_file_hashes(store) == hashes_before
            entry["data_file_count_hashed"] = len(hashes_before)
            report["boards"][name] = entry
        sl.save_json(OUT / "direct-read.json", report)
    for name, e in report["boards"].items():
        c = e["comparison"]
        print(f"{name}: reader_exit={e['reader_exit_code']} nodes_match={c.get('nodes_match')} edges_match={c.get('edges_match')} unchanged={e['data_files_unchanged_by_read']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
