# Phase 6 - Job engine, AI generation, question review, approval

Branch `phase/06-ai-generation`. Endpoints 15-22 of the Prompt B API.

## Implemented
- **Migration 0003** (idempotent): `jobs.run_after/started_at/tokens_used`, `questions.status/explanation/word_limit`; `db/schema.py`, models and mappers in step (parity tested).
- **Job engine** (`app/jobs/engine.py`): DB-backed queue, 2 s non-overlapping tick, at most 3 concurrent jobs, handler registry, retries (max 3, `run_after = now + 5 s x attempt`, provider `Retry-After` wins), non-retryable errors, readable messages, `errorCode` kept in `result_json`, stuck `running` jobs re-queued/failed after 5 min (at start and every minute), graceful stop (lets running jobs finish up to 20 s), structured logs without prompts or answers. Started by the lifespan when `JOB_LOOP_ENABLED`.
- **AI**: prompt/validation behavior includes JD data delimiting, exactly 4 unique options, A-D answers, explanations, rubrics, de-duplication, and token accounting. The adapter implements `v1` and `azure-deployments` chat-completions styles, but the owner-selected Phi Serverless API contract is not verified; no real call is authorized until the endpoint contract is confirmed and the adapter is shown compatible.
- **Endpoints**: `POST /assessments/{id}/generate` (202; checks in order 404, 409, 422 JD_TOO_SHORT, 400 sectionIndexes, 429 DAILY_AI_LIMIT with Retry-After), `GET /jobs/{id}`, `GET|POST /assessments/{id}/questions`, `PATCH|DELETE /questions/{id}`, `POST /questions/{id}/regenerate` (AI-only, in place, 202 job), `POST /assessments/{id}/approve` (409 NO_QUESTIONS / SECTION_INCOMPLETE, positions renumbered 1..n, one transaction).
- Generation is atomic: AI calls first, then one transaction swaps the AI draft questions of the chosen sections (custom ones stay); a failed or approved-meanwhile job leaves no partial questions.

## Decisions and interpretations (please confirm)
1. R5: a section must hold **exactly** its configured count to approve (your earlier decision).
2. Objective questions are worth **1 mark** by default; descriptive ones use the AI's/author's `maxScore` (1-20, default 10).
3. Editing an AI question keeps `source = "ai"`; regenerating a *section* replaces it (edits are lost), regenerating one question is blocked for `custom` ones.
4. Adding a custom question beyond the configured count is allowed (caps 20 per section, 40 total, 409 beyond); approval then asks you to delete extras.
5. `AI_DAILY_TOKEN_CAP` is enforced **per tenant per UTC day** (same 429 DAILY_AI_LIMIT), next to the 20-generation cap.
6. `requeue_stuck` is a sixth job-maintenance function that sees all tenants (like `claim_next`); it is listed in `TENANTLESS_BY_DESIGN` with a docstring. The five named cross-tenant *system* queries are unchanged.

## Verified locally
ruff and mypy clean; full local suite green (SQL variants excluded); live E2E harness `--upto 6`: 28/28 against a real uvicorn process with the real background loop and the fake AI; the engine passes ordering, back-off, stuck-recovery, two-engines-never-duplicate, <=3 concurrent, graceful-stop tests. A shutdown race (SQLite connection closed under a running claim -> interpreter crash) was found by repeated full runs and fixed (`Database.dispose` takes the lock; the loop is stopped by waking it, not cancelling it) with a regression test.

## UNVERIFIED (ledger AZ-027..030)
Real Microsoft Phi behavior (model variant, deployment/API compatibility, quality, and cost are unverified), T-SQL claim/migration on SQL Server and Azure SQL, loop footprint in 0.25 vCPU.
