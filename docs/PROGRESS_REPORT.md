# Progress Report — AI Candidate Assessment Platform (Backend)

**Report date:** 2026-11-04 · **Repository:** public (so all Azure resource names below are placeholders such as `<KV>`; the real names live only in a private, gitignored file) · **Prepared from:** the code, the git history (35 commits), `docs/PROGRESS.md`, `docs/PROVISIONING_PLAN.md`, `docs/UNVERIFIED_AZURE_LEDGER.md` and the command output captured while each step was run.

How to read this report: **✅** done and checked, **🔄** in progress, **⏳** not started. **⚠️ TO CONFIRM** marks anything that was not proven during the work. No secret value appears anywhere in this document.

**Plain-language glossary** (used throughout):
- **Azure** — Microsoft's cloud. A **resource group** is a folder that holds related cloud resources.
- **Azure CLI (`az`)** — a command-line tool to read and change Azure. **Read-only** commands only look; **write** commands create or change things.
- **Key Vault** — a locked safe in Azure that stores passwords and keys.
- **Managed identity** — a built-in Azure "login" for an application, so it needs no password.
- **Container App** — Azure's service for running our API packaged as a container image. **Container Registry (ACR)** stores those images.
- **OIDC / federated credential** — a way for GitHub to prove its identity to Azure without any stored password.
- **CI/CD** — automatic checking (CI) and automatic release (CD) of the code. **GitHub Actions** is the tool that runs it.
- **Migration** — a script that creates or changes database tables.

---

## Section 1 — Walkthrough of Steps 21 to 27

*Step numbers are the numbered "STEP CARDS" used while connecting the finished backend to real Azure. Steps 1–17 are summarised in Section 3.*

### Step 21 — Re-run the live checks after fixing what the real AI revealed

**Goal.** The first live run against real Azure passed 22 of 28 checks. This step fixed the causes and proved all 28 pass with the real database, real file storage and the real AI model, running the API on a developer laptop.

**What we did.**
1. Read the server log and the failed checks of the first run (Step 20). Two cookie checks failed because the local settings file had turned off the production cookie safety flag; four generation checks failed because every question the AI returned was rejected by our validator.
2. Called the AI deployment directly (using a short-lived Microsoft sign-in token, not a key) with the same prompts. Finding: the model returned valid JSON but wrote the *text* of the correct option in the `correct` field instead of its letter (`A`–`D`); with JSON mode off it sometimes wrapped options as `{"A": "…"}`.
3. Measured the fixed behaviour over 20 real calls: multiple-choice 10/10 valid; cognitive 4/5 and descriptive 3/5 valid, and about 3 of 20 calls **stalled for more than 60 seconds** with no answer (a service-side stall, not a content problem).
4. Changed the code (merged as the "Phi provider" change): the validator now maps the option text or letter forms to `A`–`D` without loosening any safety check (still exactly 4 distinct options, answer must match exactly one); the prompt now demands a bare letter; a stalled model call is retried once; a new setting `AI_JSON_MODE` can switch JSON mode off; the developer profile no longer disables the secure-cookie flag.
5. Stopped the local server, regenerated the local settings file from Key Vault, restarted the API and re-ran the checks.

**Services set up.** None new. The step used the services created in Steps 1–17 (database, file storage, AI model, Application Insights) from the laptop.

**How each service was used.**
- **Azure AI Foundry — Phi-4-mini-instruct model** (what it is: a small language model hosted in Azure; why: it writes the exam questions). Called over the OpenAI-compatible `v1` chat-completions route with the key in an `api-key` header. Settings that matter: `AI_MODE=azure`, `FOUNDRY_API_STYLE=v1`, `FOUNDRY_DEPLOYMENT`, `AI_JSON_MODE`, `AI_TIMEOUT_SECONDS` (30 s). The deployment is limited by Azure to 20 requests and 20,000 tokens per minute.
- **Azure SQL** (the application database): migrations were already applied; the 28 checks created tenants, users, assessments, questions and jobs in schema `assess`.
- **Azure Blob Storage** (file storage): the checks uploaded a job-description PDF and deleted it with its assessment.

**Connected services.** API → SQL (every request), API → Blob (PDF upload/delete), API → AI model (background generation jobs), API → Application Insights (telemetry).

