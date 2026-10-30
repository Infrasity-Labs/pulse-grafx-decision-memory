"""The live runs with a model: demo-state/llm-runs/<run id>/ and the LLM arm files in demo-state/arms/. They read what was recorded and recompute what can be recomputed."""
import hashlib
import json
import re
import sys

import pytest

from conftest import ROOT, missing

sys.path.insert(0, str(ROOT / "scripts"))
import check_citations  # noqa: E402
import corpus  # noqa: E402
import run_arms  # noqa: E402
import runstats  # noqa: E402
import score_arms  # noqa: E402

RUNS = sorted((ROOT / "demo-state" / "llm-runs").glob("*/run-info.json"))
PINNED = json.loads((ROOT / "config" / "agent.json").read_text())["model"]


def latest():
    if not RUNS:
        missing("no live model run recorded in demo-state/llm-runs")
    return RUNS[-1].parent


def test_manifest_hashes_match_every_copied_file_and_nothing_else_is_there():
    d = latest()
    info = json.loads((d / "run-info.json").read_text())
    on_disk = {str(p.relative_to(d)) for p in d.rglob("*") if p.is_file() and p.name != "run-info.json"}
    assert on_disk == set(info["files"])
    for rel, digest in info["files"].items():
        assert hashlib.sha256((d / rel).read_bytes()).hexdigest() == digest, rel
    for rel, digest in info["arm_files_not_copied_here_but_hashed"].items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == digest, rel


def test_every_session_asked_for_and_reported_the_pinned_model_and_none_errored():
    d = latest()
    info = json.loads((d / "run-info.json").read_text())
    assert info["model_pinned_in_config"] == PINNED
    assert info["models_reported_by_sessions"] == [PINNED] and info["model_requested_by_sessions"] == [PINNED]
    assert info["sessions"]["errors"] == 0 and info["sessions"]["count"] == info["sessions"]["in_this_folder"] + info["sessions"]["arms"]
    results = [json.loads(p.read_text()) for p in list(d.rglob("result.json")) + list((ROOT / "demo-state" / "arms").glob("llm-*/run-*/result.json"))]
    real = [r for r in results if not str(r.get("model", "")).startswith("scripted")]
    assert len(real) == info["sessions"]["count"]
    assert abs(sum(r["final"]["total_cost_usd"] for r in real) - info["sessions"]["total_cost_usd"]) < 1e-3
    assert all(r["model_requested"] == PINNED and r["model"] == PINNED and r["exit_code"] == 0 and not r["final"]["is_error"] for r in real)


def test_no_key_is_in_any_recorded_live_file():
    d = latest()
    pat = re.compile(r"sk-ant|dash_[A-Za-z0-9]{20}|ANTHROPIC_API_KEY\s*=\s*\S|OKTO_NEURON_ANTHROPIC|Bearer\s+(?!\$\{)[A-Za-z0-9._~+/-]{24,}")
    for base in (d, ROOT / "demo-state" / "arms"):
        for p in base.rglob("*"):
            if p.is_file() and (base == d or p.relative_to(base).parts[0].startswith("llm-")):
                assert not pat.search(p.read_text()), p
                assert "/Users/" not in p.read_text(), p


def n_runs():
    d = latest()
    found = sorted(d.glob("n-runs-*"))
    if not found:
        missing("no variance study recorded")
    return found


def test_variance_studies_have_at_least_five_runs_and_the_spread_is_the_one_of_the_per_run_values():
    main = [p for p in n_runs() if p.name == "n-runs-main"]
    assert main, "the main study (Recorder and Recaller with a model) is missing"
    for p in n_runs():
        s = json.loads((p / "summary.json").read_text())
        assert s["runs"] >= 5 and len(s["per_run"]) == s["runs"] == len(list(p.glob("run-*"))), p.name
        for key, sp in s["spread"].items():
            vals = []
            for r in s["per_run"]:
                node = r
                for part in key.split("."):
                    node = node.get(part) if isinstance(node, dict) else None
                if isinstance(node, (int, float)) and not isinstance(node, bool):
                    vals.append(node)
            assert (sp["n"], sp["min"], sp["max"]) == (len(vals), min(vals), max(vals)) and abs(sp["mean"] - sum(vals) / len(vals)) < 1e-3, (p.name, key)


