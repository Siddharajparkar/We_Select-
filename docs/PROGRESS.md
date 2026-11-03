# Project Progress & Phase Tracking

**Project:** AI Candidate Assessment Platform (MVP Backend)
**Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy Core + pyodbc, Azure (Node.js 0%)
**Specification:** `docs/prompts/PROMPT_A_MASTER.md` + `docs/prompts/PROMPT_B_ADDENDUM_OFFLINE_AZURE_READY.md`
**Guide:** `docs/OFFICE_CONNECTION_AND_TESTING_GUIDE.md`
**Current State:** Phases 0-6 implemented in Python. Azure OC-0 discovery is in progress; no Azure resources or provider registrations have been changed by this work. A sign-off line is present in the current local working copy, but the plan is uncommitted on a non-main branch and is not yet available to a fresh Cloud Shell clone; OC-0 inventory and owner verification remain outstanding. The user set a $50/month backend-only planning cap and accepted the suggested non-AI pilot allowances ($37/month at selected values); actual prices and Phi cost remain unverified. Phase 7 is next after the existing phase branch is published and green.
**Last Updated:** 2026-11-03 (Azure OC-0 in progress)

---

## Phase Status Summary

| Phase | Description | Status | Evidence / Notes |
|---|---|---|---|
| **Phase 0** | Foundation | **DONE (T1 verified)** | `api/app/{config,main,middleware,core,providers,telemetry}`; 87 tests in `tests/phase0`. The Python rewrite and reconciliation are documented in [`03-python-integration.md`](phase-reports/03-python-integration.md). |
| **Phase 1** | Azure provisioning & guide | **OC-0 IN PROGRESS; provisioning not started** | User-provided SQL metadata reports General Purpose `GP_S_Gen5_2`, compatibility 170, and no `assess` schema in displayed schemas; full table/index inventory remains. Cloud Shell listing confirms North Central US Phi-4-mini-instruct, version 1, `GlobalStandard`, capacity 20. User reports `Microsoft.App` and `Microsoft.ContainerRegistry` are `NotRegistered`; other queried providers are `Registered`. ACR listing returned no rows; three additional resource tables were unlabeled, likely Log Analytics, Application Insights and ACS if in query order. ACS Email readiness, Container Apps status, resource scopes, monitoring suitability, budget scope, and plan availability on `main` remain outstanding. No Azure changes have been made. |
| **Phase 2** | Database & repositories | **DONE (T1 verified; SQL path UNVERIFIED until CI)** | 12 tables in schema `assess`, tenant-scoped repos, 5 system queries, T-SQL migration + runner; 95 tests + 52 `sql`-marked tests that run in CI. |
| **Phase 3** | Container & first pipeline + integration | **DONE locally; CI/container UNVERIFIED** | Dockerfile, `deploy.yml` (fast/container/security/deploy), live/nightly/rollback/load workflows, E2E harness, 3 Postman collections; 105 tests in `tests/phase3`. |
| **Phase 4** | Auth, tenants, users | **DONE locally; SQL/Azure UNVERIFIED** | Endpoints 1-7: Argon2id, signed `sid` cookie, idle/absolute expiry, lockout, platform key, last-admin guard; [`04-auth.md`](phase-reports/04-auth.md). |
| **Phase 5** | Assessments & JD (Blob) | **DONE locally; Blob/SQL UNVERIFIED** | Endpoints 8-14: CRUD, PDF/TXT upload with pypdf, per-route body limits; [`05-assessments.md`](phase-reports/05-assessments.md). |
| **Phase 6** | Job loop & AI generation | **DONE locally; Microsoft Phi live behavior, T-SQL claim UNVERIFIED** | Endpoints 15-22, job engine, Azure AI provider, review/approve; migration 0003; [`06-ai-generation.md`](phase-reports/06-ai-generation.md). User reports Phi-4-mini-instruct, Serverless API / pay-as-you-go, North Central US, v1 route and rate limits; auth/request compatibility, pricing and live behavior remain unverified. |
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

## Azure connection activity (2026-11-03)

