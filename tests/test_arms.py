"""The shared arm scorer, the lexical baseline, the question overlap and the control-arm harness. No Pulse, no model."""
import importlib.util
import json
import subprocess
import sys

import pytest

from conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import corpus  # noqa: E402
import lexical_baseline as lb  # noqa: E402
import question_overlap as qo  # noqa: E402
import score_arms as sa  # noqa: E402

Q = {q["id"]: q for q in corpus.questions()}


def ans(i, decision=None, abstain=False, text=""):
    return {"id": i, "decision": decision, "abstain": abstain, "answer": text}


def test_right_decision_is_correct_wrong_decision_is_wrong():
    s = sa.score([Q["d1"], Q["d2"]], [ans("d1", "jwt-algorithm"), ans("d2", "comment-ownership")])["dev"]
    assert (s["correct"], s["wrong"]) == (1, 1)


def test_abstaining_on_an_answerable_question_is_a_miss_not_a_wrong_answer():
    s = sa.score([Q["d1"]], [ans("d1", abstain=True)])["dev"]
    assert (s["correct"], s["wrong"], s["missed_by_abstaining"]) == (0, 0, 1)


def test_unanswerable_question_abstention_is_correct_and_an_answer_is_fabricated():
    s = sa.score([Q["d11"], Q["d12"]], [ans("d11", abstain=True), ans("d12", "jwt-algorithm", text="HS256")])["dev"]
    assert (s["correct_abstentions"], s["fabricated"]) == (1, 1)


def test_graph_only_question_needs_the_reason_not_a_plausible_answer():
    q = Q["d5"]  # why are there no refresh tokens: the reason exists only in the graph
    plausible = ans("d5", text="Refresh tokens add attack surface, so the team avoided them.")
    graph = ans("d5", text="Review SR-2025-14 found that stolen browser profiles kept access.")
    assert sa.score([q], [plausible])["dev"]["graph_only_correct"] == 0
    assert sa.score([q], [graph])["dev"]["graph_only_correct"] == 1


def test_a_question_the_arm_never_answered_is_never_counted_correct():
    s = sa.score([Q["d1"], Q["d11"]], [])["dev"]
    assert s["correct"] == 0 and s["correct_abstentions"] == 0 and s["answered_by_arm"] == 0


def test_conflict_task_needs_the_decision_cited_and_a_stance_other_than_proceed():
    tasks = corpus.conflict_tasks()
    res = sa.score_tasks(tasks, [{"id": "t1", "stance": "stop", "cited": "no-refresh-tokens", "answer": ""},
                                 {"id": "t2", "stance": "proceed", "cited": "hard-delete-articles", "answer": ""}])
    assert (res["cited"], res["respected"]) == (2, 1)
    res = sa.score_tasks(tasks, [{"id": "t1", "stance": "adapt", "cited": None, "answer": "A past review (SR-2025-14) said no."}])
    assert (res["cited"], res["respected"]) == (1, 1)


def test_threshold_is_chosen_on_the_given_questions_and_lets_wrong_top_hits_abstain():
    triples = [(0.9, "a", "a"), (0.8, "b", "b"), (0.2, "c", None), (0.1, "d", None)]
    t = sa.calibrate_threshold(triples)
    assert 0.2 < t <= 0.8
    # a high score on an unanswerable question cannot be separated from a right answer: the rule still returns a threshold that handles most
    assert sa.calibrate_threshold([(0.5, "x", "x"), (0.5, "y", None)]) in (0.0, 0.5, 0.500001)


def test_tfidf_ranks_the_document_that_shares_the_rare_word_first():
    idx = lb.Index({"a": "tokens expire after a week", "b": "passwords use bcrypt", "c": "tokens use HS256"})
    assert idx.rank("how long do tokens last, a week")[0][0] == "a"
    assert idx.rank("bcrypt")[0][0] == "b"
    assert idx.rank("nothing in common zzz")[0][1] == 0.0


def test_lexical_baseline_reproduces_the_review_check_7_of_10_on_the_recorded_twelve():
    res = lb.run()
    leg = res["legacy_ten_on_recorded_twelve"]
    assert leg["top1_correct"] == 7 and leg["misses"] == ["l2", "l4", "l9"]


def test_committed_lexical_arm_equals_what_the_script_computes():
    committed = json.loads((ROOT / "demo-state" / "arms" / "lexical-tfidf.json").read_text())
    assert committed == json.loads(json.dumps(lb.run()))


