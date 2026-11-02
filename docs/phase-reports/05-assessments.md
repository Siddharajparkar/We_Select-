# Phase 5 - Assessments + JD upload

Branch `phase/05-assessments`. Endpoints 8-14 of the Prompt B API.

## Implemented
- `POST/GET/PATCH/DELETE /assessments`, `GET /assessments/{id}`, `POST /assessments/{id}/jd-file`, `POST /assessments/{id}/close`.
- Validation: sections (max 10, <= 20 questions/section, <= 40 total), JD text <= 20,000 chars, duration/passing score bounds.
- Draft-only edit/delete (409 otherwise); PATCH returns warnings when changed sections still hold AI questions; close from approved/open.
- JD upload: extension + magic-byte check, exact 2 MB file limit (400), 2 MB + 64 KB body ceiling (413), pypdf extraction in a worker thread with a 10 s guard, whitespace normalisation, 20..20,000 chars else 422 FILE_UNREADABLE.
- Blob path `{tenant}/{assessment}/{sanitised name}`; previous blob deleted only when the path differs; orphan blob removed if the DB update fails.
- Per-route body limits in `middleware.py`.

## Tests
- Unit (rules, text extraction, schemas): `tests/phase5/unit`.
- Integration (full endpoint matrix, cross-tenant 404s, malformed UUID 400, RBAC): `tests/phase5/integration`, run on memory locally and SQL Server in CI (`repos` fixture is parametrised).
- Azurite upload/replace/delete: `tests/phase5/integration/test_p5_int_azurite.py` (CI only).
- Live E2E: `tests/phase5/e2e`, `scripts/e2e/checks/p05_assessments.py`.

## Verified locally
ruff clean, mypy clean (54 files), phase 5 suite: 108 passed, 53 skipped (SQL/Azurite variants, CI-only). Harness `--upto 5`: 23/23.

## UNVERIFIED (see ledger)
AZ-025 (real Blob), AZ-026 (pypdf in image), plus all SQL-variant tests until CI runs.
