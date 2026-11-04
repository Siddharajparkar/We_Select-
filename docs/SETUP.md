# Setup Guide — new laptop or system

This guide takes a fresh laptop to the same state as the current working system: the API running locally **against the real Azure services**, and connected to the deployment pipeline.

- **Track A — join the existing environment** (what a teammate does). Needs access granted by the project owner.
- **Track B — rebuild the whole Azure environment** (what the owner does in a new subscription).

> **Public repository.** This file uses placeholders such as `<RG>`, `<KV>`, `<SQL_SERVER>`. The real names are in a private file, `config/azure.local.env`, that the owner shares with teammates directly. Never commit that file, `api/.env.local`, passwords, keys or connection strings.

Legend: **🔁 RUN ON EVERY NEW SYSTEM** — repeat this on every new machine (and, where noted, on every new network). **⚠️ TO CONFIRM** — not verified; check before relying on it.

**Terms:** *Azure CLI (`az`)* is the command-line tool for Azure. *Key Vault* is Azure's locked safe for passwords and keys. *Resource group* is a folder that holds related Azure resources. *Managed identity* is an Azure-provided login for an application. *OIDC* lets GitHub prove its identity to Azure without a stored password. *Migration* is a script that creates database tables.

---

## 1. How the current system is set up

**Cloud connection.** One Azure subscription (a personal account), one resource group `<RG>` in East US that also holds the unrelated, pre-existing portal resources. The owner signs in with `az login` in their own terminal (a browser window opens; the password is typed only there). Every Azure-changing command is run by a person; the AI coding assistant may run read-only `az` commands only. All changes are gated by a human approval line (`SIGN-OFF: APPROVED by …`) in `docs/PROVISIONING_PLAN.md`.

**Azure services in use**

| Service | Resource (placeholder) | What it does for the app | Created by us? |
|---|---|---|---|
| Azure SQL (serverless) | `<SQL_SERVER>` / `<SQL_DB>` (West US) | Stores all data in schema `assess`; the app user `assess_app` owns only that schema | Reused (existing) |
| Azure AI Foundry | `<AI_RESOURCE>` (North Central US), deployment Phi-4-mini-instruct | Writes the exam questions | Reused (existing) |
| Communication Services | `<ACS>` + Email service `<EMAIL>` with an Azure-managed domain | Will send candidate invitations (Phase 7) | ACS reused; email service created |
| Application Insights (+ Log Analytics) | `<APPINSIGHTS>` | Request, dependency and log telemetry | Reused (existing) |
| Key Vault | `<KV>` (East US, RBAC) | Holds the nine application secrets | Created |
| Storage account | `<STORAGE>`, private container `jd-files` | Stores uploaded job-description PDFs | Created |
| Container Registry | `<ACR>` (Basic) | Stores the application image | Created |
| Container Apps environment + app | `<CAE>`, `assess-api` (0.25 vCPU / 0.5 GiB, exactly 1 replica) | Runs the API over HTTPS | Created |
| Managed identities | `<APP_IDENTITY>` (runtime), `<DEPLOY_IDENTITY>` (GitHub deploy) | Passwordless access: the app pulls its image and reads Key Vault; the pipeline pushes images and updates the app | Created |

