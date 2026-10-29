"""Step 8: direct read of the stopped stores."""
import pytest

BOARDS = ("decision_board", "crash_test_board")


def test_pulse_was_stopped_cleanly_before_the_read(loadj):
    assert loadj("step8/direct-read.json")["stop_pulse"]["exit_code"] == 0


@pytest.mark.parametrize("board", BOARDS)
def test_cli_reads_succeeded_and_were_read_only(loadj, board):
    e = loadj("step8/direct-read.json")["boards"][board]
    for cmd in ("capabilities", "schema", "indexes"):
        assert e[cmd]["exit_code"] == 0 and e[cmd]["output"]["result"] == "ok"
    assert e["schema"]["output"]["read_only"] is True and e["indexes"]["output"]["read_only"] is True
    assert e["capabilities"]["output"]["version"] == "0.0.8"


@pytest.mark.parametrize("board", BOARDS)
def test_schema_matches_what_pulse_reported_in_step_3(loadj, board):
    schema = loadj("step8/direct-read.json")["boards"][board]["schema"]["output"]
    info = loadj("step3/schema-info.json")["data"]
    assert {t["name"] for t in schema["tables"] if t["kind"] == "node"} >= {n["name"] for n in info["stable_node_types"]}
    assert schema["total_spaces"] == 11


@pytest.mark.parametrize("board", BOARDS)
def test_python_reader_opened_read_only_and_counts_match_pulse(loadj, board):
    e = loadj("step8/direct-read.json")["boards"][board]
    assert e["reader_exit_code"] == 0
    c = e["comparison"]
    assert c["nodes_match"] is True and c["edges_match"] is True
    assert c["node_diff"] == {} and c["edge_diff"] == {}
    reader = loadj(f"step8/reader-{board}.json")
    assert reader["opened"] and reader["db_read_only"] is True


@pytest.mark.parametrize("board", BOARDS)
def test_read_only_passes_left_every_data_file_unchanged(loadj, board):
    e = loadj("step8/direct-read.json")["boards"][board]
    assert e["data_files_unchanged_by_read"] is True and e["data_file_count_hashed"] > 100


def test_decision_count_is_explained_by_recorded_commits(loadj):
    """12 from the Recorder, 1 from the Reviewer, plus the commits made by Kill A's write probe."""
    probe_commits = sum(1 for a in loadj("step7/killA.json")["write_probe_after_restart"]["attempts"] if a["ok"])
    pulse = loadj("step8/direct-read.json")["boards"]["decision_board"]["comparison"]["pulse_nodes"]
    assert pulse["Decision"] == 12 + 1 + probe_commits


def test_crash_board_holds_every_acknowledged_commit_and_the_probe(loadj):
    kb = loadj("step7/killB.json")
    probe_commits = sum(1 for a in kb["write_probe_after_restart"]["attempts"] if a["ok"])
    pulse = loadj("step8/direct-read.json")["boards"]["crash_test_board"]["comparison"]["pulse_nodes"]
    assert pulse["Decision"] == kb["present_after_restart"] + probe_commits


def test_status_read_only_is_inconclusive_by_design(loadj):
    st = loadj("step8/direct-read.json")["boards"]["decision_board"]["status_read_only"]
    assert st["exit_code"] == 6 and st["output"]["reasons"] == ["no recovery ran, because this open was read-only"]


@pytest.mark.parametrize("board", BOARDS)
def test_commit_history_state_is_recorded(loadj, board):
    ch = loadj(f"step8/reader-{board}.json")["commit_history"]
    assert isinstance(ch["enabled"], bool)
