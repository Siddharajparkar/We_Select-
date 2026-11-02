# Prompt C — Stack override: Python + FastAPI (Node.js 0%)

Authority: owner message of 2026-11-02. This file **overrides Prompt A and Prompt B wherever they name Node.js, npm, TypeScript, Express or any JavaScript tool**. Everything else in A and B (phases, endpoints, limits, security rules, the sign-off gate, the three verification tiers, public-repo rules, budget) still applies unchanged.

## Stack
Backend: Python 3.12, FastAPI, Pydantic v2 (pydantic-settings), SQL (Azure SQL / SQL Server) through SQLAlchemy 2 Core + pyodbc with ODBC Driver 18. Cloud: Azure only. Frontend (not built here): Next.js / React. LangChain: not in the MVP; allowed later only behind the AI provider port if an agentic need appears.

## Translation table (Prompt A/B term -> use this)
| Prompt says | Use |
|---|---|
| Node 20, npm ci, package.json | Python 3.12, `pip install -r api/requirements-dev.txt` |
| Express app factory, helmet | FastAPI `create_app()`, pure-ASGI `RequestContextMiddleware` (security headers, request id, 1 MB limit) |
| zod validation | Pydantic v2 models and `pydantic-settings` |
| `mssql` / `tedious` pool | SQLAlchemy engine + pyodbc, retry on transient errors (`app/db/engine.py`) |
| vitest, supertest | pytest + FastAPI `TestClient`; `httpx` for live runs |
| ESLint, tsc, prettier | ruff (lint + format), mypy |
| `NODE_ENV` | `APP_ENV` (`development` / `test` / `production`) |
| `src/...` paths, `*.ts` | `api/app/...`, `*.py` (e.g. `api/app/repositories/`, `api/app/tools/probe.py`) |
| `node dist/tools/probe.js X` | `python -m app.tools.probe X` |
| `scripts/e2e/run.mjs`, `*.mjs` | `scripts/e2e/run.py`, `scripts/e2e/checks/*.py` |
| `npm run test:*` | `pytest -m "not sql"` (T1), `pytest` (CI with SQL/Azurite), markers `sql`, `e2e`, `container`, `azurite` |
| `@node-rs/argon2`, `argon2` | `argon2-cffi` (prebuilt wheels) in Phase 4 |
| `pdf-parse`, `pdfkit` | `pypdf` (extraction), `reportlab` or `fpdf2` (export), Phase 5 / 10 |
| `applicationinsights` SDK | `azure-monitor-opentelemetry` (`app/telemetry.py`) |
| `openai` / REST for Foundry | `httpx` REST to the v1 route by default (`FOUNDRY_API_STYLE=v1`) |
| `npm audit` | `pip-audit` |
| `actions/setup-node` | `actions/setup-python@v5` with pip cache |
| `ESLint no-restricted-imports` for SQL | pytest static test (`tests/phase2/test_p2_boundaries.py`) that only repository modules import SQLAlchemy |

## Standing rules that do not change
No Docker on the owner's machines (CI only); no Azure access while building; no Azure secrets requested, stored or committed; zero-touch on Azure until a human writes `SIGN-OFF: APPROVED by`; schema `assess` only; public repo uses placeholders; backend only (do not touch `frontend/`, `backend/`, `database/`, `ai_service/`); one branch per phase, PR, merge on green CI; commit trailers as configured.

## Session start prompt for the next phase (paste into the IDE agent)
```
Read AGENTS.md, then docs/prompts/PROMPT_C_STACK_OVERRIDE_PYTHON.md, PROMPT_B_ADDENDUM_OFFLINE_AZURE_READY.md,
PROMPT_A_MASTER.md, docs/decisions.md and docs/PROGRESS.md, in that precedence (C wins on stack, then B, then A;
decisions.md wins over all prompts). The backend is Python 3.12 + FastAPI + Pydantic + SQL; Node.js is 0%.
Phases 0-6 exist in api/app (auth, assessments, job engine, AI generation, approval). Start Phase 7
(participants and invitations via ACS: endpoints 23-27) on branch phase/07-participants from latest main. Reuse the repositories, providers, error envelope and test fixtures already present. Write tests
first-class: tests/phase7/{unit,integration,e2e} (API tests use the dual-backend `repos` fixture), run `ruff check . && ruff format --check . && (cd api && mypy app)
&& pytest -m "not sql"` before every push, and update docs/PROGRESS.md and the UNVERIFIED ledger. Never write the
SIGN-OFF line, never request Azure secrets, never create Azure resources.
```
