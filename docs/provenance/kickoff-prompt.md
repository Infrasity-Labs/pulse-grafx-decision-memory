# Claude Code kickoff prompt: Okto Pulse + Okto Grafx use case repo

How to use it: put `okto-pulse-grafx-use-case-repo-plan.md` in an empty folder, open Claude Code there, and paste everything below the line.

---

You are building the repo `pulse-grafx-decision-memory-demo` from the plan in `okto-pulse-grafx-use-case-repo-plan.md` in this folder. Read the whole plan first, then work in the phases below.

## Rules for the whole job

1. Every number, output and screenshot in the repo comes from a real run on this machine. Never invent or estimate a result. If something cannot run, say so in the README and in `docs/VERIFIED.md`.
2. Secrets. Pulse agent keys are shown once. Write them only to a local file named `agents/.keys.local` with permissions 600, listed in `.gitignore`. Never print a key in the terminal, a log, a commit, a screenshot or the README. Before every commit, scan the staged files for key-like strings.
3. Pin the exact Pulse and Grafx versions you install in `requirements.txt` and `docs/VERIFIED.md`, with today's date. Pulse 0.4.2 requires Grafx 0.0.8. Confirm that from the installed package metadata, not from memory.
4. Read before you use. For each Pulse and Grafx command or tool, read its real help, MCP tool description or doc first. Pulse: `okto-pulse --help`, `okto-pulse init --help`, `okto-pulse serve --help`, and the MCP resources the server exposes, especially the knowledge-graph workflow. Grafx: clone `https://github.com/OktoLabsAI/okto-grafx` read-only outside this repo and read `README.md`, `docs/GETTING_STARTED.md`, `docs/OPERATIONS.md`, `docs/CLI.md` and `docs/BACKUP_RESTORE.md`. If the installed behaviour differs from the docs, trust the installed behaviour and record the difference.
5. Never write into a Pulse-owned Grafx store from outside Pulse. Outside tools only read it with Pulse stopped, or work on a copy.
6. Use only invented data, plus the code of the fork. No real people, emails or customer data.
7. No em dashes anywhere in the repo. Short sentences, plain words, no marketing language.
8. Commit after each step with a clear message. Do not push to any remote until I say so.
9. Keep a running task list and tick an item only after its check passes.

## Phase A: set up and prove the pairing (stop and report when done)

1. Check Python is 3.11, 3.12 or 3.13, ports 8100 and 8101 are free, and the machine is Mac or Linux. If any check fails, tell me and stop.
2. Create a virtual environment inside the repo folder and run `pip install okto-pulse`. Record the installed versions of `okto-pulse`, `okto-pulse-core` and `okto-grafx`, and print the `Requires-Dist` line that pins Grafx. Report the disk space the install used.
3. Run `okto-pulse init` in a throwaway data home (set the data directory with the setting Pulse documents, so your real `~/.okto-pulse` is not touched), start `okto-pulse serve`, run `okto-pulse status`, and confirm the web UI answers on port 8100.
4. Confirm the embedding mode is the real model (`sentence-transformers/all-MiniLM-L6-v2`) and not the stub. If it fell back to the stub, stop and tell me.
5. Find where the first board's Grafx store sits on disk. Record the real folder layout, including any generation folder. Run `oktografx capabilities --json` and, with Pulse stopped, `oktografx schema <store> --json --limit 100` as a first read-only check. Restart Pulse afterwards.
6. Fork `nsidnev/fastapi-realworld-example-app` into `app/` as a plain copy with its license file and a `FORK_NOTES.md`. Do not run it.
7. Create the repo skeleton from section 10 of the plan.
8. Report: versions, disk used, store layout, embedding mode, anything surprising. Then wait for me to reply "go".

## Phase B: build and run the ten steps (after I say "go")

Run the three agent sessions as separate headless Claude Code processes (`claude -p`) with their own `--mcp-config` file pointing at the local Pulse MCP server, and `--strict-mcp-config` so no other servers load. Each has its own Pulse agent key. Save every prompt you give them under `docs/prompts/`, and every answer under `demo-state/`. Add a test for each saved output and commit after each step.

