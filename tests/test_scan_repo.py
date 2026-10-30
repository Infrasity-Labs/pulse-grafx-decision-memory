"""The repo scanner's machine-local path check must not depend on the machine that runs it. No model, no network."""
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import scan_repo  # noqa: E402

# built from pieces so that this file does not itself look like a machine-local path to the scanner
RUNNER = "/ho" + "me/runner"
MAC = "/Us" + "ers/apple"
WORD = 'attach a belongs_to edge to the source/root Entity or use an existing one'


def tree(tmp_path: Path, text: str) -> Path:
    """A git repo with one verbatim-transcript file (the kind of file that is checked against this machine's home path)."""
    d = tmp_path / "demo-state" / "run" / "agent"
    d.mkdir(parents=True)
    (d / "transcript.jsonl").write_text(text + "\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.mark.parametrize("home", ["/root", RUNNER, MAC, "/"])
def test_the_word_root_is_not_a_home_path(tmp_path, monkeypatch, home):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path(home)))
    hits, scanned = scan_repo.scan(tree(tmp_path, WORD))
    assert scanned == 1 and hits == []


@pytest.mark.parametrize("home,line", [
    ("/root", "cwd is /root/project/x now"),
    ("/root", '{"cwd":"/root"}'),
    (RUNNER, f"opened {RUNNER}/work/repo/file.py"),
])
def test_a_real_home_path_is_one_hit(tmp_path, monkeypatch, home, line):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path(home)))
    hits, _ = scan_repo.scan(tree(tmp_path, line))
    assert hits == ["demo-state/run/agent/transcript.jsonl:1: machine-local absolute path"]


def test_a_longer_name_that_starts_with_the_home_is_not_a_hit(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path(RUNNER)))
    hits, _ = scan_repo.scan(tree(tmp_path, f"see {RUNNER}2/x and /opt{RUNNER}/x and {RUNNER}-bot"))
    assert hits == []


def test_home_of_slash_is_never_searched_for():
    assert scan_repo.home_pattern("/") is None and scan_repo.home_pattern("") is None
