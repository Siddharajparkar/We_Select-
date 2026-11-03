# Provisioning Plan — AI Candidate Assessment Platform Backend

> **Maintained by the agent.** Human fills cost estimates and writes the sign-off.
> **Public repository** — every real Azure name, ID, subscription ID, hostname, email, or key must be replaced with `<placeholder>` here. Real values live only in your local notes and Cloud Shell variables.
>
> See `docs/OFFICE_CONNECTION_AND_TESTING_GUIDE.md` for how to run each step.
> See `docs/UNVERIFIED_AZURE_LEDGER.md` for all Azure assumptions that need office verification.
>
> OC-0 update (2026-11-03, user-reported; current personal-account access context): the user reports using a personal Azure account, confirms control of the selected subscription, and accepts a $50/month backend cap. Windows PowerShell Azure CLI output showed the selected subscription enabled and one resource group in East US; listed resources included SQL in West US, AI Services accounts in East US and North Central US, Log Analytics and Application Insights in North Central US, and Communication Services (global). Storage and ACR list commands returned no rows. Provider queries reported `Microsoft.App` and `Microsoft.ContainerRegistry` as `NotRegistered`; `Microsoft.OperationalInsights`, `Microsoft.Sql`, `Microsoft.Storage`, `Microsoft.CognitiveServices`, `Microsoft.Communication`, and `Microsoft.Insights` as `Registered`. Because the ACR provider is unregistered, an empty ACR result does not establish that no registry exists. The Container Apps environment/apps could not be enumerated. These are sanitized owner-reported results, not independently verified. Full SQL object inventory, Phi ownership/API/pricing, ACS Email linkage, budget scope/alerts, and resource reuse suitability remain unresolved. The prior sign-off is superseded because this account/access context and provider-registration scope were not covered by its review. **No provider registration or provisioning is currently approved.** Since the two blocked inventories prevent closing OC-0, the first proposed approval stage is limited to conditionally registering `Microsoft.App` and `Microsoft.ContainerRegistry` if still unregistered, followed only by read-only ACR/Container Apps inventory. No service/resource provisioning is included in that stage; after re-inventory, update this plan and obtain separate fresh approval before any provisioning.

> AI update (2026-11-03, user-reported): Phi-4-mini-instruct endpoint path is `/openai/v1/chat/completions`; reported limits are 20,000 tokens/minute and 20 requests/minute. The full endpoint hostname is intentionally not recorded in this public repository. This confirms selecting API style `v1`, but endpoint authentication, full request/response compatibility, quota behavior, and prices still require portal verification. The user accepts the suggested non-AI pilot allowances below for planning; they are not Azure price quotes.

---

## Sign-off block

> ⚠️ The previous approval is superseded by the changed Azure account/access context. The first fresh approval, if added by the human and account owner on `main`, must be limited to conditional registration of the two named providers and read-only inventory. No service/resource provisioning is included. After re-inventory, this line must be superseded again and separately approved before service/resource changes.
> The provisioning scripts check only for an approval line; they do not bind approval to a subscription. Do not run them against a different subscription until this plan is freshly reviewed and approved.

```
SIGN-OFF: APPROVED by SS and SS on 2026-11-03
```

*(Only the human reviewer and account owner may write an approval line after reviewing the exact scope of that stage. The first stage is limited to conditional provider registration and read-only inventory; it does not approve provisioning. A separate final approval requires completed OC-0 evidence, resource scope, provider states, and cost/budget assumptions.)*

---

## Open questions (answer before sign-off)

