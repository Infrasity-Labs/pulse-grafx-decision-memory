"""Re-scoring stored outputs with a v2 key. The keys here are synthetic test fixtures, not reviewed keys. No model, no Pulse."""
import json
import subprocess
import sys

import pytest

from conftest import ROOT, STATE, missing

sys.path.insert(0, str(ROOT / "scripts"))
import corpus  # noqa: E402
import rescore_with_key as rk  # noqa: E402
import make_review_sheets  # noqa: E402,F401
import score_arms as sa  # noqa: E402

Q = {q["id"]: q for q in corpus.questions()}


def identity_key() -> dict:
    """A v2 key that says exactly what v1 says."""
    return {"version": 2, "reviewer": "test fixture", "review_date": "none",
            "questions": [{"id": q["id"], "kind": q["kind"], "expected_slug": q["expected_slug"], "accepted_slugs": []} for q in corpus.questions()],
            "conflict_tasks": [{"id": t["id"], "accepted_slugs": []} for t in corpus.conflict_tasks()]}


def arm_state(tmp_path, answers, tasks=()):
    (tmp_path / "arms").mkdir(parents=True)
    (tmp_path / "arms" / "toy.json").write_text(json.dumps({"arm": "toy", "kind": "llm", "answers": answers, "tasks": list(tasks)}))
    return tmp_path


def test_v2_equal_to_v1_gives_identical_metrics_on_the_recorded_outputs():
    if not (STATE / "arms").exists() or not (STATE / "llm-runs").exists():
        missing("demo-state/arms or demo-state/llm-runs not recorded yet")
    res = rk.rescore(STATE, identity_key(), {"version": 2, "entries": corpus.reference_entries()})
    assert res["changed"] == {"questions_changed": [], "tasks_changed": [], "unknown_ids": []}
    assert res["sources"], "nothing was re-scored"
    for s in res["sources"]:
        if "v1" in s:
            assert s["v1"] == s["v2"], s["source"]
            assert s.get("tasks_v1") == s.get("tasks_v2"), s["source"]
        else:
            assert s["recorder_v1"] == s["recorder_v2"], s["source"]
    recallers = [s for s in res["sources"] if "v1_matches_stored_scores_by_split" in s]
    assert recallers and all(s["v1_matches_stored_scores_by_split"] for s in recallers)


def test_an_accepted_alternative_slug_turns_a_wrong_answer_into_a_correct_one(tmp_path):
    answers = [{"id": "d1", "decision": "token-expiry", "abstain": False, "answer": "x"}]
    state = arm_state(tmp_path, answers)
    key = {"version": 2, "questions": [{"id": "d1", "accepted_slugs": ["token-expiry"]}]}
    res = rk.rescore(state, key, None)
    (src,) = res["sources"]
    assert (src["v1"]["correct"], src["v1"]["wrong"]) == (0, 1)
    assert (src["v2"]["correct"], src["v2"]["wrong"]) == (1, 0)
    assert res["changed"]["questions_changed"] == ["d1"]
    # the original expected slug stays right
    answers[0]["decision"] = "jwt-algorithm"
    state = arm_state(tmp_path / "b", answers)
    (src,) = rk.rescore(state, key, None)["sources"]
    assert src["v1"]["correct"] == src["v2"]["correct"] == 1


def test_accepted_slugs_also_count_for_a_conflict_task(tmp_path):
    tasks = [{"id": "t1", "stance": "stop", "cited": "token-expiry", "answer": ""}]
    state = arm_state(tmp_path, [], tasks)
    key = {"version": 2, "conflict_tasks": [{"id": "t1", "accepted_slugs": ["token-expiry"]}]}
    (src,) = rk.rescore(state, key, None)["sources"]
    assert src["tasks_v1"]["respected"] == 0 and src["tasks_v2"]["respected"] == 1


def test_reviewer_can_turn_a_question_into_an_abstention_question(tmp_path):
    state = arm_state(tmp_path, [{"id": "d1", "decision": None, "abstain": True, "answer": ""}])
    key = {"version": 2, "questions": [{"id": "d1", "kind": "unanswerable"}]}
    (src,) = rk.rescore(state, key, None)["sources"]
    assert (src["v1"]["missed_by_abstaining"], src["v1"]["correct_abstentions"]) == (1, 0)
    assert (src["v2"]["missed_by_abstaining"], src["v2"]["correct_abstentions"]) == (0, 1)


def test_an_answerable_question_needs_a_slug(tmp_path):
    with pytest.raises(SystemExit):
        rk.apply_questions_key([{"id": "x", "kind": "unanswerable", "expected_slug": None, "tags": []}], [], {"questions": [{"id": "x", "kind": "answerable"}]})


def test_a_reference_key_changes_the_recorder_recall(tmp_path):
    (tmp_path / "step3").mkdir()
    node = {"slug": "n1", "title": "Something nobody listed", "content": "Why.\nSource: app/app/other.py:999", "quote": "x"}
    (tmp_path / "step3" / "decisions-from-graph.json").write_text(json.dumps([node]))
    v1 = corpus.reference_entries()
    key = {"version": 2, "entries": v1 + [{"id": "added", "files": ["app/app/other.py"], "lines": [999], "keywords": []}]}
    (src,) = rk.rescore(tmp_path, None, key)["sources"]
    assert (src["recorder_v1"]["reference_covered"], src["recorder_v1"]["reference_entries"]) == (0, 22)
    assert (src["recorder_v2"]["reference_covered"], src["recorder_v2"]["reference_entries"]) == (1, 23)


def test_a_key_that_is_not_version_2_is_refused(tmp_path):
    f = tmp_path / "k.json"
    f.write_text(json.dumps({"version": 1}))
    with pytest.raises(SystemExit):
        rk.load_key(f, "questions")


def test_the_script_refuses_to_run_without_a_key():
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "rescore_with_key.py")], capture_output=True, text=True)
    assert p.returncode == 2 and "no" in p.stdout


def test_v1_scoring_is_unchanged_when_no_accepted_slugs_are_given():
    s = sa.score([Q["d1"]], [{"id": "d1", "decision": "token-expiry", "abstain": False, "answer": ""}])["dev"]
    assert (s["correct"], s["wrong"]) == (0, 1)


def test_review_sheets_match_the_corpus_and_hold_no_human_judgement():
    import make_review_sheets as mk
    ref, qs = mk.reference_sheet(), mk.question_sheet()
    assert len(ref["entries"]) == len(corpus.reference_entries()) and len(qs["questions"]) == len(corpus.questions()) == 53
    assert [e["id"] for e in ref["entries"]] == [e["id"] for e in corpus.reference_entries()]
    for sheet in (ref, qs):
        assert all(sheet[k] is None for k in ("reviewer", "review_date", "decisions", "unresolved_disagreements"))
    humans = [e["human"] for e in ref["entries"] + ref["missing_decisions_to_consider"] + qs["questions"] + qs["conflict_tasks"]]
    assert all(v is None for h in humans for v in h.values())
    notes = [e["model_note"] for e in ref["entries"] + qs["questions"]]
    assert all(n["label"].startswith("MODEL DRAFT") for n in notes)


def test_review_sheets_on_disk_are_current():
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "make_review_sheets.py"), "--check"], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout


def test_no_v2_key_is_committed_by_anyone_but_the_reviewer():
    assert not (ROOT / "corpus" / "validation" / "v2").exists(), "a v2 key exists: it must come from the human reviewer, with a reviewer and a review date"
