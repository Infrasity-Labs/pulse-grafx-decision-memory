# Product observations

What this demo saw in Okto Pulse 0.4.2 and Okto Grafx 0.0.8 that differs from the docs or from what a reader would expect. These are not defects of the demo. Each entry says where the raw evidence is.

**Status.** Every entry was reported by this repository from its own recorded run (run 1, 2026-10-29, macOS arm64). An outside reviewer listed them in a technical review dated 2026-10-29 and **did not reproduce them**. Nothing here has been confirmed by OktoLabs. Treat them as reports with evidence, to be checked against a fresh install before they are filed as bugs. Items 8 to 13 come from the scripted run (`demo-state/scripted-run/`, `demo-state/notes/`): one run, macOS arm64, Pulse 0.4.2 and Grafx 0.0.8. Items 14 and 15 come from the live model runs of 2026-10-29 (`demo-state/llm-runs/`), and item 5 was re-checked in three more Kill B runs. Item 7 was explained from the installed source in this repo, see below.

The rest of the surprises, including ones that are not about the products, are in [FINDINGS.md](FINDINGS.md).

## 1. The decision-history tool returns nothing for sentence-length topics

Topics in the form of a whole sentence returned no decisions. The semantic path returned nothing for any topic tried. The non-semantic path returned the password decision for short keyword topics such as `bcrypt`. Similarity and natural-language search ranked the right decision first for every question, so this is specific to the decision-history tool.

Evidence: [`demo-state/step4/history-probe.json`](../demo-state/step4/history-probe.json), the "decision history" column of the recall table in [SCOREBOARD.md](SCOREBOARD.md) (0 of 10).

## 2. Pulse does not flag a reversal as a contradiction by itself

After a `SUPERSEDE` override, `find_contradictions` returned 0 pairs and `propose_reconciliation` returned `ADD` with "no semantic match", although `get_similar_nodes` had just returned the old decision. The pair appeared only after an explicit `contradicts` edge, which the prompt told the agent to add.

Evidence: [`demo-state/step5/after.json`](../demo-state/step5/after.json), the three `find_contradictions` results in [`demo-state/step5/agent/transcript.jsonl`](../demo-state/step5/agent/transcript.jsonl), row "Contradictions" in [FINDINGS.md](FINDINGS.md).

## 3. `SUPERSEDE` reports `nodes_added: 0`, and processes stay behind after SIGKILL

- The commit that applied the `SUPERSEDE` reported `nodes_added: 0` although the new node exists. The supersedence chain has length one from the new decision and length zero from the old one, which still names itself as `current_active`. Evidence: [`demo-state/step5/after.json`](../demo-state/step5/after.json) and the commit result in the Reviewer transcript.
- After every SIGKILL of the server, two `multiprocessing` helper processes stayed alive with parent PID 1. They held none of the board's files. Evidence: [`demo-state/notes/orphans-after-sigkill.txt`](../demo-state/notes/orphans-after-sigkill.txt).

## 4. The tool list is not filtered by permission preset

The installed server listed 288 MCP tools for each of the four identities. A call outside the preset is refused at call time. Evidence: [VERIFIED.md](VERIFIED.md) (Differences from the plan), the `init` event on line 1 of [`demo-state/step4/agent/transcript.jsonl`](../demo-state/step4/agent/transcript.jsonl), the refused write in [`demo-state/step4/recall-results.json`](../demo-state/step4/recall-results.json).

## 5. A killed server often blocks writes for about 300 seconds

After Kill B (SIGKILL during a commit burst) the board refused new commits with `lock_contention` ("another writer currently owns the board graph") until the writer lock's default 300 s TTL ran out: 310.6 s in run 1, 309.3 s in the first scripted run, 305.8 s in a Linux container. In a fourth run (macOS, integration run) the first write after the restart was accepted, 81.4 s after the kill, with no refusal. Acknowledged commits were present in all four (20 of 20, 24 of 24, 14 of 14, 16 of 16), so this is a wait, not a loss. Evidence: the `killB.json` files in [`demo-state/step7/`](../demo-state/step7/), `demo-state/scripted-run/step7/`, `demo-state/integration-*/step7/` and `demo-state/linux-crash-*/step7/`, [`restart-log-killB.txt`](../demo-state/step7/restart-log-killB.txt), the side-by-side table in [SCOREBOARD.md](SCOREBOARD.md#crash-tests-side-by-side). I did not find what decides whether the lease is still held when the server restarts.

## 6. `okto_pulse_kg_list_key_decisions` exists only in REST

The "Key Decisions" list of the web UI is a Discovery intent served over REST. It is not an MCP tool in 0.4.2, so an agent cannot call it. Evidence: [`demo-state/step4/history-probe.json`](../demo-state/step4/history-probe.json) (`key_decisions_intent`).

## 7. The `index` folder of a nearly empty Grafx store is about 200 MB

206744 KiB across 408 index files for a board with a handful of nodes, while `heap.dat` is 168 KiB. **Explained from the installed source, not reproduced.** An exact hash index gets a head page for every one of its 64 default buckets when it is created, so each costs 520 KiB at 8 KiB pages. 408 files at that size would be 212160 KiB. Details and limits of that explanation are in [FINDINGS.md](FINDINGS.md) (row "Store size"). Whether the files are sparse on disk was not checked. Evidence: [`demo-state/step2/store-layout.txt`](../demo-state/step2/store-layout.txt).

