"""A scripted stand-in for a Claude Code session: fixed tool calls, no LLM.

ScriptedSession opens one MCP session for a role, forwards every call to Pulse, and writes a transcript in the same
stream-json shape that scripts/run_agent.py saves for a real session. The scorers (step04's score(), build_closeout's
find_contradiction_counts(), the tests) read that shape, so they run unchanged on a scripted run.

The model field of a scripted transcript is SCRIPTED_MODEL. A scripted run is never presented as an agent run: it checks
what Pulse and Grafx do with a fixed sequence of calls. It says nothing about what an agent would choose to do.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import stepslib as sl

SCRIPTED_MODEL = "scripted-agent (no LLM)"
PREFIX = "mcp__pulse__"


class ScriptedSession:
    def __init__(self, role: str, out_dir: Path):
        self.role = role.lower()
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.mcp = sl.Mcp(role.upper())
        self.events = [{"type": "system", "subtype": "init", "model": SCRIPTED_MODEL, "tools": [], "mcp_servers": [{"name": "pulse", "status": "connected"}]}]
        self.tool_calls: list[str] = []
        self.t0 = time.time()

    def call(self, tool: str, args: dict | None = None) -> dict:
        args = args or {}
        uid = f"scripted_{len(self.tool_calls) + 1:04d}"
        self.tool_calls.append(PREFIX + tool)
        self.events.append({"type": "assistant", "message": {"model": SCRIPTED_MODEL, "role": "assistant",
                            "content": [{"type": "tool_use", "id": uid, "name": PREFIX + tool, "input": args}]}})
        try:
            r = self.mcp.call(tool, args)
        except Exception as exc:  # a tool-level exception (for example a rejected argument) is data too
            r = {"ok": False, "data": None, "envelope": {"outcome": "error", "error_code": type(exc).__name__, "message": str(exc)[:500]}}
        self.events.append({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": uid, "content": json.dumps(r["envelope"], default=str)}]}})
        return r

    def finish(self, final: dict) -> dict:
        seconds = round(time.time() - self.t0, 1)
        result_event = {"type": "result", "subtype": "success", "is_error": False, "result": json.dumps(final), "num_turns": len(self.tool_calls)}
        self.events.append({"type": "assistant", "message": {"model": SCRIPTED_MODEL, "role": "assistant", "content": [{"type": "text", "text": json.dumps(final)}]}})
        self.events.append(result_event)
        (self.out / "transcript.jsonl").write_text(sl.scrub("\n".join(json.dumps(e, default=str) for e in self.events)) + "\n")
        result = {"role": self.role, "exit_code": 0, "seconds": seconds, "model": SCRIPTED_MODEL, "tool_call_count": len(self.tool_calls),
                  "tool_calls": self.tool_calls, "final": result_event, "stderr_tail": ""}
        (self.out / "result.json").write_text(sl.scrub(json.dumps(result, indent=2)) + "\n")
        self.mcp.close()
        return result
