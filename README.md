# AI Candidate Assessment Platform — Backend

The backend is **Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 Core and pyodbc**. It integrates with Azure SQL, Blob Storage, Azure AI Foundry, Azure Communication Services, Application Insights and Azure Container Apps. The frontend is out of scope.

The repository is public. Do not commit credentials, real Azure resource names, hostnames, subscription or tenant IDs, or email addresses. Azure setup and live-service checks are office-only; this guide's local workflow uses in-memory repositories and fake providers.

## Run locally on Windows

Use Python 3.12, the project's selected runtime. The Windows launcher selects by minor version, so `py -3.14` resolves Python 3.14.8; `py -3.14.8` is not accepted. Python 3.14 has not been selected as a supported runtime. To reproduce an exploratory run on it, replace the first setup command below with `py -3.14 -m venv .venv`.

Open PowerShell in the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r api\requirements-dev.txt
```

If PowerShell says the Python 3.12 runtime is unavailable, install Python 3.12 and verify it with `py -0p`. Do not install or run Docker or Azure CLI for local development.

In the same PowerShell window, explicitly select the safe local configuration and start the API:

```powershell
$env:APP_ENV = "development"
$env:REPO_BACKEND = "memory"
$env:AI_MODE = "fake"
$env:EMAIL_MODE = "fake"
$env:FILES_MODE = "memory"
$env:JOB_LOOP_ENABLED = "true"
Push-Location api
..\.venv\Scripts\python.exe -m app.main
```

The API listens on `http://127.0.0.1:8080`. Leave this terminal running. In a second PowerShell window at the repository root, confirm it is ready:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/api/v1/health
```

Expected response:

```text
status
------
ok
```

Interactive API documentation is available at `http://127.0.0.1:8080/api/v1/docs` in development; `/` and `/docs` also redirect there for convenience. These shortcuts and the interactive documentation are disabled in production. To stop the server, press **Ctrl+C** in its terminal. The in-memory data is temporary and is cleared when the server restarts.

The API configuration reads environment variables. Outside production it also loads the gitignored developer file `api\.env.local` if it exists (real environment variables win; `ASSESS_IGNORE_ENV_LOCAL=1` skips it; production never loads it). It never loads `api\.env.example`, which is only a template. The explicit PowerShell settings above keep local runs on memory/fake services and prevent accidental use of Azure. `COOKIE_SECURE` defaults to `true`; the supplied end-to-end harness handles the cookie explicitly. For manual browser login over plain HTTP only, set `$env:COOKIE_SECURE = "false"` in the server terminal. Never use that setting in production.

## Run the local end-to-end flow

Keep the API running in the first terminal. From the repository root in the second terminal:

```powershell
.\.venv\Scripts\python.exe scripts\e2e\run.py --base-url http://127.0.0.1:8080 --target local --upto 6
```

The harness exercises the available live API flow through Phase 6: health and security headers, platform and staff authentication, tenant isolation, assessment creation and PDF upload, fake-AI generation jobs, review, and approval. It creates throwaway in-memory test data. Local AI and email are fakes; this does **not** call Azure or send email.

Expected final line:

```text
E2E PASS: ... checks passed (target=local, upto=6)
```

`FAIL` means one or more local checks failed; inspect the named check and the API terminal output. `SKIP` is reported separately for checks that require a real service.

## Run local quality checks

Run these from the repository root with the virtual environment installed:

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
Push-Location api
..\.venv\Scripts\python.exe -m mypy app
Pop-Location
.\.venv\Scripts\python.exe -m pytest -m "not sql"
```

The local pytest selection excludes tests that require a real SQL Server. To run one phase's tests, for example:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\phase6
```

On Windows, checks that require Bash or POSIX SIGTERM behavior are skipped; GitHub Actions runs those checks on Linux.

If you prefer the activation workflow, run `.\.venv\Scripts\Activate.ps1` first; if PowerShell blocks activation, use the direct `.venv\Scripts\python.exe` commands above instead.

## Verification tiers and Azure boundary

- **T1 — Local:** lint, format, type checks, and tests using in-memory repositories and fake providers. No Docker, database, or Azure access.
- **T2 — GitHub Actions:** SQL Server/Azurite tests, image build, and container end-to-end checks run on CI runners.
- **T3 — Office:** real Azure connection and live-service checks follow [`docs/OFFICE_CONNECTION_AND_TESTING_GUIDE.md`](docs/OFFICE_CONNECTION_AND_TESTING_GUIDE.md). Do not run these from this development machine.

Passing the local harness proves the local application flow only; it does not verify SQL Server, Azure services, deployment, or phases that have not yet been implemented. See [`docs/PROGRESS.md`](docs/PROGRESS.md) for phase status and [`docs/UNVERIFIED_AZURE_LEDGER.md`](docs/UNVERIFIED_AZURE_LEDGER.md) for pending Azure assumptions. Never run Azure provisioning scripts until the human has reviewed and signed the provisioning plan.

## Repository map

```text
api/app/                 FastAPI app, configuration, routes, services, repositories, providers and migrations
api/requirements*.txt    Runtime and development Python dependencies
api/Dockerfile           CI-built container image; Docker is not part of local setup
infra/azure/             Dry-run provisioning scripts and Container App configuration
scripts/e2e/             Live API end-to-end harness and phase checks
tests/                   Pytest suites by phase; SQL/container tests run in CI
docs/                    Decisions, progress, office guide, runbook and Azure verification ledger
.github/workflows/       GitHub Actions CI/CD workflows
```
