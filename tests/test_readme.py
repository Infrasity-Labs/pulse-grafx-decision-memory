"""The README must print the recorded numbers and nothing else."""
import importlib.util
import json
import re

from conftest import ROOT, STATE

spec = importlib.util.spec_from_file_location("render_scoreboard", ROOT / "scripts" / "render_scoreboard.py")
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)


def docs():
    return [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]


def test_generated_blocks_equal_what_the_recorded_outputs_render():
    texts = {f: (ROOT / f).read_text() for f in set(rs.BLOCK_FILES.values())}
    for name, body in rs.blocks().items():
        _, same = rs.replace_block(texts[rs.BLOCK_FILES[name]], name, body)
        assert same, f"block {name} in {rs.BLOCK_FILES[name]} differs from the recorded outputs"


def test_every_mermaid_block_uses_the_shared_theme_and_declares_a_diagram():
    kinds = ("flowchart", "sequenceDiagram", "pie", "stateDiagram", "gantt")
    count = 0
    for f in docs():
        text = f.read_text()
        for b in re.findall(r"```mermaid\n(.*?)\n```", text, flags=re.S):
            count += 1
            assert b.startswith(rs.MERMAID_INIT), f"{f.name}: diagram without the shared Grafx theme"
            assert b[len(rs.MERMAID_INIT):].lstrip().startswith(kinds), f"{f.name}: {b[:80]}"
        assert text.count("```") % 2 == 0, f.name
    assert count >= 6


def test_readme_stays_short():
    assert len((ROOT / "README.md").read_text().splitlines()) <= 200


def test_readme_has_the_front_page_sections_in_order():
    headings = re.findall(r"^## (.+)$", (ROOT / "README.md").read_text(), flags=re.M)
    order = ["About Okto Pulse and Grafx", "The Problem", "How It Works", "Pulse in Action", "Architecture", "Repository Structure", "Roles", "Prerequisites", "Quickstart", "The Ten Steps", "Where to Find Artifacts", "Limits", "Contributing & Licensing", "Conclusion"]
    assert [h for h in headings if h in order] == order


def test_every_local_image_exists():
    for f in docs():
        for target in re.findall(r"!\[[^\]]*\]\(([^)]+)\)|<img[^>]* src=\"([^\"]+)\"", f.read_text()):
            path = next(p for p in target if p)
            if not path.startswith("http"):
                assert (f.parent / path).exists(), f"{f.name}: {path}"


def test_limits_are_named_up_front_and_in_full():
    readme = (ROOT / "README.md").read_text().lower()
    for phrase in ("pre-alpha", "sigkill", "one run on one machine", "source-available", "pulse stopped", "linux container"):
        assert phrase in readme, phrase
    full = (ROOT / "docs" / "FINDINGS.md").read_text().lower()
    assert "## limits" in full and "one run, one machine" in full and "pre-release" in full