**Commands used.**
- `python scripts/dev/setup.py --skip-probes` — rewrite `api/.env.local` from Key Vault.
- `python scripts/dev/run.py` — start the API against real Azure.
- `python scripts/dev/verify.py` — run the 28 live checks.

**Outcome / verification.** **28 of 28 checks passed.** Independent read-only checks confirmed: 13 tables in schema `assess` with migrations 1–3 recorded; generation jobs stored their token counts (2,910 tokens across two successful jobs); the uploaded PDF was removed from storage (0 blobs); Application Insights recorded 147 requests and 401 dependency calls under the `assess-api` role; the shared database's `dbo` schema was untouched.

### Step 22 — Point the Container App at its secrets in Key Vault

**Goal.** The deployed app must read its passwords and keys from Key Vault, never from the code or from GitHub.

**What we did.**
1. Ran the dry run of `sync_secrets.py` to list which Key Vault secret maps to which app secret.
2. Ran it with `--apply`, which wrote nine Key Vault *references* onto the `assess-api` Container App.
3. Verified read-only: the app lists nine secret names, each marked as a Key Vault reference pointing at the vault and resolved through the app's own managed identity.

**Services set up.** Azure Container Apps secrets (as Key Vault references).

**How it was set up.**
- *What it is:* a Container App secret can hold a value or, as here, a *reference* to a Key Vault secret; Azure fetches the value when the app starts.
- *Why:* no secret value is stored on the app or in GitHub; rotating a secret in Key Vault updates it centrally.
- *Configuration:* each reference is `key=keyvaultref:<vault secret URL>,identityref:<identity id>`. Container Apps limits secret keys to **20 characters**, so three long names were shortened (`acs-conn`, `blob-conn`, `appi-conn`); the other six keep their Key Vault names. The identity used is the app's runtime identity, which holds the role *Key Vault Secrets User* on the vault (created in Step 9).

**Connected services.** Container App ↔ Key Vault (reads secrets) ↔ managed identity (authorises the read).

**Commands used.**
- `python scripts/dev/sync_secrets.py` / `--apply` — dry run, then write the references (internally `az containerapp secret set … --secrets key=keyvaultref:…,identityref:…`).
- `az containerapp secret list` / `az containerapp show` — read-only verification (names and vault URLs only).

**Outcome / verification.** All nine secrets present as Key Vault references; no value stored on the app.

### Step 23 — Give the app its production settings

**Goal.** The container must start in production mode with the right database, AI, email and storage settings.

**What we did.**
1. Dry run of `configure_app.py`: 21 setting *names* listed.
2. `--apply`: wrote 12 plain settings and 9 secret-backed settings onto the app (this creates a new revision of the app).
3. Verified read-only: the app is Running, provisioning succeeded, one revision Healthy with 100 % traffic; the nine secret-backed settings are `secretRef:` entries with no values.

**Services set up.** Container App environment variables.

**How it was set up.**
- *Plain settings:* `APP_ENV=production`, `PORT=8080`, `REPO_BACKEND=sql`, `DB_SCHEMA=assess`, `AI_MODE=azure`, `EMAIL_MODE=azure`, `FILES_MODE=azure`, `FOUNDRY_API_STYLE=v1`, `FOUNDRY_DEPLOYMENT`, `BLOB_CONTAINER`, `APP_BASE_URL`, `API_INTERNAL_URL`.
- *Secret-backed settings* (value comes from the Key Vault reference of Step 22): `DATABASE_URL`, `SESSION_SECRET`, `PLATFORM_KEY`, `FOUNDRY_ENDPOINT`, `FOUNDRY_KEY`, `ACS_CONNECTION_STRING`, `ACS_SENDER`, `BLOB_CONNECTION_STRING`, `APPLICATIONINSIGHTS_CONNECTION_STRING`.
- *Why these matter:* production mode makes the app refuse fake providers, the in-memory database, weak secrets and an insecure cookie. `COOKIE_SECURE` is deliberately **not** set so the safe default (true) applies.

**Connected services.** The settings tell the app where its database, AI model, file storage, email service and telemetry are.

**Commands used.** `python scripts/dev/configure_app.py` / `--apply` (internally `az containerapp update --set-env-vars NAME=value NAME2=secretref:key …`).

**Outcome / verification.** Read-only listing confirmed all 21 settings; the app stayed healthy (it was still running the placeholder image at this point).

