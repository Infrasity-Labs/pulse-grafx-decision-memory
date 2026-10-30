"""Token, cost and wall time are read from the result event of each session. The model is pinned in config/agent.json."""
import json
import sys

from conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import runstats  # noqa: E402


def test_recorded_runs_yield_the_numbers_in_their_result_events(loadj):
    for role, step in runstats.RECORDED.items():
        res = loadj(f"{step}/agent/result.json")
        s = runstats.summarise(res)
        assert s["role"] == role and s["model"] == "claude-opus-5-5"
        assert s["output_tokens"] == res["final"]["usage"]["output_tokens"] > 0
        assert s["wall_seconds"] == res["seconds"] and s["total_cost_usd"] == res["final"]["total_cost_usd"]


def test_committed_run1_stats_equal_the_recorded_results(loadj):
    committed = loadj("runstats-run1.json")["runs"]
    for role, step in runstats.RECORDED.items():
        assert committed[role] == runstats.summarise(loadj(f"{step}/agent/result.json"))


def test_missing_fields_stay_none_nothing_is_estimated():
    s = runstats.summarise({"role": "x", "final": None})
    assert s["input_tokens"] is None and s["total_cost_usd"] is None and s["wall_seconds"] is None


def test_spread_reports_n_mean_min_max_and_ignores_none():
    assert runstats.spread([10, 8, 9, None]) == {"n": 3, "mean": 9.0, "min": 8, "max": 10}
    assert runstats.spread([])["n"] == 0


def test_the_model_is_pinned_in_the_repo_config_and_always_passed_to_claude():
    cfg = json.loads((ROOT / "config" / "agent.json").read_text())
    assert cfg["model"] == "claude-opus-5-5"
    src = (ROOT / "scripts" / "run_agent.py").read_text()
    assert 'cmd += ["--model", a.model]' in src and "if a.model:" not in src
    assert "config" in src and "agent.json" in src


def test_every_recorded_session_used_the_pinned_model(loadj):
    for step in ("step3", "step4", "step5"):
        assert loadj(f"{step}/agent/result.json")["model"] == json.loads((ROOT / "config" / "agent.json").read_text())["model"]