- Owner confirms ACS is currently provisioned only at the Communication Services resource level, without the Email service/domain; a Foundry project and Phi-4-mini-instruct deployment exist; and the SQL database is empty. These confirmations are user-reported, not independently verified. Do not copy raw resource names, hostnames, emails, or secrets into the public repository.
- Partial Cloud Shell PowerShell inventory (2026-11-03) listed two AI Services account regions, Log Analytics/Application Insights, ACS and a SQL server; no ACR or Storage rows were returned. Microsoft.App prevented Container Apps enumeration. SQL database and AI deployment commands failed because their resource variables were empty; provider status did not run because a Bash loop was pasted into PowerShell. This is partial OC-0 evidence only; it does not authorize or establish resource absence.
- Earlier SQL metadata and CLI inventory came from the development laptop; treat those results as provisional and re-run read-only discovery in organization Cloud Shell or the portal before selecting REUSE/CREATE. Do not copy raw output, identifiers, names, hostnames, emails, or secrets into the public repository.
- Cost Analysis was deferred at the user's request. The $50/month backend cap is recorded, but Azure budget scope and alert thresholds remain unverified; the reported previous-month amount has unknown scope. The user accepted suggested non-AI planning allowances totaling about $37/month (broad $26–$45 range); this is not a quote and leaves about $13 at selected values for Phi under the cap. User reports Phi-4-mini-instruct Serverless API in North Central US, v1 chat-completions path, 20,000 TPM and 20 RPM. The endpoint hostname is not recorded here. Assessments/month are dynamic, there are about 20 candidates/assessment, and generation/marking calls are not fixed, so monthly token volume and total AI cost remain unknown. Verify auth/request compatibility and pricing before live use.
- The sign-off line is present in the local plan, but the plan changes are uncommitted on the current non-main branch; do not assume the approval gate will pass in Cloud Shell until the approved plan is committed/merged and verified there. Azure access and provisioning were not performed by this agent.
- Provider registration status from the old dev-laptop query is not verified. Check it during read-only OC-0 inventory; any provider registration is a separate Azure write that must be explicitly reviewed and approved.
- The office guide now provides a click-by-click Cloud Shell Bash path for OC-0, commands to discover names before using resource-specific variables, a read-only SQL inventory step in the portal, and a sanitized report checklist. No Azure operations were run by the agent.
- User reports read-only OC-0 results from Cloud Shell/Query Editor: SQL metadata lists only built-in schemas (no `assess` shown) and General Purpose `GP_S_Gen5_2`, compatibility 170; Foundry deployment listing succeeded using ARM API `2025-06-01`, showing Phi-4-mini-instruct version 1, GlobalStandard, capacity 20 in North Central US. Evidence is user-provided; endpoint authentication/request compatibility, quota sharing, cost, SQL full inventory, Container Apps/provider state, registry and storage remain unverified.
- The initial deployment-list command failed due to Cloud Shell's unsupported API version, and the first `az rest` attempt omitted resource variables; the corrected read-only request succeeded with API version `2025-06-01`.
- Updated the provisioning plan with the newly reported SQL SKU/compatibility and Phi deployment metadata. OC-0 remains open: the schema list alone is not the full table/index inventory; owner confirmation and remaining resource/provider/budget checks are required. No Azure resources were changed.
- User reports Cloud Shell provider states: Microsoft.App and Microsoft.ContainerRegistry are NotRegistered; Microsoft.OperationalInsights, Microsoft.Sql, Microsoft.Storage, Microsoft.CognitiveServices, Microsoft.Communication, Microsoft.Insights are Registered. ACR list returned no rows. Three resource result tables were not labeled; tentative mapping to Log Analytics, Application Insights and Communication Services is noted as conditional. Do not register providers or provision before plan review and OC-0 completion.
- The agent never writes the sign-off line and has not run Azure commands.

## Next steps

1. Complete read-only OC-0 discovery in the organization Cloud Shell/portal: verify the SQL target/tier/schema inventory, resource groups, registry, Container Apps environment/provider status, storage, monitoring, ACS/email readiness, and Foundry ownership/contract. Keep actual identifiers and endpoint hostnames in private notes.
2. Resolve remaining resource choices and cost assumptions with the owner. The signed plan currently records allowances, not verified prices; do not assume those allowances cap actual spend.
3. Ensure the reviewed plan/sign-off is committed through the repository's approved PR workflow and present on `main` before running provisioning scripts from a fresh Cloud Shell clone.
4. Once OC-0 is complete and the approved plan is available on `main`, follow the guide's ordered OC-1A..OC-13 checkpoints. Do not create resources before verifying the inventory and exact plan scope.
5. Start Phase 7 (participants and invitations) from `main` on `phase/07-participants` only after phase 0-6 CI is green and the existing branch/PR workflow requirements are met.
