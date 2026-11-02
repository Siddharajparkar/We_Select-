# Provisioning Plan — AI Candidate Assessment Platform Backend

> **Maintained by the agent.** Human fills cost estimates and writes the sign-off.
> **Public repository** — every real Azure name, ID, subscription ID, hostname, email, or key must be replaced with `<placeholder>` here. Real values live only in your local notes and Cloud Shell variables.
>
> See `docs/OFFICE_CONNECTION_AND_TESTING_GUIDE.md` for how to run each step.
> See `docs/UNVERIFIED_AZURE_LEDGER.md` for all Azure assumptions that need office verification.

---

## Sign-off block

> ⚠️ **No Azure resource may be created, modified, migrated, or deleted until the line below is filled in by the human reviewer.**
> The provisioning scripts check for this line and refuse to execute any write operation without it.

```
SIGN-OFF: <not approved>
```

*(The human writes: `SIGN-OFF: APPROVED by <name> on <YYYY-MM-DD>` here when they are ready to proceed with OC-1A.)*

---

## Open questions (answer before sign-off)

| # | Question | Answer |
|---|---|---|
| Q1 | Is the $25/month ceiling for the **new backend only**, or the **whole subscription** (including the existing Assessment Portal)? | *(fill at OC-0)* |
| Q2 | Which existing Container Apps environment does the portal use? (name and resource group) | *(fill at OC-0)* |
| Q3 | Does an existing Container Registry (ACR) already hold portal images? If yes, use `MODE_ACR=reuse`. | *(fill at OC-0)* |
| Q4 | Does an existing Azure Communication Services resource exist? If yes, use `MODE_EMAIL=reuse`. | *(fill at OC-0)* |
| Q5 | Does an existing storage account already have a `jd-files` blob container? If yes, use `MODE_BLOB=reuse`. | *(fill at OC-0)* |
| Q6 | What is the exact name of the existing GPT-4o deployment in `<AI_RESOURCE>`? | *(fill at OC-1D from `az cognitiveservices account deployment list`)* |
| Q7 | Are the existing Log Analytics workspace and Application Insights in the same resource group as the portal? | *(fill at OC-0)* |

---

## Resource plan

Pre-filled from the decision record (B3 rows 21–34). OC-0 fills the `Mode` and actual resource names.

| Resource | Region | Mode | SKU / size | Script | Reason | Cost driver | Risk | Needs approval |
|---|---|---|---|---|---|---|---|---|
| **Log Analytics workspace** | East US | REUSE (if exists) / CREATE | PerGB2018, 30-day retention | `10-core.sh` | Telemetry sink for App Insights | Usage-based; human estimates at OC-PLAN | Low | OC-0 confirms |
| **Application Insights** | East US | REUSE (if exists) / CREATE | Workspace-based | `10-core.sh` | API request logs, error tracking | Included with Log Analytics | Low | OC-0 confirms |
| **Budget alert** | Subscription | CREATE | $25 ceiling, alerts at 50/80/100% | `10-core.sh` | B3 row 21 / decision i | None | Low | OC-PLAN |
| **SQL Server** | **West US** | **REUSE** | Existing tier | `20-sql.sh` | Existing portal DB; no migration | Existing cost | **Medium** (shared DB) | OC-PLAN |
| **SQL Database** | **West US** | **REUSE** | Existing SKU | `20-sql.sh` | Existing shared database | Existing cost | **Medium** (schema collision risk) | OC-PLAN |
| **assess schema** | West US SQL | **DB-CHANGE** | Schema + app user only | `scripts/db/create-app-user.sql` | Isolation from portal tables | None | Medium | OC-1B human runs SQL |
| **Blob Storage account** | East US | *(fill at OC-0)* | Standard LRS | `30-blob.sh` | JD file uploads | Usage-based; human estimates at OC-PLAN | Low | OC-0 confirms |
| **jd-files container** | East US | CREATE (private) | — | `30-blob.sh` | Private; no public blob access | Included | Low | OC-0 confirms |
| **AI Foundry resource** | East US | **REUSE** | Existing | `40-ai.sh` | Existing `<AI_RESOURCE>` | Token usage; human estimates at OC-PLAN | Low | OC-1D verifies deployment |
| **GPT-4o deployment** | East US | **REUSE** | Existing capacity | `40-ai.sh` | Used by portal; must not conflict | Token usage; human estimates at OC-PLAN | Medium (shared quota) | OC-1D |
| **Communication Services** | East US | *(fill at OC-0)* | — | `50-email.sh` | Candidate invitation emails | Usage-based; human estimates at OC-PLAN | Low | OC-0 confirms |
| **Email / Azure-managed domain** | East US | CREATE (if new) | Azure-managed | `50-email.sh` | Decision h: no custom DNS | Free with ACS | Low | OC-1E |
| **Container Registry (ACR)** | East US | *(fill at OC-0)* | Basic SKU | `60-registry.sh` | Store assess-api image | Fixed/usage cost; human estimates at OC-PLAN | Low | OC-0 confirms |
| **Container Apps environment** | East US | REUSE (if exists) | Existing | `70-assess-api.sh` | Portal uses this env; zero-touch | Shared cost | Medium (shared env) | OC-0 confirms |
| **assess-api container app** | East US | **CREATE** | 0.25 vCPU / 0.5 GiB, 1 replica | `70-assess-api.sh` | New backend API; decision l | Usage-based; human estimates at OC-PLAN | Low | OC-PLAN |
| **User-assigned managed identity** | East US | **CREATE** | — | `70-assess-api.sh` | OIDC deploy; no stored secrets | Free | Low | OC-1F |
| **AcrPull role assignment** | Registry | **IAM-CHANGE** | AcrPull on registry scope | `70-assess-api.sh` | App can pull its image | None | Low | OC-1F |
| **Contributor role assignment** | assess-api app | **IAM-CHANGE** | Contributor on app resource only (B3 row 29) | `70-assess-api.sh` | CI/CD deploy | Low | AZ-012 (low confidence) | OC-1F |
| **GitHub OIDC federated credential** | — | **IAM-CHANGE** | `repo:Siddharajparkar/We_Select-:ref:refs/heads/main` | `70-assess-api.sh` | Keyless deploy from GitHub Actions | Free | Low | OC-1F |

