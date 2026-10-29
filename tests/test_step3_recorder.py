"""Step 3: what the Recorder committed, as read back from the graph."""
import importlib.util
import json

from conftest import ROOT

spec = importlib.util.spec_from_file_location("check_citations", ROOT / "scripts" / "check_citations.py")
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)


def final_json(loadj):
    txt = loadj("step3/agent/result.json")["final"]["result"]
    return json.loads(txt[txt.find("{"): txt.rfind("}") + 1])


def test_exactly_twelve_expected_decisions_are_in_the_graph(loadj):
    rows = loadj("step3/decisions-from-graph.json")
    assert sorted(r["slug"] for r in rows) == sorted(cc.EXPECTED_SLUGS)
    assert all(r["layer"] == "canonical" for r in rows)


def test_one_consolidation_committed_all_twelve(loadj):
    f = final_json(loadj)
    assert f["commit_status"] == "committed" and f["nodes_added"] == 12


def test_agent_report_matches_the_graph(loadj):
    f = final_json(loadj)
    graph = {r["slug"]: r for r in loadj("step3/decisions-from-graph.json")}
    for d in f["decisions"]:
        assert f"Source: {d['file']}:{d['line']}" in graph[d["slug"]]["content"]


def test_graph_edges_are_only_depends_on_between_decisions(loadj):
    edges = loadj("step3/decision-edges.json")
    assert 0 < len(edges) <= 5
    assert {e[0] for e in edges} == {"depends_on__Decision__Decision"}


def test_pulse_counts_match_the_committed_decisions(loadj):
    counts = {k: v for k, v in loadj("step3/pulse-counts.json")["nodes_by_type"]}
    assert counts["Decision"] == 12


def test_health_after_commit_is_healthy(loadj):
    h = loadj("step3/health.json")["data"]
    assert (h["graph_state"], h["discovery_state"]) == ("healthy", "healthy")
    assert h["dead_letter_count"] == 0


def test_schema_info_lists_the_documented_types(loadj):
    d = loadj("step3/schema-info.json")["data"]
    assert len(d["stable_node_types"]) == 11
    assert "Decision" in {t["name"] for t in d["stable_node_types"]}


def test_recorder_used_no_write_path_outside_the_kg_tools(loadj):
    calls = loadj("step3/agent/result.json")["tool_calls"]
    assert all(c.startswith("mcp__pulse__okto_pulse_kg_") or c in {"Read", "Grep", "Glob"} for c in calls)
