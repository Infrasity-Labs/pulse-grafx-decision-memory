# Response to the follow-up review

This maps each P0 and P1 item of the follow-up technical review (October 30, 2026, of the merged `main`) to the files changed and a status. Statuses: Done, or In progress with what is left. Links point to `main`.

## Change summary

| Priority | Review item | Files | Status |
|---|---|---|---|
| P0 | Reword the ~3x result as an agent-session comparison and disclose the access and setup asymmetries | [README.md](../README.md) (Limits section), [SCOREBOARD.md](SCOREBOARD.md#agent-session-cost-under-the-tested-tool-configurations), [FINDINGS.md](FINDINGS.md), `scripts/render_scoreboard.py` (column header) | Done |
| P0 | Human-validate the reference decisions and questions, correct citations and multi-answer scoring, re-score | [HUMAN-VALIDATION.md](HUMAN-VALIDATION.md), `corpus/validation/`, re-scoring scripts, [EVIDENCE-AND-CONTROLS.md](EVIDENCE-AND-CONTROLS.md) | In progress (the human review has not happened; reviewer name and date are blank; scores stay exploratory) |
| P0 | Make supersession semantics explicit; show a verified end-to-end path or disclose the limitation | [README.md](../README.md#relationship-reconciliation-and-active-state), [PRODUCT-OBSERVATIONS.md](PRODUCT-OBSERVATIONS.md) items 2, 3, 13, 14 | In progress (the edge, action and state distinction is written; the bounded end-to-end lifecycle run is planned and not recorded) |
| P0 | Reconcile the scanner report | `scripts/scan_repo.py`, tests | Done (see below) |
| P0 | CI wording | [README.md](../README.md) (Live or Recorded) | Done (see below) |
| P0 | Current links and version-specific SDLC claims | [README.md](../README.md), docs | Done: no link to a review branch or the old branch found in README, `docs/` or workflows; links point to `main`. Sprints are retired in Pulse 0.4.2, and no live spec, sprint, task path is described |
| P0 | Pin the scope of claims; license clarity | [README.md](../README.md) (Licenses, Limits) | Done: versions, model, run counts and limits sit beside the cost statement; the Licenses table separates demo code, `app/` and the Elastic-licensed products |
| P1 | SDD-aware ingestion, maintenance, retrieval and agent-overhead benchmark at several scales | [SDD-COST-BENCHMARK-PROPOSAL.md](SDD-COST-BENCHMARK-PROPOSAL.md) | In progress (proposal written; the benchmark has not been run) |
| P1 | Restricted-tool MCP overhead, payload sizing | [SDD-COST-BENCHMARK-PROPOSAL.md](SDD-COST-BENCHMARK-PROPOSAL.md) | In progress (planned as a control in the proposal; not measured; may need the Pulse maintainers) |
| P1 | Operational and product findings stated accurately | [PRODUCT-OBSERVATIONS.md](PRODUCT-OBSERVATIONS.md) (items 2, 5, 8, 9, 11) | Done (already documented; the doc is kept) |
| P1 | Closeout races, supersession consistency, delayed writes after restart | [PRODUCT-OBSERVATIONS.md](PRODUCT-OBSERVATIONS.md) | In progress (documented here; triage and fixes belong to the Pulse and Grafx maintainers) |

## What the measured cost figure includes and excludes

The figure is the ratio of mean model-reported agent-session cost: $0.462 with the graph against $0.152 with plain notes, 3.05 times. The raw artifacts are the arm files in [`demo-state/arms/`](../demo-state/arms/) (`llm-memory.json`, `llm-code-notes.json`, `llm-no-memory.json` and the per-run folders), field `run_stats` of each run. The means were recomputed from those files for this response and match the review's table.

- **Included:** one agent session is 43 questions and 2 change proposals; 5 sessions per arm; `claude-opus-5-5`; model-reported `total_cost_usd`, wall time, tool calls, output tokens and cache-read input tokens.
- **Excluded:** building and maintaining the knowledge sources (the 32-decision board and the notes file were prepared before the arms ran); database query cost, which was not measured; ingestion and lifecycle cost.
- **Not comparable one to one:** the arms had different access. The graph arm had the read-only Recaller and no source code; the notes arm had Read, Grep and Glob on `app/` plus the notes file; the code-only arm had files only.
- **Not attributable:** the cache-read counters add up across turns and do not show which part of the interface caused the cost. The large MCP tool catalog may contribute; it was not isolated. The data do not say that Grafx retrieval costs more.

## Human-review record

**Status: review pending.** No person has reviewed the 22-item reference decision list or the 53 evaluation questions. The review that exists was done by a model and is a draft ([model review](../corpus/MODEL-REVIEW-REPORT.md)).

| Field | Value |
|---|---|
| Reviewer (name, role) | to be filled in by a named human reviewer |
| Review date | to be filled in |
| Decisions made, unresolved disagreements | none recorded yet |
| Corrected key and updated score comparison | not produced; see [HUMAN-VALIDATION.md](HUMAN-VALIDATION.md) for what is prepared |

Until a named human reviewer completes this, every recall and accuracy score in this repo is exploratory and not independently validated. The original keys stay as they are.

## Scanner reconciliation

The earlier scan reported two machine-local path findings in an agent transcript. Both came from one rule: for files that hold verbatim model or tool output, the scanner flagged any line containing the machine's home folder as a plain substring. When the home folder was `/root` (a Linux container), the word `root` in `source/root Entity` matched. The two hits were not real paths. The fix is in `scripts/scan_repo.py`: the home folder now counts only as a whole path (not after a name character or `name/`, not followed by a name character), and a home of `/` is never searched for. The other path rules (`/Users/<name>`, `/home/<name>`, `C:\Users`, the dash-encoded form) are unchanged. Final result on this tree: `scripts/scan_repo.py` reports 0 hits over 800 files, both with the local home and with `HOME=/root`.

## CI scope

- `validate` runs offline on the recorded files.
- `integration` runs real Pulse and Grafx with scripted steps and no model.
- The live model studies (steps 3 to 5 with a model, the three arms) run only from the manual `llm-steps` workflow. A push does not rerun them. The recorded model runs were made locally.
- Weekly `links` checks external links.
