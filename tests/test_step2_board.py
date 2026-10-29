"""Step 2: board, identities and store folder."""
import json
import re


def test_four_identities_use_documented_presets(loadj):
    b = loadj("step2/board.json")
    roles = {a["role"]: a["preset"] for a in b["agents"]}
    assert roles == {"MAINTAINER": "Full Control", "RECORDER": "Spec", "RECALLER": "Reporter", "REVIEWER": "Validator"}
    assert all(a["board_grant_status"] == "ok" for a in b["agents"])
    assert {"Spec", "Reporter", "Validator", "Full Control"} <= set(b["presets_available"])


def test_board_grafx_folder_exists_with_a_generation(loadj):
    b = loadj("step2/board.json")
    assert b["grafx_folder_exists"] is True
    assert b["grafx_folder_entries"] == ["generation-1"]


def test_new_board_reaches_healthy_graph_state(loadj):
    log = loadj("step2/board.json")["health_after_create"]
    assert log and log[-1]["graph_state"] == "healthy"


def test_mcp_config_examples_hold_placeholders_not_keys(root):
    for role in ("recorder", "recaller", "reviewer"):
        cfg = json.loads((root / "agents" / f"mcp.{role}.example.json").read_text())
        auth = cfg["mcpServers"]["pulse"]["headers"]["Authorization"]
        assert auth == f"Bearer ${{PULSE_KEY_{role.upper()}}}"
        assert re.fullmatch(r"\$\{PULSE_MCP_URL:-http://127\.0\.0\.1:8101/mcp\}", cfg["mcpServers"]["pulse"]["url"])


def test_keys_file_is_ignored_by_git(root):
    assert "agents/.keys.local" in (root / ".gitignore").read_text().splitlines()
