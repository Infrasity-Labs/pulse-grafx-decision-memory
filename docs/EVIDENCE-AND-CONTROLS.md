# Evidence and controls

What each result in this repo proves, what it only shows, and what has not been run. Read this before you quote a number.

## Kinds of evidence

| Kind | Where | What it is | What it can show |
|---|---|---|---|
| Recorded agent run (run 1, 2026-10-29) | `demo-state/step1` to `step9`, `closeout-result.json` | Three headless Claude Code sessions with answer-key prompts ([`docs/prompts/recorded-run-1/`](prompts/recorded-run-1/)), one machine, one model, one run | That Pulse and Grafx store, return, reverse and restore decisions when an agent is told exactly what to do |
| Scripted run (2026-10-30) | `demo-state/scripted-run/` | The same Pulse calls made by a fixed script, no model, fresh data home. Made by [`run_integration.py`](../scripts/run_integration.py) | What Pulse and Grafx do with a fixed call sequence: the spec gate, role denials, crash recovery. Nothing about what an agent chooses |
| Offline baselines | `demo-state/arms/lexical-tfidf.json`, `docs/QUESTIONS.md` | A tf-idf match and a word-overlap count, no Pulse, no model | How hard the questions are for a plain lexical match |
| Live runs with a model, goal-based prompts (2026-10-29) | `demo-state/llm-runs/<run id>/`, `demo-state/arms/llm-*` | 48 headless Claude Code sessions with `claude-opus-5-5`: a smoke run, three five-run studies of the Recorder, Recaller and Reviewer, and the three arms five times each. Manifest with SHA-256 per file | How a model behaves with a goal and no answer key, its spread over five runs, and whether the graph beats the controls on this corpus |
| Dated integration and Linux container runs (2026-10-29) | `demo-state/integration-<run id>/`, `demo-state/linux-crash-<run id>/` | Scripted agents, no model, a fresh data home. One run with step 9, one in a Linux container through step 8 | What Pulse and Grafx do on macOS and on Linux with a fixed call sequence, including SIGKILL |

## Is the graph better than no graph? (review 2.1)

The first recorded run showed that Pulse's search finds a node on a 12-node board (10 of 10). It did not show a benefit: the 12 nodes held facts that the code holds too, there was no control, every question had one right node, and no later session was tested on respecting a reason. This pass adds what a control needs.

**The corpus.** 32 decisions: the 12 recorded ones, 10 more that the code shows (each with a file, a line and the exact line text, checked by a test), and 10 whose reason is written nowhere except in the graph (for example why there are no refresh tokens). Every graph-only reason is invented for the demo and says so in its text. There are near-duplicate families (six token decisions, four password decisions, two error-shape decisions, two ownership decisions). Source: [`corpus/decisions.json`](../corpus/decisions.json).

**The questions.** 53 questions in four splits. `dev` (13) and `held_out` (14) were written after the 32-decision board existed, by an assistant model (not the Recorder model, not a person). `model_authored` (16) was written by `claude-haiku-5-5` from the decision texts alone, none dropped afterwards, and is scored separately ([`corpus/questions-model-authored.json`](../corpus/questions-model-authored.json), prompt and raw reply in `corpus/authoring/`). `legacy` is the original ten. Ten are unanswerable on purpose (three each in dev and held-out, four in model-authored) (nothing in the graph answers them) and the right output is an abstention. Two change proposals conflict with graph-only decisions (add refresh tokens, add soft delete): the right output is to find the decision and to stop or adapt. The word overlap between each question and its answering decision is computed and published in [QUESTIONS.md](QUESTIONS.md), including that five held-out questions were reworded once to lower it. The abstention threshold of the lexical and Pulse arms is chosen on `dev` only and applied to the rest.

**A model reviewed the reference list and the questions (draft, not a person).** On 2026-10-30 a model (`claude-sonnet-5-5`, run as a subagent; a different model from the authors but the same vendor family) read the 22-entry reference list and all 53 questions against `app/` and `corpus/decisions.json`. Its files are [`corpus/reference_decisions_model_review.json`](../corpus/reference_decisions_model_review.json), [`corpus/questions_model_review.json`](../corpus/questions_model_review.json) and [`corpus/MODEL-REVIEW-REPORT.md`](../corpus/MODEL-REVIEW-REPORT.md). The originals were **not** changed and nothing was re-scored. Findings:

