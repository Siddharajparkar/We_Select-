# Office Azure Connection Guide: Phases 1 to 9

**Current file:** `azure_connection_1to6.md` (draft checklist in the repository root)
**Use it at:** the organisation laptop, in the browser, with **Azure Cloud Shell (Bash)** and the **Azure portal**. No Docker. No local Azure CLI.
**Scope:** short checklist for Azure connections through Phase 9. The maintained [Office Connection and Testing Guide](docs/OFFICE_CONNECTION_AND_TESTING_GUIDE.md) is authoritative for exact commands, current workflow inputs, and safety gates across all phases.
**Companion files:** `docs/OFFICE_CONNECTION_AND_TESTING_GUIDE.md` (all 13 phases, longer), `docs/PROVISIONING_PLAN.md` (the plan you sign), `docs/UNVERIFIED_AZURE_LEDGER.md` (what is still unproven), `docs/prompts/PROMPT_B_ADDENDUM_OFFLINE_AZURE_READY.md`.

> **How this guide differs from the older one.** Every name below (GitHub variables, secret names, file names, the OIDC subject) was checked against what the repository really contains. Where the older guide disagrees with the code, this guide follows the code. The differences are listed in Appendix A. **Read Appendix A before OC-1F.**

> **Read first — this file is a draft companion, not the execution authority.** Use the maintained guide linked above whenever commands or OIDC subjects differ; do not execute stale commands from this file. As of 2026-11-03, OC-0 is incomplete and the provisioning plan is unsigned. No Azure resource or provider may be created, changed, or deleted until the owner-reviewed plan is signed by a human. The current planning cap is $50/month for the backend; the Azure budget scope and thresholds have not been verified.

---

## 0. Golden rules (read aloud before you start)

1. **Nothing is created, changed or deleted in Azure until `docs/PROVISIONING_PLAN.md` contains the human line** `SIGN-OFF: APPROVED by <initials> and <owner initials> on <date>`. Only a human writes it. The scripts refuse to write without it.
2. **Reuse first.** The Assessment Portal already owns the SQL database, AI resources, logs, Application Insights, the registry and the Container Apps environment. The backend is intended to use Microsoft Phi, but the exact model variant, deployment, and API compatibility must be confirmed. We **never** touch the portal's apps, its tables, or shared AI configuration without approval.
3. **We create only:** the Blob storage account and container, Communication Services (email), the `assess-api` Container App, its managed identity, and the budget (and a registry only if the plan says none exists).
4. **No secret ever goes** into the repository, a screenshot, a chat, an email, a ticket, or **any AI tool**. Secrets live in your **password manager** and, once set, in **Container Apps secrets**. Read them into shell variables with `read -rsp`. Never `echo` them.
5. **The repository is public.** Real resource names, subscription and tenant ids, hostnames, emails go only in your **private notes file** (outside the repo). When you report to the team use placeholders: `<RG>`, `<SQL_SERVER>`, `<AI_RESOURCE>`, `<ACR>`.
6. **Budget: $50.00 per month for this backend.** Intended alerts are $25 / $40 / $50; verify the budget scope before relying on it. Container 0.25 vCPU / 0.5 GiB, exactly 1 replica.
7. **Do the checkpoints in order. If a "Proceed when" line is not fully true, stop.** Write down why, and ask.
8. **The commands were written without Azure access.** Most will work as written. A command marked **(confirm)** is likely to need adjusting: run it with `--help`, fix it, and write what you changed in the ledger (without real names).

---

## 1. Status board (copy into your private notes and tick as you go)

| ID | Phase | What gets proven | Status | Date | Evidence kept |
|---|---|---|---|---|---|
| OC-0 | 1 | Read-only discovery, SQL inventory, cost baseline | PENDING | | |
| OC-PLAN | 1 | Plan reviewed and signed by you and the account owner | PENDING | | |
| OC-1A | 1 | Core: environment, registry, logs, Application Insights (reuse), budget | PENDING | | |
| OC-1B | 1/2 | Schema `assess` and least-privilege user in the existing Azure SQL | PENDING | | |
| OC-1C | 1/5 | Private Blob container `jd-files` | PENDING | | |
| OC-1D | 1/6 | Owner-approved Microsoft Phi variant/deployment and endpoint verified | PENDING | | |
| OC-1E | 1 | Communication Services + email domain (for Phase 7) | PENDING | | |
| OC-1F | 1/3 | `assess-api` app, identity, registry access, secrets, settings | PENDING | | |
| OC-1G | 1/3 | GitHub to Azure trust (OIDC) and repository variables | PENDING | | |
| OC-3 | 3 | First real deployment, health, version header, logs | PENDING | | |
| OC-1H | 1 | Probes: config, SQL, Blob, Microsoft Phi, Application Insights, email | PENDING | | |
| OC-2 | 2 | 13 tables in `assess`, portal tables unchanged | PENDING | | |
| OC-4 | 4 | Login, tenants, users live | PENDING | | |
| OC-5 | 5 | Assessments and PDF upload to Blob live | PENDING | | |
| OC-6 | 6 | Real Microsoft Phi generation, review, approve live | PENDING | | |
| OC-7 | 7 | Real invitation email arrives | PENDING | | |
| OC-8 | 8 | Candidate exam with real token, timer and auto-submit | PENDING | | |
| OC-9 | 9 | Real AI marking and review | PENDING | | |

**Run order (not the phase order):**
`OC-0 → OC-PLAN → OC-1A → 1B → 1C → 1D → 1E → 1F → 1G → (merge to main) → OC-3 → OC-1H → OC-2 → OC-4 → OC-5 → OC-6 → OC-7 → OC-8 → OC-9`
Reason: the probe tool and the database migrations both live inside the image that OC-3 deploys.

**Current OC-0 status (2026-11-03; user-reported):** SQL database is reported empty and `assess` absent; the Communication Services resource exists but Email/domain does not; AI and monitoring resources were returned by CLI queries; ACR and Storage returned no rows; Container Apps could not be queried because `Microsoft.App` is unregistered. Some CLI output came from the development laptop, so all CLI inventory results are provisional and must be re-run from the authorized organization Cloud Shell or portal. Cost Analysis is deferred; the $50/month backend cap is reported, but actual budget scope/thresholds are unverified. These are not approvals to create or change anything.

### What can wait while something else is blocked
| Blocked | You can still do | You cannot do |
|---|---|---|
| Sign-off | OC-0 only | anything that writes to Azure |
| Schema/user permission on the shared database | OC-1A, 1C, 1D, 1E | OC-1F onward (everything needs SQL) |
| Phi deployment, route, key, or quota | everything up to OC-5 | OC-6 and the foundry probe |
| Email domain linking | everything except email | the email probe (Phase 7 later) |
| GitHub OIDC not allowed | manual deploy path B in OC-3 | automatic deploys (Phase 12) |
| Permission to assign roles | the owner runs those few commands | nothing else is blocked once they do |

---

## 2. Before you leave home (do this on your own computer)

### 2.1 Get the code into GitHub and green
The Cloud Shell clones the repository, and the pipeline deploys from `main`, so phases 3 to 6 must be on GitHub first. (Pushing is done by you from your own machine; it was not possible from the AI session.)

```bash
git clone https://github.com/Siddharajparkar/We_Select-.git && cd We_Select-
git fetch /path/to/assess-platform-phases-0-6.bundle phase/06-ai-generation:phase/06-ai-generation
git push -u origin phase/06-ai-generation
```
Then open **one pull request** `phase/06-ai-generation` into `main` titled "Phases 3 to 6", and wait for the checks **`fast`**, **`container`**, **`security`** to be green. The `deploy` job is skipped on purpose (it needs the variable `AZURE_DEPLOY_ENABLED=true`, which you set only in OC-1G).

* Why one PR and not four: the phases are stacked commits, and the earliest commit needs the lint fix that sits on top (ruff changed its formatting rules). Splitting would turn the first PR red.
* **Do not merge until the checks are green.** The `container` job is the first real proof of the SQL Server code (the T-SQL job claim, the `MERGE` upsert, migration 0003). If it fails, send the log to the team.
* **Do not set `AZURE_DEPLOY_ENABLED` yet.** Merging to `main` with the variable unset deploys nothing.

