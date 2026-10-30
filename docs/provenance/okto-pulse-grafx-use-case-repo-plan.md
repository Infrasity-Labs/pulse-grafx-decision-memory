# Okto Pulse + Okto Grafx Use Case Repo: Decision Memory Plan

Repo name: `pulse-grafx-decision-memory-demo`. Tagline: "Decisions go in once. They survive a crash, and you can read them straight from the file."

## 1. What the Pulse and Grafx pairing is

Okto Pulse is a local-first workbench where AI coding agents plan and track work through stories, specs, sprints and tasks, with a knowledge graph per board that keeps the decisions behind the work. Okto Grafx is the embedded graph database that stores that knowledge graph.

- Pulse 0.4.2 on PyPI requires exactly `okto-grafx[accel]==0.0.8`, so `pip install okto-pulse` brings Grafx with it. Both are Python 3.11 or newer.
- In the installed Pulse Community package, Grafx is the only supported graph backend. The board settings default `kg_graph_backend` and `kg_global_graph_backend` to `grafx`.
- Each board's graph is a Grafx store in a folder under the Pulse data home, at `boards/{board_id}/grafx/`. Global Discovery, the graph that spans boards, is a second Grafx store.
- Pulse owns the lifecycle of those stores. It opens them, recovers them and replaces generations, so the repo only reads them from outside and never writes.
- Both are source-available under Elastic License 2.0. Grafx adds a SaaS/Branding Addendum.

## 2. What the demo shows and where

| Feature | What it does | Where the repo shows it |
|---|---|---|
| Decisions in the board graph | Agents record decisions as nodes with links, committed in one consolidation | Steps 3 and 5 |
| Recall in a fresh session | Similarity search, natural-language search and the key-decisions list return the stored decisions | Step 4 |
| Contradictions and supersedence | A reversed decision is flagged, and the chain shows which decision replaced which | Step 5 |
| Search across boards | Global Discovery finds a decision that sits on another board | Step 6 |
| Crash safety on a Grafx store | After a SIGKILL of the Pulse server, committed decisions are present and an unfinished consolidation is not | Step 7 |
| Reading the store from outside | The `oktografx` CLI and a read-only Python reader open the board's store, and the counts match what Pulse reports | Step 8 |
| Backup and restore of the store | A copy of the stopped store is backed up with Grafx, restored to a new folder and verified | Step 9 |

## 3. Why we picked these features

- **They show the seam between the two products.** Pulse produces and uses the decisions, and Grafx holds and protects them. Every step ends with a check on the Grafx side or the Pulse side, and steps 7 to 9 check both.
- **They answer what a team asks before trusting agent memory.** Will it still be there tomorrow? Can a new session find it? What if the process dies? Can I see it without the app?
- **Pulse and Grafx both document them.** Pulse ships the knowledge-graph tools and its Grafx recovery behaviour, and Grafx documents crash recovery, read-only opens, backup and restore. The repo tests those documents against a real run.

Left out on purpose:
- Pulse's governance gates, the Builder and Validator review loop and sprint close-out. The existing Pulse demo covers them.
- Speed claims. The Grafx README timing table is one Windows sample made with Pulse 0.3.3, so this repo reports only its own timings and labels them as one machine.
- Writing into a Pulse-owned store from outside. Pulse manages those folders, so the outside tools only read, or work on a copy.
- Time travel on the board store. Pulse's Grafx adapter has code that turns on commit history, so Step 8 checks whether the board store has it on and the repo claims history features only if it does.

## 4. The scenario in one paragraph

A team plans changes to an existing blogging API and wants every design decision kept where any later agent session can find it. Three Claude Code sessions work on one Pulse board, and none remembers the others, so everything they know comes from the board graph. One session records twelve decisions read from the codebase, a fresh session recalls them, and the Maintainer reverses one so the graph flags the conflict and shows the chain. The Pulse server is then killed with SIGKILL, restarted, and checked. Last, Pulse is stopped and the same store is read directly with Grafx tools, and the counts must match.

