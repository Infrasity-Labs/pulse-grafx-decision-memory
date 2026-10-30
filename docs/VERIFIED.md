# Verified

Date: 2026-10-29. Machine: macOS (Darwin 25.3.0) on arm64. One machine: the first full run, the extra samples named below, and the later live runs in [Live runs after run 1](#live-runs-after-run-1).

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

## The earlier session id, and pins

- **`previous_session_id` in the Recorder run.** The Recorder's `begin_consolidation` returned `previous_session_id kgses_67078ed2f2da49b8` for the anchor spec on a data home that was new. The Recorder opened one consolidation only (line 62 of [`step3/agent/transcript.jsonl`](../demo-state/step3/agent/transcript.jsonl)), and the data home of that run no longer exists, so the recorded files alone cannot say where the session came from. A probe on a fresh data home ([`scripts/probe_previous_session.py`](../scripts/probe_previous_session.py), [`demo-state/notes/previous-session-id-probe.json`](../demo-state/notes/previous-session-id-probe.json)) shows that Pulse commits a `system:historical_consolidation` session of its own for each new spec, and that `begin_consolidation` reports it as `previous_session_id`: called at once, there was none; after 40 s, it was that system session. That the id `kgses_67078ed2f2da49b8` is such a session is an inference from this probe. It was not checked for that id.
- **Compatibility.** Pulse 0.4.2 with Grafx 0.0.8, Python 3.12.13, macOS arm64: agent run 1 (2026-10-29) and the scripted run (2026-10-30). The table, and the rule for adding a row, is in [EVIDENCE-AND-CONTROLS.md](EVIDENCE-AND-CONTROLS.md#pinning-and-ports-review-34).
- **`constraints.txt`.** Pins `okto-pulse-core`, `fastmcp`, `mcp`, `sentence-transformers`, `transformers`, `torch` and `numpy`. Install with `pip install -r requirements.txt -c constraints.txt`. The recorded run captured only `okto-pulse-core`, `sentence-transformers` and `torch`. The other pins were read from a clean install on 2026-10-30.
- **Step 9 image.** Now pinned as `python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159`, the digest read on 2026-10-30. The recorded run used the tag `python:3.12-slim` with no digest, so it cannot be tied to this one.
- **Full integration run, 2026-10-30.** `python scripts/run_integration.py --require-step9` ran all phases against real Pulse 0.4.2 and Grafx 0.0.8 on macOS arm64 with a temporary HOME, a fresh data home and free ports. Step 9 ran in a Linux container (Docker Desktop) and `scripts/assert_runtime.py` passed 48 of 48 checks, including the decision-level comparison of 43 decisions between the original and the restored store. The step 9 phase was started a second time on the same work folder after the first attempt failed with "Docker is not available": that run had a temporary HOME, which hid the Docker context, and `DOCKER_CONFIG` was set to fix it. The outputs of that run were not copied into `demo-state/`. The same command was run again (2026-10-29 21:05 UTC, which is 2026-10-30 in the timezone of the earlier notes) and that run is recorded in `demo-state/integration-20261029T210523Z-4ffa2a8-dirty/`, with the same 48 of 48. The `integration` workflow has still not run on GitHub.

## Live runs after run 1

All on the machine above, 2026-10-29 (UTC), against okto-pulse 0.4.2 and okto-grafx 0.0.8, Python 3.12.13, Claude Code 2.1.312, `claude-opus-5-5` for every model session (requested with `--model`, reported by every `init` event), a temporary HOME and `CLAUDE_CONFIG_DIR`, fresh data homes and free ports. The repo commit was 4ffa2a8 with uncommitted changes. Records and manifests are in `demo-state/`; the numbers are in [SCOREBOARD.md](SCOREBOARD.md).

| Run | What was run | Result | Record |
|---|---|---|---|
| Smoke run | `run_demo.py --steps 3 4 5` with the goal-based prompts | Passed. 17 decisions, 17 citations hold, 9 of 22 reference decisions, Recaller 9 of 10 dev and 11 of 11 held-out by the shared scorer, Reviewer wrote nothing (the reversal target was not on the board) | `llm-runs/<id>/smoke/` |
| Variance studies | `run_n.py --runs 5`, three variants (`main`, `reviewer-scripted-base`, `resource-tool`) | 15 runs, all passed. Recorder, Recaller and Reviewer numbers with mean, min, max in SCOREBOARD | `llm-runs/<id>/n-runs-*/` |
| LLM arms | `build_corpus.py`, then `run_arms.py --runs 3`, then `run_arms.py --runs 2 --append` | 15 sessions, graph, code only, code and notes, five runs each, same board | `arms/llm-*` |
| Model-authored questions | `claude-haiku-5-5`, one call, $0.0036 | 16 questions, none dropped; the lexical baseline scores 11 of 12 on the answerable ones | `corpus/questions-model-authored.json`, `corpus/authoring/` |
| Integration run | `run_integration.py --require-step9`, macOS host, temporary HOME with `DOCKER_CONFIG` set | 48 of 48 assertions, including step 9 in a Linux container (backup, restore, 43 decisions equal) | `integration-<id>/` |
| Linux container crash run | `run_linux_crash.py`, image built from `requirements.txt` and `constraints.txt` (torch 2.15.0+cpu), base `python:3.12-slim@sha256:aa943ce4...`, Debian 13, Linux 7.0.12-linuxkit aarch64, Python 3.12.16 | 43 of 43 assertions (step 9 not part of it). Kill A and Kill B as on macOS | `linux-crash-<id>/` |

Iterations. What failed, and what was changed:

1. The Linux run failed twice before it passed. First `capture_versions.py` crashed because the container has no `claude` binary (fixed: record `None`). Then the scripted Recorder's citation check failed for `tag-handling` with "file does not exist": the path scrubber replaced `/repo` inside `/repositories` (the repo sat at `/repo` in the container), giving `<repo>sitories`. The scrubber in `gxutil.py` now replaces a path only where it ends. The third run passed.
2. The first Reviewer outputs said it could not read `okto-pulse://workflows/kg`. A headless session cannot read an MCP resource without `ListMcpResourcesTool` and `ReadMcpResourceTool`; a probe showed refusal without them and the document with them. `run_agent.py --mcp-resources` adds them, used by steps 3 and 5. The smoke run, the `main` and `reviewer-scripted-base` studies and the arms ran before the fix; the `resource-tool` study ran after it. All five variants are kept.
3. The arms ran three times first, then two more were appended (`--append`) with the same board, to reach five.
4. `run_n.py` first listed the scripted sessions in `agent_runs` and counted new decisions by a reference prefix that the Reviewer does not have to use. `collect()` now lists only sessions that called a model, the Reviewer outcome counts edges, and the `main` and `reviewer-scripted-base` summaries were rebuilt from their saved run folders with `run_n.py --recompute` (recorded in `recomputed_because` in each summary).
5. A command of mine started `run_n.py` for real with the default HOME and the environment's own API key, because `--recompute` did not exist yet. It was killed within a minute and its partial folder was deleted. It is not part of any record.
6. A shell variable leak made `lexical_baseline.py` write its arm file to a temporary state folder instead of `demo-state/arms/`. It was caught because the arm file had no answers for the new question split, and the script was re-run from a clean shell.

## Not verified

- A SIGKILL on a bare-metal Linux host. The Linux run is a container on a Docker Desktop VM.
- Power loss, disk faults and Windows.
- Opening a running Pulse's store from outside. The repo does not do that.
- Pulse started against a restored store. The repo never does that, and the restored store carries the original database identity.
- The GitHub Actions history. This page first said the workflow was not pushed. That is outdated: an outside review dated 2026-10-29 reported ten successful `validate` runs on `main` (the latest, 21 s, 88 tests passed), and this page does not re-verify that, because the run history cannot be re-queried from here without GitHub authentication. What the repo shows is what the workflow does: `validate` only reads the recorded files in `demo-state/`. It starts neither Pulse nor Grafx, so those runs say nothing about their behavior. The `integration` workflow (`.github/workflows/integration.yml`) starts them. It was added after the runs above and has no recorded GitHub run yet.
- Any other codebase, embedding model, model for the agent sessions, or later Pulse and Grafx versions. Every model session used `claude-opus-5-5`.
- The 22-entry reference list, the dev and held-out questions and the model-authored questions by a person. None has been reviewed by one.
- A larger memory than 32 decisions, a real team, or any measure of time saved.
- Backup and restore on the macOS host. It was refused. The procedure was verified on Linux aarch64 in a container only.
- Speed. Timings are one run on one machine.
- Screenshots were taken after the run, so they show its final state (14 decisions on the decision board).
