"""Write the empty human review sheets in corpus/validation/ from the v1 corpus and the model review drafts.

  corpus/validation/reference_review_sheet.json   one entry per reference decision (corpus/reference_decisions.json), plus a section for decisions missing from the list
  corpus/validation/question_review_sheet.json    one entry per question (corpus/questions*.json and the legacy ten) and per conflict task

Every human field is null. The model's observations (corpus/*_model_review.json) are copied into "model_note" only as a convenience. They are a model
draft, not a human judgement, and nothing in the sheets or in the scorers treats them as an answer. Nothing here is filled in on anyone's behalf.

Usage: python scripts/make_review_sheets.py [--check]    --check exits 1 if the files on disk differ from what this script writes
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import corpus  # noqa: E402

OUT = ROOT / "corpus" / "validation"
DRAFT = "MODEL DRAFT, not a human judgement. Copied for convenience from {file}. Decide for yourself; do not copy it into a v2 key unchecked."

REFERENCE_HUMAN = {
    "is_a_decision_not_a_code_fact": None,       # 1. meaningful, correctly characterised as a decision
    "evidence_file_correct": None,               # 2. points to the right source file
    "evidence_lines_correct": None,              # 2. points to the exact relevant lines
    "corrected_files": None,                     # list of paths, if the file is wrong
    "corrected_lines": None,                     # list of line numbers, if the lines are wrong
    "rationale_supported_by_source": None,       # 3. "supported", "invented scenario rationale", or "no rationale claimed"
    "decision": None,                            # keep, correct, or remove
    "notes": None,
}
MISSING_HUMAN = {"include_in_reference_list": None, "scope_rule_applied": None, "files": None, "lines": None, "keywords": None, "notes": None}
QUESTION_HUMAN = {
    "answerable_from_permitted_source": None,    # 1. true or false
    "valid_decision_ids": None,                  # 2. every decision id that answers it, not only the v1 slug
    "equivalent_supported_facts": None,          # 2. other factual answers the source supports
    "sufficient_evidence": None,                 # 3. what a correct answer must be based on
    "abstention_required": None,                 # 4. true or false
    "abstention_reason": None,                   # 4. why
    "artificially_easy": None,                   # 5. true or false
    "artificially_easy_reason": None,            # 5. wording or data generation
    "notes": None,
}
SHEET_HEAD = {"reviewer": None, "review_date": None, "decisions": None, "unresolved_disagreements": None, "status": "not reviewed by a human"}


def reference_sheet() -> dict:
    review = json.loads((ROOT / "corpus" / "reference_decisions_model_review.json").read_text())
    verdicts = {v["id"]: {k: x for k, x in v.items() if k != "id"} for v in review["verdicts"]}
    note_src = "corpus/reference_decisions_model_review.json"
    entries = []
    for e in corpus.reference_entries():
        entries.append({"id": e["id"], "v1": {"files": e["files"], "lines": e["lines"], "keywords": e["keywords"]},
                        "model_note": {"label": DRAFT.format(file=note_src), "labeler": review["labeler"], **verdicts.get(e["id"], {})},
                        "human": dict(REFERENCE_HUMAN)})
    missing = [{"id": m["id"], "v1_where": m["where"], "model_note": {"label": DRAFT.format(file=note_src), "labeler": review["labeler"], "why": m["why"]},
                "human": dict(MISSING_HUMAN)} for m in review["completeness"]["missing"]]
    return {"about": "Review sheet for the reference decisions (corpus/reference_decisions.json, key v1). Protocol: corpus/validation/README.md. All human fields are null until a named human reviewer fills them in.",
            **SHEET_HEAD, "scope_rule_for_missing_decisions": None,
            "model_completeness_note": {"label": DRAFT.format(file=note_src), "verdict": review["completeness"]["verdict"]},
            "entries": entries, "missing_decisions_to_consider": missing}


def question_sheet() -> dict:
    review = json.loads((ROOT / "corpus" / "questions_model_review.json").read_text())
    verdicts = {v["id"]: {k: x for k, x in v.items() if k not in ("id", "split", "kind", "expected_slug")} for v in review["verdicts"]}
    note_src = "corpus/questions_model_review.json"
    qs = []
    for q in corpus.questions():
        qs.append({"id": q["id"], "split": q["split"], "v1": {"kind": q["kind"], "expected_slug": q["expected_slug"], "tags": q["tags"], "distractors": q.get("distractors", []),
                                                              "answer_keywords": q.get("answer_keywords", []), "text": q["text"]},
                   "model_note": {"label": DRAFT.format(file=note_src), "labeler": review["labeler"], **verdicts.get(q["id"], {})},
                   "human": dict(QUESTION_HUMAN)})
    tasks = [{"id": t["id"], "split": t["split"], "v1": {"expected_slug": t["expected_slug"], "reason_keywords": t["reason_keywords"], "proposal": t["proposal"]},
              "human": {"valid_decision_ids": None, "notes": None}} for t in corpus.conflict_tasks()]
    return {"about": "Review sheet for the evaluation questions (corpus/questions.json, corpus/questions-model-authored.json and the ten legacy questions in scripts/questions.py, key v1). Protocol: corpus/validation/README.md. All human fields are null until a named human reviewer fills them in.",
            **SHEET_HEAD, "questions": qs, "conflict_tasks": tasks}


def render(obj: dict) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    files = {OUT / "reference_review_sheet.json": render(reference_sheet()), OUT / "question_review_sheet.json": render(question_sheet())}
    if a.check:
        bad = [str(p.relative_to(ROOT)) for p, text in files.items() if not p.exists() or p.read_text() != text]
        for b in bad:
            print(f"{b}: differs from what scripts/make_review_sheets.py writes")
        return 1 if bad else 0
    OUT.mkdir(parents=True, exist_ok=True)
    for p, text in files.items():
        p.write_text(text)
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
