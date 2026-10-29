# Walkthrough

How to run each step, what it writes, and what to look at. The numbers for the run in this repo are in [`demo-state/closeout-result.json`](../demo-state/closeout-result.json) and the README scoreboard. This page does not repeat them.

Run any step with `python run_demo.py --steps N`. Preview with `python run_demo.py --dry-run`.

Conventions: the Pulse data home is `.work/pulse-home`. Pulse listens on 8100 (UI and API) and 8101 (MCP). Agent keys are in `agents/.keys.local` (mode 600). Every script reads the key it needs from there and never prints it.

## Step 1: Setup

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
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

Renders [`docs/prompts/step3-recorder.md`](prompts/step3-recorder.md) with the board and spec ids, runs `claude -p` as the Recorder, then reads the graph back as the Maintainer and runs [`check_citations.py`](../scripts/check_citations.py).

- The session runs with `--strict-mcp-config`, `--setting-sources project`, `--no-session-persistence` and the tools `Read`, `Grep`, `Glob` plus the `pulse` MCP server. [`scripts/run_agent.py`](../scripts/run_agent.py) has the exact flags.
- Look at [`step3/decisions-from-graph.json`](../demo-state/step3/decisions-from-graph.json), the agent's own report in `step3/agent/result.json`, and the full tool-call trail in `step3/agent/transcript.jsonl`.
- Pulse refuses a cognitive `Decision` that has no root. Refs like `spec:<id>:decision:<slug>` were refused with `kg_node_connectivity_violation`. The prompt uses the documented technical root `final_report:<spec-id>:decision:<slug>`.
- Edge candidates need their own `candidate_id`.
- [`step3/health.json`](../demo-state/step3/health.json) and [`step3/schema-info.json`](../demo-state/step3/schema-info.json) are the board health and `okto_pulse_kg_schema_info` as Pulse returned them.

## Step 4: Recaller

```bash
.venv/bin/python scripts/step04_recaller.py
.venv/bin/python scripts/probe_history.py
```

The ten questions are in [`scripts/questions.py`](../scripts/questions.py). They were fixed before the first run and were not changed after seeing results. Each names the decision it should reach, by slug.

- Scoring reads raw tool results from the transcript. It does not trust the agent's own report. [`step4/recall-results.json`](../demo-state/step4/recall-results.json) has the top result of each of the three tools per question and whether it is the expected decision.
- The Recaller has no file tools. It ends with a write attempt, which Pulse refuses with `permission_denied` for `kg.session.begin`.
- `probe_history.py` is a supplementary probe, not part of the score. It records what the decision-history tool returns for short topics, and the "Key Decisions" list, which is a REST Discovery intent and not an MCP tool.

## Step 5: Reversal

```bash
.venv/bin/python scripts/maintainer_reverse.py
.venv/bin/python scripts/step05_reversal.py        # add --wait to poll for the note instead
```

`maintainer_reverse.py` writes the Maintainer's note [`step5/maintainer-reversal.json`](../demo-state/step5/maintainer-reversal.json). It changes the decision about the error response shape. It does not edit the fork. The reason in the note is invented. If you want to be the Maintainer yourself, write your own note there and run `step05_reversal.py`.

The Reviewer ([prompt](prompts/step5-reviewer.md)) records the new decision with a `SUPERSEDE` override, checks `okto_pulse_kg_find_contradictions`, then opens a second session to add an explicit `contradicts` edge, and reads back the chain and history. The script snapshots the graph before and after, as the Maintainer, so you can compare with the Reviewer's own report. [`step5/after.json`](../demo-state/step5/after.json) is what Pulse returned.

- Pulse does not flag the reversal as a contradiction by itself.
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

Kill A opens a consolidation and adds three candidates, then runs `scripts/kill9_pulse.sh`, restarts, and checks. Kill B creates a separate board and starts three worker processes ([`kill_b_burst.py`](../scripts/kill_b_burst.py)). Each commits one `Decision` per consolidation and writes a line to its own log, with `fsync`, for every commit Pulse acknowledges. After a random delay the script sends SIGKILL.

- Compare `step7/burst-ack-w*.log` with `step7/killB.json`. Acknowledged commits must all be present. Commits that were started but not acknowledged may or may not be.
- After each restart the script runs [`probe_writable.py`](../scripts/probe_writable.py)'s `probe`, which retries a small commit and records when the board accepts writes again. Pulse's writer lock has a 300 second default TTL.
- The restart logs are in `step7/restart-log-killA.txt` and `restart-log-killB.txt`. Health right after each restart is in the two JSON files, as returned.
- Exit code 3 means an acknowledged commit was missing after restart. Stop and look.

## Step 8: Direct read

```bash
.venv/bin/python scripts/step08_direct_read.py
```

Takes Pulse's own counts, stops Pulse with `scripts/stop_pulse.sh`, then for each board store runs `oktografx capabilities`, `schema`, `indexes` and `status --read-only`, and [`read_store_counts.py`](../scripts/read_store_counts.py), which opens the store with `connect(path, read_only=True)` and counts rows per node and relationship table. It hashes every data file before and after to show the read wrote nothing. If a read-only open is refused, the refusal is recorded as is and nothing is opened writable.

Pulse's counts use `labels(n)[0]` and `type(r)` in Cypher with `include_working=true`. Relationship tables in Grafx are named like `supersedes__Decision__Decision`, and that is what both sides report.

## Step 9: Backup and restore

```bash
.venv/bin/python scripts/step09_backup_restore.py
```

Pulse must be stopped. The script copies the stopped store, verifies the original and the copy with `oktografx verify --scope all --read-only`, takes a backup of the copy with `okto_grafx.backup.create_backup`, restores it with `restore_backup(..., confirm_original_offline=True)`, verifies the restored folder, and compares counts and database identity. It never points Pulse at the restored folder.

On macOS, Grafx 0.0.8 refuses the backup (`unsupported_operation`, no atomic no-replace directory publication). The script then repeats the same procedure in a `python:3.12-slim` container, with the original store mounted read-only. Inside the container it verifies and counts a copy of the original, because a read-only open still needs to open `bootstrap/first-open.complete`, which a read-only mount refuses. Both runs are saved as `step9/backup-restore-<label>.json`.

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
python scripts/check_links.py --external
python run_demo.py --dry-run
```

These run on every push in [`.github/workflows/validate.yml`](../.github/workflows/validate.yml). The workflow installs `okto-pulse` with `--no-deps` only to read its requirements.
