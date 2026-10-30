"""Lexical baseline: tf-idf match of each question against the decision texts. No model, no Pulse, no network.

This replaces an ad hoc check that was never stored. The method is fixed here:
  - lower-case, split on letters and digits, drop the stop words below, no stemming
  - weight: (1 + log tf) * (log((1 + N) / (1 + df)) + 1), vectors cut to unit length, cosine similarity
  - the top-1 decision of a question is the highest cosine. A question with no overlapping word scores 0.

Two measurements are written to demo-state/arms/lexical-tfidf.json, which is also an arm file for scripts/score_arms.py:
  legacy_ten_on_recorded_twelve   the original ten questions against the 12 recorded decisions (the case the review checked by hand)
  answers                         every question against the 32 decisions, with an abstention threshold chosen on the dev
                                  split only and then applied to held_out and legacy

Usage: python scripts/lexical_baseline.py [--out FILE] [--print-misses]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import corpus  # noqa: E402
import score_arms  # noqa: E402

STOP = set("""a an and are as at be been being but by can could did do does for from had has have how i if in into is it its may of on or
our that the their them then there these they this to was we were what when where which who whom why will with would you your""".split())
TOKEN = re.compile(r"[a-z0-9_]+")


def tokens(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP]


class Index:
    def __init__(self, docs: dict[str, str]):
        self.slugs = list(docs)
        toks = {s: tokens(t) for s, t in docs.items()}
        n = len(docs)
        df: dict[str, int] = {}
        for ts in toks.values():
            for t in set(ts):
                df[t] = df.get(t, 0) + 1
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
        self.vecs = {s: self._vec(ts) for s, ts in toks.items()}

    def _vec(self, ts: list[str]) -> dict[str, float]:
        tf: dict[str, int] = {}
        for t in ts:
            tf[t] = tf.get(t, 0) + 1
        v = {t: (1 + math.log(c)) * self.idf[t] for t, c in tf.items() if t in self.idf}
        norm = math.sqrt(sum(x * x for x in v.values()))
        return {t: x / norm for t, x in v.items()} if norm else {}

    def rank(self, query: str) -> list[tuple[str, float]]:
        q = self._vec(tokens(query))
        scored = [(s, sum(w * self.vecs[s].get(t, 0.0) for t, w in q.items())) for s in self.slugs]
        return sorted(scored, key=lambda x: (-x[1], x[0]))


def retrieval_rows(index: Index, questions: list[dict]) -> list[dict]:
    rows = []
    for q in questions:
        ranked = index.rank(q["text"])
        rows.append({"id": q["id"], "top": ranked[0][0], "score": round(ranked[0][1], 4), "top3": [s for s, _ in ranked[:3]]})
    return rows


def run() -> dict:
    decisions = corpus.all_decisions()
    full = Index({d["slug"]: corpus.node_text(d) for d in decisions})
    recorded = Index({d["slug"]: corpus.node_text(d) for d in corpus.recorded_decisions()})
    legacy = corpus.questions("legacy")
    legacy_rows = retrieval_rows(recorded, legacy)
    legacy_hits = [r["id"] for r, q in zip(legacy_rows, legacy) if r["top"] == q["expected_slug"]]
    qs = corpus.questions()
    rows = retrieval_rows(full, qs)
    by_id = {r["id"]: r for r in rows}
    threshold = score_arms.calibrate_threshold([(by_id[q["id"]]["score"], by_id[q["id"]]["top"], q["expected_slug"]) for q in qs if q["split"] == "dev"])
    answers = []
    for q in qs:
        r = by_id[q["id"]]
        answers.append({"id": q["id"], "decision": r["top"] if r["score"] >= threshold else None, "abstain": r["score"] < threshold,
                        "answer": corpus.node_text(next(d for d in decisions if d["slug"] == r["top"])) if r["score"] >= threshold else "",
                        "score": r["score"]})
    return {
        "arm": "lexical-tfidf", "kind": "baseline",
        "description": "tf-idf cosine of the question against the 32 decision texts. No model and no Pulse. Abstains below a score threshold chosen on dev.",
        "method": "tf-idf cosine, no stemming, fixed stop word list (scripts/lexical_baseline.py)",
        "decisions": len(decisions), "abstention_threshold_chosen_on_dev": threshold,
        "legacy_ten_on_recorded_twelve": {"questions": len(legacy), "top1_correct": len(legacy_hits), "misses": [q["id"] for q in legacy if q["id"] not in legacy_hits],
                                           "rows": legacy_rows},
        "answers": answers, "tasks": [], "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(score_arms.ARMS_DIR / "lexical-tfidf.json"))
    a = ap.parse_args()
    res = run()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2) + "\n")
    leg = res["legacy_ten_on_recorded_twelve"]
    print(f"legacy ten questions on the 12 recorded decisions: lexical top-1 {leg['top1_correct']} of {leg['questions']} (misses {', '.join(leg['misses']) or 'none'})")
    print(f"{res['decisions']} decisions, abstention threshold {res['abstention_threshold_chosen_on_dev']} (chosen on dev)")
    print(score_arms.format_scores(score_arms.score(corpus.questions(), res["answers"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