def test_the_recorder_numbers_of_every_run_are_recomputed_from_its_graph_dump_and_the_costs_from_its_result_events():
    for p in n_runs():
        s = json.loads((p / "summary.json").read_text())
        for r in s["per_run"]:
            run = p / f"run-{r['run']}"
            rows = json.loads((run / "step3" / "decisions-from-graph.json").read_text())
            res = check_citations.check_open(rows, ROOT)
            assert (res["found"], res["citations_ok"], res["reference_covered"]) == (r["recorder"]["nodes"], r["recorder"]["citations_ok"], r["recorder"]["reference_covered"])
            for role, step in (("recorder", "step3"), ("recaller", "step4"), ("reviewer", "step5")):
                f = run / step / "agent" / "result.json"
                if f.exists() and role in r.get("agent_runs", {}):
                    assert runstats.summarise(json.loads(f.read_text())) == r["agent_runs"][role]
            # every recorded citation held: the Recorder is not allowed to cite a file or line that does not exist
            assert res["all_ok"], (p.name, r["run"])


def test_the_recaller_scores_are_recomputed_from_the_recorded_answers_with_the_shared_scorer():
    for p in n_runs():
        s = json.loads((p / "summary.json").read_text())
        if "recaller" not in s["agents_with_a_model"]:
            continue
        qs = {q["id"]: q for q in corpus.questions()}
        for r in s["per_run"]:
            rec = json.loads((p / f"run-{r['run']}" / "step4" / "recall-results.json").read_text())
            asked = [qs[q["id"]] for q in rec["per_question"]]
            answers = [{"id": q["id"], "decision": q["agent_choice"]["slug"], "abstain": q["agent_choice"]["abstained"], "answer": q["agent_choice"]["answer"] or ""}
                       for q in rec["per_question"] if q["agent_choice"]["answer"] is not None or q["agent_choice"]["abstained"]]
            assert score_arms.score(asked, answers) == r["recaller"]["scores_by_split"], (p.name, r["run"])
            assert rec["summary"]["write_probe"] and "permission" in rec["summary"]["write_probe"].lower()


def test_the_reviewer_outcomes_are_read_from_the_graph_not_from_the_reviewers_report():
    for p in n_runs():
        s = json.loads((p / "summary.json").read_text())
        if "reviewer" not in s["agents_with_a_model"]:
            continue
        for r in s["per_run"]:
            run = p / f"run-{r['run']}" / "step5"
            before, after = json.loads((run / "before.json").read_text()), json.loads((run / "after.json").read_text())
            rv = r["reviewer"]
            assert rv["supersedes_edges"] == len(after["supersedes_edges"]) - len(before["supersedes_edges"])
            assert rv["contradicts_edges"] == len(after["contradicts_edges"]) - len(before["contradicts_edges"])
            assert rv["reversal_target_present"] == int(any(n[2].endswith(":decision:error-response-shape") for n in before["error_shape_nodes"]))
            if not rv["reversal_target_present"]:  # nothing to supersede: a Reviewer that wrote anything here made something up
                assert rv["supersedes_edges"] == rv["contradicts_edges"] == 0 and rv["reviewer_reported_recorded"] == 0


def arm_files():
    found = {n: ROOT / "demo-state" / "arms" / f"llm-{n}.json" for n in ("memory", "no-memory", "code-notes")}
    if not all(f.exists() for f in found.values()):
        missing("LLM arms not recorded")
    return found


