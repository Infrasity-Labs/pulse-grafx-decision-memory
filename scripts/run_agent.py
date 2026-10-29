"""Run one headless Claude Code session as a Pulse agent and save the transcript.

The agent key is read from agents/.keys.local (or PULSE_KEYS_FILE) and handed to the child process
through an environment variable that the MCP config expands. It is never written to disk or printed.
Machine-local absolute paths are replaced in the saved files.

Usage:
  python scripts/run_agent.py ROLE PROMPT_FILE OUT_DIR [--add-dir DIR] [--tools Read,Grep,Glob] [--timeout S]
Writes OUT_DIR/transcript.jsonl (stream-json) and OUT_DIR/result.json (final result + run facts).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from pulse_mcp import load_key  # noqa: E402


def scrub(text: str) -> str:
    return text.replace(str(ROOT), "<repo>").replace(str(Path.home()), "<home>")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("role")
    ap.add_argument("prompt_file")
    ap.add_argument("out_dir")
    ap.add_argument("--add-dir", action="append", default=[])
    ap.add_argument("--tools", default="Read,Grep,Glob")
    ap.add_argument("--timeout", type=int, default=1500)
    ap.add_argument("--model", default=os.environ.get("AGENT_MODEL", ""))
    a = ap.parse_args()

    role = a.role.lower()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    workdir = ROOT / "agents" / role
    cfg = ROOT / "agents" / f"mcp.{role}.example.json"
    prompt = Path(a.prompt_file).read_text()

    env = dict(os.environ)
    env[f"PULSE_KEY_{role.upper()}"] = load_key(role)
    env["PYTHONWARNINGS"] = "ignore"
    cmd = [
        "claude", "-p", "--output-format", "stream-json", "--verbose",
        "--mcp-config", str(cfg), "--strict-mcp-config",
        "--setting-sources", "project",
        "--no-session-persistence",
        "--permission-mode", "dontAsk",
        "--tools", a.tools,
        "--allowedTools", "mcp__pulse", *[t for t in a.tools.split(",") if t],
    ]
    for d in a.add_dir:
        cmd += ["--add-dir", str((ROOT / d).resolve())]
    if a.model:
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
        "model": model,
        "tool_call_count": len(tool_calls),
        "tool_calls": tool_calls,
        "final": final,
        "stderr_tail": scrub(proc.stderr[-1500:]),
    }
    (out / "result.json").write_text(scrub(json.dumps(result, indent=2)))
    print(f"{role}: exit={proc.returncode} seconds={secs} tool_calls={len(tool_calls)} model={model}")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