| # | Question | Answer |
|---|---|---|
| Q1 | What is the budget scope and cost baseline? | User-confirmed backend-only ceiling: $50/month. The user reports a $50 budget exists; its Azure scope and thresholds are unverified. Month-to-date spend is deferred; a previous-month figure of about $50 was reported without confirmed scope. Owner must verify the budget scope and accept cost estimates before sign-off. |
| Q2 | Does a suitable existing Container Apps environment exist, and where? | **Unresolved:** the current personal-account CLI query reports `Microsoft.App` as `NotRegistered`, so the environment/apps could not be enumerated. Proposed registration is a subscription-level change; after fresh plan approval, register only if still unregistered and repeat read-only inventory before deciding REUSE/CREATE. |
| Q3 | Does an existing Container Registry (ACR) already exist? | **Unresolved:** `az acr list` returned no rows while `Microsoft.ContainerRegistry` is `NotRegistered`; that result does not establish absence. Proposed registration is a subscription-level change; after fresh plan approval, register only if still unregistered and repeat read-only inventory before deciding REUSE/CREATE. |
| Q4 | What exists for Communication Services and Email? | User reports the Communication Services resource exists; Email Communication Services/domain is not created. Confirm the exact approved Email service/domain plan before CREATE. |
| Q5 | Does an existing storage account/container suitable for private JD files exist? | The current personal-account storage list returned no rows while `Microsoft.Storage` is reported `Registered`. Confirm the intended subscription/resource scope and verify individually before selecting CREATE. |
| Q6 | Which AI account and Microsoft Phi deployment may this backend use? | Earlier user-provided output reported a North Central US Phi-4-mini-instruct deployment, version 1, `GlobalStandard`, capacity 20. User reports Serverless API / pay-as-you-go, `/openai/v1/chat/completions`, 20,000 tokens/minute and 20 requests/minute. Reverify the intended deployment in the current account and confirm ownership, auth/request/response support, pricing, quotas, and shared-resource impact before live use. The real hostname and resource identifiers are not recorded here. |
| Q7 | Are the discovered Log Analytics workspace and Application Insights suitable for reuse? | User reports both providers are registered. If the unlabeled resource tables are in the guide command order, Log Analytics and Application Insights are in North Central US; confirm resource identity, ownership, workspace association, and suitability in the portal. |
| Q8 | Is the target SQL database correct and approved for the new schema? | Earlier user-provided SQL metadata reports General Purpose, `GP_S_Gen5_2`, compatibility 170; the displayed schemas did not include `assess`. Reverify the target database in the current account and complete the full table/index inventory before deciding whether any objects conflict. Confirm the target and DB-CHANGE with its owner before proceeding. |
| Q9 | What is the actual cost and is the $50 budget backend-only in Azure? | User accepts the provisional non-AI allowances below for planning ($37/month at the selected values). Phi usage/prices are unknown, leaving at most $13/month at that baseline before the $50 ceiling is exceeded. Budget scope/thresholds and month-to-date spend remain unverified; do not claim a complete cost estimate. |

---

## Resource plan

Pre-filled from the decision record (B3 rows 21–34). OC-0 fills the `Mode` and actual resource names.