def test_every_arm_file_is_scored_by_the_same_function_and_covers_every_question():
    arms = sa.load_arms(ROOT / "demo-state" / "arms")
    assert {"lexical-tfidf", "pulse-retrieval"} <= set(arms)
    for name, arm in arms.items():
        for rs in arm["run_scores"]:  # an LLM arm is asked the splits it was run on; every other arm answers every question
            asked = sum(s["questions"] for s in rs["scores"].values())
            assert sum(s["answered_by_arm"] for s in rs["scores"].values()) == asked, name
        if not name.startswith("llm-"):
            assert asked == len(corpus.questions()), name


def test_every_llm_arm_file_comes_from_run_arms_and_carries_the_model_and_the_stats_of_each_run():
    for f in (ROOT / "demo-state" / "arms").glob("llm-*.json"):
        arm = json.loads(f.read_text())
        assert arm["kind"] == "llm" and arm["model"] and arm["model_requested"] and arm["runs"], f.name
        for r in arm["runs"]:
            assert r["model"] == arm["model"] and r["run_stats"]["total_cost_usd"] is not None and r["questions_asked"], (f.name, r["run"])
            assert (f.parent / f.stem / f"run-{r['run']}" / "result.json").exists(), (f.name, r["run"])


def test_question_overlap_files_match_the_script():
    res = qo.compute()
    assert (ROOT / "demo-state" / "arms" / "question-overlap.json").read_text() == json.dumps(res, indent=2) + "\n"
    assert (ROOT / "docs" / "QUESTIONS.md").read_text() == qo.render_md(res)


def test_overlap_summary_is_published_for_every_answerable_question():
    res = qo.compute()
    answerable = [q for q in corpus.questions() if q["kind"] == "answerable"]
    assert len([r for r in res["rows"] if r["expected_slug"]]) == len(answerable)
    assert all(0.0 <= r["exact_overlap"] <= 1.0 for r in res["rows"] if r["expected_slug"])


def test_arm_prompts_contain_no_answer_key():
    slugs = [d["slug"] for d in corpus.all_decisions()]
    for f in list((ROOT / "docs" / "prompts").glob("*.md")) + list((ROOT / "docs" / "prompts" / "arms").glob("*.md")):
        text = f.read_text()
        assert not [s for s in slugs if s in text], f.name
        assert "agent_overrides" not in text, f.name


def test_goal_prompts_hold_no_slug_list_edge_id_override_or_fixed_tool_order():
    for name in ("step3-recorder.md", "step4-recaller.md", "step5-reviewer.md"):
        text = (ROOT / "docs" / "prompts" / name).read_text()
        assert "agent_overrides" not in text and "target_node_id" not in text and "flag-contradiction" not in text and "error-response-shape" not in text, name
        assert "in this order" not in text and "call these three tools" not in text, name


def test_control_arm_prompts_render_without_a_model(tmp_path):
    import run_arms

    notes = run_arms.notes_text()
    assert notes.count("\n## ") == 32
    q = run_arms.question_lines(corpus.questions("dev"))
    assert q.splitlines()[0].startswith("d1. ") and "t1." in run_arms.task_lines()


def test_to_arm_answers_maps_graph_ids_and_note_headings_to_slugs():
    import run_arms

    final = {"answers": [{"id": "d1", "decision_id": "n1", "answer": "x", "abstain": False}], "tasks": [{"id": "t1", "stance": "stop", "decision_id": "n2", "answer": "y"}]}
    a, t = run_arms.to_arm_answers("memory", final, {"n1": "jwt-algorithm", "n2": "no-refresh-tokens"})
    assert a[0]["decision"] == "jwt-algorithm" and t[0]["cited"] == "no-refresh-tokens"
    a, _ = run_arms.to_arm_answers("no-memory", {"answers": [{"id": "d1", "answer": "x"}]}, {})
    assert a[0]["decision"] is None
    a, t = run_arms.to_arm_answers("code-notes", {"answers": [{"id": "d1", "decision": "jwt-algorithm", "answer": "x"}], "tasks": [{"id": "t1", "cited": "no-refresh-tokens", "stance": "adapt"}]}, {})
    assert a[0]["decision"] == "jwt-algorithm" and t[0]["cited"] == "no-refresh-tokens"