---

## Cost estimate (human fills from Azure Pricing Calculator)

| Line item | Estimated monthly cost |
|---|---|
| assess-api container (0.25 vCPU / 0.5 GiB, 1 replica, East US) | *(fill from Azure Pricing Calculator at OC-PLAN)* |
| ACR Basic | *(fill from Azure Pricing Calculator at OC-PLAN)* |
| Blob Storage (Standard LRS, East US) | *(fill from Azure Pricing Calculator at OC-PLAN)* |
| ACS email (usage estimate filled at OC-PLAN) | *(fill from Azure Pricing Calculator at OC-PLAN)* |
| GPT-4o token usage | *(fill from Azure Pricing Calculator at OC-PLAN)* |
| Log Analytics + Application Insights | *(fill from Azure Pricing Calculator at OC-PLAN)* |
| **Total (new backend only)** | *(fill at OC-PLAN)* |
| **Total (whole subscription including portal)** | *(fill at OC-PLAN — answers Q1)* |

---

## What is NOT touched

The following resources belong to the existing Assessment Portal and will **never** be modified, migrated, or deleted:

- Portal container app(s) and their revisions
- Portal web container (`assess-web` or equivalent)
- Portal application settings and secrets
- `dbo` schema tables in the shared SQL database
- AI Foundry resource configuration (only the existing GPT-4o deployment is used, read-only)
- Log Analytics workspace and Application Insights (reused; no configuration change)
- Any user accounts, role assignments, or access policies not listed above

---

## Teardown (if this project is cancelled)

Resources created by this plan can be identified by tag `project=ai-assessment` (all CREATE scripts add this tag). To remove them without affecting the portal, delete only the tagged resources listed in this plan.

---

## Latency note

`assess-api` (East US) queries the SQL database (West US). The actual round-trip is unverified until the human runs the probe at OC-1H; the probe warns above 150 ms. Background jobs handle all AI and email work asynchronously; only fast SQL queries occur in the request path.

---

## Office checkpoint order

```
OC-0   → Run inventory.sh (read-only); paste output to agent → fills this plan
OC-PLAN→ Human reviews this plan, fills cost estimates, writes sign-off
OC-1A  → Run 10-core.sh (DRY_RUN=0): core infra + budget
OC-1B  → Run scripts/db/create-app-user.sql in Portal Query Editor
OC-1C  → Run 30-blob.sh (DRY_RUN=0): blob storage + jd-files container
OC-1D  → Run 40-ai.sh (DRY_RUN=0): verify AI resource + deployment
OC-1E  → Run 50-email.sh (DRY_RUN=0): ACS + email domain
OC-1F  → Run 70-assess-api.sh (DRY_RUN=0): app + identity + roles + OIDC
OC-1G  → Set GitHub secrets (AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID)
OC-3   → First real deploy (phase/03-container-pipeline merged to main, deploy enabled)
OC-1H  → Run probe all (inside the container after OC-3)
OC-2   → Verify 13 tables in assess schema; dbo tables unchanged
```
