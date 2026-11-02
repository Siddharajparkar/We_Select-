# AGENTS.md

This repository holds an **existing** project: an Assessment Portal already runs in Azure, and this repository also contains the new **backend** (`api/`) of an AI candidate assessment platform, built by an AI coding agent from written specifications. **Read these files before doing anything, in this order:**

0. `docs/prompts/PROMPT_C_STACK_OVERRIDE_PYTHON.md`: **the stack is Python 3.12 + FastAPI + Pydantic + SQL; Node.js is 0%.** It overrides every Node/TypeScript/npm mention in B and A.
1. `docs/prompts/PROMPT_B_ADDENDUM_OFFLINE_AZURE_READY.md`: authoritative instructions and constraints. It overrides the master prompt where they conflict.
2. `docs/prompts/PROMPT_A_MASTER.md`: the master plan (backend only, 37 endpoints, phases 0 to 13).
3. The decision record in `docs/` titled **"Project Decisions & Organizational Constraints"**: authoritative; it wins over both prompts (only the user's latest message wins over it).
4. `docs/OFFICE_CONNECTION_AND_TESTING_GUIDE.md`: the manual the human uses later to connect and test Azure. You keep it accurate.
5. `docs/PROGRESS.md`: where the last session stopped (create it if missing).

Non-negotiable constraints (details in Prompt B):
- **No Docker** on the user's machines. Docker is used only by GitHub Actions runners.
- **No Azure access.** Never run `az login`, never ask for Azure credentials, never call real Azure endpoints. Azure code is built Azure-ready, tested against mocks, Azurite and a CI SQL Server container, and connected later by the human at the office (Azure Cloud Shell in a browser).
- **Existing project, existing repository.** Do not create a new repository; do not restructure or touch `frontend/`, `backend/`, `database/` or `ai_service/` (you may read `ai_service/`; it is reference only). Phases 0 to 3 already exist in `api/app/` (Python): extend them, do not rebuild them.
- **Public repository.** Never write real Azure resource names, subscription or tenant ids, hostnames, emails, keys or tokens into any file, comment, PR text or log. Use placeholders such as `<SQL_SERVER>`.
- **Shared Azure estate and shared database.** Zero-touch until a human has written `SIGN-OFF: APPROVED by` in `docs/PROVISIONING_PLAN.md` (you never write that line). Our tables live only in schema `assess`. Reuse the existing SQL database, AI resource, logs, registry and Container Apps environment; create only `assess-api` and what the plan lists.
- **Git workflow (Prompt B, B5.5):** one branch per phase (`phase/NN-name`) from the latest `main`, a pull request per phase, all CI and CD on GitHub Actions, merge to `main` only when the run is green. Never commit to `main` directly.
- **Budget $25.00 per month**: keep every design and script cost-aware.
- **Backend only.** Do not create or change any frontend (`web/`).
- **No secrets** in the repository, logs or documents.
- Do not wait for the user to paste prompts: read the files above and work phase by phase, keeping `docs/PROGRESS.md` up to date.

If a file above is missing, stop and ask the user to add it.