"""Step 7: SIGKILL of the Pulse server. Checks recorded results and re-derives Kill B from the worker logs."""
import json

TTL_S = 300


def test_kill_a_uncommitted_consolidation_is_absent_and_earlier_decisions_remain(loadj):
    a = loadj("step7/killA.json")
    assert a["draft_candidates_accepted_before_kill"] == 3
    assert a["draft_absent"] is True and a["draft_present_after_restart"] == []
    assert a["earlier_decisions_all_present"] is True
    assert a["decisions_before"] == a["decisions_after"] == 13


def test_kill_a_old_session_cannot_be_committed_after_restart(loadj):
    a = loadj("step7/killA.json")
    assert a["late_commit_of_old_session"]["error_code"] == "session_not_found"
    assert a["draft_present_after_late_commit_attempt"] == []


def test_kill_b_every_acknowledged_commit_is_present(loadj):
    b = loadj("step7/killB.json")
    assert b["acknowledged_missing"] == []
    assert b["acknowledged_and_present"] == b["acknowledged_commits"] > 0


def test_kill_b_numbers_match_the_worker_logs(loadj, state):
    b = loadj("step7/killB.json")
    events = [json.loads(ln) for f in sorted((state / "step7").glob("burst-ack-w*.log")) for ln in f.read_text().splitlines() if ln.strip()]
    acked = {e["slug"] for e in events if e["ev"] == "ack"}
    started = {e["slug"] for e in events if e["ev"] == "start"}
    assert len(acked) == b["acknowledged_commits"]
    assert len(started) == b["commits_started"]
    assert set(b["in_flight_at_kill"]) == started - acked


def test_unacknowledged_survivors_can_only_be_commits_that_were_in_flight(loadj):
    b = loadj("step7/killB.json")
    assert set(b["unacknowledged_but_present"]) <= set(b["in_flight_at_kill"])
    assert b["present_after_restart"] == b["acknowledged_commits"] + len(b["unacknowledged_but_present"])


def test_kill_b_ran_with_parallel_workers_so_commits_could_be_in_flight(loadj):
    assert loadj("step7/killB.json")["workers"] >= 2


def test_writes_resume_within_the_writer_lock_ttl_after_a_kill(loadj):
    """A killed server can leave a writer lease that blocks writes until it expires (default TTL 300 s)."""
    for name in ("killA", "killB"):
        wp = loadj(f"step7/{name}.json")["write_probe_after_restart"]
        assert wp["first_success_after_probe_start_s"] is not None, f"{name}: board never accepted a write"
        assert wp["writes_resumed_seconds_after_kill"] <= TTL_S + 90


def test_health_after_each_restart_is_recorded_as_returned(loadj):
    for name in ("killA", "killB"):
        env = loadj(f"step7/{name}.json")["health_after_restart"]
        assert env["outcome"] == "success"
        assert env["data"]["graph_state"] in {"healthy", "at_risk", "recovery_needed"}
        assert env["data"]["dead_letter_count"] == 0


def test_restart_logs_are_saved_without_machine_paths(state):
    for name in ("killA", "killB"):
        text = (state / "step7" / f"restart-log-{name}.txt").read_text()
        assert "/Users/" not in text and "Starting Okto Pulse Community" in text
