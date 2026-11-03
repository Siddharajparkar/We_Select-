# Provisioning Plan — AI Candidate Assessment Platform Backend

> **Maintained by the agent. The human writes the sign-off line.** The agent never writes or edits it.
> **Public repository.** Only placeholders here: `<RG>`, `<SQL_SERVER>`, `<SQL_DB>`, `<AI_RESOURCE>`, `<KV>`, `<STORAGE>`, `<ACR>`, `<CAE>`, `<APP_IDENTITY>`, `<DEPLOY_IDENTITY>`, `<ACS>`. Real names live only in the gitignored `config/azure.local.env`.
> Rules of work (2026-11-03): the human signs in to Azure CLI and runs every Azure-changing command from a STEP CARD; the agent runs only read-only `az` commands and verifies each step. Reasoning for the stack and decisions: `docs/decisions.md`.

---

## Sign-off block

Stage A (history): conditional registration of `Microsoft.App` and `Microsoft.ContainerRegistry` was approved by SS and SS on 2026-11-03 and executed. Read-only check on 2026-11-03: both `Registered`. That approval covered nothing else.

Stage B (this plan: everything below): **not yet approved.** The scripts and STEP CARDS refuse to write until the human has reviewed this plan and replaced the next line with `SIGN-OFF: APPROVED by <initials> on <date>`.

```
SIGN-OFF: <not approved>
```

The scripts check only for the approval line; they do not bind it to a subscription. Do not run them against another subscription without a fresh review.

---

## Verified starting point (read-only inventory, 2026-11-03)

| Item | Finding |
|---|---|
| Subscription | One enabled subscription; the human is Owner |
| Resource group | One group `<RG>` (East US) holds everything, including the existing portal |
| SQL | `<SQL_SERVER>` West US; database `<SQL_DB>` serverless `GP_S_Gen5`, auto-pause 60 min (can be **Paused**); public access on; "Allow Azure services" rule present; **Entra-only authentication is OFF**, so SQL-password users work |
| AI | `<AI_RESOURCE>` kind `AIServices`, North Central US, local key auth enabled; deployment Phi-4-mini-instruct v1, Running, 20 RPM / 20,000 TPM |
| AI API (probed with a short-lived Entra token, trivial prompt) | `/openai/v1/chat/completions` works and accepts `response_format: json_object`. Key-header auth, output quality and JSON validity rate are **not yet proven** |
| Logs / Application Insights | Present, North Central US (30-day / 90-day retention) |
| Communication Services | `<ACS>` exists (global); **no Email Communication Service and no domain** |
| Missing | Storage account, Key Vault, Container Registry, Container Apps environment, identities, `assess-api` |
| Providers | `Microsoft.App` and `Microsoft.ContainerRegistry` now `Registered` (others already) |

---

## Resource plan

Mode: REUSE (no change) · CREATE · IAM-CHANGE · DB-CHANGE · NONE. Every CREATE is tagged `project=ai-assessment env=mvp`. Region: **East US** for new compute and data resources, same as the existing portal (owner decision 2026-11-04). The SQL database stays in West US, so every database call crosses regions; the probe warns above 150 ms. Background jobs keep AI and email work off the request path.

| # | Resource | Region | Mode | SKU / size | Step | Notes |
|---|---|---|---|---|---|---|
| 1 | Resource providers | subscription | DONE | App, ContainerRegistry | — | Registered |
| 2 | SQL server and database | West US | REUSE | existing | — | No change to the server or to `dbo` |
| 3 | Firewall rule per developer | West US | **SQL-FIREWALL** | one rule per laptop IP | S5 / `grant_teammate.py` | "Allow Azure services" already covers the Container App |
| 4 | Schema `assess` and user `assess_app` | West US | **DB-CHANGE** | schema + contained user | S5 | `scripts/db/create-app-user.sql`, human runs it, password typed only in the SQL editor; user owns only `assess` |
| 5 | AI account + Phi deployment | North Central US | REUSE | existing | — | No change; key read into Key Vault by script without printing |
| 6 | Log Analytics + Application Insights | North Central US | REUSE | existing | — | Connection string read into Key Vault |
| 7 | Key Vault `<KV>` | East US | **CREATE** | Standard, **RBAC mode**, soft-delete on | S5 | Holds the 9 app secrets |
| 8 | Storage account `<STORAGE>` + private container `jd-files` | East US | **CREATE** | Standard LRS, no public blob access, TLS 1.2 | S5 | Connection string goes to Key Vault |
| 9 | Container Registry `<ACR>` | East US | **CREATE** | **Basic**, admin user disabled | S5 | Pipeline pushes images here |
| 10 | Container Apps environment `<CAE>` | East US | **CREATE** | Consumption; logs to the existing workspace | S5 | Only `assess-api` runs in it |
| 11 | Managed identity `<APP_IDENTITY>` | East US | **CREATE** | user-assigned | S5 | Runtime identity of the app |
| 12 | Managed identity `<DEPLOY_IDENTITY>` | East US | **CREATE** | user-assigned | S5 | GitHub OIDC deploy identity (separate from runtime) |
| 13 | Roles | various | **IAM-CHANGE** | see below | S5 | Least privilege |
| 14 | Container App `assess-api` | East US | **CREATE** | 0.25 vCPU / 0.5 GiB, exactly 1 replica, external ingress 8080 | S5 / S8 | Created from a public placeholder image, then deployed by the pipeline |
| 15 | GitHub federated credentials (both subjects) | — | **IAM-CHANGE** | on `<DEPLOY_IDENTITY>` | S8 | `repo:<OWNER>/<REPO>:ref:refs/heads/main` and `repo:<OWNER>/<REPO>:environment:production` |
| 16 | Email Communication Service + Azure-managed domain, linked to `<ACS>` | global (data location matches ACS) | **CREATE** | Azure-managed domain | S5 (portal clicks) | No custom DNS |
| 17 | Budget | — | VERIFY | $50 / month | portal | Owner states the existing $50 budget is scoped to this backend only (2026-11-04). The resource group also holds the portal, so no budget is created by script; the owner confirms alert thresholds in the portal |

