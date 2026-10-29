"""Supplementary probe for step 4. Not part of the recall score.

The scored Recaller run showed okto_pulse_kg_get_decision_history returning nothing for sentence-length topics.
This script asks the same tool a few short topics and records exactly what comes back, so the behaviour is
documented rather than guessed. Run by the Maintainer identity after the scored run.
It also records the "Key Decisions" list. That list is a Discovery catalog intent (tool_binding
okto_pulse_kg_list_key_decisions) that the web UI runs over REST at /api/v1/discovery/intents/{id}/execute.
In 0.4.2 it is not exposed as an MCP tool, so the Recaller session could not call it.
Output: demo-state/step4/history-probe.json
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import stepslib as sl  # noqa: E402

PROBES = [
    ("password hashing", {}),
    ("password hashing", {"min_confidence": 0.0, "min_similarity": 0.0}),
    ("password", {"use_semantic": False, "min_confidence": 0.0}),
    ("Passwords", {"use_semantic": False, "min_confidence": 0.0}),
    ("bcrypt", {"use_semantic": False, "min_confidence": 0.0}),
    ("hashed", {"use_semantic": False, "min_confidence": 0.0}),
]


def sl_mcp_tool_names() -> list[str]:
    import asyncio

    async def go():
        async with sl.pulse_mcp.client("MAINTAINER") as c:
            return [t.name for t in await c.list_tools()]
    return asyncio.run(go())


def main() -> int:
    board = sl.board_info()["board_id"]
    out = []
    with sl.Mcp("MAINTAINER") as m:
        for topic, extra in PROBES:
            d = m.call("okto_pulse_kg_get_decision_history", {"board_id": board, "topic": topic, **extra})["data"] or {}
            out.append({"topic": topic, "extra_args": extra, "count": d.get("count"),
                        "titles": [x["title"] for x in d.get("decisions", [])][:3]})
    intents = sl.rest("GET", "/discovery/intents")
    key = next(i for i in intents if i["name"] == "key_decisions")
    rows = sl.rest("POST", f"/discovery/intents/{key['id']}/execute", {"board_id": board})["rows"]
    mcp_tools = [t for t in sl_mcp_tool_names() if "key_decisions" in t]
    sl.save_json(sl.STATE / "step4" / "history-probe.json", {
        "note": "Supplementary. Run by the Maintainer after the scored Recaller run. Not part of the score.", "probes": out,
        "key_decisions_intent": {"tool_binding": key["tool_binding"], "min_permission": key["min_permission"], "via": "REST discovery intent",
                                 "exposed_as_mcp_tool_in_this_install": bool(mcp_tools),
                                 "rows": [{"title": r["title"], "summary": r["summary"]} for r in rows]}})
    print(f"key_decisions intent (REST): {len(rows)} rows; exposed as MCP tool: {bool(mcp_tools)}")
    for o in out:
        print(f"{o['topic']!r} {o['extra_args']} -> count {o['count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
