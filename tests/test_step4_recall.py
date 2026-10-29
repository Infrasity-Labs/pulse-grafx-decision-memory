"""Step 4: recall results. The summary must agree with the per-question rows, which come from raw tool results."""
import importlib.util

from conftest import ROOT

spec = importlib.util.spec_from_file_location("questions", ROOT / "scripts" / "questions.py")
qs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qs)


def test_ten_fixed_questions_over_ten_distinct_decisions():
    assert len(qs.QUESTIONS) == 10
    assert len({slug for _, _, slug in qs.QUESTIONS}) == 10


def test_recorded_questions_are_the_fixed_ones(loadj):
    r = loadj("step4/recall-results.json")
    assert [(q["q"], q["question"], q["expected_slug"]) for q in r["per_question"]] == list(qs.QUESTIONS)


def test_summary_is_recomputed_from_rows(loadj):
    r = loadj("step4/recall-results.json")
    rows, s = r["per_question"], r["summary"]
    assert s["questions"] == len(rows) == 10
    assert s["agent_choice_correct"] == sum(q["agent_choice"]["correct"] for q in rows)
    for tool in ("similar", "natural", "history"):
        assert s[f"{tool}_top1_correct"] == sum(bool(q["tools"].get(tool, {}).get("top_is_expected")) for q in rows)


def test_each_question_used_all_three_tools_once(loadj):
    for q in loadj("step4/recall-results.json")["per_question"]:
        assert set(q["tools"]) == {"similar", "natural", "history"}


def test_agent_choice_is_judged_against_expected_slug_not_agent_claims(loadj):
    for q in loadj("step4/recall-results.json")["per_question"]:
        assert q["agent_choice"]["correct"] == (q["agent_choice"]["slug"] == q["expected_slug"])


def test_read_only_identity_was_refused_a_write(loadj):
    probe = loadj("step4/recall-results.json")["summary"]["write_probe"]
    assert "permission_denied" in probe and "kg.session.begin" in probe


def test_recaller_had_no_file_tools(loadj):
    names = loadj("step4/recall-results.json")["summary"]["tool_call_names"]
    assert all(n.startswith("mcp__pulse__okto_pulse_kg_") for n in names)
