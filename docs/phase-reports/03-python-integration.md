# Phase 3 report — Python/FastAPI rebuild of Phases 0-3, container, pipeline and integration

Branch: `feature/phase-3-testing-integration`. Stack: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy Core + pyodbc. Node.js is not used.

## Implemented
- **Phase 0:** settings with production guard rails, JSON logging with secret redaction, request-id / security-header / body-limit ASGI middleware, uniform error envelope, health route, provider ports with scriptable fakes, telemetry hook.
- **Phase 1:** infra scripts unchanged (dry-run, sign-off gate); probe tool in Python; container app YAML and config script.
- **Phase 2:** schema (12 tables, schema `assess`), tenant-scoped repositories, 5 audited cross-tenant system queries, T-SQL migration and applock runner, memory backend on in-memory SQLite with real constraints.
- **Phase 3:** multi-stage Dockerfile (non-root, ODBC 18, port 8080), `deploy.yml` with jobs fast, container, security, deploy (OIDC, ingress target-port 8080, smoke test, rollback), live-e2e, nightly, rollback, load-test workflows; E2E harness and smoke script; 3 generated Postman collections plus a Python runner.

## Verified locally (tier T1)
- `ruff check`, `ruff format --check`, `mypy app` clean (34 source files).
- Full pytest run: 343 passed, 60 skipped; the 60 tests are skipped locally on purpose (markers `sql`, `container`, `azurite`, `e2e` needing a container runtime).
- Per folder: phase0 87, phase1 56, phase2 95 (+52 skipped), phase3 unit 77, integration 15 (+3 skipped), e2e 13 (+5 skipped).
- Postman spec executed against a live local server: unit 30/30, integration 33/33, E2E 16/16 assertions.
- Coverage of `api/app` about 92% (probe and Azure blob provider are the low spots; they need Azure/Azurite).

## UNVERIFIED (needs CI or the office)
SQL Server repositories and T-SQL (claim query, ISJSON, filtered index, parallel migration runners), pyodbc / ODBC driver, image build and size, Trivy, container E2E, Azurite tests, `prepare_sql.py`, `install_odbc.sh`, Azure Monitor telemetry, Azure probes, container app YAML, deploy and rollback. Tracked as AZ-014 to AZ-021 in the ledger.

## Decisions and open questions
- The API lives in `api/` (the repo already had this directory); `backend/` is untouched.
- Folder skeleton the owner planned to share was not received; layout follows the existing repo.
- $25/month budget scope and whether to make the repository private are still open.
