"""The 32-decision corpus, the question sets and the reference list. Checks the data, not Pulse."""
import importlib.util
import re
import sys

import pytest

from conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import corpus  # noqa: E402

spec = importlib.util.spec_from_file_location("check_citations", ROOT / "scripts" / "check_citations.py")
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

DECISIONS = corpus.all_decisions()
BY_SLUG = {d["slug"]: d for d in DECISIONS}
QUESTIONS = corpus.questions()


def test_the_corpus_has_32_decisions_with_unique_slugs():
    assert len(DECISIONS) == 32 == len(BY_SLUG)
    origins = [d["origin"] for d in DECISIONS]
    assert (origins.count("recorded-run-1"), origins.count("code-derived"), origins.count("graph-only")) == (12, 10, 10)


def test_code_derived_decisions_cite_a_real_file_line_and_exact_line_text():
    rows = [{"slug": d["slug"], "title": d["title"], "content": d["content"], "quote": d["source"]["quote"]} for d in DECISIONS if d["origin"] != "graph-only"]
    for r in rows:
        res = cc.check_one(r, ROOT)
        assert res["ok"], res


def test_graph_only_decisions_carry_a_reason_alternatives_and_keywords_and_say_they_are_invented():
    for d in DECISIONS:
        if d["origin"] == "graph-only":
            assert d["rationale"] and len(d["alternatives"]) >= 2 and d["reason_keywords"], d["slug"]
            assert "Invented for this demo" in d["rationale"] and d["source"] is None
            assert all(k.lower() in d["rationale"].lower() for k in d["reason_keywords"]), d["slug"]


def test_graph_only_reasons_are_not_in_the_code_or_the_other_decisions():
    code = "\n".join(p.read_text(errors="replace") for p in (ROOT / "app").rglob("*") if p.is_file() and p.suffix in {".py", ".sql", ".toml", ".md", ".rst"})
    for d in DECISIONS:
        if d["origin"] == "graph-only":
            for k in d["reason_keywords"]:
                assert k.lower() not in code.lower(), (d["slug"], k)
                others = [corpus.node_text(o).lower() for o in DECISIONS if o["slug"] != d["slug"]]
                assert not any(k.lower() in t for t in others), (d["slug"], k)


def test_there_are_near_duplicate_families():
    groups = {}
    for d in DECISIONS:
        groups.setdefault(d["group"], []).append(d["slug"])
    assert len(groups["token"]) >= 4  # the review's example: two or more token-related decisions
    assert sum(1 for g in groups.values() if len(g) >= 3) >= 4


def test_every_question_points_at_a_real_decision_and_real_distractors():
    for q in QUESTIONS:
        if q["kind"] == "answerable":
            assert q["expected_slug"] in BY_SLUG, q["id"]
            assert all(s in BY_SLUG for s in q["distractors"]), q["id"]
            assert q["answer_keywords"], q["id"]
        else:
            assert q["expected_slug"] is None and q["kind"] == "unanswerable"


def test_each_split_has_unanswerable_questions_and_enough_questions():
    for split, minimum in (("dev", 10), ("held_out", 10)):
        qs = corpus.questions(split)
        assert len(qs) >= minimum and sum(q["kind"] == "unanswerable" for q in qs) >= 3, split
    ma = corpus.questions("model_authored")
    assert len(ma) == 16 and sum(q["kind"] == "unanswerable" for q in ma) == 4
    assert len(corpus.questions("legacy")) == 10
    assert len({q["id"] for q in QUESTIONS}) == len(QUESTIONS)


def test_unanswerable_questions_are_unanswerable_no_decision_text_has_their_terms():
    text = "\n".join(corpus.node_text(d).lower() for d in DECISIONS)
    for q in QUESTIONS:
        for term in q.get("absent_terms", []):
            assert term.lower() not in text, (q["id"], term)


def test_graph_only_questions_are_answered_by_a_reason_that_no_distractor_carries():
    for q in QUESTIONS:
        if "graph_only" in q["tags"]:
            texts = {s: corpus.node_text(BY_SLUG[s]).lower() for s in [q["expected_slug"], *q["distractors"]]}
            assert any(k.lower() in texts[q["expected_slug"]] for k in q["answer_keywords"]), q["id"]
            for s in q["distractors"]:
                assert not any(k.lower() in texts[s] for k in q["answer_keywords"]), (q["id"], s)


def test_conflict_tasks_rest_on_graph_only_decisions():
    tasks = corpus.conflict_tasks()
    assert len(tasks) >= 2
    for t in tasks:
        assert BY_SLUG[t["expected_slug"]]["origin"] == "graph-only"
        assert all(k.lower() in corpus.node_text(BY_SLUG[t["expected_slug"]]).lower() for k in t["reason_keywords"])


def test_reference_entries_point_at_real_lines():
    for e in corpus.reference_entries():
        for f in e["files"]:
            lines = (ROOT / f).read_text(errors="replace").splitlines()
            assert any(n <= len(lines) for n in e["lines"]), e["id"]
        assert any(n <= len((ROOT / e["files"][0]).read_text(errors="replace").splitlines()) for n in e["lines"])


def test_each_recorded_decision_covers_exactly_its_own_reference_entry():
    taken = set()
    for d in corpus.recorded_decisions():
        ref = corpus.match_reference(d["title"], d["content"], taken)
        assert ref == d["slug"], d["slug"]
        taken.add(ref)


def test_the_recorded_run_covers_12_of_22_reference_entries_and_every_citation_holds(loadj):
    """What the answer-key prompt produced, measured against the list it never saw. The recorded Recorder was told the twelve topics."""
    rows = loadj("step3/decisions-from-graph.json")
    res = cc.check_open(rows, ROOT)
    assert res["all_ok"] and res["reference_entries"] == 22 and res["reference_covered"] == 12
    assert not res["nodes_matching_no_reference_entry"]


def test_open_mode_checker_rejects_a_bad_citation_and_counts_recall(tmp_path):
    (tmp_path / "a.py").write_text("one = 1\n")
    rows = [{"slug": "x", "title": "x", "content": "t\nSource: a.py:1", "quote": "one = 1"}, {"slug": "y", "title": "y", "content": "t\nSource: a.py:9", "quote": ""}]
    res = cc.check_open(rows, tmp_path)
    assert not res["all_ok"] and res["citations_ok"] == 1 and res["reference_covered"] == 0


@pytest.mark.parametrize("title,content,expected", [
    ("Access tokens expire", "x\nSource: app/app/services/jwt.py:12", "token-expiry"),
    ("Tokens are signed with HS256", "x\nSource: app/app/services/jwt.py:11", "jwt-algorithm"),
    ("Something", "x\nSource: app/app/services/jwt.py:99", None),
])
def test_line_match_beats_keyword_match(title, content, expected):
    assert corpus.match_reference(title, content) == expected


def test_decision_texts_contain_no_em_dash():
    assert not any("\u2014" in corpus.node_text(d) for d in DECISIONS)
    assert re.search(r"\w", corpus.node_text(DECISIONS[0]))
