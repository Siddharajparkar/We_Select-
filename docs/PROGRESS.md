# Project Progress & Phase Tracking

**Project:** AI Candidate Assessment Platform (MVP Backend)
**Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy Core + pyodbc, Azure (Node.js 0%)
**Specification:** `docs/prompts/PROMPT_A_MASTER.md` + `docs/prompts/PROMPT_B_ADDENDUM_OFFLINE_AZURE_READY.md`
**Guide:** `docs/OFFICE_CONNECTION_AND_TESTING_GUIDE.md`
**Current State:** Phases 0-6 implemented in Python. The owner requested publishing the pending work on `phase/01-06-consolidated`, based on latest `main`; CI is pending. Nothing has been run against Azure. Phase 7 is next.
**Last Updated:** 2026-11-02 (Phase 6)

---

## Phase Status Summary

| Phase | Description | Status | Evidence / Notes |
|---|---|---|---|
| **Phase 0** | Foundation | **DONE (T1 verified)** | `api/app/{config,main,middleware,core,providers,telemetry}`; 87 tests in `tests/phase0`. The Python rewrite and reconciliation are documented in [`03-python-integration.md`](phase-reports/03-python-integration.md). |
| **Phase 1** | Azure provisioning & guide | **Stage 1 DONE; office run pending sign-off** | Dry-run scripts + sign-off gate, probe (`python -m app.tools.probe`), container app YAML; 56 tests in `tests/phase1`. Nothing has been run against Azure. |
| **Phase 2** | Database & repositories | **DONE (T1 verified; SQL path UNVERIFIED until CI)** | 12 tables in schema `assess`, tenant-scoped repos, 5 system queries, T-SQL migration + runner; 95 tests + 52 `sql`-marked tests that run in CI. |
| **Phase 3** | Container & first pipeline + integration | **DONE locally; CI/container UNVERIFIED** | Dockerfile, `deploy.yml` (fast/container/security/deploy), live/nightly/rollback/load workflows, E2E harness, 3 Postman collections; 105 tests in `tests/phase3`. |
| **Phase 4** | Auth, tenants, users | **DONE locally; SQL/Azure UNVERIFIED** | Endpoints 1-7: Argon2id, signed `sid` cookie, idle/absolute expiry, lockout, platform key, last-admin guard; [`04-auth.md`](phase-reports/04-auth.md). |
| **Phase 5** | Assessments & JD (Blob) | **DONE locally; Blob/SQL UNVERIFIED** | Endpoints 8-14: CRUD, PDF/TXT upload with pypdf, per-route body limits; [`05-assessments.md`](phase-reports/05-assessments.md). |
| **Phase 6** | Job loop & AI generation | **DONE locally; real GPT-4o, T-SQL claim UNVERIFIED** | Endpoints 15-22, job engine, Azure AI provider, review/approve; migration 0003; [`06-ai-generation.md`](phase-reports/06-ai-generation.md). Postman for phases 4-6 in `tests/phase6/postman`. |
| Phase 7 | Participants & invitations (ACS) | Pending | Endpoints 23 to 27. |
| Phase 8 | Candidate exam & timer | Pending | Endpoints 33 to 37. |
| Phase 9 | Scoring & AI marking | Pending | Internal grading engine. |
| Phase 10 | Results, override, export, audit | Pending | Endpoints 28 to 31. |
| Phase 11 | Hardening & resilience | Pending | Limits, security, observability. |
| Phase 12 | Complete CI/CD & testing gates | Pending | Full PR/main workflow. |
| Phase 13 | Release & handover | Pending | Acceptance & execution guide. |

---

## Latest Session Activity (2026-11-02)

- Phases 4, 5 and 6 built in Python; every API test is parametrised over the in-memory and SQL Server backends (the SQL variants run only in CI).
- CI: the `container` job now runs `pytest tests -m "sql or azurite"` and a full harness run through phase 6 against the built image (`tests/phase6/e2e/test_p6_e2e_container.py`). `live-e2e` defaults to phase 6.
- Dockerfile: graceful-shutdown budget changed to 8 s + 20 s for running jobs (< 30 s Container Apps grace); a test pins it.
- Ledger now AZ-001..AZ-030. See each phase report for what is verified and what is not.
- Found and fixed by repeating full runs: a SQLite dispose race (interpreter crash) and a live-server fixture that stalled when its output pipe filled.

## Next steps

1. Open a PR from `phase/01-06-consolidated` to `main` and confirm the `fast` and `container` CI jobs are green: they are the first proof of the SQL Server path, the migrations 0001-0003, the T-SQL job claim and the image.
2. A human reviews `docs/PROVISIONING_PLAN.md` and writes the sign-off line; then office checkpoints OC-1A..H via Cloud Shell, then OC-2..OC-6.
3. Start Phase 7 (participants and invitations) from `main` on `phase/07-participants`.