### Step 24 — Let GitHub log in to Azure without a password (OIDC)

**Goal.** GitHub's deployment job must be able to sign in to Azure as the "deploy identity" without any stored password.

**What we did.**
1. Added the repository name to the private config and ran `provision.py oidc` (dry run, then `--apply`), which created two *federated credentials* on the deploy identity: one for the `main` branch and one for the GitHub environment named `production`.
2. Verified read-only: both credentials existed with the GitHub issuer and the audience `api://AzureADTokenExchange`.
3. **A problem appeared later (see Step 26):** GitHub presents its identity in an ID-qualified form, so two more credentials with the exact subject GitHub sends had to be added (also with `provision.py oidc`, driven by a private config value `GITHUB_SUBJECT_REPO`). Four credentials now exist.

**Services set up.** Microsoft Entra *federated identity credentials* on the user-assigned managed identity `<DEPLOY_IDENTITY>`.

**How it was set up.**
- *What it is:* a rule saying "tokens issued by GitHub for *this repository and this branch or environment* may act as this identity".
- *Why:* nothing secret has to be stored in GitHub; the trust is bound to the repository.
- *Settings that matter:* issuer `https://token.actions.githubusercontent.com`; audience `api://AzureADTokenExchange`; the *subject* must match the token character for character (`repo:<owner>/<repo>:environment:production` for the deploy job, `…:ref:refs/heads/main` for rollback and nightly). The deploy identity holds only *AcrPush* on the registry and *Contributor* on the `assess-api` app (Step 12).

**Connected services.** GitHub Actions → Microsoft Entra (token exchange) → deploy identity → Container Registry and Container App.

**Commands used.** `python scripts/dev/provision.py oidc` / `--apply` (internally `az identity federated-credential create … --issuer … --subject … --audiences …`); `az identity federated-credential list` for verification.

**Outcome / verification.** Four credentials listed with the expected subjects.

### Step 25 — Enter the deployment settings in GitHub

**Goal.** The pipeline needs to know which Azure identity, tenant, subscription, resource group and registry to use.

