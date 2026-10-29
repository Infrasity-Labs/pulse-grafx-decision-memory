"""Step 9: Grafx backup and restore of a copy, on every platform that was tried."""
import json

import pytest


@pytest.fixture
def runs(state):
    files = sorted((state / "step9").glob("backup-restore-*.json"))
    if not files:
        pytest.skip("step 9 not recorded yet")
    return {f.stem.replace("backup-restore-", ""): json.loads(f.read_text()) for f in files}


def test_at_least_one_platform_completed_backup_and_restore(runs):
    assert any(r["backup"]["ok"] and r["restore"]["ok"] for r in runs.values())


def test_a_platform_that_refused_says_why_and_did_not_restore(runs):
    for r in runs.values():
        if not r["backup"]["ok"]:
            assert "no supported atomic no-replace directory publication" in r["backup"]["message"]
            assert r["restore"]["ok"] is False
            assert r["counts_match"]["original_vs_restored"] is False


def test_completed_runs_verify_clean_on_original_copy_and_restored(runs):
    for r in runs.values():
        if r["restore"]["ok"]:
            for key in ("verify_original", "verify_copy_before_backup", "verify_restored"):
                assert r[key]["exit_code"] == 0 and r[key]["output"]["clean"] is True and r[key]["output"]["findings"] == []
            assert r["verify_restored_python_all_findings"] == 0


def test_completed_runs_restore_the_same_counts_and_identity(runs):
    for r in runs.values():
        if r["restore"]["ok"]:
            assert r["counts_match"] == {"original_vs_copy": True, "original_vs_restored": True}
            assert r["uuid_original_equals_restored"] is True
            assert r["backup"]["database_uuid"] == r["restore"]["database_uuid"]
            assert r["backup"]["files"] == r["restore"]["files"] and r["backup"]["checkpoint_lsn"] == r["restore"]["checkpoint_lsn"]


def test_the_original_store_was_never_modified(runs):
    assert all(r["original_untouched"] is True for r in runs.values())


def test_restored_counts_equal_the_pulse_counts_from_step_8(runs, loadj):
    pulse = loadj("step8/direct-read.json")["boards"]["decision_board"]["comparison"]
    for r in runs.values():
        if r["restore"]["ok"]:
            nonzero = lambda d: {k: v for k, v in d.items() if v}  # noqa: E731
            assert nonzero(r["counts"]["restored"]["nodes"]) == pulse["pulse_nodes"]
            assert nonzero(r["counts"]["restored"]["rels"]) == pulse["pulse_edges"]