| Resource | Region | Mode | SKU / size | Script | Reason | Cost driver | Risk | Needs approval |
|---|---|---|---|---|---|---|---|---|
| **Log Analytics workspace** | North Central US (discovered; target suitability unresolved) | REUSE candidate | Existing; reported 30-day retention | `10-core.sh` | Telemetry sink for App Insights | Usage-based; owner estimates at OC-PLAN | Medium (region/ownership) | OC-0 owner confirms |
| **Application Insights** | North Central US (discovered; target suitability unresolved) | REUSE candidate | Existing workspace-based status to verify | `10-core.sh` | API request logs, error tracking | Usage-based with Log Analytics | Medium (region/association) | OC-0 owner confirms |
| **Resource providers** | Selected subscription | **SUBSCRIPTION-CHANGE; proposed only** | Conditionally register `Microsoft.App` and `Microsoft.ContainerRegistry` if still unregistered | User-run Azure CLI; not run by the agent | Required to enumerate Container Apps and ACR and enable their resource types; registration does not create either resource | No direct charge expected; verify current Azure terms | High (subscription-level change; resource presence remains unknown) | Fresh OC-PLAN approval |
| **Budget alert** | Backend-only scope (Azure scope mechanism unresolved) | VERIFY / CREATE only after scope approval | $50/month; intended alerts at $25/$40/$50 | Portal; `10-core.sh` only if a dedicated backend-only resource-group scope is verified | Decision update 2026-11-03 | No estimate asserted; owner completes cost estimate at OC-PLAN | High (budget must not include unrelated portal spend) | OC-PLAN |
| **SQL Server** | **West US** | **REUSE** | Existing tier | `20-sql.sh` | Existing portal DB; no migration | Existing cost | **Medium** (shared DB) | OC-PLAN |
| **SQL Database** | **West US** | **REUSE candidate** | User-reported General Purpose, `GP_S_Gen5_2`; compatibility 170 | `20-sql.sh` | Existing database; target identity and full object inventory must be confirmed | Existing cost; baseline deferred | **Medium** (shared database target must be confirmed) | OC-PLAN |
| **assess schema** | West US SQL | **DB-CHANGE** | Schema + app user only | `scripts/db/create-app-user.sql` | Isolation from portal tables | None | Medium | OC-1B human runs SQL |
| **Blob Storage account** | *(owner selects after regional review)* | CREATE candidate (no rows returned) | Standard LRS | `30-blob.sh` | JD file uploads | Usage-based; owner estimates at OC-PLAN | Medium (absence/region to confirm) | OC-0 owner confirms |
| **jd-files container** | East US | CREATE (private) | — | `30-blob.sh` | Private; no public blob access | Included | Low | OC-0 confirms |
| **AI Foundry resource / endpoint** | North Central US (user-reported deployment-list result) | REUSE candidate; owner approval pending | User-provided listing: Phi-4-mini-instruct, version 1, `GlobalStandard`, capacity 20. Serverless API / pay-as-you-go, v1 route and 20,000 TPM / 20 RPM are user-reported; verify resource ownership and complete auth/request contract | Azure portal / owner; `40-ai.sh` does not verify this deployment type | User-selected model for generation and marking | Pay-per-token; monthly usage/pricing unresolved | High (account ownership and API compatibility) | OC-1D |
| **Communication Services** | Global (resource reported present) | REUSE candidate | Existing resource; verify approved Email linkage | `50-email.sh` | Candidate invitation emails | Usage-based; owner estimates at OC-PLAN | Medium (service/domain not ready) | OC-1E owner confirms |
| **Email / Azure-managed domain** | Unresolved | CREATE candidate (not present per user) | Azure-managed; exact service/domain requirements to verify | `50-email.sh` | Decision h: no custom DNS | Usage-based; owner estimates at OC-PLAN | Medium | OC-1E |
| **Container Registry (ACR)** | *(owner selects after regional review)* | **UNRESOLVED; inventory blocked by unregistered provider** | Basic only if CREATE is later approved | `60-registry.sh` | Store assess-api image | Fixed/usage cost; owner estimates at OC-PLAN | High (empty list is inconclusive until provider registration and re-query) | OC-0, then fresh OC-PLAN |
| **Container Apps environment** | Unresolved | **UNRESOLVED; inventory blocked by unregistered provider** | Reuse existing if suitable; create only if absent and separately approved | `70-assess-api.sh` | Host only `assess-api`; never touch portal apps | Shared cost; owner estimates at OC-PLAN | High (provider/region/shared environment) | OC-0, then fresh OC-PLAN |
| **assess-api container app** | East US | **CREATE** | 0.25 vCPU / 0.5 GiB, 1 replica | `70-assess-api.sh` | New backend API; decision l | Usage-based; human estimates at OC-PLAN | Low | OC-PLAN |
| **User-assigned managed identity** | Follows approved app region | **CREATE** | — | `70-assess-api.sh` | OIDC deploy; no stored secrets | No estimate asserted | Low | OC-1F |
| **AcrPull role assignment** | Registry | **IAM-CHANGE** | AcrPull on registry scope | `70-assess-api.sh` | App can pull its image | None | Low | OC-1F |
| **Contributor role assignment** | assess-api app | **IAM-CHANGE** | Contributor on app resource only (B3 row 29) | `70-assess-api.sh` | CI/CD deploy | Low | AZ-012 (low confidence) | OC-1F |
| **GitHub OIDC federated credentials** | — | **IAM-CHANGE** | `repo:Siddharajparkar/We_Select-:ref:refs/heads/main` (nightly/rollback) and `repo:Siddharajparkar/We_Select-:environment:production` (deploy job) | `70-assess-api.sh` / owner-approved identity setup | Keyless access from the workflows' actual subjects | Free | Medium (subject must match workflow) | OC-1G |

---

## Cost estimate (provisional pilot scenario; human verifies in Azure Pricing Calculator)

The approved planning ceiling is **$50 USD/month for this backend only**. The user asked to defer actual Cost Analysis baseline review. The reported prior-month amount and existing budget are not verified as backend-only. The figures below are **planning allowances, not a quote or a verified estimate**. They assume a low-volume pilot: one 0.25-vCPU / 0.5-GiB API replica running 730 hours/month in the Consumption plan; one Basic registry; up to 10 GB of hot LRS blobs and 100,000 storage operations/month; up to 200 emails/month; and 1 GB/month of incremental log ingestion with 30-day retention. The user reports Phi-4-mini-instruct Serverless API / pay-as-you-go and a v1 chat-completions route with 20,000 tokens/minute and 20 requests/minute. Verify the exact catalog entry, endpoint auth and request contract, rates, and quota in the portal. The account-level `az cognitiveservices account deployment` checks in `40-ai.sh` do not verify this Serverless API deployment; do not use that script for it.

**Owner-provided preliminary workload:** assessment volume is dynamic; plan for 20 candidates per assessment; question-generation calls per assessment and marking/evaluation calls per candidate are not fixed yet. Therefore, monthly Phi calls and input/output tokens cannot be derived, and the Phi cost remains unestimated until the workload is bounded and the endpoint's rates are confirmed. The reported TPM/RPM are throughput limits, not monthly spend caps. Prices depend on verified rates, region, account offer, and actual usage.