**What we did.**
1. Ran `python scripts/dev/github_settings.py`, which prints (to the owner's terminal only) the values to enter. The script derives its list from the names the workflows actually read.
2. In the GitHub web page, created the environment `production`; created three repository **secrets** (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`); created repository **variables** `AZURE_RESOURCE_GROUP`, `AZURE_ACR_NAME` and `AZURE_DEPLOY_ENABLED` (kept `false` until the first checks).

**Services set up.** GitHub repository settings (Actions secrets, variables, environment).

**How it was set up.** The three "secrets" are identifiers, not passwords, but are stored as secrets so they stay out of logs and files. `AZURE_DEPLOY_ENABLED` is an on/off switch: the deploy job runs only when it is `true`.

**Connected services.** GitHub ↔ Azure (via Step 24).

**Commands used.** `python scripts/dev/github_settings.py` (read-only). The GitHub steps were done in the browser.

**Outcome / verification.** The deploy job's first login (Step 26) used these values.

### Step 26 — First deployment through the pipeline

**Goal.** Prove the whole chain: a merge to `main` is built on GitHub, stored in the registry and released to the Container App, with an automatic rollback if the new version does not answer.

**What we did.**
1. Checked read-only that Azure was ready: empty registry, app still on the placeholder image on port 80, code on `main` containing all fixes.
2. Set `AZURE_DEPLOY_ENABLED=true` and re-ran the latest `main` workflow run.
3. **The first attempt failed at the Azure login** with `AADSTS700213: No matching federated identity record found`. The log showed GitHub sent `repo:<owner>@<id>/<repo>@<id>:environment:production` — the owner and repository carry their numeric IDs. We added credentials for that exact subject (Step 24) and re-ran the failed job.
4. The re-run succeeded: login → record current image → set ingress port 8080 → build image and push to the registry tagged with the commit SHA → update the app → smoke test → (rollback only on failure).
5. Verified read-only and with HTTP calls (see below).

**Services set up.** Azure Container Registry (now holding the first image), Azure Container Apps (now running our image).

**How it was set up.**
- *Container Registry:* Basic SKU, admin user disabled; the app pulls with its identity (role *AcrPull*); the pipeline pushes with its identity (*AcrPush*).
- *Container App:* 0.25 vCPU / 0.5 GiB, exactly one replica, external HTTPS ingress on port 8080, single-revision mode. The image tag is the full commit SHA, never `latest`.

**Connected services.** GitHub Actions → Container Registry → Container App → (SQL, Blob, AI model, Application Insights, Key Vault).

**Commands used (pipeline, in `.github/workflows/deploy.yml`).** `azure/login` (OIDC); `az containerapp show` (record current image); `az containerapp ingress update --target-port 8080`; `az acr login`, `docker build`, `docker push`; `az containerapp update --image … --set-env-vars GIT_SHA=…`; `bash scripts/e2e/smoke.sh`; on failure `az containerapp update --image <previous>`.

**Outcome / verification.** ACR holds the image tagged with the commit SHA; the app runs it on port 8080 with one Healthy revision at 100 % traffic; `GET /api/v1/health` returns `{"status":"ok"}`; the `x-app-version` header equals the commit SHA; `/api/v1/docs` and `/api/v1/openapi.json` return 404 (production hides API docs); `/auth/me` without a session returns 401; creating a tenant without the platform key returns 401; the startup log shows telemetry enabled, migrations checked in about 2 seconds, `config ok` (`sql`, `azure`, `azure`, `azure`) and the job loop started.

### Step 27 — Run the live checks against the deployed API

**Goal.** Prove the deployed service (not just a laptop) works end to end, and measure the real performance.

**What we did.**
1. Ran `python scripts/dev/verify.py --base-url https://<app-address>`. Result: **26 of 28 passed.**
2. Investigated both failures with direct tests; both were **test-harness issues, not server defects**: (a) over HTTPS the secure session cookie was replayed from the test client's cookie jar, so a "no session" request looked logged in; (b) a 1.1 MB upload was reset by the cloud front door before the client read the server's `413` answer (curl confirmed the server returns the correct `413` message).
3. Fixed the harness (clear the cookie jar before each request; fall back to a header-only oversized-request probe, with the same certificate bundle as the HTTP library). Phases 0–3 then passed 9/9 on three consecutive runs against the deployed API. The fix is committed locally and **awaiting merge** (⏳).

**Services set up.** None new.

**Connected services.** Same as Step 26; additionally measured Application Insights.

**Commands used.** `az containerapp show … --query …fqdn` (get the address), `python scripts/dev/verify.py --base-url …`, `python scripts/e2e/run.py --upto 3 --target azure`.

**Outcome / verification.** Measured speed from the laptop: a simple request about 190 ms; question generation about 32 s (88 s when the API ran on the laptop, because every database query then crossed to the West US database). **A full 28/28 re-run against the deployed API is pending the harness fix being merged** (⚠️ TO CONFIRM).

---

## Section 2 — Keys and keywords reference (up to Step 17)

No values are listed. "Stored" shows where the real value lives.

### 2.1 Application secrets (nine, stored in Azure Key Vault)

| Name | Type | Purpose | Where it is used | Where it is stored |
|---|---|---|---|---|
| `database-url` → `DATABASE_URL` | connection string | Log in to the Azure SQL database as the least-privilege user (includes `Connection Timeout`) | API data layer | Key Vault; copied to `api/.env.local` (gitignored) for laptops; Container App secret reference |
| `session-secret` → `SESSION_SECRET` | secret | Signs the login cookie | API authentication | Key Vault (generated by `put_secrets.py`) |
| `platform-key` → `PLATFORM_KEY` | API key | Authorises creating a tenant | `POST /platform/tenants` | Key Vault (generated) |
| `foundry-endpoint` → `FOUNDRY_ENDPOINT` | URL | Address of the AI service | AI provider | Key Vault |
| `foundry-key` → `FOUNDRY_KEY` | API key | Authenticates calls to the AI model | AI provider | Key Vault |
| `acs-connection-string` → `ACS_CONNECTION_STRING` | connection string | Authenticates to Azure Communication Services (email) | Email provider (Phase 7) | Key Vault |
| `acs-sender` → `ACS_SENDER` | env var | Sender address of outgoing email | Email provider | Key Vault |
| `blob-connection-string` → `BLOB_CONNECTION_STRING` | connection string | Access to the storage account | File provider | Key Vault |
| `appinsights-connection-string` → `APPLICATIONINSIGHTS_CONNECTION_STRING` | connection string | Sends telemetry | Telemetry setup | Key Vault |

### 2.2 Application settings (non-secret environment variables)

| Name | Type | Purpose | Where it is used | Where it is stored |
|---|---|---|---|---|
| `APP_ENV` | env var | `development` / `test` / `production`; production enables safety rules | `config.py` | `api/.env.local` (dev), Container App settings (prod) |
| `REPO_BACKEND` | env var | `memory` (SQLite) or `sql` (Azure SQL) | data layer | same |
| `DB_SCHEMA` | env var | SQL schema, `assess` | data layer, migrations | same |
| `AI_MODE`, `EMAIL_MODE`, `FILES_MODE` | env var | choose real Azure providers or fakes | provider factory | same |
| `FOUNDRY_API_STYLE`, `FOUNDRY_DEPLOYMENT`, `FOUNDRY_API_VERSION` | env var | how to call the AI route and which deployment | AI provider | same |
| `AI_JSON_MODE`, `AI_MAX_OUTPUT_TOKENS`, `AI_TIMEOUT_SECONDS` | env var | AI call behaviour | AI provider | same |
| `AI_DAILY_TOKEN_CAP`, `DAILY_GENERATION_LIMIT` | env var | per-tenant daily usage guards | generation service | same |
| `BLOB_CONTAINER` | env var | storage container name (`jd-files`) | file provider | same |
| `COOKIE_SECURE`, `ARGON2_*` | env var | cookie flag; password-hash cost | auth | same |
| `APP_BASE_URL`, `API_INTERNAL_URL`, `PORT`, `GIT_SHA` | env var | URLs, port, version label | app / middleware | same |
| `JOB_*` | env var | background-job tuning | job engine | same |
| `ASSESS_IGNORE_ENV_LOCAL`, `ASSESS_ENV_FILE` | env var | skip / relocate the developer env file | config loader | shell |

### 2.3 Private configuration (`config/azure.local.env`, gitignored, names only — no keys)

| Name | Type | Purpose | Where it is used | Where it is stored |
|---|---|---|---|---|
| `AZ_RESOURCE_GROUP`, `AZ_LOCATION` | keyword | resource group and region | all `scripts/dev` scripts | the private file (shared with teammates by the owner) |
| `AZ_KEY_VAULT`, `AZ_STORAGE`, `AZ_ACR`, `AZ_CAE`, `AZ_APP` | keyword | names of the vault, storage account, registry, Container Apps environment and app | provision / secrets scripts | same |
| `AZ_APP_IDENTITY`, `AZ_DEPLOY_IDENTITY` | keyword | runtime and deploy managed identities | provision / sync / OIDC scripts | same |
| `AZ_SQL_SERVER`, `AZ_SQL_DB`, `AZ_AI_RESOURCE`, `AZ_ACS`, `AZ_APPINSIGHTS` | keyword | existing SQL, AI, communication and telemetry resources | secrets scripts | same |
| `ACS_SENDER` | keyword | email sender address | `put_secrets.py` | same |
| `GITHUB_REPO`, `GITHUB_SUBJECT_REPO` | keyword | repository name for OIDC; the ID-qualified form GitHub actually sends (added in Step 24/26) | `provision.py oidc` | same |
| `FOUNDRY_DEPLOYMENT`, `FOUNDRY_API_STYLE`, `BLOB_CONTAINER` | keyword | defaults copied into `api/.env.local` | `setup.py` | same |

### 2.4 Important keywords

| Name | Type | Purpose | Where it is used | Where it is stored |
|---|---|---|---|---|
| `SIGN-OFF: APPROVED by …` | keyword | The human approval line that unlocks every Azure-changing script | `docs/PROVISIONING_PLAN.md`; `require_signoff()` | the plan file (written only by the owner) |
| tag `project=ai-assessment`, `env=mvp` | keyword | Marks every resource we created so it can be found or removed | all CREATE steps | on the Azure resources |
| `assess` | keyword | database schema holding all our tables | migrations | Azure SQL |
| `assess_app` | keyword | least-privilege database user (owns only the `assess` schema) | `DATABASE_URL` | Azure SQL; password in Key Vault only inside `database-url` |
| `jd-files` | keyword | private container for uploaded job descriptions | file provider | Blob Storage |
| `x-app-version` | keyword | response header carrying the commit SHA, used to prove which version answered | middleware, smoke test | response header |
| `secretref:` | keyword | tells Container Apps a setting's value comes from an app secret | `configure_app.py` | Container App settings |

---

## Section 3 — Summary of work up to Step 17

**Preparation (before Step 1).** Read the project rules, decisions and the three specification prompts; confirmed the repository and CI state; fixed the configuration loader so a developer file `api/.env.local` is read outside production only; made the test suite run on Windows (Git Bash lookup, path handling, an unread output pipe that stalled the server); read-only inventory of Azure; found that the Phi model's current route and JSON mode already work; rewrote the provisioning plan and had the owner sign it (New resources in East US; budget $50 per month).

| Step | What was done |
|---|---|
| 1 | Registered two Azure resource providers (`Microsoft.App`, `Microsoft.ContainerRegistry`) — subscription-level, free. |
| 2 | Created the **Key Vault** (RBAC mode, soft delete 7 days). |
| 3 | Created the **storage account** (Standard LRS, no public blob access, TLS 1.2). |
| 4 | Created the private container **`jd-files`**. |
| 5 | Created the **Container Registry** (Basic, admin user off). |
| 6 | Created the **Container Apps environment** (Consumption plan; no Log Analytics to save cost, telemetry goes to Application Insights). |
| 7 | Created two **managed identities**: one for the app at runtime, one for the GitHub deployment. |
| 8 | Gave the owner the *Key Vault Secrets Officer* role to store secrets. (A first attempt failed because Windows runs `az` through `cmd.exe`, which broke a query containing parentheses; the script was fixed and a test added.) |
| 9 | Gave the app identity *AcrPull* (registry) and *Key Vault Secrets User* (vault). |
| 10 | Created the **Container App** `assess-api` from a public placeholder image (0.25 vCPU / 0.5 GiB, one replica). |
| 11 | Linked the app to the registry using its identity. |
| 12 | Gave the deploy identity *AcrPush* (registry) and *Contributor* on the app only. |
| 13 | Added the laptop's public IP to the **SQL firewall** (`provision.py sql-firewall`). |
| 14 | In the portal's Query editor: created schema **`assess`** and the least-privilege user **`assess_app`** (password typed only there). |
| 15 | In the portal: created the **Email Communication Service** with an Azure-managed domain and linked it to the existing Communication Services resource; installed the `communication` CLI extension and recorded the sender address in the private config (a first attempt glued the sender onto the previous line; fixed). |
| 16 | Stored the **nine secrets** in Key Vault (`put_secrets.py`; the SQL password typed at a hidden prompt; keys read from Azure straight into the vault; names only printed). |
| 17 | Installed **ODBC Driver 18 for SQL Server** on the laptop (required to talk to Azure SQL). |

After Step 17 (details in Section 1): Step 18 wrote the local settings and ran the probes — config, blob, AI model and Application Insights passed; **SQL first failed** because the connection's login timeout was hard-coded at 15 s (a paused serverless database needs longer) and the probe tool did not read the local settings file; both fixed. Step 19 started the API against real Azure and applied the three migrations (13 tables). Step 20 ran the live checks (22 of 28).

---

## Section 4 — Phases and stages status

### 4.1 Phases (the backend has 14 phases, numbered 0 to 13)

| Phase | Scope | Status | Notes |
|---|---|---|---|
| 0 | Foundation (config, middleware, errors, providers, telemetry) | ✅ Done | Verified on real Azure indirectly (telemetry, config) |
| 1 | Azure provisioning and guide | 🔄 In progress | Resources created and verified (Steps 1–16); budget alerts and Phi pricing not verified (⚠️) |
| 2 | Database and repositories | ✅ Done | 13 tables created on real Azure SQL |
| 3 | Container, first pipeline, integration | 🔄 In progress | Container built and deployed by the pipeline; rollback drill and `live-e2e` run pending |
| 4 | Auth, tenants, users | ✅ Done | 28/28 live checks (local run on real Azure); deployed re-run pending |
| 5 | Assessments and job descriptions (Blob) | ✅ Done | PDF upload and delete proven on real Blob Storage |
| 6 | Job loop and AI question generation | ✅ Done | Real Phi model proven; quality and stalls measured |
| 7 | Participants and email invitations | ⏳ Pending | Needs the email path; real delivery not yet proven |
| 8 | Candidate exam and timer | ⏳ Pending | |
| 9 | Scoring and AI marking | ⏳ Pending | |
| 10 | Results, override, export, audit | ⏳ Pending | |
| 11 | Hardening and resilience | ⏳ Pending | |
| 12 | Complete CI/CD and test gates | ⏳ Pending | |
| 13 | Release and handover | ⏳ Pending | |

### 4.2 Stages of the Azure-connection work (the current effort)

| Stage | Description | Status | Notes |
|---|---|---|---|
| 0 | Read the code, rules, state | ✅ Done | |
| 1 | Questions to the owner (secrets in Key Vault, East US, budget $50) | ✅ Done | |
| 2 | Read-only inventory | ✅ Done | |
| 3 | Plan and owner sign-off | ✅ Done | Sign-off written by the owner |
| 4 | Repository changes (config loader, AI provider, scripts, infra fixes, docs) | 🔄 In progress | Merged: PRs 6–12; pending merge: OIDC-subject fix, live-harness fix, README/docs |
| 5 | Create missing Azure resources | ✅ Done | Steps 1–16 |
| 6 | Secrets into Key Vault | ✅ Done | Step 16 |
| 7 | Prove it locally against real Azure | ✅ Done | 28/28, cloud effects verified |
| 8 | GitHub Actions → registry → Container Apps | 🔄 In progress | First deploy ✅; rollback drill ⏳; `live-e2e` workflow ⏳; full 28/28 on deployed API ⏳ |
| 9 | Teammate dry run from a fresh clone | ⏳ Pending | Needs `docs/SETUP.md` tested line by line; no script yet to grant a teammate access (⚠️) |
| 10 | Wrap-up (docs, ledger, final report) | ⏳ Pending | |

### 4.3 What is remaining, in order
1. Merge the pending changes (OIDC-subject fix, live-harness fix, documentation); each code merge also produces a new deployed image.
2. Re-run all 28 live checks against the deployed API.
3. Rollback drill: roll back to an older image with `rollback.yml`, then forward again.
4. Run the `live-e2e` workflow from GitHub (phases ≤ 6, with the real AI).
5. Teammate dry run from a clean clone using `docs/SETUP.md`; write the `grant_teammate` helper.
6. Verify budget alert scope and Phi pricing; record actual cost vs. the $50 ceiling (⚠️ not measured yet).
7. Stage 10 wrap-up; then **Phase 7 (email invitations)** and phases 8–13.

---

## Section 5 — Manager summary (read-aloud version)

**What is built.** The backend of the assessment platform — the part that handles sign-in, companies (tenants), users, assessments, job-description uploads and AI question generation — is finished for phases 0 to 6 of 13 and is **now running in Azure**, not only on a laptop. It is packaged as a container, stored in our own registry and served over HTTPS from Azure Container Apps.

**What is working, proven with evidence.** All 28 live checks passed against the real database, file storage and AI model. The deployed service answers its health check, reports the exact version that is running, hides its API documentation in production, and rejects unauthenticated calls. Releasing is automatic: merging to the main branch builds, tests, scans and deploys, and the pipeline logs in to Azure without any stored password. All passwords and keys sit in a Key Vault; none are in the code or in GitHub.

**What we learned.** The small Phi AI model needs a more forgiving answer parser than the first draft assumed and occasionally stalls, so we added a safe retry. The first deployment failed once on a login rule because GitHub identifies the repository by numeric IDs; we fixed it and recorded it so the next person is not caught by it. Running the API inside Azure, next to the cloud database, cut a simple request from about 2.7 seconds (API on a laptop) to about 0.2 seconds, and AI question generation from about 88 seconds to about 32 seconds.

**What is next.** (1) Merge three small pending changes and re-run all checks on the deployed service; (2) practise a rollback; (3) write and test the new-laptop setup guide; (4) start Phase 7, sending real invitation emails to candidates, followed by the candidate exam, marking, results and hardening.

**Cost and risk.** The agreed ceiling is $50 per month. Planned spend for the new resources is roughly $38 per month plus AI usage; **actual spend and AI pricing have not been measured yet** (⚠️ TO CONFIRM). Email delivery to a real mailbox is configured but not yet proven; that is the first task of Phase 7.
