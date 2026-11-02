# AI Candidate Assessment Platform — Backend

Multi-tenant AI-powered candidate assessment **backend**: **Python 3.12, FastAPI, Pydantic v2, SQLAlchemy Core + pyodbc**, Azure SQL, Blob Storage, Azure AI Foundry (GPT-4o), Azure Communication Services, deployed to Azure Container Apps through GitHub Actions. (No Node.js anywhere in the backend.)

## Quick start (local, no Docker, no Azure)

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r api/requirements-dev.txt
cp api/.env.example api/.env        # optional; defaults already run fully in memory
cd api && python -m app.main        # http://localhost:8080/api/v1/health
```

Defaults are `REPO_BACKEND=memory`, `AI_MODE=fake`, `EMAIL_MODE=fake`, `FILES_MODE=memory`. `APP_ENV=production` refuses all of them.

## Project structure

```
api/app/          FastAPI app: config, core, db, repositories, providers, ai (prompts, validator), jobs (engine, handlers),
                  security, services, schemas, routes, migrations, tools (probe, seed_tenant)
api/Dockerfile    multi-stage image (python:3.12-slim + ODBC Driver 18, non-root, port 8080) — built only on GitHub runners
infra/azure/      provisioning scripts (dry-run + human sign-off gated) and the assess-api Container App config
scripts/          ci helpers, e2e smoke/harness, db scripts
tests/            phase0..phase6 pytest suites + Postman collections (tests/phase3/postman, tests/phase6/postman)
.github/workflows deploy (fast -> container -> security -> deploy), live-e2e, nightly, rollback, load-test
docs/             prompts, decisions, plan, ledger of unverified Azure assumptions, phase reports
```

## Testing

```bash
ruff check . && ruff format --check .
(cd api && mypy app)
pytest -m "not sql"                         # laptop tier (T1): no DB, no Docker
pytest tests/phase6                         # AI generation, job engine, questions, approval
python scripts/e2e/run.py --base-url http://127.0.0.1:8080 --upto 6    # live harness against a running server
python tests/phase3/postman/run_collection.py --base-url http://127.0.0.1:8080   # phases 0-3, same spec as the Postman JSON; no Node/newman
python tests/phase6/postman/run46.py --base-url http://127.0.0.1:8080            # phases 4-6
```

SQL Server, Azurite, image build, Trivy and container E2E run in the GitHub Actions `container` job (tier T2). Azure itself is checked only at the office checkpoints (tier T3) with `python -m app.tools.probe <config|sql|blob|foundry|insights|acs|all>` from Cloud Shell.

## Docs

- [Progress](docs/PROGRESS.md) · [Decisions](docs/decisions.md) · [Phase reports](docs/phase-reports/)
- [Unverified Azure ledger](docs/UNVERIFIED_AZURE_LEDGER.md) · [Runbook](docs/runbook.md)



test-exam/                         (repo root)
├── README.md                      Project overview + how to run
├── AGENTS.md                      Rules the AI agent must follow (no secrets, sign-off gates, backend-only)
├── pytest.ini                     Test config: paths + markers (sql, e2e, container, azurite)
├── ruff.toml                      Lint/format rules
├── .editorconfig  .gitignore      Editor + git hygiene
├── docker-compose.yml             Old local SQL Server dev file (Phase 0, optional)
├── AI_Assessment_MVP_Design_and_API_Contract.pdf   Confidential spec (source of truth)
│
├── .github/workflows/             CI/CD (Docker runs ONLY here, never on our laptops)
│   ├── deploy.yml                 Lint+tests -> SQL/Azurite tests + image build -> Trivy scan -> deploy
│   ├── live-e2e.yml               Manual: end-to-end run against a deployed API
│   ├── nightly.yml                Scheduled regression run
│   ├── rollback.yml               Manual: roll back to the previous revision
│   └── load-test.yml              Manual load test
│
├── infra/azure/                   Azure scripts. Dry-run by default, blocked until a human signs the plan
│   ├── 10-core.sh                 Resource group / environment checks
│   ├── 20-sql.sh                  SQL schema + app user (schema `assess` only)
│   ├── 30-blob.sh                 Blob container for JD files
│   ├── 40-ai.sh                   AI deployment settings (GPT-4o)
│   ├── 50-email.sh                Email service (used from Phase 7)
│   ├── 60-registry.sh             Container registry access
│   ├── 70-assess-api.sh           Create the `assess-api` Container App
│   ├── 80-assess-api-config.sh    Env vars / secrets via Key Vault references
│   ├── _run.sh                    Shared helper: dry-run, sign-off check, no secrets
│   ├── assess-api.containerapp.yaml   Container App spec (0.25 vCPU / 0.5 GiB, 1 replica)
│   └── discovery/                 Read-only scripts to list existing Azure resources
│
├── scripts/
│   ├── run-plan.sh                Runs the signed plan step by step
│   ├── ci/                        install_odbc.sh, prepare_sql.py (CI helpers)
│   ├── db/create-app-user.sql     Least-privilege DB user for the API
│   ├── e2e/                       End-to-end harness
│   │   ├── run.py                 Runs checks for phases 0..N against a live URL
│   │   ├── smoke.sh               Quick health smoke
│   │   └── checks/p00..p06_*.py   One check file per phase
│   └── azure-smoke/               Azure connectivity smoke (run from the office laptop)