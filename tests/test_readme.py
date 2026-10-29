"""The README must print the recorded numbers and nothing else."""
import importlib.util
import json
import re

from conftest import ROOT, STATE

spec = importlib.util.spec_from_file_location("render_scoreboard", ROOT / "scripts" / "render_scoreboard.py")
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)


def test_generated_blocks_equal_what_the_recorded_outputs_render():
    readme = (ROOT / "README.md").read_text()
    for name, body in rs.blocks().items():
        _, same = rs.replace_block(readme, name, body)
        assert same, f"README block {name} differs from the recorded outputs"


def test_every_mermaid_block_declares_a_diagram_type_and_closes():
    text = (ROOT / "README.md").read_text()
    blocks = re.findall(r"```mermaid\n(.*?)\n```", text, flags=re.S)
    assert len(blocks) >= 6
    kinds = ("flowchart", "sequenceDiagram", "pie", "stateDiagram", "gantt")
    for b in blocks:
        assert b.startswith(rs.MERMAID_INIT), "every diagram uses the shared Grafx theme"
        assert b[len(rs.MERMAID_INIT):].lstrip().startswith(kinds), b[:80]
    assert text.count("```") % 2 == 0


def test_readme_follows_the_planned_section_order():
    headings = re.findall(r"^## (.+)$", (ROOT / "README.md").read_text(), flags=re.M)
    order = ["About Pulse and Grafx", "The Problem", "How It Works", "Pulse and Grafx in Action", "Architecture",
             "Repository Structure", "Prerequisites", "Quickstart", "The Ten Steps", "Where to Find Artifacts", "Conclusion"]
    idx = [headings.index(h) for h in order]
    assert idx == sorted(idx)


def test_every_image_in_the_readme_exists():
    for target in re.findall(r"!\[[^\]]*\]\(([^)]+)\)|<img[^>]* src=\"([^\"]+)\"", (ROOT / "README.md").read_text()):
        path = next(t for t in target if t)
        if path.startswith("http"):
            continue
        assert (ROOT / path).exists(), path


def test_readme_names_the_main_limits():
    text = (ROOT / "README.md").read_text().lower()
    for phrase in ("pre-alpha", "sigkill", "one run, one machine", "source-available", "pulse stopped", "linux container"):
        assert phrase in text, phrase