def test_each_llm_arm_has_at_least_five_runs_on_the_same_questions_and_each_run_has_its_files():
    asked = None
    for name, f in arm_files().items():
        arm = json.loads(f.read_text())
        assert len(arm["runs"]) >= 5 and [r["run"] for r in arm["runs"]] == list(range(1, len(arm["runs"]) + 1)), name
        for r in arm["runs"]:
            assert r["problem"] is None and r["exit_code"] == 0 and r["model"] == PINNED
            asked = asked or r["questions_asked"]
            assert r["questions_asked"] == asked, (name, r["run"])
            d = f.parent / f.stem / f"run-{r['run']}"
            assert runstats.summarise(json.loads((d / "result.json").read_text())) == r["run_stats"]
            assert (d / "prompt.rendered.md").exists() and (d / "transcript.jsonl").exists()
    assert set(asked) == {q["id"] for sp in ("dev", "held_out", "model_authored") for q in corpus.questions(sp)}


def test_the_answers_of_the_arms_are_recomputed_from_the_final_message_of_each_session():
    for name, f in arm_files().items():
        arm = json.loads(f.read_text())
        for r in arm["runs"]:
            result = json.loads((f.parent / f.stem / f"run-{r['run']}" / "result.json").read_text())
            final = run_arms.parse_final(result)
            if name == "memory":  # graph ids need the graph to become slugs: check everything the graph is not needed for
                assert [(a["id"], a["abstain"], a["answer"]) for a in r["answers"]] == [(a["id"], bool(a.get("abstain")), a.get("answer") or "") for a in final["answers"]]
                assert [(t["id"], t["stance"], t["answer"]) for t in r["tasks"]] == [(t["id"], t.get("stance"), t.get("answer") or "") for t in final["tasks"]]
            else:
                answers, tasks = run_arms.to_arm_answers(name, final, {})
                assert (answers, tasks) == (r["answers"], r["tasks"])


def test_rendered_prompts_of_every_live_run_hold_no_decision_slug_and_no_override():
    d = latest()
    slugs = [s["slug"] for s in corpus.all_decisions() if "-" in s["slug"]]
    prompts = list(d.rglob("prompt.rendered.md")) + list((ROOT / "demo-state" / "arms").glob("llm-*/run-*/prompt.rendered.md"))
    assert len(prompts) >= 20
    for p in prompts:
        text = p.read_text()
        # the Reviewer prompt names the note file, not the decision; the question lists hold wording, not slugs
        assert not [s for s in slugs if s in text], p
        assert "agent_overrides" not in text and "target_node_id" not in text, p


def test_the_model_authored_questions_say_who_wrote_them_and_were_not_filtered_afterwards():
    q = json.loads((ROOT / "corpus" / "questions-model-authored.json").read_text())
    assert q["authoring"]["model"] == "claude-haiku-5-5" and q["authoring"]["model"] != PINNED
    assert q["authoring"]["dropped_after_writing"] == [] and q["authoring"]["questions_written"] == len(q["questions"]) == 16
    reply = json.loads((ROOT / "corpus" / "authoring" / "model-authored-reply.json").read_text())
    assert [x["text"] for x in reply["result"]["questions"]] == [x["text"] for x in q["questions"]]
    assert reply["model"] == ["claude-haiku-5-5"]


def test_the_per_tool_recall_columns_are_recomputed_from_the_raw_tool_results_in_the_transcript():
    """The Recaller's own report is not what is scored: the top-ranked id, the count and the outcome of every search come from the tool results."""
    try:
        import step04_recaller  # imports the MCP client, which the offline CI job does not install
    except ModuleNotFoundError as exc:
        pytest.skip(f"{exc.name} is not installed: the offline CI job runs the other recomputations")
    d = latest()
    for p in sorted(d.glob("n-runs-main/run-*")) + [d / "smoke"]:
        rec = json.loads((p / "step4" / "recall-results.json").read_text())
        questions = [q for q in corpus.questions() if q["id"] in {x["id"] for x in rec["per_question"]}]
        again = step04_recaller.score(p / "step4" / "agent" / "transcript.jsonl", questions, None)
        keep = ("top_id", "top_title", "top_similarity", "results_returned", "outcome")
        for a, b in zip(again["per_question"], rec["per_question"]):
            assert a["id"] == b["id"]
            assert {t: {k: v[k] for k in keep} for t, v in a["tools"].items()} == {t: {k: v[k] for k in keep} for t, v in b["tools"].items()}, (p.name, a["id"])