## 8. Spec decisions are not recallable until a closeout consolidation

Decisions added with `okto_pulse_add_decision` appear as working-layer Decision nodes. Canonical search (`find_similar`, `query_natural`) never returns them until a closeout consolidation has run. A lone Decision node is refused with `kg_node_connectivity_violation`; it needs an Alternative node and a `relates_to` edge. In the scripted run the read-only Recaller found 0 of 10 by similarity search before the closeout. Evidence: `demo-state/scripted-run/step3b/spec-flow.json`, [EVIDENCE-AND-CONTROLS.md](EVIDENCE-AND-CONTROLS.md#decisions-through-pulses-own-flow-and-the-gate-review-22).

## 9. Pulse's own session can undo a closeout

Pulse's `system:historical_consolidation` session, lagging the spec by 20 s or more, re-projected the spec's decisions into the working layer and superseded the canonical nodes after a closeout. About 23 seconds after the closeout canonical search returned none of them. `scripts/spec_flow.py` now waits until that session has been quiet for 30 seconds before and after the closeout. That wait is a workaround for the demo, recorded in `spec-flow.json`. Evidence: [`demo-state/notes/closeout-superseded-by-system-session.json`](../demo-state/notes/closeout-superseded-by-system-session.json).

## 10. A transient `database is locked` error returned to the agent

`okto_pulse_submit_spec_evaluation` returned `sqlite3.OperationalError: database is locked` once, in an exploratory run, and succeeded on retry. **Seen once, not recorded.** The recorded run has no such error: `retries_on_transient_error` in `spec-flow.json` is 0. `spec_flow.py` retries on it, so a later run records it there.

## 11. okto-pulse 0.4.2 has retired sprints

The installed `okto_pulse/core/models/schemas.py` rejects a card-to-sprint link as retired (`card_sprint_link_retired`: defined at line 2998, raised at line 3001). The lifecycle code says `Sprint lifecycle is retired` (`application/use_cases/allowed_transitions.py:311`), lifecycle discovery refuses `entity_type='sprint'` (`mcp/server.py:2740`), none of the 288 MCP tool names contains the word sprint, and no `/sprints` route string exists in the package. Sprint-related permission names and ownership entries are still in the code, so this says the sprint path cannot be used, not that every trace was removed. The spec, sprint and task path named in the review therefore cannot be followed in this version. Evidence: the installed source, as read for [EVIDENCE-AND-CONTROLS.md](EVIDENCE-AND-CONTROLS.md#decisions-through-pulses-own-flow-and-the-gate-review-22).

## 12. Most Reporter write refusals are `session_ownership_mismatch`

Of the 10 refused Reporter actions in the scripted role probe, 5 were permission refusals and 5 were `session_ownership_mismatch`. For the five session-bound tools the answer does not say the Reporter lacks a permission. Evidence: `demo-state/scripted-run/roles/role-denials.json`.

## 13. Reconciliation applies `SUPERSEDE` at commit for near-identical text

In an exploratory run (not recorded), a retried burst commit also marked an older, unrelated burst decision as superseded, because the synthetic texts were almost identical and Pulse applied its reconciliation hint `SUPERSEDE` at commit. An observation, not evidence. See the Kill B bullet in [EVIDENCE-AND-CONTROLS.md](EVIDENCE-AND-CONTROLS.md#crash-tests-tied-to-the-story-review-33).

## 14. A `supersedes` edge does not flag the old decision as superseded

Without the override JSON of the recorded run, the goal-based Reviewer recorded the new decision with a `supersedes` and a `contradicts` edge to the old one in 5 of 5 runs, and Pulse then reported one contradiction pair. In 4 of 5 the old node's `superseded_by` and `superseded_at` stayed empty, the commit reported `nodes_superseded 0`, and the supersedence chain asked from the old decision's id still named the old decision as `current_active`. Asked from the new decision's id it showed the old one at depth 1 with `superseded_by` null. In the fifth run the Reviewer overrode the `ADD` hint of `propose_reconciliation` with a `SUPERSEDE` at commit, and then the old node was flagged. So the flag comes from the reconciliation action, not from the edge, and the default hint for a reversal was `ADD`. Evidence: `demo-state/llm-runs/<run id>/n-runs-reviewer-scripted-base/run-*/step5/after.json` and the Reviewer transcripts. Five runs, one model.

## 15. The documented write format is an MCP resource

The guidance for writing to the graph is the resource `okto-pulse://workflows/kg`. A headless Claude Code session has no way to read an MCP resource unless it is given the two resource tools, so the 17 Recorder and Reviewer sessions of the first live runs reported that they could not read it. The Reviewers describe finding the call shapes by trial and error: an edge candidate to an existing node was refused with `to_node_id` ("to_candidate_id required"); one Reviewer got it accepted with a `kg:` prefixed id in `to_candidate_id`, another added a copy of the old node as a candidate. A client without resource support gets no documentation of the write path from the server. This was a defect of this repo's harness first (fixed, see [VERIFIED.md](VERIFIED.md)); it is listed because it shows that the server's own instructions depend on a client feature. Evidence: the `problems` fields of the Reviewer results in `n-runs-reviewer-scripted-base/`.
