"""Step 5: the reversal, as returned by Pulse to the Maintainer identity after the Reviewer ran."""
import json

from conftest import STATE, missing

OLD = "error-response-shape"
NEW = "error-response-shape-v2"


def test_maintainer_note_names_the_decision_and_leaves_the_fork_alone(loadj):
    n = loadj("step5/maintainer-reversal.json")
    assert n["reverses_slug"] == OLD and n["new_slug"] == NEW
    assert "not changed" in n["scope"]


def test_thirteen_decisions_after_reversal_and_before_was_twelve(loadj):
    assert loadj("step5/before.json")["decisions_total"] == 12
    assert loadj("step5/after.json")["decisions_total"] == 13


def test_no_contradiction_existed_before(loadj):
    assert loadj("step5/before.json")["contradictions"]["data"]["count"] == 0


def test_supersede_alone_did_not_create_a_contradiction_pair(loadj):
    """Read from the Reviewer's transcript: find_contradictions is called three times, in this order."""
    lines = STATE / "step5" / "agent" / "transcript.jsonl"
    if not lines.exists():
        missing("step5/agent/transcript.jsonl not recorded yet")
    names, results = {}, []
    for ln in lines.read_text().splitlines():
        ev = json.loads(ln)
        if ev.get("type") == "assistant":
            for b in ev["message"]["content"]:
                if b.get("type") == "tool_use" and b["name"].endswith("find_contradictions"):
                    names[b["id"]] = None
        if ev.get("type") == "user" and isinstance(ev["message"].get("content"), list):
            for b in ev["message"]["content"]:
                if b.get("type") == "tool_result" and b["tool_use_id"] in names:
                    txt = b["content"] if isinstance(b["content"], str) else "".join(x.get("text", "") for x in b["content"])
                    results.append(json.loads(txt)["data"]["count"])
    assert results == [0, 0, 1]


def test_contradiction_pair_links_new_and_old_decision(loadj):
    after = loadj("step5/after.json")
    pairs = after["contradictions"]["data"]["pairs"]
    assert len(pairs) == 1
    ids = {n[0] for n in after["error_shape_nodes"]}
    assert {pairs[0]["id_a"], pairs[0]["id_b"]} == ids


def test_supersedence_chain_from_new_decision_ends_at_it(loadj):
    after = loadj("step5/after.json")
    chain = after[f"chain_from_{NEW}"]["data"]
    nodes = {n[0]: n for n in after["error_shape_nodes"]}
    new_id = next(i for i, n in nodes.items() if n[2].endswith(f":{NEW}"))
    old_id = next(i for i, n in nodes.items() if n[2].endswith(f":{OLD}"))
    assert chain["depth"] == 1 and chain["current_active"] == new_id
    assert chain["chain"][0]["id"] == old_id and chain["chain"][0]["superseded_by"] == new_id


def test_old_decision_is_marked_superseded_on_the_node(loadj):
    nodes = loadj("step5/after.json")["error_shape_nodes"]
    old = next(n for n in nodes if n[2].endswith(f":{OLD}"))
    new = next(n for n in nodes if n[2].endswith(f":{NEW}"))
    assert old[3] == new[0] and old[4]
    assert new[3] is None


def test_edges_in_graph_match_the_story(loadj):
    after = loadj("step5/after.json")
    assert len(after["supersedes_edges"]) == 1 and len(after["contradicts_edges"]) == 1


def test_reviewer_reported_what_the_graph_shows(loadj):
    txt = loadj("step5/agent/result.json")["final"]["result"]
    r = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
    assert (r["contradiction_pairs_before"], r["contradiction_pairs_after_supersede"], r["contradiction_pairs_after_flag"]) == (0, 0, 1)
    assert r["chain_from_new_depth"] == 1
