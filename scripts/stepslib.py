"""Shared helpers for the step scripts. No secrets are handled here beyond reading the keys file."""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import pulse_mcp  # noqa: E402
from gxutil import data_file_hashes, save_json, scrub  # noqa: E402,F401
from pulse_rest import rest  # noqa: E402,F401

STATE = Path(os.environ.get("DEMO_STATE", ROOT / "demo-state"))
HOME = Path(os.environ.get("PULSE_HOME", ROOT / ".work" / "pulse-home"))


def load_json(path: Path):
    return json.loads(Path(path).read_text())


def board_info() -> dict:
    return load_json(STATE / "step2" / "board.json")


def render_prompt(template: Path, out: Path, **values: str) -> str:
    text = template.read_text()
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", str(v))
    if "{{" in text:
        raise SystemExit(f"unfilled placeholder in {template.name}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return text


def parse_outcome(raw):
    """MCP tools return an envelope {outcome, data, error_code, ...}. Return (ok, data, envelope)."""
    env = raw
    if isinstance(raw, list) and raw and isinstance(raw[0], str):
        with contextlib.suppress(Exception):
            env = json.loads(raw[0])
    if isinstance(env, dict) and "outcome" in env:
        return env["outcome"] == "success", env.get("data"), env
    return True, env, env


class Mcp:
    """Sync wrapper around one MCP session for a role."""

    def __init__(self, role: str):
        self.role = role
        self._loop = asyncio.new_event_loop()
        self._cm = pulse_mcp.client(role)
        self._c = self._loop.run_until_complete(self._cm.__aenter__())

    def call(self, tool: str, args: dict | None = None):
        async def _go():
            r = await self._c.call_tool(tool, args or {}, raise_on_error=False)
            raw = r.structured_content if r.structured_content is not None else [getattr(x, "text", str(x)) for x in r.content]
            return raw, bool(r.is_error)
        raw, is_error = self._loop.run_until_complete(_go())
        ok, data, env = parse_outcome(raw)
        if is_error and ok:  # a tool-level error (for example a rejected argument) comes back as plain text, not as an outcome envelope
            env = {"outcome": "error", "error_code": "tool_error", "message": " ".join(raw) if isinstance(raw, list) else str(raw), "data": None}
            return {"ok": False, "data": None, "envelope": env}
        return {"ok": ok, "data": data, "envelope": env}

    def close(self) -> None:
        self._loop.run_until_complete(self._cm.__aexit__(None, None, None))
        self._loop.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def cypher(m: Mcp, board_id: str, q: str, params: dict | None = None, include_working: bool = False):
    args = {"board_id": board_id, "cypher": q, "include_working": include_working}
    if params:
        args["params"] = params
    r = m.call("okto_pulse_kg_query_cypher", args)
    return r["data"]["rows"] if r["ok"] else r


class StepTimer:
    """Records wall time for a step into demo-state/timings.json."""

    def __init__(self, step: str):
        self.step = step

    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, *a):
        p = STATE / "timings.json"
        t = json.loads(p.read_text()) if p.exists() else {}
        t[self.step] = round(time.time() - self.t0, 1)
        save_json(p, t)


def store_path(board_id: str) -> Path:
    """Physical Grafx store of a board, from the binding file Pulse writes next to the grafx/ folder."""
    binding = json.loads((HOME / "boards" / board_id / "graph_backend_binding.json").read_text())
    return HOME / binding["physical_path"]
