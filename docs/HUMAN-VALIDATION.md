# Human validation of the reference decisions and the questions

**Status: pending. No human has reviewed the 22 reference decisions or the 53 questions.** The reviewer is to be a named person with software engineering context. None is named yet, so no review date exists. Until the review is done, every score in this repository is scored against a model-authored key and is exploratory.

## Why this matters

The reference list (22 entries) was written by an assistant model after the first recorded run. The 53 questions were written by an assistant model (dev, held-out, 16 by `claude-haiku-5-5`) or are the original ten. A second model (`claude-sonnet-5-5`, same vendor family) reviewed both on 2026-10-30 as a draft: [`corpus/MODEL-REVIEW-REPORT.md`](../corpus/MODEL-REVIEW-REPORT.md). A model agreeing with a model is not independent adjudication. The draft found these problems, none of which is resolved:

- the reference list is incomplete relative to choices visible in `app/` (the draft names 9 candidates in its JSON);
- 5 of 22 reference entries have partly wrong lines or keywords;
- 3 questions (`m8`, `l2`, `l3`) are answered by two decisions, and the scorer used to accept only one expected slug;
- 6 model-authored questions (`m3`, `m6`, `m9`, `m10`, `m11`, `m12`) are near-copies of their decision's wording.

These can move the reported Recorder coverage (7 to 10 of 22) and the answer counts in either direction. How much has not been measured.

## What is prepared (no human judgement filled in)

| Item | Where |
|---|---|
| Protocol, versioning rule, key formats | [`corpus/validation/README.md`](../corpus/validation/README.md) |
| Blank review sheet, 22 reference decisions and the candidates for missing ones | [`corpus/validation/reference_review_sheet.json`](../corpus/validation/reference_review_sheet.json) |
| Blank review sheet, 53 questions and 2 conflict tasks | [`corpus/validation/question_review_sheet.json`](../corpus/validation/question_review_sheet.json) |
| Generator for both sheets (`--check` verifies them) | [`scripts/make_review_sheets.py`](../scripts/make_review_sheets.py) |
| Re-scoring of stored outputs with a v2 key, no model call | [`scripts/rescore_with_key.py`](../scripts/rescore_with_key.py) |
| Multi-answer scoring: a question or conflict task may list `accepted_slugs` | [`scripts/score_arms.py`](../scripts/score_arms.py) (`accepted_slugs`) |
| Tests with synthetic keys (not reviewed keys) | [`tests/test_rescore.py`](../tests/test_rescore.py) |

Each sheet entry holds a `model_note` copied from the model draft, labelled as such. The human fields are all `null`.

## Rules

- **v1** (the original keys in `corpus/`) is never rewritten. **v2** is the key a human reviewer writes to `corpus/validation/v2/`. Nobody else writes there, and a key made by a model is not a v2 key.
- The reviewer records: reviewer, review date, decisions made, unresolved disagreements (fields at the top of each sheet).
- A v2 key changes scores by re-scoring the **stored** outputs. Model arms are run again only if question wording, accessible evidence or the tasks change materially.
- v1 and v2 numbers are published side by side. A change is reported in either direction.

## What re-scoring can and cannot do

It reads `demo-state/arms/*.json`, the Recaller, retrieval and Recorder files of every run under `demo-state/llm-runs/`, and the first recorded Recorder run. Stored answers record the decision slug the agent named, whether it abstained and the answer text, so multi-answer scoring, a changed abstention label, accepted alternatives on conflict tasks and a changed reference list can all be re-scored.

It cannot: change the Reviewer outcomes (edges, superseded state), costs, tokens or times (none depends on the key); score an answer to a question the reviewer rewrote (that needs a new run); tell which evidence an agent used (the stored outputs do not record that, so "which evidence is sufficient" is a judgement for the reviewer and does not feed the scorer); re-check citations (that is [`scripts/check_citations.py`](../scripts/check_citations.py), which reads `app/`).

## Acceptance (follow-up review 4.2)

| Criterion | State |
|---|---|
| Versioned, human-reviewed evaluation key | not done, pending a named human reviewer |
| Corrected citations | not done; the draft lists 5 entries to check |
| Defensible multi-answer scoring | the scorer supports it; no human-approved answer sets exist yet |
| Account of how the revised judgements change the metrics | not possible before a v2 key exists; `scripts/rescore_with_key.py` produces it |
| Separation of validated findings from model-generated exploratory evidence | validated findings: none. Everything scored against v1 is exploratory |