- Before this fix the list's own text called it "hand-made", but an assistant model wrote it. A person did not.
- All 22 decisions are really in the code. The cited lines are fully right for 17 and partly wrong for 5 (for example `settings-loading` cites line 16, which is blank; the decorator is on line 17 of `app/app/core/config.py`; `duplicate-registration` cites line 75, and its keyword "already taken" is in no code, because `strings.py` says "already exists"). A new maintainer must know the decision: 14 yes, 7 borderline, 1 no (`jwt-subject-claim`).
- **The list is not complete.** It misses decisions the code shows, for example: the salt is prepended to the password before hashing (`models/domain/users.py:20,24`); every authentication failure answers 403, not 401 (`api/dependencies/authentication.py:54,59,90,98`); the token prefix is `Token` (`core/settings/app.py:29`); hard deletes with cascading foreign keys (`db/repositories/articles.py:93-99`); renaming an article regenerates the slug with no existing-slug check (`routes/articles/articles_resource.py:100`); camelCase JSON field names (`models/domain/rwmodel.py:10,21`); a failed login answers 400 (`routes/authentication.py:29-30`); a 100 percent coverage gate (`pyproject.toml:58`). So "decisions recorded out of 22" is recall against an incomplete list, and a recorded decision outside the list is not credited.
- Of the 53 questions: 28 have exactly one right decision, 12 have one with a caveat, 3 (`m8`, `l2`, `l3`) are answered by two decisions, and the 10 unanswerable ones are confirmed (their absent terms are missing from all 32 decision texts and from `app/`). `m3`, `m6`, `m9`, `m10`, `m11` and `m12` are near-copies of their decision's wording.

What this means for the recorded numbers: they were scored against the original list and keys, so the reference coverage (7 to 10 of 22) may be wrong in either direction for the 5 entries with wrong lines or keywords, and the three two-answer questions could be scored wrong when an arm names the other correct decision. This has not been measured. A project member read the review's summary and its examples on 2026-10-30 and found no problems, but nobody has decided which proposed fixes are right; only then should the list be corrected and the studies re-scored.

**The arms and one scorer.** Every arm is scored by [`scripts/score_arms.py`](../scripts/score_arms.py): an answerable question is right if the arm names the expected decision (or, with no decision named, if the answer carries a fact the decision holds; a graph-only question needs the invented reason); an unanswerable question is right only if the arm abstains; a conflict task needs the decision cited and a stance of stop or adapt.

