"""Token use, cost and wall time of agent runs, read from the `result` event of each session.

run_agent.py saves the final stream-json event of a headless session in result.json. That event carries the token counts, the
cost Claude Code reports, the number of turns and two durations. This module turns it into one flat record. It reads recorded
files only and calls no model.

  python scripts/runstats.py RESULT_JSON [RESULT_JSON ...]     print one line per run
  python scripts/runstats.py --write                           write demo-state/runstats-run1.json for the three recorded agent runs
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORDED = {"recorder": "step3", "recaller": "step4", "reviewer": "step5"}


def summarise(result: dict) -> dict:
    """Flat stats of one run_agent.py result. Missing fields stay None: nothing is estimated."""
    ev = result.get("final") or {}
    u = ev.get("usage") or {}
    return {
        "role": result.get("role"), "model": result.get("model"), "exit_code": result.get("exit_code"),
        "wall_seconds": result.get("seconds"), "duration_ms": ev.get("duration_ms"), "duration_api_ms": ev.get("duration_api_ms"),
        "num_turns": ev.get("num_turns"), "tool_calls": result.get("tool_call_count"),
        "input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
        "cache_creation_input_tokens": u.get("cache_creation_input_tokens"), "cache_read_input_tokens": u.get("cache_read_input_tokens"),
        "total_cost_usd": ev.get("total_cost_usd"), "is_error": ev.get("is_error"), "stop_reason": ev.get("stop_reason"),
    }


def spread(values: list[float]) -> dict:
    vs = [v for v in values if v is not None]
    return {"n": len(vs), "mean": round(sum(vs) / len(vs), 3), "min": min(vs), "max": max(vs)} if vs else {"n": 0, "mean": None, "min": None, "max": None}


def format_row(s: dict) -> str:
    return (f"{s['role']}: model {s['model']}, wall {s['wall_seconds']} s, {s['num_turns']} turns, input {s['input_tokens']}, output {s['output_tokens']}, "
            f"cache read {s['cache_read_input_tokens']}, cache write {s['cache_creation_input_tokens']}, cost {s['total_cost_usd']} USD")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    if a.write:
        runs = {role: summarise(json.loads((ROOT / "demo-state" / step / "agent" / "result.json").read_text())) for role, step in RECORDED.items()}
        out = {"note": "Read from the result event of the three recorded agent sessions (run 1, 2026-10-29). One run each. Nothing here is a spread.", "runs": runs}
        (ROOT / "demo-state" / "runstats-run1.json").write_text(json.dumps(out, indent=2) + "\n")
        for s in runs.values():
            print(format_row(s))
        return 0
    if not a.files:
        ap.error("give result.json files or --write")
    for f in a.files:
        print(format_row(summarise(json.loads(Path(f).read_text()))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
