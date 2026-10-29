"""The citation checker: behaviour on small fixtures, then on the recorded Recorder output."""
import importlib.util
import json

import pytest

from conftest import ROOT

spec = importlib.util.spec_from_file_location("check_citations", ROOT / "scripts" / "check_citations.py")
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)


def row(slug, path, line, quote):
    return {"slug": slug, "title": slug, "content": f"text\nSource: {path}:{line}", "quote": quote}


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("one = 1\ntwo = 2\nthree = 3\n")
    return tmp_path


def test_valid_citation_passes(repo):
    assert cc.check_one(row("x", "pkg/a.py", 2, "two = 2"), repo)["ok"]


def test_line_past_end_of_file_fails(repo):
    r = cc.check_one(row("x", "pkg/a.py", 4, ""), repo)
    assert not r["ok"] and "not in file" in r["problem"]


def test_quote_must_be_on_the_cited_line(repo):
    r = cc.check_one(row("x", "pkg/a.py", 1, "two = 2"), repo)
    assert not r["ok"] and "quote" in r["problem"]


def test_missing_file_and_missing_source_line_fail(repo):
    assert "does not exist" in cc.check_one(row("x", "pkg/none.py", 1, ""), repo)["problem"]
    assert "no 'Source" in cc.check_one({"slug": "x", "content": "no cite", "quote": ""}, repo)["problem"]


def test_path_traversal_is_refused(repo):
    assert "escapes" in cc.check_one(row("x", "../outside.py", 1, ""), repo)["problem"]


def test_exactly_the_twelve_slugs_are_required(repo):
    rows = [row(s, "pkg/a.py", 1, "one = 1") for s in cc.EXPECTED_SLUGS[:11]]
    res = cc.check(rows, repo)
    assert not res["all_ok"] and res["missing_slugs"] == [cc.EXPECTED_SLUGS[11]]
    rows.append(row(cc.EXPECTED_SLUGS[11], "pkg/a.py", 1, "one = 1"))
    assert cc.check(rows, repo)["all_ok"]
    rows.append(row("surprise", "pkg/a.py", 1, "one = 1"))
    assert not cc.check(rows, repo)["all_ok"]


def test_recorded_decisions_cite_lines_that_exist(loadj, root):
    rows = loadj("step3/decisions-from-graph.json")
    res = cc.check(rows, root)
    assert res["all_ok"], [r for r in res["results"] if not r["ok"]]
    assert res["citations_ok"] == 12