1. **Setup.** Write `scripts/start_pulse.sh` and `scripts/status.sh`. Save the version proof and the `status` output.
2. **Board and identities.** Create the board and three agent identities with the presets Pulse documents for each role. Write the MCP config examples with the key replaced by a placeholder. Confirm the board's `grafx/` folder exists.
3. **Recorder.** Run the Recorder session: read the fork, find twelve decisions listed in section 8 of the plan, and record them in one consolidation using the knowledge-graph tools Pulse exposes. Each decision cites its file path and line. Write `scripts/check_citations.py` that confirms each cited line exists. Save the health report and schema info.
4. **Recaller.** Run a fresh session with no history on ten questions about the codebase. Use similarity, natural-language and key-decisions tools. Save each question, the tool used, the top result and whether it is the right decision. Do not tune the questions after seeing results.
5. **Reversal.** I will reverse one decision. Until I do, prepare the Reviewer prompt and a script that waits. When the decision is changed, run the Reviewer to record it, then save the contradiction result, the supersedence chain and the decision history exactly as Pulse returns them.
6. **Second board.** Create a second board with three invented shared conventions. Run a Global Discovery query from the first board's context and save what it returns. If cross-board search needs a setting or a wait for indexing, record what you did.
7. **Crash test.** Kill A: begin a consolidation, add candidates, SIGKILL the `okto-pulse serve` process before commit, restart, and check that the draft is absent while earlier decisions remain. Kill B: run a burst of commits with a script that logs each acknowledgement, SIGKILL at a random moment, restart, and compare acknowledged commits with what is in the graph. Save Pulse's health output and restart log after each kill. If Pulse reports a problem or needs recovery, record exactly what it printed and what happened next.
8. **Direct read.** Stop Pulse cleanly. Run `oktografx schema`, `indexes` and `capabilities` on the board store. Write a read-only Python reader (`read_only=True`) that counts nodes and edges by type. Compare with Pulse's own counts from earlier steps. If the read-only open is refused, record the refusal and what it says, and do not work around it by writing.
9. **Backup and restore.** With Pulse still stopped, copy the board store folder to a work area. Take a Grafx backup of the copy, restore it to a new folder with the original participants stopped, run `verify` on both, and compare counts. Never point Pulse at the restored folder.
10. **Close-out.** Build `demo-state/closeout-result.json` with every item in section 9 of the plan, including per-step times.

## Phase C: finish the repo

1. Write `run_demo.py` with `--steps`, `--start` and `--dry-run`. A dry run must print every command and prompt and need no Pulse install.
2. Write the README in the order named in section 10 of the plan, using only numbers from `closeout-result.json`. Add a hero image and an architecture diagram as SVG files. Put the limits from section 11 in plain words.
3. Take screenshots of the Pulse board and graph view for steps 3, 5 and 6. Check no key or personal path shows. If you cannot capture one, list it for me and carry on.
4. Write `docs/walkthrough.md`, `docs/VERIFIED.md` and `.github/workflows/validate.yml` with the checks in section 10.
5. Add a license for the demo code only, and link the Pulse and Grafx licenses without copying them.
6. Run every check from a fresh clone in a temporary folder. Fix what fails.
7. Scan the whole repo for em dashes, key-like strings and absolute paths from this machine. Remove them.
8. Final report to me: what was built, the real scoreboard numbers, anything that behaved differently from the docs, and anything that needs my decision. Do not push.

## When to stop and ask me

- A Python, port or platform check fails, or the embedding model falls back to the stub.
- Pulse refuses to start, or a store fails `verify`.
- The Kill B check finds an acknowledged commit missing after restart.
- Any result contradicts the Pulse or Grafx docs.
- You would need to write into a Pulse-owned store, or print a key, to continue.
- You are about to claim something you did not measure.
