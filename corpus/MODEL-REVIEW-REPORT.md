# Model review of the reference decisions and the questions (DRAFT)

Labeler: claude-sonnet-5-5 (omp subagent), model-labelled, not human. Labeled 2026-10-30T06:33:37Z.
Limit: the reviewer is a different model from the authors (reference list: an assistant model; questions: an assistant model and claude-haiku-5-5) but the same vendor family. A person must spot-check. Nothing was run; I read files only.
Files: `reference_decisions_model_review.json`, `questions_model_review.json` (both in this folder). Originals untouched.

## (a) Reference decisions (22)
- Decision really at the cited place: 22 of 22.
- Lines fully correct: 17; partly wrong: 5.
  - `settings-loading`: line 16 is blank (decorator is 17).
  - `duplicate-registration`: line 75 is a `status_code` line; the email detail is 76. Keyword "already taken" is in no code (strings say "already exists").
  - `pagination-parameters`, `cors-allowed-origins`, `connection-pool-size`: `lines` is one flat list for several files, so a line number meant for one file also hits an unrelated line in the other.
- Must a new maintainer know it: yes 14, borderline 7, no 1 (`jwt-subject-claim`, a one-line constant).
- Generic keywords (only used when the line misses): `errors`, `comment`, `author`, `username`, `origin`.
- Note: the file says "hand-made". Its own about text says an assistant model wrote it after the first recorded run. Entries 13-22 repeat the 10 code-derived decisions of the board.
- `connection-pool-size` is only true for the defaults: `core/settings/test.py:16-17` sets 5, and `pyproject.toml:64-65` sets `MAX_CONNECTIONS_COUNT`/`MIN_CONNECTIONS_COUNT` which do not match the field names (inference: those env entries do nothing).

### Is it complete? No. Missing visible decisions
1. `app/app/models/domain/users.py:20,24`: salt is prepended to the password before bcrypt hashing.
2. `app/app/api/dependencies/authentication.py:54,59,90,98`: all auth failures are 403, not 401.
3. `app/app/core/settings/app.py:29`: prefix `Token`, not Bearer.
4. `articles.py:93-99` (repository), `articles.sql:89`, migration `fdf8821871d7_main_tables.py:82,133,160,181` (ON DELETE CASCADE) and `:108` (author SET NULL): hard deletes with cascades.
5. `app/app/api/routes/articles/articles_resource.py:100`: renaming regenerates the slug, with no existing-slug check (create has one at :65).
6. `app/app/models/domain/rwmodel.py:10,21`: camelCase JSON aliases.
7. `app/app/api/routes/authentication.py:29-30`: login failure is 400.
8. `app/pyproject.toml:58`: 100% coverage gate.

## (b) Questions (53: dev 13, held_out 14, legacy 10, model_authored 16)
Board texts: `decisions.json` has only 20 of the 32. The other 12 are in `demo-state/step3/decisions-from-graph.json`; I used both.
- Exactly one right decision: yes 28; yes with caveat 12; two decisions answer 3 (`m8`, `l2`, `l3`); unanswerable confirmed absent 10 (every absent_term searched in all 32 texts and app/ code: none found).
- Caveat cases: d1, d4, h1, h2, h5, h6, m6, m7, m9, l4, l6, l8.
  - Example: `token-expiry` and `no-refresh-tokens` both say "one week" (m8, l2). `password-hashing` and `reject-fancyhash` both say passlib with bcrypt (l3). `h1` and `h2` have answer keywords that appear in two or more decision texts.
- Overlap: I agree with `docs/QUESTIONS.md` on every question I checked (recounted m6 by hand: 0.62). I did not re-run the script. I would call these near-lexical copies of the decision's own wording: m3, m6, m9, m10, m11, m12 (model_authored, mean 0.48), and the table agrees. The dev, held_out and legacy items are mostly paraphrases, but paraphrase can still be easy for an embedding search (d2, h10 have zero shared words and one clear target).
- Every question was written by a model. None was written by a person.

## Looked wrong in the source material
- `decisions.json` title of `aiosql-over-orm` ("Queries are hand-written SQL files") is not fully true: the article filter query is built with pypika (`repositories/articles.py:115,125,146`).
- `m10` asks for a library and a driver, but only `asyncpg` is checked.
