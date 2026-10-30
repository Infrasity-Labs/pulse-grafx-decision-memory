"""Run one headless Claude Code session as a Pulse agent and save the transcript.

The agent key is read from agents/.keys.local (or PULSE_KEYS_FILE) and handed to the child process
through an environment variable that the MCP config expands. It is never written to disk or printed.
Machine-local absolute paths are replaced in the saved files.

The model is pinned: --model, else AGENT_MODEL, else the model in config/agent.json. It is always passed to Claude Code with --model.

Usage:
  python scripts/run_agent.py ROLE PROMPT_FILE OUT_DIR [--add-dir DIR] [--tools Read,Grep,Glob] [--mcp-resources] [--timeout S] [--model NAME]

--mcp-resources adds the two Claude Code tools that list and read MCP resources. A headless session has no way to read a resource without them, and the
Recorder and Reviewer prompts send the agent to the Pulse resource okto-pulse://workflows/kg. Without them (the 20261029T203549Z live runs) every session
reported that it could not read it and worked out the write format by trial and error.
Writes OUT_DIR/transcript.jsonl (stream-json) and OUT_DIR/result.json (final result, run facts and run_stats: tokens, cost, turns, wall time).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from pulse_mcp import load_key  # noqa: E402
from runstats import summarise  # noqa: E402


def dash_encoded(path: Path) -> str:
    """Claude Code names a project folder after the project path with every / and . turned into a dash."""
    return re.sub(r"[/.]", "-", str(path))


def scrub(text: str) -> str:
    text = text.replace(dash_encoded(ROOT), "<dash-encoded-project-path>").replace(dash_encoded(Path.home()), "<dash-encoded-home>")
    return text.replace(str(ROOT), "<repo>").replace(str(Path.home()), "<home>")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("role")
    ap.add_argument("prompt_file")
    ap.add_argument("out_dir")
    ap.add_argument("--add-dir", action="append", default=[])
    ap.add_argument("--tools", default="Read,Grep,Glob")
    ap.add_argument("--mcp-resources", action="store_true", help="also give the session ListMcpResourcesTool and ReadMcpResourceTool")
    ap.add_argument("--timeout", type=int, default=1500)
    ap.add_argument("--model", default=os.environ.get("AGENT_MODEL") or json.loads((ROOT / "config" / "agent.json").read_text())["model"])
    a = ap.parse_args()

    role = a.role.lower()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    workdir = ROOT / "agents" / role
    cfg = ROOT / "agents" / f"mcp.{role}.example.json"
    prompt = Path(a.prompt_file).read_text()

    env = dict(os.environ)
    if f"PULSE_KEY_{role.upper()}" in cfg.read_text():  # a role with no Pulse server (the answerer of the control arms) has no key
        env[f"PULSE_KEY_{role.upper()}"] = load_key(role)
    env["PYTHONWARNINGS"] = "ignore"
    tools = ",".join(t for t in [a.tools, "ListMcpResourcesTool,ReadMcpResourceTool" if a.mcp_resources else ""] if t)
    cmd = [
        "claude", "-p", "--output-format", "stream-json", "--verbose",
        "--mcp-config", str(cfg), "--strict-mcp-config",
        "--setting-sources", "project",
        "--no-session-persistence",
        "--permission-mode", "dontAsk",
        "--tools", tools,
        "--allowedTools", "mcp__pulse", *[t for t in tools.split(",") if t],
    ]
    for d in a.add_dir:
        cmd += ["--add-dir", str((ROOT / d).resolve())]
    cmd += ["--model", a.model]

    t0 = time.time()
    proc = subprocess.run(cmd, input=prompt, text=True, capture_output=True, cwd=workdir, env=env, timeout=a.timeout)
    secs = round(time.time() - t0, 1)

    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    (out / "transcript.jsonl").write_text(scrub("\n".join(lines)) + "\n")
    final, model, tool_calls = None, None, []
    for ln in lines:
        try:
            ev = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            model = ev.get("model")
        if ev.get("type") == "assistant":
            for blk in ev.get("message", {}).get("content", []):
                if blk.get("type") == "tool_use":
                    tool_calls.append(blk["name"])
        if ev.get("type") == "result":
            final = ev
    result = {
        "role": role,
        "exit_code": proc.returncode,
        "seconds": secs,
        "model_requested": a.model,
        "model": model,
        "tool_call_count": len(tool_calls),
        "tool_calls": tool_calls,
        "final": final,
        "stderr_tail": scrub(proc.stderr[-1500:]),
    }
    result["run_stats"] = summarise(result)
    result["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (out / "result.json").write_text(scrub(json.dumps(result, indent=2)))
    print(f"{role}: exit={proc.returncode} seconds={secs} tool_calls={len(tool_calls)} model={model}")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