### 2.2 Prepare a private notes file (not in the repo)
Make a text file `office-notes-PRIVATE.txt` in your password manager or an encrypted note, with the sections: **Names** (from OC-0), **Secrets inventory** (Appendix B, names only, values stay in the password manager), **Answers** (section 3 questions), **Evidence** (command outputs).

### 2.3 Open on the office laptop
This guide, `docs/PROVISIONING_PLAN.md`, `docs/UNVERIFIED_AZURE_LEDGER.md`, the repository on GitHub (to read workflow runs), the Azure portal, and your password manager.

---

## 3. Questions to ask at the office (write the answers in your private notes)

1. Which **subscription** (name and id) and which **resource groups** hold: the Container Apps environment, the registry, Log Analytics, Application Insights, the AI resource, the SQL server?
2. Is there an **Azure Policy** forcing tags/names/private endpoints, or blocking public access on storage or SQL?
3. **Budget:** the approved planning ceiling is **$50.00/month for this backend only**. The user has deferred Cost Analysis; the actual Azure budget scope and thresholds still need verification before sign-off.
4. Who may create a **schema and a database user** inside the shared SQL database, and with which login (Entra admin or SQL admin)?
5. Is any AI key shared with the portal? **Unknown until verified by the owner. Never regenerate or rotate a key during discovery.** What endpoint/API contract does the existing portal use? Do not assume it applies to Phi.
6. May we create an **Entra app registration**? (Not needed: this guide uses a managed identity.)
7. Is **GitHub Actions** allowed to deploy to this subscription with **OIDC**? If not, we use the manual path B in OC-3.
8. Which **mailbox** receives test emails? (Your own office mailbox. Never write it into the repo.)
9. Is there a **corporate proxy / TLS inspection**? (If the browser shows certificate warnings, ask IT. Never disable certificate checks.)
10. Who is the **account owner** who co-signs the plan?

---

## 4. The office environment (no Docker, no local Azure CLI)

| Need | How |
|---|---|
| Run Azure commands | **Azure Cloud Shell, Bash**, opened from the portal. When it asks about storage choose **"No storage account required"**, pick the subscription, Apply. The session is **ephemeral**: files and variables vanish after about 20 minutes idle. |
| Get the repo scripts | `git clone https://github.com/Siddharajparkar/We_Select-.git && cd We_Select-` (public, no login). Re-clone in every session. |
| Variables | Paste the **non-secret variable block** (section 5) at the start of every session. Secrets are re-entered with `read -rsp` from your password manager. |
| Build the image | **GitHub Actions** (preferred). Fallback: `az acr build` (builds inside Azure, no Docker). |
| Live E2E tests | GitHub Actions workflow **`live-e2e`** (manual start), or Python in Cloud Shell. |
| Probes | `az containerapp exec` runs them **inside** the running container (no SQL firewall changes). Fallback: portal, Container App, **Monitoring, Console**. |
| Run T-SQL | **Azure portal, SQL database, Query editor** (sign in as the owner arranged). Adding your IP to the SQL firewall changes the shared server: only with the owner's agreement, and remove it at the end. |

---

## 5. The variable block (non-secret; paste at the start of every Cloud Shell session)

Fill the `<...>` from OC-0. Keep the filled block **only in your private notes**. Names must stay exactly as written.

