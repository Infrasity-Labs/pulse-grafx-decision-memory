"""Step 2: create the demo board, agent identities, and the anchor spec.

Identities use presets that ship with Pulse:
  MAINTAINER -> Full Control (the only preset with kg.operations.health.read; used by scripts, not by a session)
  RECORDER -> Spec       (kg.session.* incl. commit, kg.power.cypher)
  RECALLER -> Reporter   (read-only, kg.query.*, kg.power.natural, no kg.session.*)
  REVIEWER -> Validator  (kg.session.* incl. commit, kg.power.cypher)
Keys go to the keys file (0600) and are never printed.

Env: PULSE_API_PORT, PULSE_KEYS_FILE, PULSE_HOME. Output: demo-state/step2/board.json
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from pulse_rest import rest  # noqa: E402
import stepslib  # noqa: E402

KEYS = Path(os.environ.get("PULSE_KEYS_FILE", ROOT / "agents" / ".keys.local"))
HOME = Path(os.environ.get("PULSE_HOME", ROOT / ".work" / "pulse-home"))
OUT = Path(os.environ.get("STEP_OUT", ROOT / "demo-state" / "step2"))

ROLES = [
    ("MAINTAINER", "Full Control", "Maintainer", "Terminal identity: health reads, Cypher dumps and step scripts. Not an agent session."),
    ("RECORDER", "Spec", "Recorder", "Reads the fork and records decisions in one consolidation."),
    ("RECALLER", "Reporter", "Recaller", "Starts with no history and answers questions from the board graph. Read focus."),
    ("REVIEWER", "Validator", "Reviewer", "Checks a reversed decision and reads contradictions and the supersedence chain."),
]


def store_key(role: str, key: str) -> None:
    lines = [ln for ln in KEYS.read_text().splitlines() if ln.partition("=")[0] != role] if KEYS.exists() else []
    lines.append(f"{role}={key}")
    old = os.umask(0o077)
    try:
        KEYS.write_text("\n".join(lines) + "\n")
    finally:
        os.umask(old)
    KEYS.chmod(0o600)


def write_store_layout(board_id: str, label: str) -> None:
    """Write the board store's folder layout (lock files left out) with the board id replaced."""
    root = HOME / "boards" / board_id
    lines = [f"# board store layout, {label}", "# lock files omitted, board id replaced by <board_id>", ""]
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.suffix == ".lock" or len(rel.parts) > 3 or (len(rel.parts) == 3 and rel.parts[2] == "index"):
            continue
        lines.append(f"boards/<board_id>/{rel}")
    store = next(root.glob("grafx/generation-*"), None)
    if store:
        lines += ["", f"index/ files: {len(list((store / 'index').glob('*')))}", f"wal/ files: {len(list((store / 'wal').glob('*')))}", "", "sizes:"]
        for p in sorted(store.iterdir()):
            size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else p.stat().st_size
            lines.append(f"  {p.name:<12} {size / 1024:>10.0f} KiB")
    (OUT / "store-layout.txt").write_text("\n".join(lines) + "\n")


def wait_until_healthy(board_id: str, timeout_s: int = 240) -> list[dict]:
    """A new board reports recovery_needed for a while (queue drains, graph initialises lazily). Log it."""
    log, t0 = [], time.time()
    with stepslib.Mcp("MAINTAINER") as m:
        while time.time() - t0 < timeout_s:
            d = m.call("okto_pulse_kg_health", {"board_id": board_id})["data"] or {}
            log.append({"t_s": round(time.time() - t0), "graph_state": d.get("graph_state"), "overall_state": d.get("overall_state"),
                        "metric_status": d.get("metric_status"), "queue_depth": d.get("queue_depth")})
            if d.get("graph_state") == "healthy":
                break
            time.sleep(5)
    return log


def main() -> None:
    with stepslib.StepTimer("step2"):
        run()


def run() -> None:
    presets = {p["name"]: p for p in rest("GET", "/presets")}
    board = rest("POST", "/boards", {"name": "RealWorld API Decisions", "description": "Decision memory demo board (invented scenario, fork of fastapi-realworld-example-app)."})
    bid = board["id"]
    agents = []
    for role, preset_name, display, objective in ROLES:
        created = rest("POST", "/agents", {
            "name": f"{display} (demo)",
            "description": f"{display} session, preset {preset_name}",
            "objective": objective,
            "preset_id": presets[preset_name]["id"],
        })
        key = created["reveal_once_secret"]
        store_key(role, key)
        aid = created["agent"]["id"]
        grant = rest("POST", f"/agents/{aid}/boards/{bid}")
        agents.append({"role": role, "agent_id": aid, "name": f"{display} (demo)", "preset": preset_name,
                       "preset_id": presets[preset_name]["id"], "board_grant_status": "ok" if grant else "empty"})
    spec = rest("POST", f"/boards/{bid}/specs", {
        "title": "Decision register: fastapi-realworld-example-app",
        "description": "Anchor spec for the decision consolidation. Decisions are read from the fork's code.",
        "delivery_context": "brownfield",
    })
    health_log = wait_until_healthy(bid)
    store = HOME / "boards" / bid / "grafx"
    layout = sorted(str(p.relative_to(store)) for p in store.glob("*")) if store.exists() else []
    OUT.mkdir(parents=True, exist_ok=True)
    write_store_layout(bid, "after board creation and the health wait")
    info = {
        "board_id": bid, "board_name": board["name"], "anchor_spec_id": spec["id"], "anchor_spec_status": spec.get("status"),
        "agents": agents, "grafx_folder_exists": store.exists(), "grafx_folder_entries": layout,
        "presets_available": sorted(presets),
        "health_after_create": health_log,
    }
    (OUT / "board.json").write_text(json.dumps(info, indent=2) + "\n")
    print(json.dumps({k: info[k] for k in ("board_id", "anchor_spec_id", "grafx_folder_exists", "grafx_folder_entries")}, indent=1))
    print("agents:", [(a["role"], a["preset"]) for a in agents], "(keys stored, not printed)")


if __name__ == "__main__":
    main()
