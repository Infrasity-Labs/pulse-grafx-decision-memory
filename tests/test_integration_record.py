"""The dated integration run (macOS host, step 9 in a Linux container) and the Linux container crash run: demo-state/integration-<id>/ and linux-crash-<id>/."""
import hashlib
import json

from conftest import ROOT, missing

INTEGRATION = sorted((ROOT / "demo-state").glob("integration-*/run-info.json"))
LINUX = sorted((ROOT / "demo-state").glob("linux-crash-*/run-info.json"))


def manifest_ok(info_path):
    d = info_path.parent
    info = json.loads(info_path.read_text())
    assert d.name.endswith(info["run_id"]) and info["run_id"].count("-") >= 2
    assert set(info["sha256"]) == set(info["files"])
    for rel, digest in info["sha256"].items():
        assert hashlib.sha256((d / rel).read_bytes()).hexdigest() == digest, rel
    assert info["files_missing_in_the_run"] == [] or d.name.startswith("linux-crash")
    return info


def test_the_integration_run_passed_every_assertion_including_step_9():
    if not INTEGRATION:
        missing("no dated integration run recorded")
    info = manifest_ok(INTEGRATION[-1])
    assert info["assertions"]["failed"] == 0 and info["assertions"]["skipped"] == [] and info["assertions"]["checks"] >= 48
    d = INTEGRATION[-1].parent
    rep = json.loads((d / "assert-report.json").read_text())
    assert rep["failed"] == 0 and all(r["ok"] for r in rep["results"])
    s9 = json.loads((d / "step9" / "backup-restore-linux-container.json").read_text())
    assert s9["backup"]["ok"] and s9["restore"]["ok"] and s9["counts_match"]["original_vs_restored"] and s9["decisions"]["original_vs_restored"]
    assert s9["decisions"]["original_count"] == s9["decisions"]["restored_count"] > 0 and s9["verify_restored_python_all_findings"] == 0
    assert info["okto_pulse"] == "0.4.2" and info["okto_grafx"] == "0.0.8"


def test_the_linux_container_run_killed_pulse_on_linux_and_lost_no_acknowledged_commit():
    if not LINUX:
        missing("no Linux crash run recorded")
    info = manifest_ok(LINUX[-1])
    d = LINUX[-1].parent
    assert info["platform"].startswith("Linux") and info["assertions"]["failed"] == 0
    assert "step 9 (backup and restore) did not run" in info["assertions"]["skipped"]
    li = json.loads((d / "linux-run-info.json").read_text())
    assert li["docker_run_exit"] == 0 and li["inner_exit"] == "0" and li["packages"]["okto-pulse"] == "0.4.2" and li["packages"]["okto-grafx"] == "0.0.8"
    assert li["base_image"].startswith("python:3.12-slim@sha256:") and "Linux" in (d / "container-info.txt").read_text()
    a, b = json.loads((d / "step7" / "killA.json").read_text()), json.loads((d / "step7" / "killB.json").read_text())
    assert a["draft_absent"] and a["earlier_decisions_all_present"] and a["resume"]["every_slug_exactly_once"]
    assert b["acknowledged_missing"] == [] and b["acknowledged_commits"] > 0 and b["retry"]["every_started_slug_exactly_once"]
