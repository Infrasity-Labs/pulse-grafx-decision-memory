# Verified

Date: 2026-10-29. Machine: macOS (Darwin 25.3.0) on arm64. One machine, one full run, plus the extra samples named below.

Everything here was run. Anything not run is under [Not verified](#not-verified). Run results are in [`demo-state/closeout-result.json`](../demo-state/closeout-result.json) and [SCOREBOARD.md](SCOREBOARD.md). This page does not repeat them.

## Versions

| Item | Version | How it was read |
|---|---|---|
| Python | 3.12.13 (venv) | `capture_versions.py` |
| okto-pulse | 0.4.2 | `importlib.metadata` |
| okto-pulse-core | 0.4.2 | `importlib.metadata` |
| okto-grafx | 0.0.8 | `importlib.metadata` and `oktografx capabilities --json` |
| sentence-transformers | 5.7.0 | `importlib.metadata` |
| torch | 2.15.0 | `importlib.metadata` |
| Claude Code | 2.1.312 | `claude --version` |
| Agent model | claude-opus-5-5 | `init` event of each session transcript |
| Docker image for step 9 | `python:3.12-slim`, Linux aarch64, `okto-grafx[accel]==0.0.8` | step 9 output |

Pin proof, from the installed `okto-pulse` metadata: `Requires-Dist: okto-grafx[accel]==0.0.8`. `okto-pulse-core` does not require Grafx. The Grafx docs were read from a read-only clone of `OktoLabsAI/okto-grafx` at tag `v0.0.8`. [`demo-state/step1/versions.json`](../demo-state/step1/versions.json) holds the machine-readable proof.

## Install

`pip install okto-pulse` into a fresh venv: 1.42 GiB by free-space change, 1.3 GB by `du -sh .venv`, 63 seconds on this network. See [`demo-state/step1/install.json`](../demo-state/step1/install.json). These were measured on the first install.

## Embedding mode

`sentence-transformers/all-MiniLM-L6-v2`, dimension 384, `is_stub` false, loaded by Pulse's own provider. [`demo-state/step1/embedding.json`](../demo-state/step1/embedding.json). On the very first server start the log said `kg.embedding.load_deferred` while the model downloaded. No `kg.embedding.load_failed` event appeared in any run.

## Store layout

The board store is `boards/<board_id>/grafx/generation-1/`. It holds `catalog.dat`, `heap.dat`, `grafx.meta`, `control/`, `index/` and `wal/`. After commit history is on it also holds `commits.dat` and `commits.dir`. A `graph_backend_binding.json` next to `grafx/` names the generation. Global Discovery is `global/grafx/generation-1/`. Listings: [`demo-state/phase-a/store-layout.txt`](../demo-state/phase-a/store-layout.txt) (fresh init) and [`demo-state/step2/store-layout.txt`](../demo-state/step2/store-layout.txt) (decision board). No `.lbug` file exists on disk.

## Commands verified

| Step | Command | Result |
|---|---|---|
| 1 | `capture_versions.py`, `init_pulse.sh`, `start_pulse.sh`, `status.sh`, `check_embedding.py` | Pass. Both servers up, real embedding model. |
| 2 | `setup_board.py` | Pass. Four identities, anchor spec, board graph `healthy` after the wait. |
| 3 | `step03_recorder.py` | Pass. Twelve decisions, every citation valid. |
| 4 | `step04_recaller.py`, `probe_history.py` | Pass. Scored from raw tool results. |
| 5 | `maintainer_reverse.py`, `step05_reversal.py` | Pass. |
| 6 | `step06_second_board.py` | Pass. |
| 7 | `step07_crash.py` | Pass. No acknowledged commit lost. |
| 8 | `step08_direct_read.py` | Pass. Read-only open worked on both stores, counts match, data files unchanged. |
| 9 | `step09_backup_restore.py` | Backup refused on macOS. Pass in a Linux container. |
| 10 | `build_closeout.py`, `render_scoreboard.py --write` | Pass. |
| All | `python -m pytest tests -q`, `scan_repo.py`, `check_links.py --external`, `run_demo.py --dry-run`, `render_scoreboard.py --check` | Pass from a fresh `git clone` into a temporary folder, in a clean virtualenv that had only `requirements-dev.txt` and `okto-pulse==0.4.2 --no-deps` installed. |

Steps 1 to 5 were run twice. The first attempt used prompts that left out `candidate_id` on edge candidates, which Pulse requires. The prompts were fixed and the steps were re-run from a fresh data home. The saved prompts are the fixed ones. Two facts from the first attempt are kept in [`demo-state/notes/`](../demo-state/notes/).

Step 7 was also run twice, the first time before the write probe was added to the script. Its Kill B result is kept as [`extra-sample-killB-first-run.json`](../demo-state/step7/extra-sample-killB-first-run.json). The second run is the scoreboard run.

## Differences from the plan, the docs and expectation

Plan and docs:

- The plan says the board store is `boards/{board_id}/grafx/`. The Grafx store is one level lower, in `generation-1`. Pulse's README shows `grafx/{generation}/`.
- The plan says the Pulse README describes the graph runtime as LadybugDB. The README fetched on 2026-10-29 says Grafx only, pinned to `okto-grafx[accel]==0.0.8`. The installed Core code still contains LadybugDB names in its boundary checks, and `okto_pulse/community/cli.py` has one stale comment about `global/discovery.lbug`.
- The Pulse README table lists 285 MCP tools for 0.4.0. The installed 0.4.2 server listed 288 for each of the four identities. The tool list is not filtered by preset. A call is refused instead.
- The installed 0.4.2 CLI has `init`, `serve`, `test-runner`, `status`, `code-traceability`, `metrics` and `api-key`. An older Pulse install on the same machine also had `kg`, `verify-pipeline` and `reset`. There is no `stop` command.
- The data home is set with the `DATA_DIR` environment variable. `okto-pulse init --help` does not mention it. `init` prints the first API key unless `--bootstrap-key-handoff` is used.

Pulse behaviour:

- A cognitive `Decision` with a source ref like `spec:<id>:decision:<slug>` is refused with `kg_node_connectivity_violation`, because the `belongs_to` edge it needs is reserved for the deterministic worker. The documented technical root is a ref that starts with `final_report:`.
- `okto_pulse_kg_add_edge_candidate` needs `candidate_id` in the candidate object.
- `propose_reconciliation` returned `ADD` with "no semantic match in existing graph" for a decision whose old counterpart `get_similar_nodes` had just returned. Pulse did not flag the reversal as a contradiction. A pair appeared only after an explicit `contradicts` edge, which an edge-only session accepted.
- The `SUPERSEDE` commit reported `nodes_added: 0` although the new node exists. `get_supersedence_chain` from the old decision returns depth 0 and names the old decision as `current_active`. From the new decision it returns depth 1.
- `okto_pulse_kg_get_decision_history` returned no decisions in semantic mode for any topic tried. In non-semantic mode it returned the password decision for short keyword topics.
- The "Key Decisions" list in the web UI is a Discovery catalog intent (`okto_pulse_kg_list_key_decisions`) served over REST. It is not an MCP tool in 0.4.2.
- `okto_pulse_kg_health` returned `at_risk` or `recovery_needed` for a new board for 37 s and 68 s in the two runs before turning `healthy`. A commit sent before that returned `kg_health_state: recovery_needed_graph_readable`.
- After a SIGKILL during commits, the board refused new commits with `lock_contention` until the writer lock's 300 second default TTL ran out. The first Kill B restart log printed a `GuardedWriteError` traceback for a queued consolidation.
- After every SIGKILL, a `multiprocessing` resource tracker and a spawn worker of the killed server stayed alive with parent PID 1 ([`ps` snapshot](../demo-state/notes/orphans-after-sigkill.txt)). In `lsof` on the crash board's control folder after Kill B only the new server held the lease and commit files. The orphans were stopped by hand after the run.
- The Pulse web UI opens an onboarding tour and a metrics opt-in panel on first visit. Metrics were left off.

Grafx behaviour:

- Backup is refused on macOS: `This platform has no supported atomic no-replace directory publication. [code=unsupported_operation retryable=False]`. This matches the Grafx docs, which name Windows and Linux.
- `connect(path, read_only=True)` worked on a cleanly stopped store, including the store of a server that had been killed and restarted. A read-only open still opens `bootstrap/first-open.complete` for writing, so it fails on a read-only mount (errno 30). Step 9 therefore verifies a copy inside the container.
- `oktografx status --read-only` exits 6, "inconclusive", with the reason "no recovery ran, because this open was read-only".
- Commit history is enabled on the board stores. Pulse's adapter calls `enable_commit_history()`. The demo only reads that state.

## Not verified

- A SIGKILL on Linux. The crash tests ran on macOS only.
- Power loss, disk faults and Windows.
- Opening a running Pulse's store from outside. The repo does not do that.
- Pulse started against a restored store. The repo never does that, and the restored store carries the original database identity.
- The GitHub Actions run itself. The workflow is not pushed. Its commands were run locally from a fresh clone.
- Any other codebase, embedding model, model for the agent sessions, or later Pulse and Grafx versions.
- Backup and restore on the macOS host. It was refused. The procedure was verified on Linux aarch64 in a container only.
- Speed. Timings are one run on one machine.
- Screenshots were taken after the run, so they show its final state (14 decisions on the decision board).