### Role assignments (IAM-CHANGE)

| Principal | Role | Scope | Why |
|---|---|---|---|
| The human (setup only) | Key Vault Secrets Officer | `<KV>` | Store the 9 secrets |
| `<APP_IDENTITY>` | AcrPull | `<ACR>` | Pull the image |
| `<APP_IDENTITY>` | Key Vault Secrets User | `<KV>` | Container App Key Vault references |
| `<DEPLOY_IDENTITY>` | AcrPush | `<ACR>` | Pipeline pushes images |
| `<DEPLOY_IDENTITY>` | Contributor | the `assess-api` app only | Pipeline updates the app and rolls back |
| Each teammate (granted by the human, `grant_teammate.py`) | Key Vault Secrets User | `<KV>` | `setup.py` pulls secrets into `api/.env.local` |

---

## Cost (planning allowances, NOT verified prices)

Ceiling: **$50 USD/month for this backend** (decision record). The allowances below were accepted by the owner for planning on 2026-11-03; the prices themselves are unverified and must be checked against the Azure pricing page for the chosen regions before signing.

| Line | Allowance / month | Notes |
|---|---:|---|
| Container App | $18 (range $15–20) | 0.25 vCPU / 0.5 GiB, 1 replica |
| ACR Basic | $6 (range $5–7) | one registry |
| Blob Storage | $2 | Standard hot LRS |
| Key Vault | $1 | Standard; a few secrets, low operation count |
| ACS email | $2 | up to ~200 emails |
| Log Analytics + App Insights | $7 | about 1 GB/month extra ingestion |
| Network / misc | $2 | |
| **Non-AI subtotal** | **about $38** | broad range about $27–46 |
| Phi-4-mini-instruct | **not estimated** | token volume unknown; guardrail is `AI_DAILY_TOKEN_CAP` (per tenant per day) and the 20 RPM / 20k TPM deployment limits |
| Existing SQL, AI base, portal | not included | reuse adds only incremental usage |

An Azure budget alerts; it does not stop spending. Teardown: delete only resources tagged `project=ai-assessment`.

---

## What is NOT touched

Portal apps and their settings; `dbo` tables; the AI deployment configuration; Log Analytics and Application Insights configuration; any role assignment not listed above.

---

## Order of work (STEP CARDS, one at a time, each verified read-only before the next)

1. Resource providers — DONE.
2. Key Vault → Storage + container → Container Registry → Container Apps environment → identities and roles → `assess-api` placeholder app.
3. SQL: firewall rule for the developer IP; human runs `create-app-user.sql` in the portal Query editor; verification queries.
4. Email: Email Communication Service and managed domain, linked in the portal.
5. Secrets: `put_secrets.py` fills the 9 Key Vault secrets (values never printed); `sync_secrets.py` points the Container App at them.
6. Local proof against real Azure (probes, migrations, live harness with the real Phi model).
7. GitHub variables/secrets, OIDC credentials, first deploy, rollback drill.
8. Teammate dry run from a fresh clone.

Decisions recorded (2026-11-04): (a) new resources in **East US**; (b) the existing $50 budget is scoped to this backend only; (c) `AI_DAILY_TOKEN_CAP=200000` stays as the existing per-tenant per-day MVP guard, no per-user limits and no further hardening for now.
