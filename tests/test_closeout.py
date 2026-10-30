"""Step 10: the scoreboard builder. It must reproduce recorded values and refuse to run on missing outputs."""
import importlib.util
import json
import shutil

import pytest

from conftest import ROOT, STATE, missing

spec = importlib.util.spec_from_file_location("build_closeout", ROOT / "scripts" / "build_closeout.py")
bc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bc)


@pytest.fixture(scope="module")
def result():
    if not (STATE / "step9").exists():
        missing("step9 not recorded yet")
    return bc.build(STATE)


def test_every_section_of_the_plan_scoreboard_is_present(result):
    assert {"versions", "decisions", "recall", "reversal", "kill_a", "kill_b", "health_after_restart_as_returned", "node_counts", "verify", "step_seconds"} <= set(result)


def test_values_equal_the_recorded_outputs(result):
    kb = json.loads((STATE / "step7" / "killB.json").read_text())
    assert result["kill_b"]["acknowledged_before_kill"] == kb["acknowledged_commits"]
    assert result["kill_b"]["acknowledged_missing_after_restart"] == len(kb["acknowledged_missing"])
    assert result["decisions"]["committed_to_graph"] == 12 == result["decisions"]["citations_checked_and_valid"]
    assert result["versions"]["installed_pulse_requires_installed_grafx"] is True


def test_reversal_numbers_separate_what_pulse_did_from_what_the_agent_added(result):
    r = result["reversal"]
    assert (r["contradiction_pairs_before"], r["contradiction_pairs_after_supersede_only"], r["contradiction_pairs_after_explicit_flag"]) == (0, 0, 1)
    assert r["pulse_flagged_a_contradiction_without_an_agent_edge"] is False
    assert r["supersedence_chain_length_from_new_decision"] == 1
    assert r["supersedence_chain_length_when_queried_from_old_decision"] == 0


def test_every_step_has_a_time(result):
    assert set(result["step_seconds"]) >= {f"step{i}" for i in range(1, 10)}
    assert all(v > 0 for v in result["step_seconds"].values())


def test_node_counts_match_for_each_board(result):
    for board in result["node_counts"].values():
        assert board["nodes_match"] and board["edges_match"] and not board["read_only_open_refused"]


def test_missing_output_stops_the_builder(tmp_path):
    shutil.copytree(STATE, tmp_path / "s", ignore=shutil.ignore_patterns("closeout-result.json"))
    shutil.rmtree(tmp_path / "s" / "step7")
    with pytest.raises(bc.MissingOutput):
        bc.build(tmp_path / "s")


def test_committed_closeout_file_is_current(result):
    p = STATE / "closeout-result.json"
    if not p.exists():
        missing("closeout-result.json not built")
    committed = json.loads(p.read_text())
    for k in result:
        if k != "generated_at":
            assert committed[k] == result[k], k


def test_committed_closeout_says_whether_the_run_was_recorded():
    p = STATE / "closeout-result.json"
    if not p.exists():
        missing("closeout-result.json not built")
    run = json.loads(p.read_text())["run"]
    assert isinstance(run["recorded"], bool)
    if not run["recorded"]:
        assert "run_id" not in run and "commit" not in run, "an unrecorded run must not carry an invented id or commit"


def test_run_info_takes_run_id_commit_and_versions_from_the_environment(result, monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    run = bc.run_info(result)
    assert (run["run_id"], run["run_attempt"], run["commit"], run["recorded"]) == ("12345", "2", "a" * 40, True)
    assert run["tool_versions"]["okto_grafx"] == result["versions"]["okto_grafx"] and run["date"] == result["generated_at"]
