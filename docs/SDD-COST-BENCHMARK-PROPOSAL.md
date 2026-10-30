# Proposal: an SDD-aware lifecycle cost benchmark

**Status: proposal. Nothing in this file has been run or measured.** No figure below is a result. The only cost numbers in this repo are the agent-session numbers in the [cost table](SCOREBOARD.md#agent-session-cost-under-the-tested-tool-configurations), and those do not answer the questions here.

## Why

The recorded arms compare whole agent sessions with different retrieval interfaces and different access (graph arm: read-only Recaller, no source code; notes arm: Read, Grep and Glob on `app/` plus the notes file). The knowledge sources were prepared before the arms ran, so building and maintaining them is not in the figure. The comparison says nothing about Grafx query cost, about the cost of the MCP tool surface, or about the lifetime cost of a decision memory that Pulse fills as a by-product of spec-driven development (SDD). This benchmark would measure those separately.

## Arms

| Arm | Knowledge creation and access | Purpose |
|---|---|---|
| A. SDD + Pulse + Grafx | The same SDLC artifacts go through Pulse. The normal supported projections and consolidations run. Retrieval is through Pulse, with code access where relevant. | Structured SDD memory in its intended setting |
| B. SDD + code + notes or ADRs | Same source artifacts. Equivalent Markdown decision notes, kept up by an automated or manual step that is counted. Same code access. | A documentation memory with equal content and equal upkeep duty |
| C. SDD + code only | Same implementation, no persistent decision memory beyond the code. | No-memory control |
| D. Retrieval-only controls | Direct Grafx or native queries, Pulse retrieval APIs and indexed document retrieval over the same information, with no agent. | Separates database and retrieval behavior from agent and MCP overhead |

Arms A and B start from the same facts, the same temporal state and the same code access. A relationship that one arm represents and the other does not is reported as part of the feature under test, not hidden. A second view compares graph-only against notes-only access to the same information; it does not replace the arms above.

## Dataset sizes and query types

Three documented sizes: **50, 500 and 5,000 decisions**, with links to requirements, specifications, implementation targets and evidence. Query types:

1. Find one documented rationale.
2. Recover the current decision after one or more reversals.
3. Trace from a requirement to an architectural decision and its implementation evidence.
4. Find conflicting or dependent decisions across several artifacts.
5. A question whose correct result is abstention.

Updates are applied between runs, so the study measures stale-context prevention and not only first lookup.

## Three cost layers

- **Ingestion and maintenance.** SDD authoring that is already required, deterministic projection, cognitive consolidation where it applies, generated notes, edits to decisions, dependency changes, versioning and corrections. Compute cost and added agent or human effort. Authoring is counted on both sides or on neither.
- **Retrieval.** Database or API latency, items returned, bytes and tokens returned, lookup, index and traversal operations, plus quality, provenance and freshness. Document retrieval uses an index, not a read of every file.
- **Agent orchestration.** Cost of the agent consuming the retrieved material: MCP and tool schemas, tool calls, cached and uncached input tokens, output tokens, turns, model cost and elapsed time.

Lifecycle formula:

`Total cost = incremental ingestion + maintenance and updates + (number of queries x retrieval cost) + agent-context and orchestration cost`

For a team already running Pulse SDD, also report the cost above the SDD authoring it already pays for. For a new adopter, report full setup and operation. Break-even points are computed from measured values, not assumed.

## Metrics

- Per-query latency distributions (not only session totals).
- Bytes and tokens returned per query.
- Answer quality against a human-reviewed key (see [HUMAN-VALIDATION.md](HUMAN-VALIDATION.md); until that review is done, quality results are exploratory).
- Provenance: does the answer point to the right source.
- Freshness: is a superseded decision ever returned as current.
- Warm-cache and cold-cache runs reported separately.
- Constant across arms: model, task, output format, scoring method. Repeated runs, with the spread reported.

## Restricted Pulse tool surface control

Run arm A twice: once with the full Pulse MCP tool catalog, once with only the tools the role needs. The difference in input tokens, turns and cost shows how much of the session cost comes from the tool surface rather than from retrieval. Whether the harness can restrict the catalog without changing Pulse is to be checked first.

## What can be done without changing the products

- Arms B and C, and arm A with the supported Pulse flow as installed.
- The 50, 500 and 5,000 decision datasets, generated by this repo's scripts.
- Per-query timing from the client side, bytes and tokens of returned payloads, model-reported cost and token counters.
- Arm D with the public Grafx and Pulse read paths and a standard document index.
- A restricted tool list, if it can be set in the agent's own MCP configuration.

## What needs the Pulse maintainers

- Server-side timing and counters for projection, consolidation and query execution, if the client cannot observe them.
- A supported way to expose a smaller tool catalog per role, if the client cannot do it.
- Guidance on which deterministic projections apply to SDD artifacts, and on the timing of `system:historical_consolidation` relative to closeout, so that ingestion cost is not measured on an unsupported path.
- Triage of the closeout and supersession behavior listed in [PRODUCT-OBSERVATIONS.md](PRODUCT-OBSERVATIONS.md); the benchmark reports these as found and does not patch them.

## Possible outcomes

The study is free to find that plain notes are cheaper, or as good, at small sizes such as 50 decisions, and that any advantage of the graph appears only at larger sizes or only for some query types (reversals, traces, conflicts). It may also find no advantage in the tested range. Each of these results would be published as measured.

## Out of scope here

This proposal is not part of the publication of the current demo. It will not be started before the human review of the evaluation key, and it needs a separate run budget.