**Other tools.** GitHub (source control, Actions); Python 3.12 / FastAPI; ruff, mypy, pytest; the Python scripts in `scripts/dev/`. No Docker is needed on laptops (images are built on GitHub's runners).

**Deployment.** Merging to `main` runs `.github/workflows/deploy.yml`: *fast* checks → *container* tests (SQL Server and Azurite in Docker on the runner) → *security* scans → *deploy* (only when the repository variable `AZURE_DEPLOY_ENABLED` is `true`). The deploy job logs in to Azure with OIDC as `<DEPLOY_IDENTITY>`, builds and pushes the image (tag = commit SHA) to `<ACR>`, updates `assess-api`, runs a smoke test, and rolls back automatically if the smoke test fails.

---

## 2. Prerequisites

| Tool | Version used here | Needed for |
|---|---|---|
| Git | any recent | clone |
| Python | **3.12** recommended (3.11.15 was used on the laptop; the code requires ≥ 3.11) | everything |
| Azure CLI | 2.86 (the CI runner uses 2.91) | cloud-connected mode |
| ODBC Driver 18 for SQL Server | 18 | talking to Azure SQL |
| Azure CLI extensions `containerapp`, `communication` | latest | owner scripts only (Track B); `application-insights` is optional (telemetry queries) |
| A GitHub account with access to the repository | — | clone, pull requests, Actions |
| Docker | **not needed** | — |

**Install commands**

Windows (PowerShell):
```powershell
winget install -e --id Git.Git
winget install -e --id Python.Python.3.12
winget install -e --id Microsoft.AzureCLI
winget install -e --id Microsoft.msodbcsql.18
```
Close and reopen the terminal afterwards so the new tools are on the PATH.

macOS ⚠️ TO CONFIRM (only Windows was exercised):
```bash
brew install git python@3.12 azure-cli
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
brew install msodbcsql18
```
Linux (Debian/Ubuntu) ⚠️ TO CONFIRM: install Git, Python 3.12 and the Azure CLI from your distribution or Microsoft's instructions; for the ODBC driver see `scripts/ci/install_odbc.sh` in this repository, which is the script CI uses.

**Check:**
```powershell
git --version; python --version; az version; python -c "import pyodbc; print([d for d in pyodbc.drivers() if '18' in d])"
```
(The last command works after step 3.2; it must list `ODBC Driver 18 for SQL Server`.)

---

## 3. Step-by-step setup (Track A: join the existing environment)

### 3.1 Clone the repository from `main`
Gets the code, scripts and documentation.
```powershell
git clone https://github.com/Siddharajparkar/We_Select-.git
cd We_Select-
git branch --show-current
```
Expect: `main`.

### 3.2 Install the dependencies
Creates an isolated Python environment and installs the app plus the test and lint tools.
```powershell
py -3.12 -m venv .venv          # or: python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r api\requirements-dev.txt
```
Expect: no errors. If PowerShell blocks `Activate.ps1`, run the commands as `.\.venv\Scripts\python.exe -m pip …` instead. macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate`.

### 3.3 The two environment files
Two files hold configuration. **Both are gitignored — never commit them.**

| File | Contains | Where it comes from |
|---|---|---|
| `config/azure.local.env` | Azure resource **names** (no keys) | Get it **privately from the project owner**. Template with every name: `config/azure.example.env`. |
| `api/.env.local` | The app's settings **including secrets** | **Generated for you** by `setup.py` (step 3.5); never write it by hand. |

Names in `config/azure.local.env` and where each value comes from:

| Variable | Meaning | Where to get it |
|---|---|---|
| `AZ_RESOURCE_GROUP`, `AZ_LOCATION` | resource group and region | owner |
| `AZ_KEY_VAULT`, `AZ_STORAGE`, `AZ_ACR`, `AZ_CAE`, `AZ_APP` | vault, storage, registry, Container Apps environment, app names | owner |
| `AZ_APP_IDENTITY`, `AZ_DEPLOY_IDENTITY` | the two managed identities | owner |
| `AZ_SQL_SERVER`, `AZ_SQL_DB` | SQL server and database | owner |
| `AZ_AI_RESOURCE`, `AZ_ACS`, `AZ_APPINSIGHTS` | AI, communication and telemetry resources | owner |
| `ACS_SENDER` | email sender address | owner |
| `GITHUB_REPO`, `GITHUB_SUBJECT_REPO` | repository name; the ID-qualified form GitHub sends in OIDC tokens (owner only) | owner |
| `FOUNDRY_DEPLOYMENT`, `FOUNDRY_API_STYLE`, `BLOB_CONTAINER` | defaults: `Phi-4-mini-instruct`, `v1`, `jd-files` | defaults are in the template |

Place the file at `config\azure.local.env` and confirm Git ignores it:
```powershell
git check-ignore -v config/azure.local.env
```
Expect: a line mentioning `.gitignore` and `config/*.local.env`.

The generated `api/.env.local` holds the nine application settings that are secrets (`DATABASE_URL`, `SESSION_SECRET`, `PLATFORM_KEY`, `FOUNDRY_ENDPOINT`, `FOUNDRY_KEY`, `ACS_CONNECTION_STRING`, `ACS_SENDER`, `BLOB_CONNECTION_STRING`, `APPLICATIONINSIGHTS_CONNECTION_STRING`) plus non-secret ones (`APP_ENV`, `REPO_BACKEND`, `DB_SCHEMA`, `AI_MODE`, `EMAIL_MODE`, `FILES_MODE`, `FOUNDRY_API_STYLE`, `FOUNDRY_DEPLOYMENT`, `BLOB_CONTAINER`, `APP_BASE_URL`, `API_INTERNAL_URL`).

### 3.4 Sign in to Azure and select the subscription  🔁 RUN ON EVERY NEW SYSTEM
```powershell
az login
az account set --subscription "<SUBSCRIPTION_NAME_OR_ID>"
az account show --query "{name:name, state:state}" -o table
```
Expect: the subscription listed with state `Enabled`. If the browser does not open, try `az login --use-device-code` (then open the printed address in any browser).
If sign-in fails with `AADSTS530035` ("blocked by security defaults"), see Troubleshooting.

### 3.5 Get access, then connect to every Azure service  🔁 RUN ON EVERY NEW SYSTEM (access is once per person)
**Access (done by the owner, once per teammate).** The owner grants you the role *Key Vault Secrets User* on `<KV>` (⚠️ TO CONFIRM: there is no script for this yet; the owner can use `az role assignment create --assignee <your identity> --role "Key Vault Secrets User" --scope <KV resource id>`).

Then, on your laptop:
```powershell
python scripts/dev/setup.py --add-ip
```
What it does: checks tools (ODBC Driver 18, sign-in); reads `config/azure.local.env`; pulls the nine secrets from Key Vault into `api/.env.local` **without printing them**; offers to add your public IP to the SQL firewall (answer `y`); then runs the connectivity probes for config, SQL, Blob, the AI model and Application Insights.

Expect the final lines:
```
PROBE CONFIG PASS … PROBE SQL PASS … PROBE BLOB PASS … PROBE FOUNDRY PASS … PROBE INSIGHTS PASS
PROBE ALL PASS (5 passed, 0 failed, 0 skipped)
```
(A SQL "WARN avg … > 150ms" is normal from a laptop far from the West US database.)

### 3.6 Connect to the database
Step 3.5 already tested it (`PROBE SQL`). The database is **serverless and pauses when idle**: the first connection after a pause can take up to about a minute; retry once. The connection uses the least-privilege user `assess_app` (password only inside Key Vault, inside `database-url`). Tables are created automatically by the migrations when the API starts. To re-test the database only:
```powershell
cd api; python -m app.tools.probe sql; cd ..
```

### 3.7 Run the application locally against Azure
```powershell
python scripts/dev/run.py
```
Expect the log to show `migrations applied`, `config ok` with `repo_backend: sql`, `ai: azure`, `email: azure`, `files: azure`, `job_loop_started` and `Uvicorn running on http://0.0.0.0:8080`. Leave this terminal open. In a second terminal:
```powershell
Invoke-RestMethod http://127.0.0.1:8080/api/v1/health
```
Expect `status : ok`. (Interactive API docs, development only: `http://127.0.0.1:8080/api/v1/docs`.)

Offline alternative — no Azure, fake data, nothing saved:
```powershell
$env:ASSESS_IGNORE_ENV_LOCAL = "1"
cd api; python -m app.main
```

### 3.8 Connect to the deployment and CI/CD
For a teammate there is nothing to configure: your work reaches Azure only through GitHub.
1. Make changes on a branch (`git switch -c <type>/<short-name>`).
2. Push (`git push -u origin <branch>`) and open a pull request into `main`.
3. The checks `fast`, `container` and `security` must be green before merging.
4. Merging to `main` runs the deploy automatically (when `AZURE_DEPLOY_ENABLED` is `true`). The pipeline signs in to Azure itself using OIDC; **you need no Azure credentials for it.**

The pipeline's one-time connection (owner only) is described in Track B, steps B.12–B.14.

### 3.9 Verify the full setup end to end
With the API running (step 3.7), in a second terminal:
```powershell
python scripts/dev/verify.py
```
This creates test tenants and assessments, uploads a PDF, generates questions with the real AI model and approves an assessment. It uses a few thousand AI tokens and leaves test data in the shared database. Expect the last line:
```
E2E PASS: 28/28 checks passed (target=local, upto=6)
```
(`--no-ai` skips the real AI calls.) To test the **deployed** API instead:
```powershell
$u = az containerapp show -g <RG> -n assess-api --query properties.configuration.ingress.fqdn -o tsv
python scripts/dev/verify.py --base-url "https://$u"
```
Also run the quality gates before opening a pull request:
```powershell
ruff check api scripts tests; ruff format --check api scripts tests
cd api; mypy app; cd ..
pytest -m "not sql and not container and not azurite"
```

---

## 4. ⚠️ Commands to run on EVERY new system

These are the commands that depend on the machine (or its network), not on the project. Skipping one breaks the step shown.

| # | 🔁 Command | Why it must be run on every new system | What breaks if skipped |
|---|---|---|---|
| 1 | Install **ODBC Driver 18 for SQL Server** (`winget install -e --id Microsoft.msodbcsql.18`, then a new terminal) — the same step as "Step 17" in the progress report | pyodbc cannot reach Azure SQL without it | `setup.py` reports `PROBLEM ODBC Driver 18 … not found`; the API cannot connect to SQL |
| 2 | `az login` then `az account set --subscription "<…>"` | Azure CLI sign-in is stored per machine and expires | `Please run 'az login'` / "You are not signed in"; nothing can read Key Vault |
| 3 | Place `config/azure.local.env` (from the owner) in `config/` | The scripts need the resource names; the file is never in Git | `config/azure.local.env not found` |
| 4 | `python scripts/dev/setup.py --add-ip` | Writes `api/.env.local` (secrets are not in Git) and opens the SQL firewall for **this machine's IP** — the same purpose as the "SQL firewall" step ("Step 13") of the progress report | No local settings file (the API runs in memory mode instead); or `Client with IP address … is not allowed` when connecting to SQL |
| 5 | **Re-run `python scripts/dev/setup.py --add-ip` whenever your network (public IP) changes** — home, office, hotspot | The SQL firewall allows specific IP addresses only | SQL probe/API fails with `Client with IP address … is not allowed` |
| 6 | `pip install -r api\requirements-dev.txt` inside a new `.venv` | Python environments are per machine | `ModuleNotFoundError` |
| 7 | Role *Key Vault Secrets User* granted to you (once per person, by the owner) | Reading secrets needs this role | `Azure refused access` when `setup.py` pulls secrets |

*Note on "Step 12":* in the progress report, Step 12 (granting the deploy identity its roles) is a **one-time change in Azure**, not a per-machine command; Step 13 (the SQL firewall rule) is the per-machine/per-network one.

Owner-only, once per **new Azure subscription** (Track B): provider registration, the `communication` CLI extension (`az extension add --name communication`), and the resource creation steps below.

---

## 3-B. Track B — rebuild the Azure environment from scratch (owner)

Use this for a new subscription. It assumes the pre-existing resources already exist: the SQL server and database, the AI Foundry resource with a Phi-4-mini-instruct deployment, a Communication Services resource, and Application Insights. (⚠️ TO CONFIRM: creating those four from nothing is not covered by the scripts.)

Nothing below changes Azure until the plan carries the owner's approval line. Every `provision.py` step is a **dry run unless `--apply` is added**; run the dry run first and read it.

**B.1 Prepare.** Do 3.1, 3.2 and 3.4 first. Then:
```powershell
copy config\azure.example.env config\azure.local.env     # fill every value with your real names
```
Choose globally unique names for `<KV>`, `<STORAGE>` (lowercase letters/digits) and `<ACR>`. Add `GITHUB_REPO=<owner>/<repo>`.

**B.2 Sign the plan.** Review `docs/PROVISIONING_PLAN.md` and replace its line `SIGN-OFF: <not approved>` with `SIGN-OFF: APPROVED by <initials> on <date>`. Only a person does this. Scripts refuse to write without it.

**B.3 Register providers** (once per subscription):
```powershell
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.ContainerRegistry --wait
```
**B.4 Create the resources, one step at a time** (dry run, then `--apply`; verify each before the next):
```powershell
python scripts/dev/provision.py keyvault --apply
python scripts/dev/provision.py storage --apply
python scripts/dev/provision.py container --apply
python scripts/dev/provision.py registry --apply
python scripts/dev/provision.py environment --apply
python scripts/dev/provision.py identities --apply
python scripts/dev/provision.py roles-owner --apply
python scripts/dev/provision.py roles-app --apply
python scripts/dev/provision.py app --apply
python scripts/dev/provision.py registry-link --apply
python scripts/dev/provision.py roles-deploy --apply
```
**B.5 Database access for the laptop** 🔁 (repeat on each new network):
```powershell
python scripts/dev/provision.py sql-firewall --apply
```
**B.6 Create the schema and database user (portal).** Open the database in the Azure portal → Query editor, paste `scripts/db/create-app-user.sql`, replace the single placeholder `<APP_USER_PASSWORD>` with a password you choose (letters, digits, `-_.!@#`; avoid `; { } =` and quotes) and run it. Keep the password in a password manager. Verify:
```sql
SELECT s.name AS schema_name, p.name AS owner FROM sys.schemas s JOIN sys.database_principals p ON p.principal_id = s.principal_id WHERE s.name = 'assess';
```
Expect `assess` owned by `assess_app`.

**B.7 Email (portal).** Create an *Email Communication Services* resource (data location matching your Communication Services), add an **Azure subdomain**, wait for *Verified*, note the `DoNotReply@<domain>.azurecomm.net` sender, and in the Communication Services resource use *Email → Domains → Connect domain*. Add the tags `project=ai-assessment`, `env=mvp`. Put the sender in `config/azure.local.env` as `ACS_SENDER=…` (on its own line).

**B.8 CLI extension for the ACS key:**
```powershell
az extension add --name communication
```
**B.9 Store the nine secrets in Key Vault** (you will be asked for the SQL password at a hidden prompt):
```powershell
python scripts/dev/put_secrets.py --apply
```
**B.10 Point the app at Key Vault and give it its settings:**
```powershell
python scripts/dev/sync_secrets.py --apply
python scripts/dev/configure_app.py --apply
```
**B.11 Prove it locally against Azure:** do 3.5, 3.7 and 3.9.

**B.12 Let GitHub log in to Azure (OIDC).** GitHub may identify the repository in its tokens by numeric IDs (`repo:<owner>@<owner_id>/<repo>@<repo_id>:…`), and Azure only accepts a credential that matches the token's subject character for character. Look the IDs up first (public data, no login needed; verified on this repository):
```powershell
curl.exe -s https://api.github.com/repos/<owner>/<repo>
```
In the JSON, `id` is the repository ID and `owner.id` the owner ID. Add this line to `config/azure.local.env` (on its own line):
```
GITHUB_SUBJECT_REPO=<owner>@<owner_id>/<repo>@<repo_id>
```
Then run (dry run first, then apply). This creates credentials for both the plain-name and ID-qualified subjects, for the `main` branch and for the `production` environment:
```powershell
python scripts/dev/provision.py oidc
python scripts/dev/provision.py oidc --apply
```
If a deploy login still fails with `AADSTS700213`, the failed log prints the exact subject GitHub sent; use that.

**B.13 Enter the GitHub settings.**
```powershell
python scripts/dev/github_settings.py
```
Enter what it prints in GitHub → Settings: create the environment `production`; add repository **secrets** `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`; add repository **variables** `AZURE_RESOURCE_GROUP`, `AZURE_ACR_NAME`, and `AZURE_DEPLOY_ENABLED` (keep `false` for now). Never paste these values into chat or files.

**B.14 First deploy.** Make sure CI is green on the latest `main` commit, set `AZURE_DEPLOY_ENABLED` to `true`, then in GitHub → Actions open the latest `main` run → *Re-run all jobs* (a push that changes only `docs/**` or `*.md` does not start CI). Verify:
```powershell
$u = az containerapp show -g <RG> -n assess-api --query properties.configuration.ingress.fqdn -o tsv
curl.exe -s -D - "https://$u/api/v1/health"
```
Expect `200`, body `{"status":"ok"}`, and an `x-app-version` header equal to the commit SHA; `https://$u/api/v1/docs` must return 404.

---

## 5. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `az login` fails with `AADSTS530035` ("blocked by security defaults") | A tenant security policy. Sign in to the Azure portal first, complete MFA registration, then retry `az login` from your own terminal. Do not try to bypass the policy. |
| Browser does not open for `az login` | Use `az login --use-device-code` and open the printed address in any browser. |
| `Please run 'az login'` / "You are not signed in to Azure" | Step 3.4; sign-in expired or is missing. |
| `PROBLEM ODBC Driver 18 … not found` | Install ODBC Driver 18 (Section 4, row 1) and open a **new** terminal. |
| `config/azure.local.env not found` or "still has placeholder values" | Get the real file from the owner (3.3). |
| `Azure refused access` when pulling secrets | You lack *Key Vault Secrets User*; ask the owner. Role changes can take a minute or two to apply. |
| `PROBE SQL FAIL … Client with IP address … is not allowed` | Your public IP is not in the SQL firewall. Re-run `python scripts/dev/setup.py --add-ip` (Section 4, row 5). |
| `PROBE SQL FAIL … Login timeout expired` right after a long idle period | The serverless database was paused and is resuming (up to about a minute). Retry once. |
| `PROBE SQL FAIL` with a login failure for `assess_app` | The password stored in Key Vault differs from the database user's password; the owner resets one of them (Track B step B.6 and B.9). |
| `PROBE CONFIG FAIL … missing` although you ran setup | Old tooling that did not read `api/.env.local`; update to the latest `main`. |
| Windows: "`-o` was unexpected at this time" from a script | `az` runs through `cmd.exe`, which breaks on parentheses in arguments; fixed in the scripts (a test guards it). Update to the latest `main`. |
| `config/azure.local.env` has a setting glued to the previous line | The file lacked a trailing newline when you appended with `Add-Content`. Put the setting on its own line. |
| Tests that run scripts fail with "No such file or directory" on Windows | `bash` on PATH is WSL. Install Git for Windows; the tests use its Git Bash. |
| `pytest` fails `test_no_hardcoded_secrets_in_tracked_files` | A non-test file assigns a variable named `key`, `secret`, `token` or `password` from a plain word; rename the variable. |
| Deploy login fails: `AADSTS700213 No matching federated identity record` | The OIDC subject GitHub sends differs from the credential; copy the subject printed in the failed login log into `GITHUB_SUBJECT_REPO` and run `provision.py oidc --apply` (B.12). |
| Deploy job does not appear after setting `AZURE_DEPLOY_ENABLED=true` | The job runs only for a push to `main`: re-run the latest `main` workflow run (B.14). |
| `git push` rejected: "would publish a private email address" | Commit with your GitHub `noreply` address (`git config user.email`) or relax the setting in GitHub's email settings. |
| `git push` returns 403 | The wrong GitHub account is cached. Remove the cached credential or sign in with the account that has write access. |
| Port 8080 already in use | Stop the other program or set `PORT`. |
| A generation job fails with "The AI could not produce usable questions" | The small model returned unusable output three times, or stalled; retry the job. If it persists, report it with the time so the logs can be checked. |
