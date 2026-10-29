You are the Recorder. Read the codebase in `../../app` and record exactly twelve design decisions in the Pulse board knowledge graph, in ONE consolidation session.

Board id: 8d5c16c0-fc18-4266-9f8c-ec1903c80a18
Anchor spec id: 966a4578-acae-4179-a83d-60f67721a15f

## The twelve topics (fixed slugs)

For each topic, find the choice the code makes. One decision per topic.

| slug | topic |
|---|---|
| auth-header-scheme | how the auth header is read (scheme or prefix) |
| token-expiry | how long tokens live |
| password-hashing | how passwords are hashed and checked |
| error-response-shape | the JSON shape of error responses |
| pagination-parameters | the paging query parameters and their defaults |
| slug-rules | how article slugs are made |
| comment-ownership | who may delete a comment |
| favorites | how favoriting an article works |
| tag-handling | how tags are stored and linked to articles |
| database-access-layer | how the code talks to the database |
| settings-loading | how settings are loaded |
| test-layout | how the tests are organised |

## What to do

1. Read the code. Use Grep and Read. Find the one line that best shows each choice.
2. Open the session: `okto_pulse_kg_begin_consolidation` with `artifact_type` `spec`, `artifact_id` the anchor spec id above, `raw_content` a short list of the twelve slugs and titles, and `deterministic_candidates` an empty list. If `nothing_changed` is true, stop and report it.
3. For each topic, call `okto_pulse_kg_add_node_candidate` with node_type `Decision` and these fields:
   - `candidate_id`: the slug
   - `title`: one sentence stating the choice
   - `content`: two or three sentences on what the code does, then a last line `Source: <repo-relative path>:<line number>`
   - `context`: where it applies
   - `justification`: the reason if the code or a comment states one, otherwise `not stated in code`
   - `source_artifact_ref`: `final_report:966a4578-acae-4179-a83d-60f67721a15f:decision:<slug>` (Pulse allows a cognitive Decision on a technical root only with this prefix)
   - `source_confidence`: 0.9
   - `source_span_quote`: the exact text of the cited line, trimmed
4. After each add, call `okto_pulse_kg_get_similar_nodes` for that candidate with `top_k` 5 and `min_similarity` 0.85. The graph is empty, so expect no matches. Report any match.
5. Add at most five `depends_on` edges between your decisions, only where the code shows one needs the other. Use `okto_pulse_kg_add_edge_candidate` with a `candidate` object holding `candidate_id` (a unique id such as `edge-<from>-<to>`), `edge_type` `depends_on`, `from_candidate_id`, `to_candidate_id` and a `confidence`. Every edge needs its own `candidate_id`. Skip this if the code does not show a clear dependency.
6. Call `okto_pulse_kg_propose_reconciliation` and read every hint.
7. Call `okto_pulse_kg_commit_consolidation` with a one-sentence `summary_text`. If it fails, report the exact error and call `okto_pulse_kg_abort_consolidation`. Do not retry with changes you were not asked to make.
8. Verify with `okto_pulse_kg_query_cypher`: `MATCH (n:Decision) WHERE n.source_artifact_ref STARTS WITH 'final_report:966a4578-acae-4179-a83d-60f67721a15f:decision:' RETURN n.id, n.title, n.source_artifact_ref`. Then one `okto_pulse_kg_query_natural` call for "how are passwords hashed".

## Final answer

Reply with a single JSON object and nothing else:
`{"session_id": "...", "commit_status": "...", "nodes_added": N, "edges_added": N, "decisions": [{"slug": "...", "title": "...", "file": "app/...", "line": N, "quote": "..."}], "problems": ["..."]}`
