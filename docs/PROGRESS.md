# Project Progress & Phase Tracking

**Project:** AI Candidate Assessment Platform (MVP Backend)
**Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy Core + pyodbc, Azure (Node.js 0%)
**Specification:** `docs/prompts/PROMPT_A_MASTER.md` + `docs/prompts/PROMPT_B_ADDENDUM_OFFLINE_AZURE_READY.md`
**Guide:** `docs/OFFICE_CONNECTION_AND_TESTING_GUIDE.md`
**Current State:** Phases 0-6 implemented in Python. The user reports using a personal Azure account and Windows PowerShell CLI, with control of the selected subscription and a $50/month backend cap. Current-account read-only inventory reports `Microsoft.App` and `Microsoft.ContainerRegistry` as `NotRegistered`; Container Apps and ACR inventory are blocked/inconclusive. The prior provisioning approval is superseded and has been removed from the revised plan pending a fresh review. OC-0 remains incomplete; no Azure resources or provider registrations have been changed by this work. Actual prices, budget scope, and Phi cost remain unverified.
**Last Updated:** 2026-11-03 (Azure OC-0 in progress)

---

## Phase Status Summary

| Phase | Description | Status | Evidence / Notes |
|---|---|---|---|
| **Phase 0** | Foundation | **DONE (T1 verified)** | `api/app/{config,main,middleware,core,providers,telemetry}`; 87 tests in `tests/phase0`. The Python rewrite and reconciliation are documented in [`03-python-integration.md`](phase-reports/03-python-integration.md). |
| **Phase 1** | Azure provisioning & guide | **OC-0 IN PROGRESS; provider approval/re-inventory required before OC-1A** | Current-account Windows PowerShell inventory (user-reported) found SQL, AI Services, Log Analytics, Application Insights, and Communication Services resources; storage/ACR list commands returned no rows. `Microsoft.App` and `Microsoft.ContainerRegistry` are `NotRegistered`; the Container Apps query was blocked and the empty ACR result is inconclusive. The prior plan approval is superseded; this plan update proposes only conditional provider registration and read-only re-inventory as a first stage. SQL metadata inventory, Phi ownership/API/pricing, ACS Email linkage, budget scope/alerts, and final resource decisions remain outstanding. No Azure changes have been made. |
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
- Earlier SQL metadata and CLI inventory came from a different access context; treat those results as provisional and re-run read-only discovery from the currently authorized account/device before selecting REUSE/CREATE. Do not copy raw output, identifiers, names, hostnames, emails, or secrets into the public repository.
- Cost Analysis was deferred at the user's request. The $50/month backend cap is recorded, but Azure budget scope and alert thresholds remain unverified; the reported previous-month amount has unknown scope. The user accepted suggested non-AI planning allowances totaling about $37/month (broad $26–$45 range); this is not a quote and leaves about $13 at selected values for Phi under the cap. User reports Phi-4-mini-instruct Serverless API in North Central US, v1 chat-completions path, 20,000 TPM and 20 RPM. The endpoint hostname is not recorded here. Assessments/month are dynamic, there are about 20 candidates/assessment, and generation/marking calls are not fixed, so monthly token volume and total AI cost remain unknown. Verify auth/request compatibility and pricing before live use.
- The previous sign-off is superseded because the current personal-account access context and provider-registration scope were not covered by its review. The revised plan has `SIGN-OFF: <not approved>` until the human and account owner approve the staged provider-registration scope. Azure access and provisioning were not performed by this agent.
- Current-account provider registration states are user-reported from Windows PowerShell; any registration remains a separate subscription-level change requiring a limited approved stage.
- The office guide supports Windows PowerShell inventory and Bash where available, includes the read-only SQL inventory step, and records the staged provider-registration procedure. No Azure operations were run by the agent.
- User reports read-only OC-0 results from Cloud Shell/Query Editor: SQL metadata lists only built-in schemas (no `assess` shown) and General Purpose `GP_S_Gen5_2`, compatibility 170; Foundry deployment listing succeeded using ARM API `2025-06-01`, showing Phi-4-mini-instruct version 1, GlobalStandard, capacity 20 in North Central US. Evidence is user-provided; endpoint authentication/request compatibility, quota sharing, cost, SQL full inventory, Container Apps/provider state, registry and storage remain unverified.
- The initial deployment-list command failed due to Cloud Shell's unsupported API version, and the first `az rest` attempt omitted resource variables; the corrected read-only request succeeded with API version `2025-06-01`.
- Updated the provisioning plan with the newly reported SQL SKU/compatibility and Phi deployment metadata. OC-0 remains open: the schema list alone is not the full table/index inventory; owner confirmation and remaining resource/provider/budget checks are required. No Azure resources were changed.
- Earlier Cloud Shell/provider reports are historical. The current personal-account PowerShell report is the active provider-state evidence below. ACR list results remain inconclusive while its provider is unregistered.
- **Personal-account inventory update (2026-11-03):** Cloud Shell authentication was blocked by AADSTS530035. The user confirms control of the selected personal subscription and ran read-only Azure CLI from Windows PowerShell. Provider states: `Microsoft.App` and `Microsoft.ContainerRegistry` are `NotRegistered`; the other six queried providers are `Registered`. Resource listings reported SQL, AI Services, Log Analytics, Application Insights, and Communication Services; storage and ACR returned no rows. Do not infer Container Apps or ACR absence while their providers are unregistered. The prior approval is superseded; fresh plan review is required. No Azure changes were made by the agent.
- The agent never writes the sign-off line and has not run Azure commands.

## Next steps

1. Complete read-only OC-0 discovery from the authorized account/device: verify the SQL object inventory, Phi ownership/API/pricing, ACS Email linkage, budget scope/alerts, and remaining resource details. Keep actual identifiers and endpoint hostnames private.
2. Review and merge this revised plan. The first approval stage is limited to conditionally registering `Microsoft.App` and `Microsoft.ContainerRegistry` if they remain unregistered, then rerunning read-only Container Apps/ACR inventory. Do not run provisioning scripts during this stage.
3. Use the resulting inventory to revise the plan again; obtain fresh human/account-owner approval on `main` before any service/resource provisioning.
4. Follow the ordered OC-1A..OC-13 checkpoints only against the verified selected subscription and exact approved plan scope.
5. Start Phase 7 (participants and invitations) from `main` on `phase/07-participants` only after phase 0-6 CI is green and the existing branch/PR workflow requirements are met.
