# Findings and limits

What this run found, and what it does not show. Evidence files are linked in each row. Differences from the plan and the docs, in full, are in [VERIFIED.md](VERIFIED.md).

## Limits

> [!IMPORTANT]
> - **Pre-release software.** Grafx is pre-alpha and Pulse is a 0.x line. This repo pins both and was verified on those versions only: okto-pulse 0.4.2 and okto-grafx 0.0.8, on 2026-10-29.
> - **One run, one machine.** macOS on Apple silicon, Python 3.12, one Claude model. The recall numbers show this setup. They are not a general accuracy claim. The timings are not a speed claim.
> - **The crash is a SIGKILL of the server process.** It does not cover power loss, disk faults or Windows. The kill ran on macOS. Linux was not run.
> - **Reads happen with Pulse stopped.** Grafx read-only opens need a checkpoint-complete store, and a live Pulse owns its handles. The repo does not open a running Pulse's store from outside, and it never writes into a Pulse-owned store.
> - **Backup needs Linux.** Grafx 0.0.8 refused to take a backup on macOS, so that step ran in a Linux container, on a copy of the stopped store.
> - **A killed server can block writes for about five minutes.** After a SIGKILL during commits, the board refused new commits until a writer lease expired. Acknowledged commits were not lost.
> - **Search quality depends on the local embedding model.** It ran `sentence-transformers/all-MiniLM-L6-v2`, not the stub.
> - **Source-available, not open source.** Both products use the Elastic License 2.0 (Grafx adds a SaaS/Branding Addendum). This repo links to their licenses and copies none of their source.
> - **Invented data.** The scenario, the Maintainer's reason for the reversal, and the three shared conventions are invented. The only real code is the fork of `fastapi-realworld-example-app`.
> - **Graph runtime wording.** An older plan note said the Pulse README describes the graph runtime as LadybugDB. The README fetched on 2026-10-29 says Pulse uses Grafx only. This repo describes the installed 0.4.2 package and shows the commands that confirm it.

## Things that behaved differently from the docs or from expectation

| Area | What happened | Evidence |
|---|---|---|
| Recall | ✅ Similarity and natural-language search put the right decision first every time. ⚠️ The decision-history tool returned no decisions for any sentence-length topic. Its semantic path returned nothing for the topics tried. Its non-semantic path returned the password decision for short keyword topics such as `bcrypt`. | [`history-probe.json`](../demo-state/step4/history-probe.json) |
| Key Decisions | ⚠️ The "Key Decisions" list in the web UI is a Discovery intent served over REST. It is not an MCP tool in 0.4.2, so the Recaller could not call it. | [`history-probe.json`](../demo-state/step4/history-probe.json) |
| Contradictions | ⚠️ A `SUPERSEDE` override did not make Pulse flag a contradiction. `propose_reconciliation` still returned `ADD` with "no semantic match", although `get_similar_nodes` had just returned the old decision. The pair appeared only after an explicit `contradicts` edge in a second session. | [`step5/after.json`](../demo-state/step5/after.json) |
| Supersedence | ⚠️ The chain has length one from the new decision. From the old decision it returns length zero and still names the old decision as `current_active`. The `SUPERSEDE` commit reports `nodes_added: 0` although the new node exists. | [`step5/after.json`](../demo-state/step5/after.json) |
| Decision anchor | ⚠️ A cognitive `Decision` with a `spec:` source ref was refused with `kg_node_connectivity_violation`. The documented technical root is a ref that starts with `final_report:`. | [`walkthrough`](walkthrough.md#step-3-recorder) |
| Kill A | ✅ The uncommitted consolidation lives in server memory, so the kill discards it by design. Committing its old session id returns `session_not_found`. | [`killA.json`](../demo-state/step7/killA.json) |
| Kill B | ✅ No acknowledged commit was lost. ⚠️ A server killed during commits left the board refusing writes with `lock_contention` ("another writer currently owns the board graph") until the writer lock's 300 second default TTL ran out. In the first Kill B attempt one in-flight commit survived without being acknowledged, and the restart log printed a `GuardedWriteError` traceback for a queued consolidation. | [`killB.json`](../demo-state/step7/killB.json), [extra sample](../demo-state/step7/extra-sample-killB-first-run.json), [log](../demo-state/notes/first-run-killB-restart-log.txt) |
| Leftover processes | ⚠️ After every SIGKILL, two `multiprocessing` helper processes of the killed server stayed alive with parent PID 1. They did not hold the board's files. They have to be stopped by hand. | [`ps` snapshot](../demo-state/notes/orphans-after-sigkill.txt) |
| Health after restart | ⚠️ Pulse reported `at_risk` with `health_probe_unavailable` right after the Kill A restart, and the board accepted a commit seconds later. A new board reports `at_risk` or `recovery_needed` for a while after creation (37 s in step 2, 68 s in step 6), and a commit sent before that returned `kg_health_state: recovery_needed_graph_readable`. | [step 2](../demo-state/step2/board.json), [step 6](../demo-state/step6/board2.json), [first attempt](../demo-state/notes/first-attempt-recorder.json) |
| Direct read | ✅ Read-only opens worked on both stopped stores, including the store of the killed server, and left every data file unchanged. ⚠️ `oktografx status --read-only` exits 6, "inconclusive", because no recovery ran on a read-only open. A read-only open still needs to open `bootstrap/first-open.complete` for writing, so it fails on a read-only mount (errno 30). | [`direct-read.json`](../demo-state/step8/direct-read.json) |
| Commit history | ✅ Enabled on both board stores. Pulse's adapter turns it on. The demo only reads that state and makes no history claims beyond it. | [`reader-*.json`](../demo-state/step8/) |
| Backup | ⚠️ Grafx 0.0.8 supports atomic directory publication on Windows and Linux only. On macOS it refused with `unsupported_operation`. The same procedure succeeded in a Linux container. | [`step9/`](../demo-state/step9/) |
| Prompts | The first attempt of steps 3 to 5 used prompts that left out `candidate_id` on edge candidates, which Pulse requires. Both prompts were fixed and steps 1 to 5 were re-run from a fresh data home. The saved prompts are the ones that produced the recorded outputs. | [`docs/prompts/`](prompts/) |

The full list, including differences from the plan, is in [`docs/VERIFIED.md`](VERIFIED.md).
