# Project Decisions & Organizational Constraints

**Project:** AI Candidate Assessment Platform (MVP Backend)  
**Context:** Existing Assessment Portal project (not a new application)  
**Last Updated:** 2026-11-03

---

## 1. Confirmed Project & Architectural Decisions

| # | Topic / Decision | Confirmed Value | Operational Notes |
|---|---|---|---|
| a | **GitHub Repository** | Existing Repository: `https://github.com/Siddharajparkar/We_Select-.git` | Do not create a new repository. Continue on current repo and branch hierarchy. |
| b | **Azure Subscription & Tenant** | User-reported personal Azure account/subscription for current connection work (2026-11-03) | User confirms control of the selected subscription and a $50/month project cap. Re-run discovery and obtain fresh plan approval for this scope; do not commit subscription or tenant identifiers. |
| c | **Azure Regional Architecture** | Reported existing resources span East US, North Central US, West US and Global | Current personal-account inventory reports SQL in West US; AI Services accounts in East US and North Central US; and Log Analytics/Application Insights in North Central US. Confirm each exact resource, owner and deployment target before finalizing regions. Preserve the existing SQL location unless its owner separately approves a change. |
| d | **R1 — Global Email Uniqueness** | **YES** | User email addresses are globally unique and case-insensitive across all tenants. |
| e | **R5 — Min Questions per Section** | **Equal to configured count** | Assessments require all configured questions to be present before approval is granted. |
| f | **R13 — API Ingress** | **External ingress enabled** | Target port 8080 with strict authentication, authorization, and rate-limiting controls. |
| g | **ACS Test Email** | User's office email | To be provided securely during Phase 1/Phase 7 live verification. |
| h | **Email Domain** | **Azure-managed domain** | For initial development and testing; avoid custom domain DNS complexity in MVP. |
| i | **Monthly Budget Ceiling** | **$50.00 USD / month for this backend** (superseded 2026-11-03) | Alerts are intended at 50% ($25), 80% ($40), and 100% ($50); verify the actual Azure budget scope and thresholds before relying on them. |

---

## 2. Azure Access & Credential Constraints

1. **Current owner-reported access path (2026-11-03):**
   - The user reports using their personal Azure account and Windows PowerShell Azure CLI for the selected subscription, and confirms they control that subscription.
   - Azure Cloud Shell authentication was blocked with AADSTS530035. Do not retry sign-in or attempt to bypass tenant security settings; use the supported account/device path or contact the tenant administrator.
   - This personal-account context supersedes the earlier organization-laptop-only workflow for current Azure discovery, but all Azure changes remain subject to fresh review and approval in the provisioning plan.
2. **Workflow separation:**
   - The user runs Azure commands manually from an authorized account/device. The coding agent has no Azure access and must not run Azure CLI commands or contact Azure resources.
   - Application code, tests, workflows, scripts, and documentation are developed offline; CI runs on GitHub Actions.
3. **Credential protection:**
   - No Azure passwords, client secrets, MFA codes, subscription/tenant IDs, hostnames, or connection strings shall be requested from the user or committed to Git, local files, or logs.

---

## 3. Existing Regional Resource Mapping

| Resource Category | Region | Known Existing Resource / Purpose | Notes / Constraints |
|---|---|---|---|
| **SQL Database & Server** | **West US** | Assessment SQL Server & Database | Chosen due to Azure SQL service tier availability restrictions in East US. Must not be migrated or duplicated without approval. |
| **Application & Portal** | **East US** *(resource type/target to verify)* | Existing Assessment Portal resource reported in inventory | Confirm its exact type, runtime and ownership before choosing a backend region. |
| **Telemetry & Logs** | **North Central US** *(current-account inventory, user-reported; suitability to verify)* | Log Analytics & Application Insights | Centralized diagnostic logging for application components; verify ownership, association, and suitability before reuse. |
| **AI Foundry / Microsoft Phi** | **North Central US and East US accounts reported; target deployment to verify** | `<AI_RESOURCE>` | User previously reported Phi-4-mini-instruct Serverless API / pay-as-you-go, v1 chat-completions route, 20,000 TPM and 20 RPM. Reverify the exact deployment and ownership in the current subscription; confirm auth/request contract, pricing and access before live connection. |
| **Storage & Artifacts** | **Unresolved** | Storage Account (`jd-files` blob container) | Current storage-account query returned no rows; confirm subscription/scope and target region before deciding whether to create. |
| **Email Communication** | **East US / Global** *(to verify)* | Azure Communication Services | Managed email sending. |

---

## 4. Execution Directives Before Provisioning

- [x] Zero-touch on existing Azure resources: No creation, modification, migration, or deletion until plan approval.
- [ ] Complete read-only discovery in the currently authorized personal-account context; PowerShell inventory is partial and provider-blocked.
- [x] Evaluate East US vs. West US latency and network topology.
- [ ] Revise and review the resource plan, including staged conditional registration of `Microsoft.App` and `Microsoft.ContainerRegistry`; actual prices and budget scope remain unverified.
- [ ] Obtain fresh human/account-owner approval before provider registration, then separately re-approve the final resource plan before provisioning.




