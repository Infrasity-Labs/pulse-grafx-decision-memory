# Walkthrough

How to run each step, what it writes, and what to look at. The numbers for the run in this repo are in [`demo-state/closeout-result.json`](../demo-state/closeout-result.json) and the README scoreboard. This page does not repeat them.

Run any step with `python run_demo.py --steps N`. Preview with `python run_demo.py --dry-run`.

Two kinds of run exist, and the repo keeps them apart:

- **Agent run** (`claude -p`, costs money): steps 3, 4 and 5 with the prompts in [`docs/prompts/`](prompts/). The recorded outputs in `demo-state/` come from an agent run, made with the earlier answer-key prompts in [`docs/prompts/recorded-run-1/`](prompts/recorded-run-1/). Runs with the goal-based prompts in `docs/prompts/` are recorded in `demo-state/llm-runs/` (one smoke run and three studies of five runs: [SCOREBOARD](SCOREBOARD.md#live-runs-with-a-model)). To repeat them: `python run_demo.py --steps 3 4 5` for one run, `python scripts/run_n.py --runs 5 --agents recorder recaller reviewer` for five on fresh data homes, `python scripts/build_corpus.py` then `python scripts/run_arms.py --runs 5 --splits dev held_out model_authored` for the arms. Set `PULSE_*` ports and `HOME` as the CI scripts do if another Pulse is running.
- **Scripted run** (no model, no key, no network beyond the local server): the same Pulse calls made by a fixed script. `python scripts/run_integration.py` runs steps 1 to 9 this way on a fresh data home and asserts the outcomes. Its recorded output is in `demo-state/scripted-run/`. It shows what Pulse and Grafx do, not what an agent would choose to do. See [EVIDENCE-AND-CONTROLS.md](EVIDENCE-AND-CONTROLS.md).

Conventions: the Pulse data home is `.work/pulse-home`. Pulse listens on 8100 (UI and API) and 8101 (MCP). Agent keys are in `agents/.keys.local` (mode 600). Every script reads the key it needs from there and never prints it.

## Step 1: Setup

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt -c constraints.txt
.venv/bin/python scripts/capture_versions.py
scripts/init_pulse.sh MAINTAINER agents/.keys.local
scripts/start_pulse.sh
scripts/status.sh
.venv/bin/python scripts/check_embedding.py
```

- `capture_versions.py` reads package metadata and writes [`step1/versions.json`](../demo-state/step1/versions.json). Look at `requires_dist_grafx_line`. It must read `Requires-Dist: okto-grafx[accel]==0.0.8`.
- `init_pulse.sh` runs `okto-pulse init` with `--bootstrap-key-handoff`, so the first key goes to a private file and not to the terminal.
- The data home comes from the `DATA_DIR` environment variable. `okto-pulse init --help` does not mention it.
- There is no `okto-pulse stop`. `scripts/stop_pulse.sh` sends SIGTERM and waits.
- `check_embedding.py` builds Pulse's own embedding provider and embeds three sentences. It exits 1 if the provider is the stub. On the first start the server log may say `kg.embedding.load_deferred` while the model downloads.

## Step 2: Board, identities, anchor spec

```bash
.venv/bin/python scripts/setup_board.py
```

Creates the board, four agents from the presets `Full Control`, `Spec`, `Reporter` and `Validator`, grants each access to the board, creates an anchor spec, and polls `okto_pulse_kg_health` until the board's graph is `healthy`. Output: [`step2/board.json`](../demo-state/step2/board.json) and [`step2/store-layout.txt`](../demo-state/step2/store-layout.txt).

- Presets are documented by Pulse. `GET /api/v1/presets` lists them. The `kg.session.*` flags (begin, add node, add edge, propose, commit) are on in `Spec` and `Validator`, off in `Reporter`.
- Only `Full Control` has `kg.operations.health.read`, so the Maintainer identity is `Full Control`. It is used by scripts, not by a session.
- Look at `grafx_folder_entries`. The store is `boards/<board-id>/grafx/generation-1`.
- The MCP config examples in `agents/mcp.*.example.json` hold `${PULSE_KEY_*}` placeholders. They are the files the runner uses.

## Step 3: Recorder

```bash
.venv/bin/python scripts/step03_recorder.py
```

Renders [`docs/prompts/step3-recorder.md`](prompts/step3-recorder.md) with the board and spec ids, runs `claude -p` as the Recorder, then reads the graph back as the Maintainer and runs [`check_citations.py`](../scripts/check_citations.py) in open mode: the goal-based Recorder chooses its own topics, every citation must hold, and recall is reported against the hand-made list in [`corpus/reference_decisions.json`](../corpus/reference_decisions.json). `python scripts/step03_recorder.py --scripted` replays the 12 recorded decisions with a scripted client instead.

- The session runs with `--strict-mcp-config`, `--setting-sources project`, `--no-session-persistence` and the tools `Read`, `Grep`, `Glob` plus the `pulse` MCP server, and (`--mcp-resources`) the two tools that read MCP resources, without which the session cannot open `okto-pulse://workflows/kg`. [`scripts/run_agent.py`](../scripts/run_agent.py) has the exact flags.
- Look at [`step3/decisions-from-graph.json`](../demo-state/step3/decisions-from-graph.json), the agent's own report in `step3/agent/result.json`, and the full tool-call trail in `step3/agent/transcript.jsonl`.
- The recorded run's prompt listed the twelve topics. The goal-based prompt does not. Measured against the reference list, the recorded twelve cover 12 of 22 reference decisions (`python scripts/check_citations.py demo-state/step3/decisions-from-graph.json --open`).
- Pulse refuses a cognitive `Decision` that has no root. Refs like `spec:<id>:decision:<slug>` were refused with `kg_node_connectivity_violation`. The prompt uses the documented technical root `final_report:<spec-id>:decision:<slug>`.
- Edge candidates need their own `candidate_id`.
- [`step3/health.json`](../demo-state/step3/health.json) and [`step3/schema-info.json`](../demo-state/step3/schema-info.json) are the board health and `okto_pulse_kg_schema_info` as Pulse returned them.

### Step 3b: the other 20 decisions, and the Pulse spec flow

```bash
.venv/bin/python scripts/scripted_steps.py code-extras
.venv/bin/python scripts/spec_flow.py
```

A recall test on 12 decisions cannot tell a retrieval tool from a lookup, so the board grows to 32. `scripted_steps.py code-extras` records 10 more code-derived decisions with a file, a line and the exact line text. `spec_flow.py` records 10 decisions whose reason is written nowhere except in the graph (the reasons are invented and say so). It records them the way a team would: as spec decisions with `okto_pulse_add_decision`, a verification plan, and the Pulse spec gate, then a closeout consolidation that makes them canonical. Output: `step3b/spec-flow.json`. The role denials of all three restricted identities are probed by `scripts/probe_roles.py` (`roles/role-denials.json`). Details: [EVIDENCE-AND-CONTROLS.md](EVIDENCE-AND-CONTROLS.md).

## Step 4: Recaller

```bash
.venv/bin/python scripts/step04_recaller.py
.venv/bin/python scripts/probe_history.py
```

The ten legacy questions are in [`scripts/questions.py`](../scripts/questions.py). They were fixed before the first run and were not changed after seeing results. Each names the decision it should reach, by slug. The goal-based Recaller prompt gets the questions of [`corpus/questions.json`](../corpus/questions.json) (split `dev` and `held_out`, some unanswerable), chooses its own tools and abstains when the graph has no answer. `--scripted` asks the ten legacy questions with the same three tools each, as a regression check on Pulse.

- Scoring reads raw tool results from the transcript. It does not trust the agent's own report. [`step4/recall-results.json`](../demo-state/step4/recall-results.json) has the top result of each of the three tools per question and whether it is the expected decision.
- The Recaller has no file tools. It ends with a write attempt, which Pulse refuses with `permission_denied` for `kg.session.begin`.
- `probe_history.py` is a supplementary probe, not part of the score. It records what the decision-history tool returns for short topics, and the "Key Decisions" list, which is a REST Discovery intent and not an MCP tool.

## Step 5: Reversal

```bash
.venv/bin/python scripts/maintainer_reverse.py
.venv/bin/python scripts/step05_reversal.py        # add --wait to poll for the note instead
```

`maintainer_reverse.py` writes the Maintainer's note [`step5/maintainer-reversal.json`](../demo-state/step5/maintainer-reversal.json). It changes the decision about the error response shape. It does not edit the fork. The reason in the note is invented. If you want to be the Maintainer yourself, write your own note there and run `step05_reversal.py`.

In the recorded run the Reviewer ([prompt](prompts/recorded-run-1/step5-reviewer.md)) was handed the old slug, the query, the override JSON and the edge ids. It records the new decision with a `SUPERSEDE` override, checks `okto_pulse_kg_find_contradictions`, then opens a second session to add an explicit `contradicts` edge, and reads back the chain and history. The script snapshots the graph before and after, as the Maintainer, so you can compare with the Reviewer's own report. [`step5/after.json`](../demo-state/step5/after.json) is what Pulse returned.

- Pulse does not flag the reversal as a contradiction by itself. The `contradicts` edge was added by the Reviewer because its prompt said to. It is an agent-added step, not a Pulse feature.
- `python scripts/maintainer_reverse.py --no-rationale` writes a second note with no reason. The goal-based Reviewer prompt tells the agent to record nothing in that case. `step05_reversal.py --note maintainer-reversal-no-rationale.json` checks that the graph is unchanged.
- The goal-based Reviewer prompt ([`docs/prompts/step5-reviewer.md`](prompts/step5-reviewer.md)) gives only the note and the goal.
- Ask the chain from the new decision. From the old decision it is empty.

## Step 6: Second board and Global Discovery

```bash
.venv/bin/python scripts/step06_second_board.py
```

Creates a board with three invented conventions, commits them, then runs `okto_pulse_kg_query_global` for two fixed questions. Cross-board delivery is asynchronous, so each query is polled until the second board answers. The attempts and seconds are in [`step6/global-discovery.json`](../demo-state/step6/global-discovery.json). Two more checks are saved: the same query restricted to the first board, and the same query from the read-only identity, which has access to the first board only.

## Step 7: Crash tests

```bash
.venv/bin/python scripts/step07_crash.py
```

Kill A creates its own crash board, commits three baseline decisions, opens a consolidation and adds three drafts, then runs `scripts/kill9_pulse.sh`, restarts, and checks. It then resumes: a new Recorder session replays all six decisions, and the script counts the nodes per slug. Kill B creates a second crash board and starts three worker processes ([`kill_b_burst.py`](../scripts/kill_b_burst.py)). Each commits one `Decision` per consolidation and writes a line to its own log, with `fsync`, for every commit Pulse acknowledges. After a random delay the script sends SIGKILL.

- Compare `step7/burst-ack-w*.log` with `step7/killB.json`. Acknowledged commits must all be present. Commits that were started but not acknowledged may or may not be.
- After each restart the script runs [`probe_writable.py`](../scripts/probe_writable.py)'s `probe`, which retries a small commit and records when the board accepts writes again. Pulse's writer lock has a 300 second default TTL.
- The restart logs are in `step7/restart-log-killA.txt` and `restart-log-killB.txt`. Health right after each restart is in the two JSON files, as returned.
- After Kill B the script commits the in-flight slugs again with a new session and counts the nodes per slug. Resume and retry are application logic. Pulse only decides what its reconciliation does with a repeated decision, and the result is recorded as found.
- The decision board is never written in step 7. `decision-board-check.json` records that it has the same decisions before and after.
- Exit code 3 means an acknowledged commit was missing after restart. Exit code 4 means a resume or retry left a duplicate, or the decision board changed. Stop and look.

## Step 8: Direct read

```bash
.venv/bin/python scripts/step08_direct_read.py
```

Takes Pulse's own counts, stops Pulse with `scripts/stop_pulse.sh`, then for each board store (decision board and both crash boards) runs `oktografx capabilities`, `schema`, `indexes` and `status --read-only`, and [`read_store_counts.py`](../scripts/read_store_counts.py), which opens the store with `connect(path, read_only=True)` and counts rows per node and relationship table. It hashes every data file before and after to show the read wrote nothing. If a read-only open is refused, the refusal is recorded as is and nothing is opened writable.

Pulse's counts use `labels(n)[0]` and `type(r)` in Cypher with `include_working=true`. Relationship tables in Grafx are named like `supersedes__Decision__Decision`, and that is what both sides report.

## Step 9: Backup and restore

```bash
.venv/bin/python scripts/step09_backup_restore.py
```

Pulse must be stopped. The script copies the stopped store, verifies the original and the copy with `oktografx verify --scope all --read-only`, takes a backup of the copy with `okto_grafx.backup.create_backup`, restores it with `restore_backup(..., confirm_original_offline=True)`, verifies the restored folder, and compares counts and database identity, and reads every Decision node (title, text, source reference, quote) from the original, the copy and the restored folder and compares them. It never points Pulse at the restored folder.

On macOS, Grafx 0.0.8 refuses the backup (`unsupported_operation`, no atomic no-replace directory publication). The script then repeats the same procedure in a `python:3.12-slim` container, pinned by digest in `scripts/step09_backup_restore.py`, with the original store mounted read-only. Inside the container it verifies and counts a copy of the original, because a read-only open still needs to open `bootstrap/first-open.complete`, which a read-only mount refuses. Both runs are saved as `step9/backup-restore-<label>.json`.

## Step 10: Close-out

```bash
.venv/bin/python scripts/build_closeout.py
python scripts/render_scoreboard.py --write
```

`build_closeout.py` reads the recorded outputs of steps 1 to 9. A missing output is an error. `render_scoreboard.py --write` copies the generated blocks into `README.md` and `docs/SCOREBOARD.md` between their markers.

## Checks

```bash
python -m pytest tests -q            # recorded outputs, citation checker, scoreboard builder, README
python scripts/scan_repo.py          # keys, em dashes, machine paths
python scripts/check_links.py        # add --external to check http links (weekly in CI)
python run_demo.py --dry-run
```

These run on every push in [`.github/workflows/validate.yml`](../.github/workflows/validate.yml), with `REQUIRE_EVIDENCE=1` so a missing recorded output fails. The workflow installs `okto-pulse` with `--no-deps` only to read its requirements. It reads recorded files and starts no Pulse.

To run the real products without a model (steps 1 to 9 with the scripted agents, on a fresh data home and free ports), as the [`integration`](../.github/workflows/integration.yml) workflow does:

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt -c constraints.txt
.venv/bin/python scripts/run_integration.py --work .work/integration
```

Logs stay in `.work/integration/logs`. Steps 3 to 5 with a model are the manual [`llm-steps`](../.github/workflows/llm-steps.yml) workflow, which needs the `ANTHROPIC_API_KEY` secret. The same scripts in a Linux container (Kill A and Kill B on Linux): `python scripts/run_linux_crash.py --out DIR` (Docker; with a temporary HOME set `DOCKER_CONFIG`).
