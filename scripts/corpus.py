"""The decision corpus, the questions and the reference list, loaded from corpus/ and demo-state/.

The corpus has 32 decisions:
  - 12 recorded decisions, copied from the first real run (demo-state/step3/decisions-from-graph.json)
  - 10 code-derived decisions with a file, a line and the exact line text (corpus/decisions.json)
  - 10 graph-only decisions whose reason is written nowhere except in the graph (corpus/decisions.json)

Standard library only, so the offline baselines run without Pulse.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
RECORDED = ROOT / "demo-state" / "step3" / "decisions-from-graph.json"

RECORDED_GROUPS = {
    "auth-header-scheme": "auth", "token-expiry": "token", "password-hashing": "password", "error-response-shape": "errors",
    "pagination-parameters": "pagination", "slug-rules": "slug", "comment-ownership": "ownership", "favorites": "favorites",
    "tag-handling": "tags", "database-access-layer": "database", "settings-loading": "settings", "test-layout": "tests",
}


def _load(path: Path):
    return json.loads(path.read_text())


def recorded_decisions() -> list[dict]:
    """The 12 decisions of the recorded Recorder run, as the graph held them."""
    out = []
    for r in _load(RECORDED):
        path, _, line = r["content"].rsplit("Source: ", 1)[1].strip().rpartition(":")
        out.append({"slug": r["slug"], "origin": "recorded-run-1", "group": RECORDED_GROUPS[r["slug"]], "title": r["title"],
                    "content": r["content"], "source": {"path": path, "line": int(line), "quote": r["quote"]},
                    "rationale": None, "alternatives": [], "reason_keywords": []})
    return out


def extra_decisions() -> list[dict]:
    out = []
    for d in _load(CORPUS / "decisions.json")["decisions"]:
        out.append({"slug": d["slug"], "origin": d["origin"], "group": d["group"], "title": d["title"], "content": d["content"],
                    "source": d.get("source"), "rationale": d.get("rationale"), "alternatives": d.get("alternatives", []),
                    "reason_keywords": d.get("reason_keywords", [])})
    return out


def all_decisions() -> list[dict]:
    return recorded_decisions() + extra_decisions()


def node_text(d: dict) -> str:
    """What the graph holds for a decision and what a reader of the board can see: title, content and the reason."""
    text = f"{d['title']}\n{d['content']}"
    if d.get("rationale"):
        text += f"\nReason: {d['rationale']}"
    return text


def reason_keywords(slug: str) -> list[str]:
    return next((d["reason_keywords"] for d in all_decisions() if d["slug"] == slug), [])


LEGACY_KEYWORDS = {"l1": ["prefix"], "l2": ["week"], "l3": ["bcrypt"], "l4": ["errors"], "l5": ["limit", "offset"], "l6": ["slugify"],
                   "l7": ["author"], "l8": ["favorites"], "l9": ["BaseSettings", "lru_cache"], "l10": ["tests"]}


def legacy_questions() -> list[dict]:
    """The original ten questions from scripts/questions.py, in the same record shape as the new ones."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("questions", ROOT / "scripts" / "questions.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return [{"id": f"l{n}", "split": "legacy", "kind": "answerable", "expected_slug": slug, "tags": [], "distractors": [], "text": text,
             "answer_keywords": LEGACY_KEYWORDS[f"l{n}"]}
            for n, text, slug in mod.QUESTIONS]


def questions(split: str | None = None) -> list[dict]:
    """All questions. split is dev, held_out, model_authored, legacy or None for every split. model_authored was written by claude-haiku-5-5."""
    qs = list(_load(CORPUS / "questions.json")["questions"]) + list(_load(CORPUS / "questions-model-authored.json")["questions"]) + legacy_questions()
    by_slug = {d["slug"]: d for d in all_decisions()}
    for q in qs:
        if "graph_only" in q["tags"]:
            q["answer_keywords"] = by_slug[q["expected_slug"]]["reason_keywords"]
    return [q for q in qs if split in (None, q["split"])]


def conflict_tasks() -> list[dict]:
    return _load(CORPUS / "questions.json")["conflict_tasks"]


def reference_entries() -> list[dict]:
    return _load(CORPUS / "reference_decisions.json")["entries"]


def group_of(slug: str) -> str | None:
    return next((d["group"] for d in all_decisions() if d["slug"] == slug), None)


def parse_source(content: str | None) -> tuple[str, int] | None:
    """The cited file and line of a node: its last line that reads 'Source: path:line'."""
    for line in reversed((content or "").strip().splitlines()):
        if line.startswith("Source:"):
            path, _, num = line[len("Source:"):].strip().rpartition(":")
            if num.isdigit():
                return path, int(num)
    return None


def match_reference(title: str, content: str, taken: set[str] | None = None) -> str | None:
    """The reference entry a recorded node covers, or None. Line match first, keyword in the title only as a fallback.

    taken holds the entries other nodes already cover, so one entry is matched by at most one node."""
    taken = taken or set()
    src = parse_source(content)
    if src is None:
        return None
    path, line = src
    entries = [e for e in reference_entries() if path in e["files"] and e["id"] not in taken]
    for e in entries:
        if line in e["lines"]:
            return e["id"]
    low = (title or "").lower()
    if any(path in e["files"] and line in e["lines"] for e in reference_entries()):
        return None  # the line belongs to an entry that another node already covers
    for e in entries:
        if any(k in low for k in e["keywords"]):
            return e["id"]
    return None


def slug_for_node(title: str, content: str | None, ref: str | None) -> str | None:
    """Map a graph node to the corpus slug it stands for: by exact title, by a slug in a final_report ref, or by the reference rules."""
    decisions = all_decisions()
    for d in decisions:
        if d["title"].strip() == (title or "").strip():
            return d["slug"]
    if ref and ":decision:" in ref:
        slug = ref.rsplit(":", 1)[-1]
        if any(d["slug"] == slug for d in decisions):
            return slug
    return match_reference(title or "", content or "")