## 5. Additional decisions (2026-11-01)

| # | Decision | Value |
|---|---|---|
| j | Database isolation | New schema `assess` in the existing database; app user owns only that schema; no access to existing tables |
| k | AI resource | User reports Microsoft Phi-4-mini-instruct via Serverless API / pay-as-you-go in North Central US, endpoint path `/openai/v1/chat/completions`, 20,000 tokens/minute and 20 requests/minute. Select API style `v1`; verify exact catalog entry, auth/request contract, pricing and access before live calls. Never store the full endpoint hostname in this public repo; `ai_service/` is reference only. |
| l | Container apps | Create only `assess-api` in the existing environment (0.25 vCPU, 0.5 GiB, 1 replica); never touch the portal's apps |
| m | GitHub deploy identity | Contributor on the `assess-api` app only, AcrPush on the registry. OIDC subjects: `repo:Siddharajparkar/We_Select-:ref:refs/heads/main` for nightly/rollback and `repo:Siddharajparkar/We_Select-:environment:production` for the deploy job's GitHub Environment. |
| n | Public repository | No real Azure names, ids, emails or secrets in the repo; plan uses placeholders |
| o | Removed to save cost | Clean-slate rehearsal, stress test, real database restore, RG-wide lock, availability test (unless the plan approves it) |
| p | Superseded 2026-11-03 | The $50/month ceiling applies to this backend only; the user reports that a $50 budget is set, but Azure scope and alert thresholds have not been independently verified. |

## 6. Technology stack (2026-11-02, supersedes any earlier Node/TypeScript wording)

| # | Decision | Value |
|---|---|---|
| p | Backend language/framework | **Python 3.12 + FastAPI + Pydantic v2** (Node.js 0%) |
| q | Data access | SQLAlchemy 2 Core + pyodbc (ODBC Driver 18); one repository implementation; `REPO_BACKEND=memory` runs on in-memory SQLite, `sql` on Azure SQL / SQL Server |
| r | Tests and tooling | pytest, ruff, mypy; Postman collections generated from one Python spec |
| s | Cloud | Azure only (SQL, Blob, Microsoft Phi through Azure AI Foundry, ACS email, Container Apps, Application Insights) |
| t | Frontend (out of scope here) | Next.js / React, consumes the REST API |
| u | LangChain | Not used in the MVP; add only if an agentic use case needs it (Phase 6+), behind the AI provider port |

## 7. Phase 4-6 decisions (2026-11-02)

| # | Decision | Value |
|---|---|---|
| v | Passwords and sessions | Argon2id (19 MiB, t=2, p=1); signed cookie `sid`, only its SHA-256 stored; idle 30 min, absolute 8 h; 5 failures in 10 min lock the account (429 + Retry-After) |
| w | Emails | Globally unique (R1); identical 401 for unknown, wrong or disabled accounts |
| x | JD upload | PDF (pypdf) or UTF-8 text, 2 MB, 20..20,000 characters of extracted text; blob `tenant/assessment/file` |
| y | Approval rule (R5) | A section must hold exactly its configured number of questions |
| z | Daily caps | 20 generations and `AI_DAILY_TOKEN_CAP` tokens per tenant per UTC day (429 `DAILY_AI_LIMIT`) |
| aa | Marks | Objective questions default to 1 mark; descriptive 1-20 (default 10) |
| ab | Job engine | In-process, DB-backed, 2 s tick, <= 3 concurrent, 3 attempts with 5 s x n back-off, stuck jobs recovered after 5 min, 20 s drain on shutdown |
| ac | AI call shape | Batches of <= 5 questions, JSON mode, JD between delimiters and treated as data, 3 validation attempts |

## 8. Budget and Azure discovery update (2026-11-03)

- The user set the backend-only monthly ceiling to **$50 USD**, superseding the earlier $25 amount. Intended budget alerts are 50% ($25), 80% ($40), and 100% ($50).
- The user reports a $50 budget exists, but its Azure scope and alert thresholds have not been verified. Month-to-date spend is deferred at the user's request; a previous-month figure of approximately $50 was reported without a confirmed scope.
- OC-0 user-reported leads: the SQL database is empty and has no `assess` schema; an Azure Communication Services resource exists but its Email service/domain is not created; AI resources and Log Analytics/Application Insights were returned in CLI output; no ACR or Storage rows were returned. The Microsoft.App query could not run because the provider is not registered. The user later clarified that some CLI output came from the development laptop, so **all CLI inventory findings are provisional and must be re-run from the authorized organization Cloud Shell or portal**. These findings do not authorize any Azure changes.
- Before provisioning, the resource owner must confirm the target AI account/deployment, whether discovered monitoring resources are suitable for reuse, Container Apps environment status, registry/storage absence, Email service/domain requirements, provider registration, and a backend-only budget scope. Do not register providers or create resources before the human sign-off in `docs/PROVISIONING_PLAN.md`.
