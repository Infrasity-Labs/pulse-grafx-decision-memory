"""Step 1: the pairing and the embedding mode, from recorded proof."""
from importlib.metadata import PackageNotFoundError, requires, version

from conftest import missing


def test_recorded_pulse_requires_the_installed_grafx(loadj):
    v = loadj("step1/versions.json")
    assert v["okto_pulse"] == "0.4.2"
    assert v["okto_grafx"] == "0.0.8"
    assert v["requires_dist_grafx_line"] == "Requires-Dist: okto-grafx[accel]==0.0.8"
    assert v["pulse_requires_exact_installed_grafx"] is True


def test_requirements_pin_matches_recorded_versions(loadj, root):
    pins = {ln.split("==")[0].split("[")[0]: ln.split("==")[1] for ln in (root / "requirements.txt").read_text().splitlines()
            if "==" in ln and not ln.startswith("#")}
    v = loadj("step1/versions.json")
    assert pins["okto-pulse"] == v["okto_pulse"]
    assert pins["okto-grafx"] == v["okto_grafx"]


def test_installed_pulse_metadata_pins_grafx_if_pulse_is_installed(root):
    """CI installs okto-pulse with --no-deps, which is enough to read its requirements."""
    try:
        reqs = requires("okto-pulse")
        pulse_version = version("okto-pulse")
    except PackageNotFoundError:
        missing("okto-pulse is not installed (CI installs its metadata with --no-deps)")
    pinned = [ln.split("==")[1] for ln in (root / "requirements.txt").read_text().splitlines() if ln.startswith("okto-pulse==")][0]
    assert pulse_version == pinned
    assert any(r.replace(" ", "").startswith("okto-grafx[accel]==0.0.8") for r in reqs)


def test_embedding_is_the_real_model_not_the_stub(loadj):
    e = loadj("step1/embedding.json")
    assert e["metadata_after_load"]["is_stub"] is False
    assert e["configured_model"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert e["vector_length"] == 384
    assert e["similarity_related_pair"] > e["similarity_unrelated_pair"] + 0.2