The codebase is a fresh fork of [`nsidnev/fastapi-realworld-example-app`](https://github.com/nsidnev/fastapi-realworld-example-app), the upstream the [Pulse demo](https://github.com/OktoLabsAI/pulse-brownfield-feature-demo) uses. The agents read its code to find decisions. The app is not run, so Postgres is not needed.

## 5. The cast

| Who | Does | Pulse identity |
|---|---|---|
| Recorder (session) | Reads the code and records the twelve decisions in one consolidation | Its own agent key |
| Recaller (session) | Starts with no history and answers questions from the board graph | Its own agent key, read focus |
| Reviewer (session) | Checks the reversed decision, reads contradictions and the supersedence chain | Its own agent key |
| Maintainer (you) | Reverses a decision, kills the server, stops it for the direct read | A terminal |

Each session is a separate agent connection with its own key, as in the Pulse demo. Keys stay in a local file that git ignores and are never printed.

## 6. Requirements before Claude Code starts

1. A Mac or Linux machine. Step 7 uses SIGKILL, so Windows is not covered.
2. Python 3.11, 3.12 or 3.13. Grafx does not list 3.14.
3. Claude Code installed with the native installer and logged in. No other model key is needed, because Pulse and Grafx use no LLM of their own.
4. Network access to PyPI, GitHub and Hugging Face. On first run Pulse downloads the `all-MiniLM-L6-v2` embedding model, and it falls back to a stub mode if the download fails. A stub makes search results meaningless, so Claude Code stops if it sees stub mode.
5. Free disk space for the Pulse install, which pulls `sentence-transformers` and its dependencies. Claude Code reports the real size at the end of Phase A.
6. Ports 8100 and 8101 free.
7. A decision from you on the GitHub owner and repo name, and the license for the demo code. Nothing is pushed until you say so.
8. A named person at Okto Labs to confirm the wording about Pulse's Grafx backend before the repo goes public.

## 7. The ten steps

| Step | What happens | Shows |
|---|---|---|
| 1 | Create a virtual environment, install `okto-pulse` at a pinned version, confirm Grafx 0.0.8 came with it, run `okto-pulse init`, start the server and check `status` | Setup, the pairing |
| 2 | Create the board, three agent identities and their MCP configs, then confirm the board's `grafx/` folder exists | Identities, store location |
| 3 | The Recorder reads the code and records twelve decisions in one consolidation, then checks board health and schema | Decisions in the graph |
| 4 | The Recaller, with no history, answers ten questions through similarity, natural-language and key-decisions tools | Recall |
| 5 | The Maintainer reverses one decision. The Reviewer records the new one, reads the contradiction flag, the supersedence chain and the decision history | Contradictions, supersedence |
| 6 | A second board holds three shared conventions, and a Global Discovery query finds one of them from the first board | Cross-board search |
| 7 | Kill A: begin a consolidation, add candidates, SIGKILL the server, restart. Kill B: run a burst of commits and SIGKILL at a random moment. Check what survived | Crash safety |
| 8 | Stop Pulse cleanly. Run `oktografx schema`, `indexes` and `capabilities` on the board store, then count nodes by type with a read-only Python reader and compare with Pulse's own counts | Reading from outside |
| 9 | Copy the stopped store, back up the copy with Grafx, restore to a new folder, run `verify` and compare counts | Backup and restore |
| 10 | The close-out script builds the scoreboard from the recorded outputs | Scoreboard |

`run_demo.py` replays any set of steps (`--steps 5 7 8`, `--start`, `--dry-run`). A dry run prints every command and prompt and needs no Pulse install.

## 8. The twelve decisions and the reversal

- **Twelve decisions** are read from the fork's code, so each can be checked against a file: auth header scheme, token expiry, password hashing, error response shape, pagination parameters, slug rules, comment ownership, favorites, tag handling, database access layer, settings loading and test layout.
- **One reversal in step 5**: the error response shape changes. The repo records whether Pulse flags it as a contradiction and which decision sits at the end of the supersedence chain.
- **Three shared conventions** on the second board in step 6, clearly labelled as invented.

Each decision carries the file path it came from, and a script checks that the file still contains the cited line.

## 9. The scoreboard

`demo-state/closeout-result.json` is built from the recorded outputs:

- Pulse and Grafx versions, and whether the installed Pulse requires that Grafx version
- decisions committed, and ten recall questions answered with the right decision on top
- contradictions flagged for the reversal, and the supersedence chain length
- Kill A: whether the uncommitted consolidation is absent after restart (target: absent)
- Kill B: commits acknowledged before the kill, how many of those are present afterwards (target: all), and how many unacknowledged ones survived
- Pulse's health report after each restart, quoted as printed
- node counts by type from Pulse and from the direct read, and whether they match
- `verify` result on the stopped store and on the restored copy
- time taken by each step on the machine used

The README prints these numbers from the real run and nothing else.

## 10. Repo layout and automated checks

Layout: `app/` (the fork, read only), `agents/` (a `CLAUDE.md` per role and the MCP config examples), `scripts/` (start, kill, inspect and count helpers), `demo-state/` (recorded outputs, scoreboard, screenshots), `docs/` (walkthrough, one prompt per step, `VERIFIED.md`, hero and architecture SVGs), `tests/`, `.github/workflows/validate.yml`, `run_demo.py`, `requirements.txt` with the pinned versions, and an env example. The README follows the [Pulse](https://github.com/OktoLabsAI/pulse-brownfield-feature-demo) and [Nexus](https://github.com/OktoLabsAI/nexus-brownfield-handoff-demo) order: banner, About, The Problem, How It Works, Pulse and Grafx in Action, Architecture, Repository Structure, Prerequisites, Quickstart, the ten steps, Where to Find Artifacts, Conclusion.

Checks on every push: unit tests for the scoreboard builder and the citation checker on recorded outputs, a test that the pinned Pulse requires the pinned Grafx, link and JSON checks, a compile check, a secret scan, and a dry run of all ten steps. `docs/VERIFIED.md` states the versions and date the commands were verified.

## 11. Limits the README states up front

- Grafx is pre-alpha and Pulse is a 0.x line. The repo pins both and says it was verified on those versions only.
- The Pulse repository README still describes the graph runtime as LadybugDB. This repo describes the installed 0.4.2 package and shows the commands that confirm it.
- The kill in step 7 is a SIGKILL of the server process on Linux or macOS. It does not cover power loss, disk faults or Windows.
- Step 8 reads the store with Pulse stopped. Grafx read-only opens need a checkpoint-complete store, and a live Pulse owns its handles, so the repo does not open a running Pulse's store from outside.
- Step 9 works on a copy, because restoring a backup needs the original participants stopped and restored stores carry the same identity as the original.
- Search quality depends on the local embedding model, and the repo names the model it ran with.
- The twelve decisions come from reading one codebase, so the recall numbers show this setup and are not a general accuracy claim.
- Both products are source-available, not open source, and the demo repo links to their licenses without copying their source.

Sources: [Okto Pulse](https://github.com/OktoLabsAI/okto-pulse), [Okto Pulse on PyPI](https://pypi.org/project/okto-pulse/), [Okto Grafx](https://github.com/OktoLabsAI/okto-grafx), [Okto Grafx on PyPI](https://pypi.org/project/okto-grafx/), [Pulse demo](https://github.com/OktoLabsAI/pulse-brownfield-feature-demo), [Nexus demo](https://github.com/OktoLabsAI/nexus-brownfield-handoff-demo), [RealWorld FastAPI app](https://github.com/nsidnev/fastapi-realworld-example-app).