| Line item | Suggested pilot allowance / month | Scenario notes |
|---|---:|---|
| `assess-api` container | **$18** (planning range: $15–$20) | User accepts this planning allowance. 0.25 vCPU / 0.5 GiB, one replica, 730 hours; assume subscription-level free grant may already be consumed by portal. Confirm Consumption plan and environment profile. |
| ACR Basic | **$6** (planning range: $5–$7) | User accepts this planning allowance. One registry, no geo-replication; confirm current regional price and image storage. |
| Blob Storage | **$2** (planning range: $1–$2) | User accepts this planning allowance. Standard, hot, LRS; 10 GB and 100,000 operations. |
| ACS email | **$2** (planning range: $1–$3) | User accepts this planning allowance. Up to 200 emails; verify whether the selected Email service/domain or data transfer adds charges. |
| Microsoft Phi-4-mini-instruct (user-selected) | **Not estimated yet** | Obtain North Central US Serverless API input/output rates. Assessments/month are dynamic, 20 candidates/assessment, and generation/marking calls are not fixed, so monthly token volume is unknown. Reported TPM/RPM limits are not cost caps. |
| Log Analytics + Application Insights | **$7** (planning range: $3–$10) | User accepts this planning allowance. 1 GB/month incremental ingestion and 30-day retention; do not assume shared workspace free allowance is available. |
| Cross-region/network and small miscellaneous usage | **$2** (planning range: $1–$3) | User accepts this planning allowance. Placeholder for low-volume East US to West US traffic; validate actual transfer and related charges. |
| **Non-AI pilot subtotal** | **about $37/month** | User accepts the selected allowances for planning; broad combined range is about **$26–$45/month**. This is not a full project total. At selected values, only about $13 remains under the $50 ceiling for Phi and other overages. |
| **Total including Microsoft Phi** | **Not estimated yet** | Add the model/deployment estimate after the owner confirms the precise Phi deployment and workload. The total may exceed the $50/month ceiling. |
| Existing SQL database and shared AI/monitoring resource base charges | **Not included** | Reuse avoids creating another base resource, but incremental database, model, or monitoring usage can still increase the shared subscription bill. |
| **Whole subscription including the existing portal** | **Not estimated** | Requires owner-authorized Cost Analysis; the user deferred that review. |

**Budget decision:** The user accepts the suggested non-AI allowances as the planning scenario, not as verified Azure prices. The full estimate still cannot be completed until actual regions/SKUs, Phi input/output rates, and monthly workload are entered in the [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/). Aim for a complete estimate of **$40/month or less** to preserve 20% headroom under the $50 ceiling. The current non-AI subtotal alone is about $37, leaving little room for model usage; if the full estimate exceeds the ceiling, reduce usage or revise the architecture with the owner. A budget alert is not a spending cap.

**AI cost guardrail:** the app's `AI_DAILY_TOKEN_CAP` is **200,000 tokens per tenant per day**, not a global monthly spend limit. At 30 days, that permits up to 6 million tokens per tenant, and multiple tenants multiply the exposure. Confirm expected monthly input/output token volume, Phi rates, and an aggregate AI usage limit before relying on the $50 ceiling.

**Budget scope guardrail:** `10-core.sh` creates a resource-group-scoped budget. Do not use that operation unless the signed plan confirms that the entire resource group is backend-only. An Azure budget sends alerts; it does not stop consumption.

---

## What is NOT touched

The following resources belong to the existing Assessment Portal and will **never** be modified, migrated, or deleted:

- Portal container app(s) and their revisions
- Portal web container (`assess-web` or equivalent)
- Portal application settings and secrets
- `dbo` schema tables in the shared SQL database
- AI Foundry resource configuration (use only the owner-approved Microsoft Phi deployment; do not alter shared AI resources)
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
OC-1D  → Verify the Phi Serverless API model/deployment in Foundry portal (do not run 40-ai.sh)
OC-1E  → Run 50-email.sh (DRY_RUN=0): ACS + email domain
OC-1F  → Run 70-assess-api.sh (DRY_RUN=0): app + identity + roles + OIDC
OC-1G  → Set GitHub secrets (AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID)
OC-3   → First real deploy (phase/03-container-pipeline merged to main, deploy enabled)
OC-1H  → Run probe all (inside the container after OC-3)
OC-2   → Verify 13 tables in assess schema; dbo tables unchanged
```