| Arm | State |
|---|---|
| Lexical tf-idf baseline ([`lexical_baseline.py`](../scripts/lexical_baseline.py)) | Run. Replaces the inline script of the review. On the original ten questions and the 12 recorded decisions it gets 7 of 10 (the review's inline script got 7 of 10 too, with misses 2, 6 and 9; this one misses 2, 4 and 9) |
| Pulse retrieval, scripted client ([`arm_pulse_retrieval.py`](../scripts/arm_pulse_retrieval.py)) | Run on three data homes (first scripted run, dated integration run, Linux container run) and in each of the 16 live runs (smoke run and variance studies). Not an agent |
| LLM with the graph, LLM with the code only, LLM with the code and plain notes ([`run_arms.py`](../scripts/run_arms.py)) | Run, five times each on one board, `claude-opus-5-5` |

The side-by-side table is in [SCOREBOARD.md](SCOREBOARD.md#arms-side-by-side) and is generated from the arm files. **Measured difference:** Pulse's search is better than the tf-idf match on the dev and held-out splits and fabricates an answer to one unanswerable question in each split. An agent with the graph and an agent with a text file of the same 32 decisions did not differ (one question apart in 43, five runs each), and both beat the agent with only the code on every question whose answer lives only in the graph or the notes, which is true by construction because those reasons are invented. So the measurement supports "a memory helps when the answer is only in the memory", and does not support "the graph is better than plain notes". It says nothing about a memory too large to read in one file.

The arms were run with `scripts/build_corpus.py` and then `run_arms.py --runs 3` and `run_arms.py --runs 2 --append`, on the splits dev, held_out and model_authored. To run them (calls Claude Code, costs about $0.15 to $0.9 per arm and run):

```bash
python run_demo.py --steps 1 2
.venv/bin/python scripts/build_corpus.py          # scripted: 32 decisions through the Pulse flow
.venv/bin/python scripts/run_arms.py --runs 5 --splits dev held_out model_authored   # memory, no-memory, code-notes; writes demo-state/arms/llm-*.json
python scripts/render_scoreboard.py --write
```

## Decisions through Pulse's own flow, and the gate (review 2.2)

[`scripts/spec_flow.py`](../scripts/spec_flow.py) records the 10 graph-only decisions the way a team would: `okto_pulse_add_decision` on a spec (rationale, alternatives, verification plan), moved through review and approved, validated by a second identity, then closed out into the graph. The record is `demo-state/scripted-run/step3b/spec-flow.json`.

What the record shows:

- **Gate refused.** The spec has one decision with no verification plan. The validation is refused with `spec_validation_gate_not_ready: decision_verification_plan_incomplete`. A direct move to `validated` is refused too. `get_spec_validation_cycle` lists the blocked components.
- **Gate passed.** The Maintainer reopens the spec (a new edition). The missing plan is added. The same validation then promotes the spec to `validated`.
- **The Spec preset is refused** the reopen it tried before (`spec.move.approved_to_draft`).
- **Spec decisions are not recallable by themselves.** After approval they exist as Decision nodes in the working layer. The read-only Recaller found 0 of 10 by similarity search, which reads the canonical layer. Only a closeout consolidation (Decision plus Alternative nodes, `relates_to` edges) makes them canonical. A Decision with no such edge is refused by the connectivity rule (`kg_node_connectivity_violation`). This is a product behaviour worth knowing, not a demo defect: see [PRODUCT-OBSERVATIONS.md](PRODUCT-OBSERVATIONS.md).
- **A worker of Pulse's own can undo a closeout.** In the first scripted run the closeout was committed right after the validation. About 23 seconds later Pulse's own `system:historical_consolidation` session re-projected the spec's decisions into the working layer and superseded the canonical nodes, so canonical search returned none of them. The evidence is kept in `demo-state/notes/closeout-superseded-by-system-session.json`. `spec_flow.py` now waits until that worker has been quiet for 30 seconds before the closeout and after it, records the wait, and a runtime assertion checks that the canonical nodes are still active. The wait is a workaround for the demo and is reported as a product observation, not hidden.

**What the scripted gate does not show.** The scores in the lint, evaluation and validation calls are fixed values written by the script, and their justification says so. They exercise the gate. They are not a judgement of the decisions by a model, and a real reviewer may score differently and be refused.

**The sprint and task part of the path.** The review asks for the spec to sprint to task path. In okto-pulse 0.4.2 sprints are retired. The installed `okto_pulse/core/models/schemas.py` rejects a card-to-sprint link as retired (`card_sprint_link_retired`: the check is defined at line 2998 and raises at line 3001), the lifecycle code says `Sprint lifecycle is retired` (`application/use_cases/allowed_transitions.py:311`), lifecycle discovery refuses `entity_type='sprint'` (`mcp/server.py:2740`), none of the 288 MCP tool names contains the word sprint, and no `/sprints` route string exists in the package. Sprint-related permission names and ownership entries are still in the code, so this is a statement about the path that can be used, not that every trace was removed. The flow therefore stops at a validated spec. It creates no Task card, because Pulse's own documentation for `okto_pulse_add_decision` says not to create a Task or Test Card solely to cover a Decision.

### What Pulse did and what the script or the prompt told

| Step | Pulse did | The script or the prompt told it |
|---|---|---|
| Store a decision on a spec | Created the id, kept the alternatives and the plan, refused a malformed plan | The content of every decision |
| Refuse the validation | Computed the blocked component and returned the error | The script left one plan out on purpose |
| Promote to validated | Checked the gates, promoted the spec | The scores and the order of the calls |
| Put decisions in the graph | Its deterministic worker created working-layer Decision nodes after the spec was approved | Nothing |
| Make decisions canonical | Enforced the connectivity rule and reconciled the candidates (an exact source reference gave a `SUPERSEDE` of the working node) | The closeout: which nodes, which `relates_to` edges |
| Reverse a decision | Applied the `SUPERSEDE` override it was given: old node marked superseded, chain of length 1 from the new decision | In the recorded run the prompt gave the override JSON. Pulse flagged no contradiction by itself (0 pairs after the supersede). This is the answer-key run only; without the override, the goal-based Reviewers marked the old node superseded in 1 of 5 runs (see [Decision lifecycle](#decision-lifecycle-what-is-recorded)) |
| Contradiction pair | Stored the edge and then reported one pair | The explicit `contradicts` edge was added because the prompt said to. It is an agent-added step, not a Pulse feature |
| Role limits | Refused each action outside a preset and named the missing permission, or refused a foreign session by ownership | Nothing |
| Survive SIGKILL | Grafx and Pulse kept every acknowledged commit | Nothing |
| Resume after Kill A, retry after Kill B | Reconciled the repeated decisions: `UPDATE` for the ones already committed, `ADD` for the new ones | The decision to replay. This is application logic, not a Pulse feature |

### The `final_report:` prefix

The 12 recorded and the 10 code-derived decisions use the source reference `final_report:<spec id>:decision:<slug>`. Pulse's connectivity rule asks a Decision for a judgement edge (to another Decision or to an Alternative) or a technical root. In the installed 0.4.2 `okto_pulse/core/kg/connectivity_guard.py` (lines 480 to 513) `final_report:` is on the list of technical-root prefixes for Decision nodes written by `commit_consolidation`. The code-derived facts have no alternative and no other decision to point at, so they use the prefix. No final report exists in the demo. The prefix is a way past the connectivity rule, not a link to real work. The 10 graph-only decisions use the documented route instead (`spec:<spec id>:decision:<decision id>`, with Alternative nodes).

### Role claim, tested in both directions

[`scripts/probe_roles.py`](../scripts/probe_roles.py) (record: `demo-state/scripted-run/roles/role-denials.json`) tries actions outside each preset and an action inside it. Reporter: 5 permission refusals and 5 refusals by session ownership. Spec: 4 permission refusals. Validator: 5 permission refusals. Every identity also succeeded at its own work. Two kinds of refusal appear and they are different: a missing permission (named in the answer), and, for the five session-bound tools, ownership of someone else's session. The Reporter reaches the ownership check there, so the answer does not say the Reporter lacks a permission for those tools. The preset stops it earlier, at `begin_consolidation`.

## Prompts without answer keys (review 3.1)

The prompts of the recorded run listed the 12 slugs, fixed the Recaller's tool order, and handed the Reviewer the old slug, the query, the override JSON and the edge ids. They are kept, unchanged, in [`docs/prompts/recorded-run-1/`](prompts/recorded-run-1/) because the recorded outputs came from them. The prompts in [`docs/prompts/`](prompts/) give a goal and the tools:

- **Recorder**: record the decisions a new maintainer must know. No slugs. Scored by citation validity (every file and line must exist) and by recall against an assistant-written reference list ([`corpus/reference_decisions.json`](../corpus/reference_decisions.json)) that is in no prompt. Measured on the recorded run, the twelve nodes it wrote cover 12 of the 22 reference decisions.
- **Recaller**: answer from the graph, any tools, any order, abstain when the graph has no answer, report the tools used. Scored on the final answer, per split.
- **Reviewer**: the Maintainer's note and the goal. If the note has no reason, record nothing. A second note without a reason ([`maintainer_reverse.py --no-rationale`](../scripts/maintainer_reverse.py)) is the failing path.

A test checks that no prompt contains a slug, an override or an edge id, and a second test checks the rendered prompts of every live run. **These prompts were run 33 times** (smoke run, three studies): see [the live runs](SCOREBOARD.md#live-runs-with-a-model). Measured against the assistant-written reference list (not human-reviewed, see [HUMAN-VALIDATION.md](HUMAN-VALIDATION.md)), the goal-based Recorder covers 7 to 10 of 22 decisions, against 12 of 22 for the answer-key run. The prompts also made two weaknesses visible that the answer-key prompts hid: the Recorder never wrote the decision the note later reverses (0 of 11 runs), and without the override JSON only 1 of 5 Reviewers flagged the old node as superseded. Run them with `python run_demo.py --steps 3 4 5`.

## Decision lifecycle: what is recorded

The reversal is **not shown to work end to end** by the recorded evidence. What is recorded, and what is not:

- **Fresh agent-recorded boards.** The goal-based Recorder never wrote the decision the Maintainer later reverses (the shape of HTTP error bodies): 11 of 11 runs. The Reviewer then had no old decision to supersede, wrote nothing and said why. The chain Recorder, Recaller, Reviewer did not succeed end to end in those runs.
- **Prepared board.** In the study where the scripted client built the board (so the old decision is on it), 5 of 5 Reviewers created a `supersedes` edge and a `contradicts` edge, and Pulse then reported one contradiction pair. Only 1 of 5 marked the old node superseded; that one overrode Pulse's `ADD` hint with `SUPERSEDE`. In the other four the old node still reads as the current decision when asked from its own id. Source: `demo-state/llm-runs/<run id>/n-runs-reviewer-scripted-base/summary.json` (`reviewer.supersedes_edges`, `reviewer.contradicts_edges`, `reviewer.old_marked_superseded`).
- **Three different things.** A relationship **edge** (`supersedes`, `contradicts`) records a link. A **reconciliation action** (`SUPERSEDE`, `UPDATE`, `ADD`) is an operation applied at commit. The **authoritative state** is whether the old node is active or superseded (`superseded_by`, `superseded_at`). An edge does not set the state; the `SUPERSEDE` action did in the one successful case. A reader that sees the edge can still treat the old decision as active. This is a product and workflow question that the demo does not resolve.
- **Not recorded yet.** A bounded end-to-end lifecycle test is planned: the old decision present and retrievable, a change request with a reason, the Reviewer performing the supported supersession, the edge and the authoritative state both verified, a fresh read that sees the new decision active and the old one superseded, and no invented reversal for a request with no reason or an unrelated decision. It needs a live model run and has **not** been run. No result for it exists in this repository.
- **Natural-prompt failures stay visible.** The 0 of 11 recording of the reversal target and the 1 of 5 state change are kept in the scoreboard and in this repository's findings. They are not removed or explained away by the answer-key run, which only shows what happens when the agent is told the override.

## Variance, the model pin and token use (review 3.2)

- **Model pin.** [`config/agent.json`](../config/agent.json) names `claude-opus-5-5`. `run_agent.py` always passes it with `--model` and records the requested and the reported model. Exercised: Claude Code 2.1.312 accepted the name, and all 48 live sessions requested it and reported it in their `init` event. No alias fix was needed.
- **N runs.** [`scripts/run_n.py`](../scripts/run_n.py) repeats the recording, recall and (optionally) reversal steps and the Pulse arm N times on fresh data homes and reports n, mean, minimum and maximum. `--agents` chooses which sessions call a model; `--scripted` needs none. Recorded: three studies of five runs ([SCOREBOARD](SCOREBOARD.md#live-runs-with-a-model)). A test recomputes the spread, the citations, the costs and the Recaller scores from the saved files.
- **Tokens and time.** [`scripts/runstats.py`](../scripts/runstats.py) reads token counts, cost, turns and wall time from the result event of each session. For the three sessions of run 1 (`demo-state/runstats-run1.json`): Recorder 134.9 s and 13654 output tokens, Recaller 55.7 s and 6488, Reviewer 47.8 s and 3832, one run each. For the goal-based runs, the spread over five runs is in the SCOREBOARD (Recorder 118 s and 13392 output tokens, Recaller 103 s and 9734, Reviewer 39 s and 2314, means; cost $3.24 and 260 s for the three sessions together, against the pilot's about $3.2 and 4 minutes).
- **`previous_session_id`.** The Recorder's `begin_consolidation` returned `previous_session_id kgses_67078ed2f2da49b8` for a spec on a data home that was new. The Recorder opened one consolidation only, and the data home of that run no longer exists, so the recorded files cannot say where the session came from. A probe on a fresh data home ([`probe_previous_session.py`](../scripts/probe_previous_session.py), `demo-state/notes/previous-session-id-probe.json`) shows it: Pulse commits a consolidation session of its own for every new spec, with the agent id `system:historical_consolidation`, within the 40 seconds the probe waited, and `begin_consolidation` reports the latest one as `previous_session_id`. A call made at once after the spec was created had none. For the specific id of the recorded run this is an inference.

## Crash tests tied to the story (review 3.3)

- All crash writes go to their own crash boards (A for the open session, B for the burst). The decision board is never written in step 7, and `decision-board-check.json` records that it has the same decisions before and after. In the first recorded run Kill A wrote drafts to the decision board and the write probe added `Write probe 1` as a Decision; that is why its scoreboard shows 14 decisions. That file is kept as it was.
- **Kill A, resume.** After the restart a new Recorder session replays all six decisions. Pulse's reconciliation answered `UPDATE` for the three committed ones and `ADD` for the three drafts, and each slug exists exactly once.
- **Kill B, retry.** The commits that were in flight are committed again by a new session. No slug exists twice. The record has a field `retry.superseded_by_another_decision`; it is empty in the recorded run. In an earlier exploratory run that is not recorded, a retry also marked an older, unrelated burst decision as superseded, because the synthetic texts are almost identical and Pulse applies the reconciliation hint `SUPERSEDE` at commit. Treat that as an observation, not as evidence.
- **Restore, decision level.** Step 9 reads every Decision node (title, text, source reference, quote) from the original, the copy and the restored folder and compares them. It ran in the dated integration run (a Linux container, because macOS refuses the backup): 43 decisions, original equal to restored, `verify` clean, same database identity. Record: `demo-state/integration-<run id>/step9/`.
- **Image pin.** The step 9 container image is pinned by the digest of its multi-platform index, read on 2026-10-30 with `docker buildx imagetools inspect python:3.12-slim`. It lists python 3.12.16 on Debian trixie, the python version the recorded run reported. The recorded run did not record a digest, so it cannot be tied to this one.
- **Platform.** Kill A and Kill B ran four times: three on macOS and once in a Linux container ([`run_linux_crash.py`](../scripts/run_linux_crash.py), Debian 13 on a Docker Desktop VM, Linux 7.0.12-linuxkit aarch64, torch 2.15.0+cpu, the pins of `requirements.txt` and `constraints.txt`). Results are side by side in [SCOREBOARD](SCOREBOARD.md#crash-tests-side-by-side). The outcomes agree: draft absent, earlier decisions kept, no acknowledged commit lost, resume and retry leave each decision once. The refusal after Kill B (`lock_contention`, about 300 s) appeared in the macOS agent run, the first macOS scripted run and the Linux run, and not in the macOS integration run. The README headline names all four runs. The container is a VM on the same Mac, so this is not a bare-metal Linux host.

## Pinning and ports (review 3.4)

- [`constraints.txt`](../constraints.txt) pins `fastmcp`, `mcp`, `transformers`, `numpy` and the embedding libraries `sentence-transformers` and `torch`. `okto-pulse-core`, `sentence-transformers` and `torch` are the versions recorded in [VERIFIED.md](VERIFIED.md). The others were read from a clean install on 2026-10-30, because the recorded run did not capture them. Install with `pip install -r requirements.txt -c constraints.txt`. `pip install --dry-run` and `pip check` against the constraints on that install found no conflict.
- `scripts/start_pulse.sh` refuses to start when either port is already in use, says which port, and changes nothing. A test starts it against busy ports.

| Pulse | Grafx | Python | Platform | Run |
|---|---|---|---|---|
| 0.4.2 | 0.0.8 | 3.12.13 | macOS arm64 | Agent run 1 (2026-10-29), scripted run (2026-10-30), live model runs and dated integration run (2026-10-29 UTC) |
| 0.4.2 | 0.0.8 | 3.12.16 | Linux aarch64 container (Docker Desktop VM) | Crash run through step 8 (2026-10-29 UTC), step 9 in the same kind of container |

Add a row when a new Pulse or Grafx version appears and the integration workflow has passed on it.

## Commands

```bash
python scripts/run_integration.py            # scripted steps 1 to 9, fresh data home, assertions. No model
python scripts/lexical_baseline.py           # the tf-idf baseline
python scripts/question_overlap.py --check   # the published overlap matches the script
python scripts/check_data_dir_claim.py       # does a run leave ~/.okto-pulse alone
python scripts/run_n.py --runs 5 --scripted  # spread over fresh data homes, no model
python scripts/run_linux_crash.py --out DIR  # Kill A and Kill B in a Linux container (Docker, DOCKER_CONFIG if HOME is temporary)
python scripts/export_llm_runs.py --help     # keep the evidence of live model runs, with a manifest
python scripts/export_scripted_run.py --work .work/integration   # keep a run's evidence in demo-state/scripted-run/
```