```bash
# --- where things are (from OC-0) ---
export SUB="<subscription-id>"
export LOC_APP="eastus"
export SUFFIX="<5 lowercase letters/digits you choose, e.g. k3x9q; keep it forever>"

# --- existing resources (REUSE; copy exact names from OC-0) ---
export RG="<resource group of the Container Apps environment; assess-api will live here>"
export RG_SQL="<resource group of the SQL server>"
export RG_ACR="$RG"      # change if the registry is in another group
export RG_MON="$RG"      # change if Log Analytics / Application Insights are elsewhere
export RG_AI="$RG"       # change if the AI resource is elsewhere
export CAE="<Container Apps environment name>"
export ACR="<registry name>"
export LAW="<Log Analytics workspace name>"
export APPI="<Application Insights component name>"
export SQLSRV="<SQL server name>"
export SQLDB="<database name>"
export AIACC="<AI resource name>"
export AI_DEPLOY="<exact Microsoft Phi DEPLOYMENT name, not the model name>"

# --- new resources (CREATE only if the signed plan says so) ---
export API_APP="assess-api"                 # the only container app we create
export IDN="assess-api-identity"            # managed identity used by the app AND by GitHub
export STG="assessstg$SUFFIX"               # lowercase letters/digits, 3-24 chars
export BLOB_CONTAINER="jd-files"
export ACS="assess-acs-$SUFFIX"
export ACS_EMAIL="assess-email-$SUFFIX"
export GH_REPO="Siddharajparkar/We_Select-"  # exact case matters for OIDC
export TAGS="project=ai-assessment env=mvp"

az account set --subscription "$SUB"
az account show -o table
```
**Check:** the table shows the subscription the owner named. If not, stop. (Cloud Shell is already signed in. Do **not** run `az login` with anyone else's account.)

**One-time (only if OC-0 shows a provider `NotRegistered`; this is a subscription-level change, so it needs sign-off):**
```bash
for p in Microsoft.App Microsoft.Communication Microsoft.Storage Microsoft.Insights Microsoft.ManagedIdentity; do
  echo -n "$p: "; az provider show -n "$p" --query registrationState -o tsv; done
# register ONLY the NotRegistered ones:  az provider register --namespace Microsoft.Communication
az extension add --name containerapp --upgrade
```

**Secrets: how to handle them**
```bash
read -rsp "Some secret: " SOME_SECRET; echo      # typed or pasted from the password manager; nothing is echoed
```
Save each generated secret in the password manager **first**, then use it. Variables disappear when the session ends, so do the steps that need a secret in one sitting.

---

## 6. THE CHECKPOINTS

Each has: **Needs, Do, Expect, Test, If it fails, Proceed when.**

---

### OC-0: Read-only discovery (nothing is created or changed)
**Needs:** Cloud Shell open (no storage), repo cloned. Nobody runs anything that creates, changes, deletes or reveals secrets here.

**Do 1: Azure inventory**
```bash
git clone https://github.com/Siddharajparkar/We_Select-.git && cd We_Select-
export RG="<the portal's resource group>"; export RG_SQL="<sql resource group>"
DRY_RUN=0 bash infra/azure/discovery/inventory.sh | tee ../inventory-PRIVATE.txt
```
(`DRY_RUN` defaults to `1` and only prints the commands. `DRY_RUN=0` runs them; they are all `list`/`show`.) Copy the output into your **private notes**. The file lands outside the repo clone, which is what you want. If the script fails, run these (all read-only):
```bash
az group list -o table
az resource list -o table --query "[].{name:name,type:type,rg:resourceGroup,loc:location}"
az containerapp env list -o table
az containerapp list -o table --query "[].{name:name,rg:resourceGroup,external:properties.configuration.ingress.external}"
az acr list -o table
az sql server list -o table
az cognitiveservices account list -o table
az monitor log-analytics workspace list -o table
az monitor app-insights component show -o table
az storage account list -o table
az communication list -o table
az consumption budget list -o table
```
**Never run** `keys list`, `list-key`, `show-connection-string`, `get-shared-keys`, `secret show`, `exec`, or anything with `create`, `update`, `set` or `delete` in this checkpoint.

**Do 2: SQL inventory.** Portal → SQL database → **Query editor**. Paste `infra/azure/discovery/sql-inventory.sql` (read-only: schemas, table names, column counts; no row data). Save the result in your notes. Look for an existing schema `assess` and tables named like ours (`tenants, users, sessions, login_attempts, assessments, questions, participants, attempts, responses, scores, jobs, audit_log, schema_migrations`).

**Do 3: cost status.** Cost Analysis is deferred at the user's request. Do not invent spend. Record the reported $50/month backend cap but leave the actual Azure budget scope and alert thresholds unresolved for owner review before sign-off.

**Do 4: answer sheet (private notes)**
| Item | Answer |
|---|---|
| Resource groups of: environment, registry, Log Analytics, App Insights, AI resource, SQL server | |
| Existing container apps (names only; never touched) | |
| Registry exists? Container Apps environment exists? | |
| SQL tier, serverless / auto-pause? | |
| Schema `assess` already there? Name clashes? | |
| AI deployments: name, model, version, capacity; quota shared with portal? | |
| Existing storage / ACS resources? | |
| Providers not registered | |
| Cost baseline | Deferred by user; month-to-date not checked; previous-month figure reported as about $50 with scope unknown |
| Reported planning ceiling | $50/month, backend-only; Azure budget scope and alert thresholds unverified |
| Policies that could block us | |
| Account owner who co-signs | |

**Do 5: report to the team using placeholders only** (`<RG>`, `<SQL_SERVER>`, `<AI_RESOURCE>`, `<ACR>`): which resources exist (yes/no), regions, SKU classes, clashes, and unresolved budget scope/thresholds. Actual Cost Analysis is deferred; do not invent estimates.

**Test:** `az resource list -o table | wc -l` before and after gives the same number.
**If it fails:** *AuthorizationFailed on a list*: you lack Reader on that group; ask the owner. *Query editor cannot sign in*: ask for the Entra admin login, or let the owner run the T-SQL. *Script not found*: use the fallback commands.

**Proceed when:** the resource answer sheet and SQL inventory are complete and the sanitized report was sent. Cost Analysis is deferred; leave the budget scope and thresholds unresolved for owner review. **Nothing was created or changed.**

---

### OC-PLAN: Review and sign the plan
**Needs:** OC-0 done; the team merged a filled `docs/PROVISIONING_PLAN.md` (placeholders only).

**Before you sign, check that the plan includes these four items that the scripts need but the first plan draft does not list** (ask the team to add them as rows, mode `IAM-CHANGE`):
| Item | Why |
|---|---|
| Role **AcrPush** for the identity `assess-api-identity` on the registry | The pipeline pushes the image. The draft only has AcrPull. |
| Federated credentials for `Siddharajparkar/We_Select-` | Match the workflow subjects exactly: the deploy job uses the `production` environment, while nightly/rollback jobs use the `main` branch subject. Confirm the maintained guide and workflow before sign-off. |
| `az containerapp registry set` for `assess-api` with that identity | Lets the app pull from the registry. |
| The ACS email domain link | Needed before any email can be sent. |

**Do:**
1. For each plan row (REUSE / CREATE / IAM-CHANGE / DB-CHANGE / NONE) check with the owner: the mode is right for what OC-0 found, nothing existing is modified, the cost is believable, the risk is accepted.
2. The plan estimates fit **$50/month for the backend only**; verify the Azure budget scope and thresholds. If either is unclear or estimates exceed the ceiling, **do not sign**.
3. "What is NOT touched" matches your OC-0 notes (portal apps, portal tables, the AI key).
4. When you **and the owner** agree, edit the line from `SIGN-OFF: <not approved>` to exactly:
   `SIGN-OFF: APPROVED by <your initials> and <owner initials> on <YYYY-MM-DD>`
   Do it through a small pull request (`chore/plan-signoff`) and merge it. Only humans write this line.

**Test (fresh clone in Cloud Shell):** `grep -n "^SIGN-OFF: APPROVED by" docs/PROVISIONING_PLAN.md` prints the line.
**If it fails:** someone disagrees with a row → change the row, review again. Never edit a mode to make the plan fit.

**Proceed when:** the line exists on `main` from both people, the grep prints it, and the plan lists nothing outside the agreed scope.

---

### OC-1A: Core resources (reuse), tags, budget
**Needs:** OC-PLAN signed. Variables set.

**Do 1: verify what the plan says to REUSE (read-only)**
```bash
az containerapp env show -n "$CAE" -g "$RG" --query "{name:name,loc:location,state:properties.provisioningState}" -o table
az acr show -n "$ACR" -g "$RG_ACR" --query "{name:name,sku:sku.name,loginServer:loginServer}" -o table
az monitor log-analytics workspace show -g "$RG_MON" -n "$LAW" --query "{name:name,loc:location,retentionDays:retentionInDays}" -o table
az monitor app-insights component show --app "$APPI" -g "$RG_MON" --query "{name:name,loc:location}" -o table
```
**Do 2: create ONLY the rows the signed plan marks CREATE.** Normally all four exist and this step is skipped. If the plan says CREATE for the registry:
```bash
az acr check-name -n "$ACR" -o table
az acr create -g "$RG_ACR" -n "$ACR" --sku Basic --admin-enabled false --tags $TAGS
```
(For logs / Application Insights / the environment use the commands in the older guide, OC-1A, or `MODE_CORE=create DRY_RUN=0 bash infra/azure/10-core.sh`. The script's budget command is **(confirm)**: prefer the portal for the budget.)

**Do 3: the Application Insights connection string** (needed in OC-1F)
```bash
APPINSIGHTS_CS=$(az monitor app-insights component show --app "$APPI" -g "$RG_MON" --query connectionString -o tsv)
```
Save it in the password manager as `appinsights-connection-string` (treat it as a secret).

**Do 4: verify the budget only after the signed plan defines its scope.** The intended backend-only amount is **$50.00/month** with alerts at **$25, $40, and $50**. Do not treat a subscription or shared-resource-group budget as backend-only. The current CLI budget command scopes the entire resource group and is disabled by default; use it only if the signed plan confirms that group is dedicated to this backend. A budget alerts; it does not stop spending.

**Expect:** reused resources show the expected names/regions; anything created shows `Succeeded`.
**Test:** `az resource list --tag project=ai-assessment -o table` lists only what we created. The budget appears under Budgets.
**If it fails:** *provider not registered* → section 5 note. *Policy denied* → give the policy name to the owner. *Not authorised* → you lack Contributor on that group.

**Proceed when:** environment, registry, Log Analytics and Application Insights exist exactly as the plan says, the Application Insights connection string is saved, and the budget with three alerts exists.

---

### OC-1B: Existing Azure SQL: schema `assess` and the app user
**Needs:** OC-1A. A login that may create users and schemas in the database (question 4). **We never create a server or a database.**

**Do 1: verify the database and the network path (read-only)**
```bash
az sql db show -g "$RG_SQL" -s "$SQLSRV" -n "$SQLDB" --query "{status:status,sku:sku.name,tier:sku.tier,loc:location}" -o table
az sql server firewall-rule list -g "$RG_SQL" -s "$SQLSRV" -o table
```
The portal already reaches this server from Container Apps. A rule `AllowAllWindowsAzureIps` (`0.0.0.0` to `0.0.0.0`) means we use the same path and change nothing. **If it does not exist and the plan has no row for it, stop and ask.**

**Do 2: password for the app user.** Generate it and save it in the password manager **now**:
```bash
APP_PW="$(openssl rand -base64 24 | tr -d '/+=')Aa1"
```
(No symbols beyond letters/digits, so the portal editor does not mangle it.)

**Do 3: create the schema and user.** Portal → the database `<SQLDB>` → **Query editor**, sign in as arranged. **Be connected to the application database, not `master`.** Open `scripts/db/create-app-user.sql` from the repo on GitHub, copy it into the editor, replace `<APP_USER_PASSWORD>` with `APP_PW` **in the editor only** (never in the file), and run it. It is safe to run twice. It creates schema `assess`, user `assess_app`, makes the user the schema owner, and grants `CREATE TABLE`. It does **not** add `assess_app` to `db_datareader`, `db_datawriter` or `db_ddladmin`: those roles would expose the portal's tables.

**Do 4: build the connection string** and save it as `database-url`:
```bash
DATABASE_URL="Server=tcp:${SQLSRV}.database.windows.net,1433;Database=${SQLDB};User ID=assess_app;Password=${APP_PW};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30"
```
(The app parses ADO.NET-style strings: `Server=`, `Database=`, `User ID=`, `Password=`, optional `Encrypt`, `TrustServerCertificate`, `Connection Timeout`. If the database is **serverless and paused**, the first connection can take up to a minute: raise `Connection Timeout` to 60 and note it.)

**Expect:** the script prints "Schema [assess] created", "User [assess_app] created", "ownership transferred", "GRANT CREATE TABLE".
**Test:** in the Query editor sign in again with **SQL authentication** as `assess_app` and run:
```sql
SELECT USER_NAME() AS me, SCHEMA_NAME() AS default_schema;
SELECT COUNT(*) AS visible_tables FROM sys.tables;
SELECT TOP 1 * FROM dbo.<any portal table from your OC-0 notes>;
```
Expect `assess_app`, `assess` (or `dbo`: the migrations qualify every name with `assess.`, so the default schema does not matter), `0` tables, and for the third statement **"The SELECT permission was denied"**. If it returns rows, **stop**: the user has too much access.
**If it fails:** *password complexity* → regenerate. *"not supported" / you are in `master`* → switch to the application database. *Cannot sign in as `assess_app`* → regenerate the password without symbols. *Query editor wants to add your IP* → only with the owner's agreement; note the rule name and remove it in OC-2.

**Proceed when:** schema `assess` exists owned by `assess_app`; signing in as `assess_app` works; it sees no portal table and gets permission-denied on a portal table; `database-url` is saved.

---

### OC-1C: Blob Storage (create)
**Needs:** OC-1A. The plan says CREATE (default).

**Do** (uses the account connection string, so it does not depend on extra data-plane roles):
```bash
az storage account create -g "$RG" -n "$STG" -l "$LOC_APP" --sku Standard_LRS --kind StorageV2 \
   --allow-blob-public-access false --min-tls-version TLS1_2 --https-only true --tags $TAGS
BLOB_CS=$(az storage account show-connection-string -g "$RG" -n "$STG" --query connectionString -o tsv)
az storage container create --name "$BLOB_CONTAINER" --connection-string "$BLOB_CS" --public-access off
```
Save `BLOB_CS` as `blob-connection-string`. (The repo script `30-blob.sh` uses `--auth-mode login`, which needs a data-plane role on the account; the commands above avoid that. See Appendix A.)

**Expect:** `"created": true`.
**Test:** `az storage container show --name "$BLOB_CONTAINER" --connection-string "$BLOB_CS" --query properties.publicAccess` prints `null` (private).
**If it fails:** *name invalid* → lowercase letters and digits only, 3 to 24. *Name taken* → change `SUFFIX`. *Public access blocked by policy* → good, keep it off.

**Proceed when:** public access prints `null`, the account carries tag `project=ai-assessment`, and the connection string is saved.

---

### OC-1D: Phi-4-mini-instruct Serverless API (verify before use)
**Needs:** OC-1A and an owner-approved plan. The user reports Phi-4-mini-instruct, Serverless API / pay-as-you-go, North Central US; verify each in the Foundry portal. Do not run `infra/azure/40-ai.sh` for this deployment: it checks Cognitive Services account deployments, not this Serverless API.

In the Foundry portal, confirm the exact catalog model identifier, serverless deployment type, North Central US region, endpoint format, authentication method, request/response API, token usage reporting, quota, and input/output rates. The public pricing list currently labels a Phi-4-mini model; verify the exact deployed identifier rather than assuming it is identical to the name reported.

The current backend adapter expects chat-completions requests, `api-key` authentication, a `model` deployment name, and JSON response mode. Do not guess or set `FOUNDRY_ENDPOINT`, `FOUNDRY_API_STYLE`, or keys until the selected endpoint is confirmed to support this contract. If it does not, stop and update/test the adapter before deployment.

**Proceed when:** the exact model/deployment and cost inputs are confirmed, the adapter supports the endpoint contract, and an authorized small probe passes. Until then, OC-1D is BLOCKED; do not set live AI secrets or call the model.

---

### OC-1E: Communication Services (email), for Phase 7
**Needs:** OC-1A. If OC-0 found an existing ACS resource marked REUSE, only read its domain and connection string.

**Do**
```bash
DATA_LOC="<supported data location, e.g. unitedstates; confirm with: az communication create --help>"
az communication create --name "$ACS" -g "$RG" --location global --data-location "$DATA_LOC" --tags $TAGS
az communication email create --name "$ACS_EMAIL" -g "$RG" --location global --data-location "$DATA_LOC" --tags $TAGS
az communication email domain create --domain-name AzureManagedDomain \
   --email-service-name "$ACS_EMAIL" -g "$RG" --location global --domain-management AzureManaged
```
**Link the domain to the Communication Service: use the portal.** Open the Communication Service `$ACS` → **Email → Domains → Connect domain** → choose the Azure-managed domain. (The repo script `50-email.sh` uses `az communication link-notification-hub`, which is the wrong command for this. See Appendix A.)

**Get the sender and the connection string**
```bash
az communication email domain show --domain-name AzureManagedDomain --email-service-name "$ACS_EMAIL" \
   -g "$RG" --query mailFromSenderDomain -o tsv          # (confirm) else copy "MailFrom" from the portal Domains page
ACS_SENDER="DoNotReply@<the domain printed above>"
ACS_CS=$(az communication list-key --name "$ACS" -g "$RG" --query primaryConnectionString -o tsv)
```
Save `ACS_CS` as `acs-connection-string` and the sender as `acs-sender` (it is stored as a secret by the app config; keep the real address out of the repo).
Azure-managed domains are throttled and mail may land in **spam**; a custom verified domain is a later request to IT.

**Proceed when:** the domain shows as connected to the Communication Service; sender and connection string are saved. (The real send test happens in OC-1H.)

---

### OC-1F: The `assess-api` Container App: identity, registry access, secrets, settings
**Needs:** OC-1A to OC-1E, all secrets in your password manager. **Do this whole checkpoint in one Cloud Shell session.** We create only `assess-api` and its identity; never anything of the portal's.

**Do 0: re-enter secrets into variables** (skip any you still have in this session)
```bash
read -rsp "DATABASE_URL: " DATABASE_URL; echo
read -rsp "FOUNDRY_KEY: " FOUNDRY_KEY; echo
read -rsp "ACS_CS: " ACS_CS; echo
read -rsp "BLOB_CS: " BLOB_CS; echo
read -rsp "APPINSIGHTS_CS: " APPINSIGHTS_CS; echo
read -rp  "FOUNDRY_ENDPOINT (host only): " FOUNDRY_ENDPOINT
read -rp  "ACS_SENDER: " ACS_SENDER
```

**Do 1: the identity and the app (from a public placeholder image)**
```bash
az identity create -g "$RG" -n "$IDN" -l "$LOC_APP" --tags $TAGS
IDN_ID=$(az identity show -g "$RG" -n "$IDN" --query id -o tsv)
IDN_PID=$(az identity show -g "$RG" -n "$IDN" --query principalId -o tsv)

az containerapp create -n "$API_APP" -g "$RG" --environment "$CAE" \
   --image mcr.microsoft.com/k8se/quickstart:latest --target-port 80 --ingress external \
   --cpu 0.25 --memory 0.5Gi --min-replicas 1 --max-replicas 1 \
   --user-assigned "$IDN_ID" --tags $TAGS
```
(External ingress is temporary and intended: there is no frontend yet. The placeholder listens on port 80; the pipeline switches the target port to 8080 before it deploys the real image. Min = max = 1 because the job loop and the exam timer need a running container.)

**Do 2: let the app pull from the registry, and let the pipeline push** (needs permission to assign roles; otherwise the owner runs these two lines)
```bash
ACR_ID=$(az acr show -n "$ACR" -g "$RG_ACR" --query id -o tsv)
az role assignment create --assignee-object-id "$IDN_PID" --assignee-principal-type ServicePrincipal --role AcrPull --scope "$ACR_ID"
az role assignment create --assignee-object-id "$IDN_PID" --assignee-principal-type ServicePrincipal --role AcrPush --scope "$ACR_ID"
# "PrincipalNotFound": wait 30 seconds and run again (up to 6 times)
az containerapp registry set -n "$API_APP" -g "$RG" --server "$ACR.azurecr.io" --identity "$IDN_ID"
```

**Do 3: generate the two app secrets** (save in the password manager first)
```bash
SESSION_SECRET=$(openssl rand -hex 32)
PLATFORM_KEY=$(openssl rand -hex 32)
```
(Production requires both to be at least 32 characters and not start with `dev-only`. Hex 32 bytes is 64 characters. ✔)

**Do 4: store ALL nine secrets in the app** (these exact names; nothing is printed)
```bash
az containerapp secret set -n "$API_APP" -g "$RG" --secrets \
   "database-url=$DATABASE_URL" \
   "session-secret=$SESSION_SECRET" \
   "platform-key=$PLATFORM_KEY" \
   "foundry-endpoint=$FOUNDRY_ENDPOINT" \
   "foundry-key=$FOUNDRY_KEY" \
   "acs-connection-string=$ACS_CS" \
   "acs-sender=$ACS_SENDER" \
   "blob-connection-string=$BLOB_CS" \
   "appinsights-connection-string=$APPINSIGHTS_CS" >/dev/null
```

**Do 5: the settings** (secrets by reference, the rest as plain values). Proceed only after OC-1D confirms an adapter-supported API contract; if none is supported, stop and update/test the adapter before configuring AI:
```bash
API_FQDN=$(az containerapp show -n "$API_APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)
AI_API_STYLE="<verified supported style from OC-1D>"

az containerapp update -n "$API_APP" -g "$RG" --set-env-vars \
  "APP_ENV=production" "PORT=8080" \
  "REPO_BACKEND=sql" "DB_SCHEMA=assess" \
  "AI_MODE=azure" "EMAIL_MODE=azure" "FILES_MODE=azure" \
  "FOUNDRY_API_STYLE=$AI_API_STYLE" "FOUNDRY_DEPLOYMENT=$AI_DEPLOY" \
  "BLOB_CONTAINER=$BLOB_CONTAINER" \
  "APP_BASE_URL=https://$API_FQDN" "API_INTERNAL_URL=https://$API_FQDN" \
  "JOB_LOOP_ENABLED=true" \
  "DATABASE_URL=secretref:database-url" \
  "SESSION_SECRET=secretref:session-secret" \
  "PLATFORM_KEY=secretref:platform-key" \
  "FOUNDRY_ENDPOINT=secretref:foundry-endpoint" \
  "FOUNDRY_KEY=secretref:foundry-key" \
  "ACS_CONNECTION_STRING=secretref:acs-connection-string" \
  "ACS_SENDER=secretref:acs-sender" \
  "BLOB_CONNECTION_STRING=secretref:blob-connection-string" \
  "APPLICATIONINSIGHTS_CONNECTION_STRING=secretref:appinsights-connection-string"
```
Notes: `COOKIE_SECURE` is left unset on purpose (default `true`; production refuses `false`). `FOUNDRY_API_VERSION` is deliberately not set. `APP_BASE_URL` points at the API for now because the frontend does not exist; candidate links will not open a page until it does. The optional limits `AI_MAX_OUTPUT_TOKENS`, `AI_DAILY_TOKEN_CAP`, `DAILY_GENERATION_LIMIT` already default to 2000 / 200000 / 20; set them only to change them.

**Expect:** no errors. The app still runs the placeholder image.
**Test (names only, nothing secret is shown):**
```bash
az containerapp show -n "$API_APP" -g "$RG" --query "properties.template.containers[0].env[].name" -o tsv | sort
az containerapp secret list -n "$API_APP" -g "$RG" --query "[].name" -o tsv | sort        # 9 names
az role assignment list --scope "$ACR_ID" --query "[?principalId=='$IDN_PID'].roleDefinitionName" -o tsv   # AcrPull, AcrPush
az containerapp list -g "$RG" --query "[].name" -o tsv                                      # portal apps unchanged + assess-api
```
**If it fails:** *`--user-assigned` not recognised* → `az extension update -n containerapp`. *Role assignment denied* → the owner runs Do 2. *Secret name rejected* → names are lowercase letters, digits and dashes. *Not enough CPU in the environment* → tell the team.

**Proceed when:** `assess-api` exists and **no other app was created or changed**; `AcrPull` and `AcrPush` are assigned to the identity; the 9 secret names are listed; every variable name above appears in the app settings.

---

### OC-1G: GitHub trust (OIDC, narrow scope) and repository variables
**Needs:** OC-1F. This creates the deploy permission. The plan lists it as `IAM-CHANGE`; the owner may need to run the role lines.

**Do 1: two federated credentials on the same identity.** The deploy job runs with `environment: production`, so the token GitHub presents has the subject `...:environment:production`, **not** `...:ref:refs/heads/main`. Create both (the second is the one the pipeline actually uses; the first covers the nightly and rollback workflows):
```bash
az identity federated-credential create -g "$RG" --identity-name "$IDN" --name gh-main \
   --issuer "https://token.actions.githubusercontent.com" \
   --subject "repo:${GH_REPO}:ref:refs/heads/main" --audiences "api://AzureADTokenExchange"
az identity federated-credential create -g "$RG" --identity-name "$IDN" --name gh-env-production \
   --issuer "https://token.actions.githubusercontent.com" \
   --subject "repo:${GH_REPO}:environment:production" --audiences "api://AzureADTokenExchange"
```
**Do 2: narrow role** on the app only (AcrPull/AcrPush on the registry were given in OC-1F):
```bash
APP_ID=$(az containerapp show -n "$API_APP" -g "$RG" --query id -o tsv)
az role assignment create --assignee-object-id "$IDN_PID" --assignee-principal-type ServicePrincipal --role Contributor --scope "$APP_ID"
```
Do not grant anything on the resource group or on the portal's apps. **Widen only if the first deploy fails with `AuthorizationFailed`, and only as the error says** (for example read on the environment). Record any widening in the ledger and the plan.

**Do 3: GitHub secrets and variables** (repository → Settings → Secrets and variables → Actions). Because the repository is public, ids go in **secrets**, never in the workflow log.
| Kind | Name | Value |
|---|---|---|
| Secret | `AZURE_CLIENT_ID` | `az identity show -g "$RG" -n "$IDN" --query clientId -o tsv` |
| Secret | `AZURE_TENANT_ID` | `az account show --query tenantId -o tsv` |
| Secret | `AZURE_SUBSCRIPTION_ID` | `$SUB` |
| Variable | `AZURE_RESOURCE_GROUP` | `$RG` |
| Variable | `AZURE_ACR_NAME` | `$ACR` |
| Variable | `AZURE_DEPLOY_ENABLED` | leave **unset** until OC-3 |

(These are the names the workflows read. The older guide's `ACR_NAME`, `RG_NAME`, `API_APP_NAME`, `API_URL` are **not** used by any workflow.)

**Do 4: the GitHub environment.** Repository → Settings → Environments. Create **`production`** now if it does not exist (GitHub also creates it on first use). A required reviewer is optional.

**If it fails later:** *`AADSTS70021` / "No matching federated identity record"* → the subject did not match. The deploy job uses `repo:Siddharajparkar/We_Select-:environment:production`; nightly/rollback use the `main` branch subject. Confirm the exact subject in the maintained guide and workflow before use (case-sensitive). *Rename or move of the repo* → create new credentials for the new name.

**Proceed when:** both federated credentials exist; the identity has `Contributor` on the `assess-api` app only plus `AcrPush` on the registry; the three secrets and two variables are set; the `production` environment exists.

---

### (Merge) Make the pipeline deploy
1. Make sure the "Phases 3 to 6" pull request is green (section 2.1) and merge it into `main`.
2. Repository → Settings → Secrets and variables → Actions → Variables: set **`AZURE_DEPLOY_ENABLED` = `true`**.
3. Trigger a deploy: push any small commit to `main` (for example a docs change through a pull request), or re-run the latest `deploy` workflow run on `main`. The `deploy` job only runs for a push to `main` while the variable is `true`.

---

### OC-3: First real deployment (Phase 3)
**Needs:** OC-PLAN signed, OC-1A to OC-1G, the code on `main`.

#### Path A: GitHub Actions (preferred)
Open the repository → **Actions** → the run for your push to `main`. Jobs: `fast` → `container` → `security` → `deploy`.
The `deploy` job does, in order: Azure login (OIDC) → records the current image → sets ingress target port **8080** → logs in to the registry, **builds on the GitHub runner** and pushes `assess-api:<commit sha>` → `az containerapp update --image ... --set-env-vars GIT_SHA=<sha>` → resolves the URL → runs `scripts/e2e/smoke.sh` (health must be `{"status":"ok"}` and `x-app-version` must equal the commit sha, up to 120 s) → if the smoke fails, **rolls back** to the previous image.
**Expect:** all green; only the app `assess-api` changed.

#### Path B: manual (Actions blocked or failing). Run from the cloned repo in Cloud Shell:
```bash
SHA=$(git rev-parse HEAD)
az acr build --registry "$ACR" --image "assess-api:$SHA" --build-arg GIT_SHA="$SHA" ./api
az containerapp ingress update -n "$API_APP" -g "$RG" --target-port 8080
az containerapp update -n "$API_APP" -g "$RG" --image "$ACR.azurecr.io/assess-api:$SHA" --set-env-vars "GIT_SHA=$SHA"
```
(`az acr build` builds inside Azure, no local Docker.)

#### Probes and size, once (both paths)
The real image needs health probes. Make a **temporary copy** of the YAML with the real image and apply it:
```bash
CUR_IMAGE=$(az containerapp show -n "$API_APP" -g "$RG" --query "properties.template.containers[0].image" -o tsv)
sed -e "s|<ACR>.azurecr.io/assess-api:<GIT_SHA>|$CUR_IMAGE|" \
    -e "s|<AI_DEPLOYMENT_NAME>|$AI_DEPLOY|" \
    infra/azure/assess-api.containerapp.yaml > /tmp/assess-api.yaml
az containerapp update -n "$API_APP" -g "$RG" --yaml /tmp/assess-api.yaml            # (confirm) AZ-020
rm /tmp/assess-api.yaml
```
The YAML has an `<AI_DEPLOYMENT_NAME>` placeholder and may replace the whole environment list. **Afterwards re-run the `az containerapp update ... --set-env-vars` command from OC-1F Do 5** (it is idempotent) so `FOUNDRY_DEPLOYMENT` is your real deployment name and `APP_BASE_URL`, `API_INTERNAL_URL`, `BLOB_CONTAINER`, `JOB_LOOP_ENABLED` are present. Then repeat the four listings of OC-1F Test. If the CLI rejects the YAML, set the probes in the portal instead: Container App → Application → Containers → **Health probes**: Startup, Readiness, Liveness on path `/api/v1/health`, port 8080; Startup allowed 60 s (migrations run at start).

**Test (both paths)**
```bash
API_FQDN=$(az containerapp show -n "$API_APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)
curl -i "https://$API_FQDN/api/v1/health"
az containerapp revision list -n "$API_APP" -g "$RG" -o table
az containerapp logs show -n "$API_APP" -g "$RG" --tail 100
az monitor app-insights query --app "$APPI" -g "$RG_MON" --analytics-query "requests | take 5"
```
**Expect:** `HTTP/2 200`, body `{"status":"ok"}`, header `x-app-version: <the commit sha>`; newest revision `Running`; the logs show `migrations applied` and the app start; Application Insights returns request rows within about 5 minutes. Also `curl -i https://$API_FQDN/api/v1/docs` must be **404** (docs are off in production).

**If it fails**
- *Revision stuck `Activating`/`Failed`*: target port not 8080, a failing probe, a missing secret, or a migration error. Read `az containerapp logs show -n "$API_APP" -g "$RG" --type system` and `--type console --tail 100`.
- *Startup fails with `ConfigError`*: the message lists the exact setting (production refuses fakes, memory repository, placeholder secrets, secrets under 32 characters).
- *Image pull `unauthorized`*: registry not set on the app or `AcrPull` missing (OC-1F Do 2).
- *Push `unauthorized` in the pipeline*: `AcrPush` missing (OC-1F Do 2).
- *`azure/login` fails `AADSTS70021`*: federated subject mismatch (OC-1G Do 1).
- *Login to Azure OK but `AuthorizationFailed` on a `containerapp` command*: widen only as the error says (OC-1G).
- *Health OK but an old version header*: traffic is still on the previous revision.
- *Smoke fails and the pipeline rolled back*: expected behaviour; read the failing step, fix, push again.
**Cost note:** check Cost Management (tag `project=ai-assessment`) the next day for the real running cost.

**Proceed when:** `/api/v1/health` returns `200 {"status":"ok"}`, `x-app-version` equals the deployed commit, the newest revision is `Running`, the logs show migrations applied, Application Insights returned `requests` rows, and `/api/v1/docs` is 404. For path A the smoke step was green.

---

### OC-1H: Probes (prove every service)
**Needs:** OC-3 (the probe tool is inside the image).

**Do** (runs inside the container, so no SQL firewall change is needed):
```bash
az containerapp exec -n "$API_APP" -g "$RG" --command "python -m app.tools.probe config"
az containerapp exec -n "$API_APP" -g "$RG" --command "python -m app.tools.probe all"
# email is NEVER part of 'all': send one real test mail to your own mailbox
az containerapp exec -n "$API_APP" -g "$RG" --command "python -m app.tools.probe acs --to <your office mailbox>"
```
If `exec` is not usable in Cloud Shell: portal → Container App → **Monitoring → Console**, pick the container, run the same commands.

**Expect (shape):**
```
PROBE CONFIG  PASS  ...ms  N vars present
PROBE SQL     PASS  ...    connected, schema assess ok, dbo not readable, avg_rtt=<n> ms
PROBE BLOB    PASS  ...    put/get/delete ok, anonymous access denied
PROBE FOUNDRY PASS  ...    HTTP 200; tokens=<n>; style=<verified supported style>
PROBE INSIGHTS PASS ...    marker=<id>
PROBE ALL PASS (5 passed, 0 failed, 0 skipped)
```
The SQL line includes the average round trip of 10 `SELECT 1` calls. The database is in West US and the app in East US, so tens of milliseconds are normal; **above 150 ms prints WARN**: write the number in the ledger and tell the team (it is not a failure by itself). The probe masks secrets by design.

Application Insights check (wait up to 5 minutes):
```bash
az monitor app-insights query --app "$APPI" -g "$RG_MON" --analytics-query "traces | where message has '<marker from the probe>' | take 5"
```
For email: the message must arrive in your mailbox (check spam).

**If it fails:** each line names the failing service. `config` FAIL lists the exact missing variables; the probe requires `DATABASE_URL, SESSION_SECRET, PLATFORM_KEY, REPO_BACKEND, FILES_MODE, AI_MODE, EMAIL_MODE, BLOB_CONNECTION_STRING, BLOB_CONTAINER, APP_BASE_URL, API_INTERNAL_URL` plus `FOUNDRY_*` and `ACS_*` in azure mode. `sql` FAIL → wrong `database-url`, firewall, permissions. `blob` FAIL → wrong connection string or public access policy. For `foundry`, stop on any error and verify the owner-approved Phi Serverless API endpoint/auth/API contract; do not switch API styles or keys by guess. `acs` FAIL → `DomainNotLinked`/`Unauthorized` means the domain link (OC-1E) or the connection string.

**Proceed when:** `PROBE ALL PASS` for config, sql, blob, foundry and insights; the SQL round-trip time is written down; the **test email arrived**; the Application Insights query returned the marker. (If foundry or email fails only for quota/approval, mark BLOCKED.)

---

### OC-2: Database schema on Azure SQL
**Needs:** OC-1B and OC-3 (migrations run when the container starts).

**Do:** nothing extra. To check by hand, Portal → Query editor. Sign in as `assess_app` for the first block and as the **owner's admin login** for the second (the app user cannot see the portal's tables):
```sql
-- as assess_app
SELECT COUNT(*) AS tables_found FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'assess' AND TABLE_TYPE = 'BASE TABLE';
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'assess' AND TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME;
SELECT version, name, applied_at FROM assess.schema_migrations ORDER BY version;
```
```sql
-- as the owner's admin login: compare with the OC-0 inventory
SELECT COUNT(*) AS dbo_tables FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'dbo' AND TABLE_TYPE = 'BASE TABLE';
SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA <> 'assess' AND TABLE_TYPE = 'BASE TABLE' ORDER BY 1, 2;
```
**Expect:** the app tables: `assessments, attempts, audit_log, jobs, login_attempts, participants, questions, responses, schema_migrations, scores, sessions, tenants, users` (**13 tables**: 12 domain tables plus `schema_migrations`; `tables_found` must print 13). `schema_migrations` lists `0001_init`, `0002_sessions_last_seen`, `0003_jobs_questions_ai` once each. The second block equals your OC-0 inventory exactly.
**Test:** restart the app (`az containerapp revision restart -n "$API_APP" -g "$RG" --revision <name>`) and run the first block again: nothing changes (migrations are idempotent).
**If it fails:** *no tables* → the container did not reach the database or crashed: `az containerapp logs show ... --tail 100`. *Permission denied creating tables* → tell the team; the owner may grant exactly the permission named in the error; record it (AZ-008). *Login failed for `assess_app`* → wrong password in `database-url`: `ALTER USER assess_app WITH PASSWORD = '<new>'` and update the secret. *A table appeared in `dbo`* → **stop and report at once**.
**Remove** any temporary SQL firewall rule **you** added (`az sql server firewall-rule list ...`); never delete the portal's rules.

**Proceed when:** exactly 13 tables exist in `assess` with the names above, `schema_migrations` lists every migration once, a restart changes nothing, and everything outside `assess` equals OC-0.

---

### OC-4: Login, tenants and users live (Phase 4)
**Needs:** OC-3, OC-2.

**Do:** create two throwaway test companies (strong passwords from your password manager):
```bash
API="https://$(az containerapp show -n "$API_APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
read -rsp "PLATFORM_KEY: " PLATFORM_KEY; echo
read -rsp "Password A: " PW_A; echo
read -rsp "Password B: " PW_B; echo
for t in A B; do
  pw=PW_$t
  curl -sS -X POST "$API/api/v1/platform/tenants" -H "X-Platform-Key: $PLATFORM_KEY" -H "Content-Type: application/json" \
    -d "{\"name\":\"E2E-$t\",\"adminName\":\"E2E $t Admin\",\"adminEmail\":\"e2e-$(echo $t | tr A-Z a-z)@example.com\",\"password\":\"${!pw}\"}"; echo
done
```
Each returns `201` with `tenantId` and `adminUserId`. Create the GitHub **secrets** `E2E_PLATFORM_KEY`, `E2E_A_EMAIL`, `E2E_A_PASSWORD`, `E2E_B_EMAIL`, `E2E_B_PASSWORD`.

**Test:** GitHub → Actions → **Live E2E Tests (Azure)** → Run workflow: `base_url=https://<API_FQDN>`, `upto_phase=4`, `with_ai=false`, `with_email=false`, `expected_version=<deployed sha>`. (No Actions? In Cloud Shell: `pip install httpx` then `E2E_PLATFORM_KEY=... E2E_A_EMAIL=... python scripts/e2e/run.py --target azure --base-url "$API" --upto 4`. Set the five `E2E_*` variables with `read -rsp` first.)
**Expect:** every check `PASS`: health, wrong platform key rejected, login both tenants, `/auth/me`, cookie `sid` has `HttpOnly; Secure; SameSite=Lax`, tenant A cannot see tenant B (404), logout, lockout.
**Manual double check:** `curl -i -X POST "$API/api/v1/auth/login" -H "Content-Type: application/json" -d '{"email":"e2e-a@example.com","password":"<A>"}'` and read `Set-Cookie`.
**If it fails:** *401 on the platform call* → wrong key. *Cookie lacks `Secure`* → `COOKIE_SECURE` is not true (production refuses false; check the app settings). *409 EMAIL_EXISTS* → the tenant exists; reuse it. *429* → rate limit/lockout; wait 10 minutes.

**Proceed when:** every live check up to phase 4 prints `PASS`, the cookie flags are right, tenant A cannot read tenant B, and the E2E credentials are stored as GitHub secrets.

---

### OC-5: Assessments and PDF upload to Azure Blob (Phase 5)
**Needs:** OC-4, OC-1C.
**Test:** run `live-e2e` with `upto_phase=5`.
**Expect:** create an assessment, upload a real PDF job description (≤ 2 MB, text-based), the list shows it, tenant B gets 404 for tenant A's assessment, delete removes it.
**Verify in Azure:**
```bash
read -rsp "BLOB_CS: " BLOB_CS; echo
az storage blob list --container-name "$BLOB_CONTAINER" --connection-string "$BLOB_CS" --prefix "<tenantId of E2E-A>/" -o table
```
During the test you see `<tenantId>/<assessmentId>/<file>`; after the delete step it is gone. Check the stored text in SQL (Query editor, owner login or `assess_app`):
```sql
SELECT TOP 3 id, LEN(job_description) AS jd_chars FROM assess.assessments ORDER BY created_at DESC;
```
**If it fails:** *500 on upload* → check logs for a Blob authentication error: the `blob-connection-string` secret may be wrong. *`FILE_UNREADABLE`* → a scanned PDF without text; use a text PDF. *Over 2 MB* → `413`, expected.

**Proceed when:** the uploaded PDF is visible in Azure Blob at `<tenantId>/<assessmentId>/<file>`, its text is in SQL, deleting the assessment removes the blob, and tenant B gets 404.

---

### OC-6: Real Microsoft Phi generation (Phase 6)
**Needs:** OC-5, OC-1D, and `PROBE FOUNDRY PASS` in OC-1H.
**Test:** `live-e2e` with `upto_phase=6` and `with_ai=true` (a small number of calls; estimate cost using the confirmed Phi model and deployment mode first).
**Expect:** `POST /assessments/{id}/generate` returns `202` with a `jobId`; polling `GET /api/v1/jobs/{jobId}` goes `queued → running → done` within about a minute with `result.questionsCreated ≥ 1`; every question has 4 options, a `correctAnswer` A to D and an explanation (descriptive ones have a rubric and `maxScore`); regenerating one question keeps its id and position; approve works only when **every section holds exactly its configured number of questions** (else `409 SECTION_INCOMPLETE`; no questions gives `409 NO_QUESTIONS`); editing after approval gives `409`.
**Verify in Azure:**
```sql
SELECT TOP 5 type, status, attempts, tokens_used, error FROM assess.jobs ORDER BY created_at DESC;   -- tokens_used > 0
```
```kusto
dependencies | order by timestamp desc | take 5
ContainerAppConsoleLogs_CL | where Log_s has "job_done" or Log_s has "job_retry" or Log_s has "job_failed" | order by TimeGenerated desc | take 10
```
(The logs carry ids, types, durations and token counts, never prompts. Ledger AZ-030.)
**If it fails:** *job `failed` with `AI_OUTPUT_INVALID`* → stop further calls and verify Phi output compatibility using sanitized diagnostics only. For HTTP 4xx/5xx, 404, or auth errors, verify the documented Serverless API contract and update/test the adapter; do not try another route or key by guess. *429* → the current adapter retries once after 2 seconds; Phi's retry/rate-limit contract remains unverified, so update the adapter if the endpoint requires different handling. Do not assume quota is shared with the portal. *Daily limit* → `429 DAILY_AI_LIMIT` after 20 generations per company per UTC day (by design). *Timeout* → check documented endpoint/region latency and record it.

**Proceed when:** a generation job reaches `done` with `questionsCreated ≥ 1`, `jobs.tokens_used > 0`, the logs show `job_done` and Application Insights shows a dependency to the Phi endpoint, regenerate keeps id and position, approve is refused with `409 SECTION_INCOMPLETE` until every section has exactly its count and then succeeds, and editing after approval returns `409`.

---

### OC-7: Real invitation email (Phase 7)
Use the maintained guide's [OC-7 instructions](docs/OFFICE_CONNECTION_AND_TESTING_GUIDE.md#oc-7-real-invitation-email-phase-7). Requires the signed plan, email service/domain readiness, and passing ACS probe. Use only your office mailbox; never put it in this repository or chat. Proceed only when the invitation is delivered and resend behavior is verified.

### OC-8: Candidate exam with the real token (Phase 8)
Use the maintained guide's [OC-8 instructions](docs/OFFICE_CONNECTION_AND_TESTING_GUIDE.md#oc-8-candidate-exam-with-the-real-token-phase-8). Keep the token in the designated GitHub secret only. Verify candidate DTO redaction, autosave/resume, submit, one-attempt behavior, deadline auto-submit, and the late-save rejection before continuing.

### OC-9: Real AI marking (Phase 9)
Use the maintained guide's [OC-9 instructions](docs/OFFICE_CONNECTION_AND_TESTING_GUIDE.md#oc-9-real-ai-marking-phase-9). Keep candidate personal data out of prompts and reports. Verify score bounds, review fallback, blank-answer handling, and record the prompt-injection observation without treating it as a pass/fail criterion.

---

## 7. Report back to the team (copy this, fill it, use placeholders only)

```
OFFICE REPORT <date>
Checkpoints done: OC-0 .. OC-9   Blocked: <list and why>
Deployed commit: <short sha>     Revision: Running / Healthy
Probes: config PASS | sql PASS (avg_rtt <n> ms) | blob PASS | foundry PASS (tokens <n>) | insights PASS | acs PASS (mail arrived: yes/no, spam: yes/no)
Tables in assess: <n>   Portal tables unchanged: yes/no
Live E2E up to phase 9: <n>/<n> PASS   Job tokens_used: <n>
Cost Analysis: deferred / reviewed <date>   $50 backend-only budget scope and alerts verified: yes/no
Changes I had to make to a command (no real names): <list>
Anything unexpected: <free text>
```
The team then updates `docs/PROGRESS.md`, the status board and `docs/UNVERIFIED_AZURE_LEDGER.md` (AZ-001 to AZ-030) from it.

---

## 8. Troubleshooting quick table

| Symptom | Likely cause | Fix |
|---|---|---|
| `AuthorizationFailed` | missing role on that scope | ask the owner for the minimum role; record it |
| `PrincipalNotFound` right after creating an identity | replication delay | wait 30 s, retry up to 6 times |
| Revision `Failed`, logs show `ConfigError` | production rejects a fake/memory/short secret | fix the named setting, not the check |
| Health OK, `x-app-version: local` | the placeholder or a very old image still serves | check revisions; redeploy |
| Smoke test times out | probes, port, or migrations slow | check `--type system` logs; startup probe 60 s |
| SQL probe slow (> 150 ms) | cross-region database | log the number; the team reviews chatty queries; do not raise the SQL tier |
| Phi endpoint 4xx/5xx or authentication error | endpoint/API contract not confirmed or adapter incompatible | stop probing; verify contract with the owner and update/test adapter |
| 429 from Phi endpoint | endpoint quota/rate limit | current adapter retries once after 2 seconds; verify/update against endpoint guidance and do not assume shared quota |
| Email in spam | Azure-managed domain | expected; custom domain later |
| Cloud Shell variables lost | session expired | repaste the variable block; re-enter secrets with `read -rsp` |

---

## Appendix A: Where the older guide and the repo scripts disagree with the code (and what this guide does)

| # | Finding | Effect | This guide |
|---|---|---|---|
| 1 | Workflows read variables **`AZURE_RESOURCE_GROUP`**, **`AZURE_ACR_NAME`**, **`AZURE_DEPLOY_ENABLED`** and secrets `AZURE_CLIENT_ID/TENANT_ID/SUBSCRIPTION_ID`. The older guide lists `ACR_NAME`, `RG_NAME`, `API_APP_NAME`, `API_URL`. | Deploy would fail with empty values. | Uses the real names (OC-1G). |
| 2 | The `deploy` job has `environment: production`, so the OIDC subject is `repo:...:environment:production`. `70-assess-api.sh` and the plan create only `...:ref:refs/heads/main`. | `azure/login` fails with `AADSTS70021`. | Creates both credentials (OC-1G). The plan needs the extra row. |
| 3 | The pipeline pushes the image, which needs **`AcrPush`**. `70-assess-api.sh` assigns only `AcrPull`. | Push `unauthorized`. | Assigns both (OC-1F). Plan needs the extra row. |
| 4 | `70-assess-api.sh` never runs `az containerapp registry set`. | The app cannot pull from the registry. | Added (OC-1F Do 2). |
| 5 | `assess-api.containerapp.yaml` references **nine** secrets (including `acs-sender`, `appinsights-connection-string`) and contains placeholders `<ACR>`, `<GIT_SHA>`, and `<AI_DEPLOYMENT_NAME>`; it lacks `APP_BASE_URL`, `API_INTERNAL_URL`, `BLOB_CONTAINER`. The older guide names the file `containerapp-api.yaml` and uses 8 secrets. | The YAML cannot be applied as-is, and the probe's `config` check fails without those three variables. | Nine secrets, temporary copy with image and exact owner-approved Phi deployment substituted, then the settings command is re-run (OC-3). |
| 6 | `30-blob.sh` uses `--auth-mode login` (needs a data-plane role) and never outputs the connection string the app needs. | Container create may fail with an authorization error. | Uses the connection-string method (OC-1C). |
| 7 | `50-email.sh` links the domain with `az communication link-notification-hub` and places the email service in `LOC_APP`. | Wrong command / location for an email domain. | Portal "Connect domain", location `global` (OC-1E). |
| 8 | `10-core.sh` budget command is unverified. | May fail. | Portal budget (OC-1A). |
| 9 | `inventory.sh` defaults to `DRY_RUN=1`. | It only prints commands. | `DRY_RUN=0` (OC-0). |
| 10 | Application settings are **not** loaded from `.env` files. | Irrelevant in Azure; matters for local use. | n/a |

The IDE agent should fix items 1 to 9 in the repository (scripts and older guide) on a branch and record AZ-006, AZ-020 and AZ-021 in the ledger. That work needs no Azure access.

## Appendix B: Secrets inventory (names only; values live in the password manager and in Container Apps secrets)

| Secret name (Container Apps) | Environment variable | Source | Created in |
|---|---|---|---|
| `database-url` | `DATABASE_URL` | built from the `assess_app` password | OC-1B |
| `session-secret` | `SESSION_SECRET` | `openssl rand -hex 32` | OC-1F |
| `platform-key` | `PLATFORM_KEY` | `openssl rand -hex 32` | OC-1F |
| `foundry-endpoint` | `FOUNDRY_ENDPOINT` | portal team's AI host | OC-1D |
| `foundry-key` | `FOUNDRY_KEY` | AI resource Key 1 (list only) | OC-1D |
| `acs-connection-string` | `ACS_CONNECTION_STRING` | `az communication list-key` | OC-1E |
| `acs-sender` | `ACS_SENDER` | email domain | OC-1E |
| `blob-connection-string` | `BLOB_CONNECTION_STRING` | storage account | OC-1C |
| `appinsights-connection-string` | `APPLICATIONINSIGHTS_CONNECTION_STRING` | Application Insights | OC-1A |

Plain settings (after OC-1D compatibility verification and adapter updates): `APP_ENV=production, PORT=8080, REPO_BACKEND=sql, DB_SCHEMA=assess, AI_MODE=azure, EMAIL_MODE=azure, FILES_MODE=azure, FOUNDRY_API_STYLE=<verified supported style>, FOUNDRY_DEPLOYMENT, BLOB_CONTAINER=jd-files, APP_BASE_URL, API_INTERNAL_URL, JOB_LOOP_ENABLED=true, GIT_SHA` (set by the pipeline). Do not enable Azure AI or run the Foundry probe before then.

GitHub secrets: `AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID, E2E_PLATFORM_KEY, E2E_A_EMAIL, E2E_A_PASSWORD, E2E_B_EMAIL, E2E_B_PASSWORD`. GitHub variables: `AZURE_RESOURCE_GROUP, AZURE_ACR_NAME, AZURE_DEPLOY_ENABLED`.

## Appendix C: End-of-day lock-down for this scope
- Remove any temporary SQL firewall rule you added (only yours).
- Confirm `az resource list --tag project=ai-assessment -o table` shows only what the plan lists.
- Confirm the portal's apps, tables and AI key are unchanged (compare with OC-0).
- Check the budget alerts exist and look at Cost Management tomorrow.
- Make sure no secret or real name was written into the repository, a PR, an issue or a workflow log.
- Clear the Cloud Shell session; keep the private notes in the password manager.