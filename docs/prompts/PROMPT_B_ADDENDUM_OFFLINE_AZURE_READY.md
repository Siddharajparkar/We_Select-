---
title: Prompt B - Addendum (offline, Azure-ready build)
repo_path: docs/prompts/PROMPT_B_ADDENDUM_OFFLINE_AZURE_READY.md
relation: ADDENDUM to docs/prompts/PROMPT_A_MASTER.md (overrides it where they conflict)
audience: AI coding agent (Antigravity or any IDE agent) reading this file directly from the repository
companion_files:
  - docs/<decision record: Project Decisions & Organizational Constraints>
  - docs/prompts/PROMPT_A_MASTER.md
  - docs/OFFICE_CONNECTION_AND_TESTING_GUIDE.md
  - docs/PROGRESS.md        (created and maintained by the agent)
---

# Prompt B: Addendum to the Master Prompt (no Docker, no Azure access while building)

## AGENT: READ THIS FIRST

You are an AI coding agent working inside this repository. **The user will not paste prompts to you phase by phase.** They placed these files in the repo so that you read them yourself and then build the whole backend. Treat this file as your standing instructions for the whole project, across sessions.

### Reading order (do this at the start of every session)
1. **This file** (Prompt B). It is authoritative and **overrides Prompt A where they conflict**.
2. **`docs/prompts/PROMPT_A_MASTER.md`** (Prompt A, the master plan: backend only, no frontend, 37 endpoints, 14 phases numbered 0 to 13, Azure services, database, CI/CD, deployment). If that file is missing, look for `ANTIGRAVITY_BACKEND_E2E_PROMPT.md` anywhere in the repo; if you cannot find either, **stop and ask the user to add it**. Ignore Prompt A's "how to use / paste into Antigravity" instructions: you read it from the repo.
3. **The decision record** in `docs/` titled "Project Decisions & Organizational Constraints" (find it by title). It is authoritative and wins over everything except the user's latest message.
4. **`docs/OFFICE_CONNECTION_AND_TESTING_GUIDE.md`** (the manual the human follows later, at the office, without AI, to connect and test each Azure service). You **maintain** it (section B9).
5. **`docs/PROGRESS.md`** if it exists (where the last session stopped). If it does not exist, create it (section B12).

### What the user's situation is (hard facts, not suggestions)
- This is the user's **company project** and an **existing project** (an Assessment Portal already runs in Azure). Company laptops have **no AI tools**, so the code is built on a development laptop and the user works in the **existing repository** `Siddharajparkar/We_Select-` (public at the time of writing).
- **Docker is unavailable everywhere**: no disk space on the personal laptop, and forbidden on the company network. Never require Docker on the user's machine.
- **You have no Azure access.** The Azure account can be used only from the organisation laptop, through **Azure Cloud Shell in a browser** (Azure CLI cannot be installed there); the user is not allowed to log into it from the machine you run on. Never run `az login`, never ask for Azure credentials, never call real Azure endpoints.
- Therefore: **build all 14 phases (0 to 13) completely and Azure-ready**, verify them with **GitHub Actions** (SQL Server and Azurite service containers on the runners), and let the user **connect and test each Azure service later at the office** using the guide.

### Commands the user may give you (you must understand all of these)
| The user says | You do |
|---|---|
| "Read `docs/prompts/PROMPT_B_ADDENDUM_OFFLINE_AZURE_READY.md` and build the backend" (first run) | Do the reading order above. Reply in **at most 10 lines**: your understanding of the situation, the three verification tiers (B2), the five biggest overrides (B3), and the checkpoint IDs. Create `docs/PROGRESS.md`. Then start Phase 0 and **keep going phase by phase without waiting**, following Prompt A's operating protocol (A:C) plus this file, stopping only at a stop condition (B10), a failed gate you cannot fix, or the end of Phase 13. |
| "continue" or "next" | Read `docs/PROGRESS.md`, resume at the first phase not marked `HOME-DONE`, and keep going. |
| "status" | Summarise `docs/PROGRESS.md` in at most 12 lines (per-phase status, last CI run, unverified ledger count, open questions, next action). Change nothing. |
| "phase N" | Work only on Phase N (and fix what its gate needs), then stop and report. |
| "office report OC-n: ..." (or a filled report from the guide's template) | Apply B9 and B13: update the ledger and the guide, fix the code if the report shows a defect, keep everything Azure-ready, update `docs/PROGRESS.md`. |
| "ci failed" plus pasted log | Diagnose and fix (B5.4). |

### Where files live in the repository
```
AGENTS.md                                  (short pointer to these files)
docs/prompts/PROMPT_A_MASTER.md            (master prompt)
docs/prompts/PROMPT_B_ADDENDUM_OFFLINE_AZURE_READY.md   (this file)
docs/OFFICE_CONNECTION_AND_TESTING_GUIDE.md
docs/PROGRESS.md                           (you create and maintain)
docs/UNVERIFIED_AZURE_LEDGER.md            (you create and maintain)
```

---

# BEGIN PROMPT B

## B0. Precedence and how to cite

1. Order of authority: **the user's latest message > the decision record in `docs/` ("Project Decisions & Organizational Constraints") > Prompt B > Prompt A**. If B is silent, A applies. Inside Prompt B, B3 rows 21 to 34 and the phase blocks in B7 win over B3 rows 1 to 20.
2. Cite Prompt A steps as `A:<step>` (for example `A:6.3`) and Prompt B rules as `B:<section>`. In every phase report write one line "Overrides applied: ..." so the human can see which rules from B changed the work.
3. If you find a conflict between A and B that this file does not resolve, **stop and ask** one precise question.

## B1. The situation, as hard constraints

| # | Constraint | What it means for you |
|---|---|---|
| C1 | **No Docker anywhere** (not on the personal laptop, forbidden on the company network) | Never write a step that needs `docker`, `docker compose` or Testcontainers on the human's machine. Docker is used **only by GitHub-hosted CI runners**. |
| C2 | **No Azure access while building** (the subscription belongs to a teammate; logging in is forbidden) | Never run `az login`, `az ...` commands that call Azure, or any code that contacts a real `*.azure.com`, `*.windows.net`, `*.azurecr.io` or `*.azurecomm.net` endpoint. You may read **public** Microsoft documentation to write correct code. |
| C3 | **Company laptops have no AI** | At the office the human works **alone**. Everything they must do has to be written as explicit, copy-paste steps in the office guide, with expected outputs and failure causes. |
| C4 | **Existing project and repository** (decision record) | Work in the existing public repository `Siddharajparkar/We_Select-`; do not create a new one; do not restructure existing folders. No secrets, no `.env`, no real Azure names, ids or emails in the repo (B3 row 32). |
| C5 | **Limited disk space on the personal laptop** | Keep `node_modules` lean; no large fixtures or binaries in the repo; no local databases. |
| C6 | **Restricted machines** | Avoid npm packages that compile native code or download binaries in `postinstall`. Use `@node-rs/argon2` (prebuilt) instead of `argon2`. Avoid headless-browser packages. Commit the lockfile. Pin Node 20. |
| C7 | The human is on **Windows** | `.gitattributes` with `* text=auto eol=lf` (shell scripts and Dockerfiles must keep LF). npm scripts must be cross-platform (use `cross-env`, Node scripts or `rimraf`, no bash-only syntax in `package.json`). Shell scripts are for CI and the office only. |
| C8 | **Existing Azure estate** | The subscription already holds the Assessment Portal's resources. Zero-touch until a signed plan exists (B3 row 24). |
| C9 | **Shared database** | Our tables live only in schema `assess` of the existing West US database (B3 row 26). |
| C10 | **Budget $25 per month** | Every design and script choice must be cost-aware; alerts at 50, 80 and 100 percent (B3 rows 21, 30, 31). |
| C11 | **Cloud Shell is the only Azure CLI** | The org laptop cannot install Azure CLI; all Azure commands run in Azure Cloud Shell in a browser (session is ephemeral). Write every command to be pasted there. |

## B2. The principle: build complete, verify in three tiers, connect later

Every requirement from Prompt A is assigned to a verification tier. **A phase is "done at home" when Tier 1 and Tier 2 are green. It is "done for real" only after its Tier 3 office checkpoint passes.** Never claim Tier 3 results you did not see.

| Tier | Where | Tools | Proves |
|---|---|---|---|
| **T1** | The human's laptop (no Docker, no DB, no Azure) | `npm run lint`, `typecheck`, `test:unit`, **`test:api:memory`** (the whole HTTP API on in-memory repositories and fake providers), `shellcheck`, workflow linting | Business logic, validation, security rules, state machines, time rules, DTOs |
| **T2** | **GitHub Actions** runners (the existing repository; it is public, so no secrets or real names in logs, B3 row 32) | SQL Server 2022 service container, Azurite (real Blob SDK), Docker build of the image, Trivy, container E2E, `gitleaks` | The real SQL repositories and migrations, real Blob client behaviour, the **container image itself**, tenant isolation against a real database, pipeline gating |
| **T3** | **The office**, against real Azure, using the guide | Azure CLI or Cloud Shell, GitHub Actions in the company repo, `probe` tool, `live-e2e` workflow | Azure SQL, Blob, owner-verified Microsoft Phi endpoint, Communication Services, Application Insights, ACR, Container Apps, OIDC, real deployment |

Tag every test with its tier (`@t1`, `@t2`, `@t3`) and make `npm run` scripts accordingly. **Tier 3 tests must be skipped automatically (never failed) when `E2E_TARGET` is not `azure`.**

## B3. Overrides to Prompt A (authoritative table)

| # | Prompt A says | Prompt B replaces it with |
|---|---|---|
| 1 | A:0.1 preflight checks Docker, `az`, `gh` | Require only `node` 20, `npm`, `git`. `gh` is **optional** (see B5.4). Do **not** check for or install Docker or `az`. |
| 2 | A:0.2 ask the human about subscription, region, email recipient, domain, budget | **Do not ask.** Those are office decisions: store them as required placeholders in `.env.azure.example` and as inputs in the guide. Ask only: (a) repo name and whether `gh` is installed and authenticated, (b) **R1** globally unique email (default yes), (c) **R5** minimum questions per section (default "at least 1"), (d) **R13** external api ingress until web exists (default yes). If unanswered, use the defaults and record them. |
| 3 | A:0.5 `docker-compose.yml`, `db:up`, local SQL and Azurite | **Delete the idea.** No compose file. Local development needs **no database**: `REPO_BACKEND=memory`. Write `docs/local-dev.md` saying so. |
| 4 | A:B rule 6 modes `AI_MODE`, `EMAIL_MODE`, `FILES_MODE` | Add **`REPO_BACKEND=memory\|sql`**. `FILES_MODE=memory\|azurite\|azure`. `AI_MODE=fake\|azure`, `EMAIL_MODE=fake\|azure`. In production (`NODE_ENV=production`) the app **refuses to start** unless `REPO_BACKEND=sql` and all other modes are `azure`. |
| 5 | A:1.x scripts are executed against Azure | Scripts are **authored only**. Every script uses a `run` wrapper: when `DRY_RUN=1` (the **default**) it prints the command that would run and exits 0; the office sets `DRY_RUN=0`. CI runs every script in `--plan` mode and through `shellcheck`. |
| 6 | A:1.1 `az login [HUMAN]` | Removed from your work. The guide tells the human how to log in at the office. |
| 7 | A:1.11 live checks as separate `.mjs` scripts run locally | One tool: **`src/tools/probe.ts`** (B6.3), compiled into the image, runnable inside the container (`az containerapp exec`) or locally with env vars. Unit-tested with mocks. |
| 8 | A:2.6 integration harness on a docker DB or Testcontainers | CI service containers (B5). Local runs use memory repositories only. |
| 9 | A:3.3 local container test | Done **in CI only** (job `image`). |
| 10 | A:3.5 `deploy` job always runs on `main` | The deploy job is **guarded**: `if: github.ref == 'refs/heads/main' && vars.AZURE_DEPLOY_ENABLED == 'true'`. When disabled the workflow shows a clear "deploy disabled" notice and is still green. |
| 11 | A:3.9, 12.6 pipeline proofs (a) to (h) | Proofs (a) to (e) are done at home on the personal repo (they need no Azure). Proofs (f) to (h) (real deploy, rollback) are office checkpoints OC-3 and OC-12. |
| 12 | A:4.10, 5.8, 6.11, 7.9, 8.12, 9.6, 10.7 "live checks" | Write them as checks in `scripts/e2e/checks/NN-*.mjs` with `E2E_TARGET=local-container\|azure`. In CI they run against the **locally started container** (`local-container`). At the office the same checks run against Azure. |
| 13 | A:11.7 restore drill, A:11.8 load test on the deployed app | Author both. The load test also runs in CI against the container with a **small profile** (5 virtual users, 1 minute) to check the script works. The real run and the restore drill are office checkpoint OC-11. |
| 14 | A:12.1 stages 7 to 11 (deploy, smoke, live E2E, release record, rollback) | Implement all, guarded as in row 10. Add `live-e2e.yml` (manual dispatch) so the human can run the Azure E2E from GitHub without installing anything. |
| 15 | A:13.1 clean-slate rehearsal | **Removed** (B3 row 30). |
| 16 | A:G final document | Two parts: **Part 1 "Built and verified at home"** (with CI evidence links) and **Part 2 "Azure connection status"** (one row per office checkpoint, all `PENDING` until the human reports back). |
| 17 | A:I Definition of Done | Two levels: **Home-DoD** (B8) and **Office-DoD** (= A:I, completed at the office). |
| 18 | A:B rule 10 merge to `main` after the gate | One branch and one pull request per phase (B5.5); merge to `main` only when its **GitHub Actions run is green** (T1 and T2). |
| 19 | A:1.3 and A:R19 choose the region now | Region and model availability are **office inputs**. The code and scripts take them from variables. No default region in code. |
| 20 | A:1.6 read the GA API version "from Learn" | You may read the public docs, but **`FOUNDRY_API_VERSION` has no default in code** and no hard-coded model version anywhere. Both are required configuration. Record the documentation URL and date you used in the ledger (B6.5). |

### B3 (continued): overrides from the user's decision record and the repo facts (these win over rows 1 to 20 on conflict)

The user keeps a file titled **"Project Decisions & Organizational Constraints"** in `docs/` (the file name may vary; find it by its title). It is **authoritative**. Its content as of 2026-11-01 is reflected in rows 21 to 34. If the file changes, the file wins.

| # | Prompt A / earlier Prompt B says | Replaced by |
|---|---|---|
| 21 | Rows 2 and 19 ask the human for repo, region and similar | **Already answered.** Existing repository `Siddharajparkar/We_Select-` (**do not create a new repository**), deploy branch **`main`**, `gh` is available and authenticated on the dev laptop. **R1 = yes** (globally unique, case-insensitive email). **R5 = equal to configured count.** **R13 = external ingress** on port 8080 with strict authentication, authorisation and rate limiting. Azure-managed email domain. The ACS test mailbox is the user's **office email**, given by the human at the office (never committed). Monthly budget **$25.00**, alerts at 50, 80 and 100 percent. |
| 22 | A:0.x builds Phase 0 from nothing | Phase 0 already exists: **reconcile** it (Phase 0 block in B7). |
| 23 | A:R5 and A:6.8 "at least 1 question per section" | **`POST /assessments/{id}/approve` requires, for every section, exactly the configured `count` questions (AI plus custom).** Otherwise `409 SECTION_INCOMPLETE` with `details:[{sectionIndex, expected, actual}]`; zero questions overall is `409 NO_QUESTIONS`. Extra questions must be deleted before approval. A partial AI result (A:R7) therefore cannot be approved until the section is filled (re-run generate, regenerate single questions, or add custom questions). Update tests and the guide. |
| 24 | A:1.x creates every Azure resource | **Discovery, written plan, human sign-off, then create only what is missing** (Phase 1 block in B7). No Azure change before `SIGN-OFF: APPROVED by`. |
| 25 | A:R19 default names and one region | No default names for existing resources (they come from the inventory). Regions: `LOC_APP=eastus`, `LOC_SQL=westus`, `LOC_AI=eastus`. The SQL server and database are in **West US** (chosen because of tier availability); app, logs, AI and storage in East US. Cross-region database calls are expected: no chatty query loops, report latency in the probe. |
| 26 | A:1.4 creates the SQL server and an app user with `db_datareader`, `db_datawriter`, `db_ddladmin` | **Reuse the existing SQL server and database.** Dedicated schema **`assess`** and an app user that owns only that schema (Phase 2 block in B7). Never use `dbo`. |
| 27 | A:1.6 creates the AI resource and deployment; `FOUNDRY_API_VERSION` mandatory | The user-selected target is **Microsoft Phi-4-mini-instruct Serverless API / pay-as-you-go, North Central US**, pending owner/portal verification. Do not assume an existing AI resource, model catalog identifier, endpoint, API route, auth scheme, quota, or pricing. The current backend adapter only implements `v1` and `azure-deployments` chat-completions styles; neither is presumed compatible with this target. Verify the endpoint contract in the Foundry portal, then update and test the adapter if needed. Do not set live AI secrets or run the real probe until compatible code is ready. `FOUNDRY_API_STYLE` must have no default and must be explicitly set only to a verified supported style. |
| 28 | A:1.8 creates `assess-api` **and** a placeholder `assess-web` | Create **only `assess-api`**. The portal and any frontend belong to others; never create, change or deploy to `assess-web` or the portal apps. |
| 29 | A:1.9 gives the GitHub identity Contributor on the whole resource group | The resource group also holds the existing portal. Scope **Contributor to the `assess-api` container app only** and **AcrPush to the registry**. If the first deploy fails with an authorisation error naming the environment, widen only as that error says and record it in the ledger. Use the **existing repository's exact case** in the federated credential subject: `repo:Siddharajparkar/We_Select-:ref:refs/heads/main`. If the repository is ever moved, create a new credential for the new repository. |
| 30 | A:13.1 rehearsal, A:11.7 restore drill, A:11.8 stress test, availability tests, 100 percent telemetry | Removed or reduced (Phase 11 and 13 blocks in B7): cost ceiling and zero-touch. |
| 31 | A:3.4 container 0.5 vCPU and 1 GiB | Default 0.25 vCPU and 0.5 GiB, min and max replicas 1 (A:R15: the job loop and deadline timer need a running container). If the signed plan shows the budget is exceeded, **ask the user before changing the architecture** (for example scale-to-zero would delay auto-submit). |
| 32 | (new) the repository is **public** | While the repository is public: **never write real Azure resource names, subscription or tenant ids, hostnames, emails or tokens into any file, issue, PR text, workflow summary or log**; use placeholders such as `<SQL_SERVER>`; mask values in workflow logs with `::add-mask::`. Tell the user (once, in your first reply) that the repository is public while the documents describe a confidential design and recommend making it private. |
| 33 | (new) existing `ai_service/` (Python, FastAPI) | **Reference only.** The PDF architecture puts AI inside the Node `api`. Do not deploy or depend on `ai_service/`. You may read it to align prompts and the endpoint style; do not copy any secret you may find. |
| 34 | C4 "code moves from a personal repo to the company repo" | Work in the **existing repository** as decided. If it moves later, only the OIDC credential and repo-name variables change. |

## B4. Architecture additions (so the whole backend is testable without a database)

1. **Ports and adapters.** Services depend on a `RepoSet` interface (one interface per repository from A:2.4 and A:D5). Two implementations:
   - `src/repositories/sql/*`: the real T-SQL (A:2.4).
   - `src/repositories/memory/*`: an in-memory implementation that reproduces the **same semantics**: tenant filtering with `assertTenant`, unique constraints (`(assessment_id,email)`, filtered unique `token_hash` where NULLs may repeat, `(attempt_id,question_id)`, `attempts(participant_id)`, globally unique email), `responses.upsert` deadline rule with the injected `Clock`, atomic `jobs.claimNext`, `withTransaction` implemented as snapshot and rollback of the store, composite tenant integrity checks.
   - `createRepos(config)` picks one by `REPO_BACKEND`. The memory backend must refuse to start when `NODE_ENV=production`.
2. **Repository contract suite** `test/repo-contract/*.contract.ts`: written once, executed against **both** implementations (`npm run test:repo:memory` at home, `npm run test:repo:sql` in CI). It covers all repository behaviour from A:2.7 that is not purely SQL-specific, including tenant isolation on every function. This is what proves the memory fake is faithful.
3. **SQL-only suite** `test/sql-only/*`: things only a real engine can show: migrations twice and in parallel under `sp_getapplock`, composite foreign keys, filtered unique index, `MERGE ... HOLDLOCK` race, `READPAST` job-claim race with two workers, transient-error retry. CI only (`@t2`).
4. **Dual-run API tests:** every supertest API test (A:4.9 to A:10.6, including the cross-tenant tests) is written **once** and executed twice: `npm run test:api:memory` (T1, seconds, at home) and `npm run test:api:sql` (T2, in CI against SQL Server). A test that only passes on one backend is a defect in the fake or in the SQL repository.
5. **Providers.** `FilesProvider` implementations: `memory` (T1), `azurite` (T2, the **real** `@azure/storage-blob` SDK against Azurite), `azure` (T3). `AiProvider` and `EmailProvider`: `fake` and `azure`. The `azure` implementations are thin adapters: all Azure SDK calls live in one small file each so they can be mocked at the module boundary.
6. **Config** accepts connection-string flags for both worlds (`Encrypt=true;TrustServerCertificate=false` for Azure SQL, `TrustServerCertificate=true` for the CI SQL container). A unit test parses both forms.
7. **T-SQL portability.** CI uses SQL Server 2022, production is Azure SQL. Use only features available in both. Do not use `xp_` procedures, cross-database queries, SQL Agent, or `OPENROWSET`. `sp_getapplock`, `MERGE`, `OUTPUT`, `READPAST`, `UPDLOCK`, filtered indexes and `ISJSON` are fine.
8. **Schema isolation.** All SQL is schema-qualified with `assess` (B7 Phase 2 block). The repository contract suite and the SQL-only suite run against a database that also contains decoy `dbo` tables.
9. **AI endpoint style.** `FOUNDRY_API_STYLE` selects a supported style only after the owner verifies that the Phi endpoint uses it; no style is assumed or defaulted (B3 row 27).

## B5. CI as the test bench

### B5.1 One workflow file, grown phase by phase
`.github/workflows/deploy.yml` is **created in Phase 0** (not Phase 3) with job `fast`, and extended as phases need it. Required jobs:

| Job | Runs on | Needs | Content |
|---|---|---|---|
| `fast` | every push and PR | none | Node 20, `npm ci`, lint, typecheck, `test:unit`, `test:repo:memory`, `test:api:memory`, `shellcheck infra/**/*.sh scripts/**/*.sh`, `actionlint`, infra scripts in `--plan` mode, OpenAPI file validity |
| `sql` | PR and `main` (from Phase 2) | `fast` | service container `mcr.microsoft.com/mssql/server:2022-latest` (`ACCEPT_EULA=Y`, `MSSQL_SA_PASSWORD` from a **workflow-level generated** value, health check `/opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -Q "SELECT 1"`, port 1433) and Azurite (service container `mcr.microsoft.com/azure-storage/azurite` or `npx azurite`); runs `test:repo:sql`, `test:sql-only`, `test:api:sql`, blob tests with `FILES_MODE=azurite` |
| `image` | PR and `main` (from Phase 3) | `sql` | `docker build` of `api`, Trivy scan, then **container E2E**: run the image with `--network host` against the SQL service container and Azurite (`NODE_ENV=test`, `REPO_BACKEND=sql`, fake AI and email, `ENABLE_TEST_OUTBOX=true`), run `node scripts/e2e/run.mjs --target local-container --upto <N>`, stop the container |
| `security` | PR and `main` | none | `npm audit --omit=dev --audit-level=high`, `gitleaks`, dependency review on PRs |
| `deploy` | `main` only, `vars.AZURE_DEPLOY_ENABLED == 'true'` | `fast`, `sql`, `image`, `security` | OIDC login, push image, update Container App, smoke test, live E2E, release record, rollback on failure (A:12.1 stages 7 to 11) |

Also author, with the same guard and `workflow_dispatch` triggers (the office guide uses these exact names, inputs and secrets, so do not rename them):
- `live-e2e.yml`: inputs `base_url`, `upto_phase`, `with_ai` (boolean), `with_email` (boolean). It reads these repository secrets: `E2E_PLATFORM_KEY`, `E2E_A_EMAIL`, `E2E_A_PASSWORD`, `E2E_B_EMAIL`, `E2E_B_PASSWORD`, `E2E_MAILBOX` (the real mailbox that receives the test invitation), `E2E_CANDIDATE_TOKEN` (the token copied from the real email, used only by the Phase 8 candidate checks). It runs `node scripts/e2e/run.mjs --target azure ...`; a check whose required secret is missing must print `SKIPPED (missing <name>)`, never fail.
- `rollback.yml`: input `image_tag` (A:12.4).
- `nightly.yml` (A:12.5; skips Azure steps when the deploy flag is off).
- `load-test.yml`: inputs `base_url`, `profile` (`target` only = 20 users for at most 5 minutes; **no stress profile**, B3 row 30), runs `scripts/load/exam.js` with k6.

### B5.2 Cost and speed rules (public repositories get free runner minutes, but keep runs short anyway; if the repository is made private the free allowance is limited, so the human should check their plan)
- `concurrency` group per ref with `cancel-in-progress: true` for PRs.
- `paths-ignore: ['docs/**', '**/*.md']` on the `sql` and `image` jobs; docs-only pushes run only `fast`.
- Cache npm (`actions/setup-node` cache). Keep `fast` under 3 minutes and the whole pipeline under 12.
- Work on phase branches with **draft PRs**: `fast` runs on every push, `sql` and `image` on PR updates. Batch fixes: run `npm run test:api:memory` locally before pushing to avoid wasted CI runs.
- Never loop on CI blindly: after **3 failed runs on the same problem**, stop, summarise the failing logs and your hypotheses, and ask the human.

### B5.3 Test selection by environment variables
`REPO_BACKEND`, `FILES_MODE`, `AI_MODE`, `EMAIL_MODE`, `E2E_TARGET` (`local-container` default in CI, `azure` only at the office), `E2E_BASE_URL`. Tier 3 checks read `E2E_TARGET` and `skip` themselves; a skipped T3 test prints `SKIPPED (needs E2E_TARGET=azure)` and is **never** counted as a pass in the final report.

### B5.4 Feedback loop for you (the agent)
- If `gh` is installed and authenticated on the personal account: push the branch, run `gh run watch --exit-status`, on failure `gh run view --log-failed`, fix, repeat (subject to B5.2 limits).
- If `gh` is not available: tell the human exactly which branch you pushed and ask them to paste the failing log (or the run summary) back.
- You never need Azure credentials for any of this.

### B5.5 Git and GitHub workflow: one branch per phase, everything verified by GitHub Actions
All CI and CD run on **GitHub Actions** in the existing repository. Nothing is verified on the user's laptop beyond the T1 commands (B2). Every workflow lives in `.github/workflows/`.

**Branches (mandatory, one per phase, created from the latest `main`):**
| Phase | Branch |
|---|---|
| 0 | `phase/00-reconcile` |
| 1 | `phase/01-azure-discovery-plan` |
| 2 | `phase/02-database` |
| 3 | `phase/03-container-pipeline` |
| 4 | `phase/04-auth-tenants-users` |
| 5 | `phase/05-assessments-blob` |
| 6 | `phase/06-ai-generation` |
| 7 | `phase/07-participants-email` |
| 8 | `phase/08-candidate-exam` |
| 9 | `phase/09-scoring` |
| 10 | `phase/10-results-export` |
| 11 | `phase/11-hardening` |
| 12 | `phase/12-full-cicd` |
| 13 | `phase/13-release` |

If a branch with a similar name already exists on `origin` (for example `phase/00-foundation` or `phase/01-azure-provisioning`), do not delete it; create the new branch above from `main` and note the older one in `docs/PROGRESS.md`. Fixes found later go on a new branch `fix/<phase>-<topic>` and follow the same loop.

**The loop for every phase (no exceptions):**
1. `git switch main && git pull`, then create the phase branch.
2. Build the phase in small conventional commits (`feat:`, `fix:`, `test:`, `ci:`, `docs:`). Never commit to `main` directly. Never force-push a shared branch.
3. Run the T1 commands locally, then push the branch and open a **draft pull request** to `main` (use `gh pr create --draft`; if `gh` is unavailable, tell the human the branch name).
4. GitHub Actions runs `fast` on every push, and `sql`, `image`, `security` on the pull request. Watch the run (B5.4), fix, push again. Stay within the cost rules of B5.2.
5. When **all required jobs are green** and the phase's exit gate and Home-DoD items are met, write `docs/phase-reports/NN-name.md` (with the line "Overrides applied: ..."), mark the PR ready and **merge to `main`** (squash or merge commit, linear history), then delete the merged branch.
6. A merge to `main` triggers the `deploy` job, which stays **disabled** (`vars.AZURE_DEPLOY_ENABLED != 'true'`) until the human enables it at OC-3. A skipped deploy job is the correct result before then; it is not a failure.
7. Update `docs/PROGRESS.md` (phase `HOME-DONE`, PR link, last green run id, next action) in the same PR or a follow-up commit on `main`, then start the next phase branch from the new `main`.

**Phase 3 exception:** its pipeline is proven by its own PR runs; the real deploy is the office checkpoint OC-3.
**Branch protection** on `main` is set at the office (OC-12). Until then the rule is a discipline you keep: no direct commits to `main`, merge only on green.
**The human only needs to:** read the PR link in `docs/PROGRESS.md`, and send "continue". Do not ask the human to run tests locally or to merge for you, unless `gh` cannot merge.

## B6. "Azure-ready, not yet verified" discipline

For **every** component that will touch Azure (SQL pool settings, Blob provider, Foundry client, ACS provider, Application Insights wiring, ACR/Container Apps scripts, OIDC setup, deploy steps):

1. **Thin adapter**, one small file per service, all SDK calls inside it.
2. **Mock-based tests** of request construction (URL, headers, body shape, api-version param), response parsing, error mapping (429, 401, timeouts, quota errors) and retry behaviour. For Foundry use HTTP-level interception (for example `msw` or `nock`) so the real SDK builds the request; for ACS and Application Insights mock the SDK module.
3. **Probe tool** `src/tools/probe.ts` (compiled to `dist/tools/probe.js`), usage `node dist/tools/probe.js <sql|blob|foundry|insights|acs|config|all> [--to someone@example.com]`:
   - prints one line per probe: `PROBE <name> PASS|FAIL <ms> <short reason>`, and a final `PROBE ALL PASS|FAIL`; exit code 0 or 1;
   - **never prints secrets or full connection strings** (mask to the first 4 characters);
   - `config`: lists each required env var as `present` or `MISSING` (names only);
   - `sql`: connect as the app user, `SELECT 1`, create and drop a temp table (DDL right), report whether `schema_migrations` exists and its row count;
   - `blob`: put, get and delete `selftest/<uuid>.txt` in `BLOB_CONTAINER`; then an **anonymous** request for the same blob URL must fail (container is private);
   - `foundry`: one tiny chat completion asking for `{"ok":true}`, 30 s timeout, report latency and token usage;
   - `insights`: send a trace with a unique marker and print the marker (the human then finds it with the KQL in the guide);
   - `acs`: sends **one real email only when `--to` is given** (never by default, never in `all`);
   - unit-tested with the same mocks as item 2.
4. **Documented configuration:** `.env.azure.example` lists every variable from A:D8 and the additive ones, with placeholders such as `<from OC-1B>`, and a comment saying which checkpoint produces each value. No real values.
5. **Unverified ledger** `docs/UNVERIFIED_AZURE_LEDGER.md`: a table with columns `ID, component, file, assumption made (including doc URL and date read), verified by (OC-n), status (UNVERIFIED | VERIFIED | FIXED-AT-OFFICE), notes`. Add a row for **every** Azure-touching assumption (API version, header names, SDK method, role name, CLI flag, SKU names). The human updates the status at the office.
6. **Never guess.** If you are not sure of an Azure CLI flag or SDK call, read the public documentation, cite it in the ledger, and mark that row `UNVERIFIED (low confidence)` so the guide tells the human to confirm with `--help`.
7. **No fake success.** A mock passing is not evidence that Azure works. Never write "Azure integration verified" anywhere; write "Azure adapter tested against mocks".
8. **Repository hygiene:** secret scanning in CI, `.gitignore` per A:0.3, no company or personal names in code or docs, no Azure resource names that look real (use `<placeholder>` in docs; real names are chosen at the office). **The repository is public (B3 row 32): treat every committed file and every workflow log as visible to the world.**

## B7. Phase-by-phase instructions

For each phase: **Build** (what changes versus Prompt A), **Verify at home** (tier and gate), **Authored for the office** (what is written but cannot run), **Office checkpoint**. Prompt A's detailed steps still apply unless a row of B3 overrides them.

### Phase 0: Foundation, RECONCILE the work that already exists (A:0.x)
- **Status you must assume:** the repository **already contains a Phase 0**: `api/` (Node 20, Express, TypeScript; app factory, health endpoint, config validation, logger with redaction, clock and id utilities, error model, provider abstractions) with about 53 unit and contract tests passing, published on branches `main` and `phase/00-foundation`. It was built **before** this addendum. **Do not rebuild it.** Audit it, then close the gaps on a new branch `phase/00-reconcile` created from `main`, and write `docs/phase-reports/00-reconcile.md` listing every gap found and how it was closed. All existing tests must stay green.
- **Reconcile checklist (each item: found / missing / fixed):**
  1. No Docker in the developer workflow: remove or move to CI-only any `docker-compose.yml`, `db:up` scripts or Testcontainers use. `npm test` must never need Docker.
  2. Ports and adapters from B4: `REPO_BACKEND=memory|sql`, memory repositories skeleton, `FILES_MODE=memory`, production refusal rules (B3 row 4).
  3. Native or download-on-install packages: replace `argon2` with `@node-rs/argon2` if present; no `postinstall` downloads.
  4. Cross-platform npm scripts (`cross-env`), `.gitattributes` (`* text=auto eol=lf`).
  5. `.env.example` (local, fake defaults) and `.env.azure.example` (placeholders only), including the new variables: `FOUNDRY_API_STYLE`, `AI_MAX_OUTPUT_TOKENS`, `AI_DAILY_TOKEN_CAP`, `APPINSIGHTS_SAMPLING_PERCENT`, `DB_SCHEMA` (default `assess`).
  6. `.github/workflows/deploy.yml` with job `fast` (B5.1). If any workflow already exists, **extend it, never replace it**.
  7. `docs/local-dev.md` and the repo-root `AGENTS.md` (leave it if it exists and is correct).
  8. **Repository secret scan** (B6.8, the repository is public): run `gitleaks` or an equivalent search over the **whole git history**. If you find any key, token, connection string or password, **tell the user immediately** and recommend rotating it; do not copy it anywhere.
  9. Read, **read-only**, the existing `ai_service/` Python files (`question_generator.py`, `answer_evaluator.py`) to learn the prompts and the Azure endpoint style the portal team already uses (see B3 row 27). Do not import them, do not deploy them, do not modify them.
- **Do not touch:** `frontend/`, `backend/`, `database/`, `ai_service/` (reading is allowed). Never create `web/`.
- **Verify at home:** T1 all green; `fast` job green in CI; the 53 existing tests still pass plus the new ones.
- **Checkpoint:** none. **Status after this phase:** `HOME-DONE`.

### Phase 1: Azure discovery, plan, sign-off, then targeted provisioning (replaces A:1.x)
The Azure subscription already contains resources that belong to the existing Assessment Portal. **Nothing may be created, modified, migrated or deleted until a human has approved a written plan.** Phase 1 therefore has three stages.

**Stage 1: build the tools (at home, no Azure):**
1. `infra/azure/discovery/inventory.sh`: **strictly read-only** (Azure CLI `list` and `show` only). It must **never** call anything that returns secrets or changes state: no `keys list`, `list-key`, `show-connection-string`, `get-shared-keys`, `secret show`, `exec`, `create`, `update`, `delete`, `set`. It prints names, types, SKUs, regions, provisioning states, ingress type, image **names**, app-setting and secret **names only** (never values), firewall rule names, role-assignment role names. A unit test greps the script for the forbidden verbs and fails if any appear. `shellcheck` clean.
2. `infra/azure/discovery/sql-inventory.sql`: read-only T-SQL for the portal Query editor: schemas, table names and column counts (no row data), database tier, collation, compatibility level.
3. `docs/PROVISIONING_PLAN.md` **template**: one row per resource with columns `Resource | Region | Mode (REUSE / CREATE / IAM-CHANGE / DB-CHANGE / NONE) | SKU or size | Reason | Cost driver (no invented prices; the human fills the estimate from the Azure pricing calculator and Cost Management) | Risk | Needs approval`. Pre-fill from the decision record (B3 rows 21 to 34): REUSE the SQL server and database (West US), the existing AI resource (`<AI_RESOURCE>`), Log Analytics, Application Insights, the registry and the Container Apps environment when they exist; CREATE only what is missing (storage account and private container `jd-files`, Communication Services with the Azure-managed domain, the `assess-api` container app, the budget); IAM-CHANGE rows (`AcrPull`, `AcrPush`, a narrowly scoped deploy role); DB-CHANGE row (schema `assess` and an app user inside the existing database). Sections: cost headroom (the **$25 per month** ceiling; whether it is for the new backend only or the whole subscription is an open question to ask the human), latency note (East US to West US), "what is NOT touched", teardown by tag, open questions, and a **sign-off block** that ends with exactly this line left blank for the human:
   `SIGN-OFF: <not approved>`
4. Provisioning scripts `infra/azure/10-*.sh` to `70-*.sh` (names as in A:1.3 to A:1.10, but each resource has `MODE_<RESOURCE>=reuse|create|skip`). `reuse` means **verify only** (read-only checks that the resource matches the plan). `create` creates only that resource. All use the `run` wrapper with `DRY_RUN=1` default. **Every script refuses to execute any write unless `docs/PROVISIONING_PLAN.md` contains a line that starts with `SIGN-OFF: APPROVED by`** (a unit test proves this). **You must never write that line yourself**; only the human does.
5. All names and regions come from variables, never literals: `LOC_APP` (East US), `LOC_SQL` (West US), `LOC_AI` (East US), `RG`, `RG_SQL`, `ACR`, `CAE`, `LAW`, `APPI`, `SQLSRV`, `SQLDB`, `STG`, `AIACC`, `ACS`, `ACS_EMAIL`, `API_APP`. The A:R19 default names apply **only** to resources the plan says to create (`assess-api`, `assessstg<suffix>`, `assess-acs-<suffix>`, `assess-email-<suffix>`).
6. `src/tools/probe.ts` (B6.3) with two additions: `sql` reports the **average round-trip time of 10 `SELECT 1` calls** and warns above 150 ms (East US to West US), and verifies the `assess` schema exists and that the app user cannot read any `dbo` table; `foundry` uses the style set by `FOUNDRY_API_STYLE`.
7. GitHub trust: prefer a user-assigned managed identity with a federated credential, scoped as narrowly as possible (B3 row 29).

**Stage 2: the human runs OC-0 at the office** (read-only discovery) and brings the output back. When the user gives you an "office report OC-0", **fill in `docs/PROVISIONING_PLAN.md`** from it (modes, SKU classes, regions, whether existing tables could collide), list every open question, and **stop** (B10): the human reviews it and records the sign-off themselves. **Because the repository is public, the plan uses placeholders for every real name and id** (`<SQL_SERVER>`, `<AI_RESOURCE>`, `<ACR>`, `<RG>`); the real values live only in the human's private notes outside the repository, and the human's variable block in the guide (section 3) is filled from those notes.

**Stage 3: after sign-off only** the human runs the provisioning checkpoints **OC-1A to OC-1H** in the guide, each as "reuse: verify" or "create: only if missing".

- **Verify at home:** `shellcheck`; forbidden-verb test; sign-off-gate test; `--plan` output saved to `docs/phase-reports/01-plan-output.txt`; probe unit tests.
- **Checkpoints:** **OC-0** discovery, **OC-PLAN** sign-off, **OC-1A** core (reuse or create) and budget, **OC-1B** existing SQL: schema and app user, **OC-1C** Blob, **OC-1D** existing AI resource, **OC-1E** email, **OC-1F** `assess-api` app, **OC-1H** probes.
- **Office order:** OC-0, OC-PLAN, OC-1A to OC-1G, then **OC-3** (first deploy; the probe tool lives in the image), then **OC-1H**, then **OC-2**, then OC-4 to OC-13.

### Phase 2: Database and API skeleton (A:2.x), inside a SHARED database
The existing database already belongs to the Assessment Portal. Our tables must never mix with or overwrite theirs.
- **Build:** everything in A:2.x **plus**: all objects live in a dedicated schema **`assess`** (config `DB_SCHEMA`, default `assess`). Every SQL statement uses schema-qualified names (`[assess].[users]`). `schema_migrations` lives in `assess`. The migration runner **does not create the schema** (the human creates it with the app user in OC-1B); if the schema is missing it exits with a clear message. A static test fails if any SQL in `src/repositories` or `src/migrations` uses an unqualified table name, or touches `dbo`.
- **Permission model (replaces A:1.4):** the app user owns only the `assess` schema and has `CREATE TABLE`; it must **not** be in `db_datareader`, `db_datawriter` or `db_ddladmin` (those would expose the portal's tables). Record this permission set in the ledger as UNVERIFIED (low confidence) with the fallback "ask the database owner to grant what the first migration error names".
- **Verify at home:** T1 `test:repo:memory`; T2 `sql` job green. In CI create the schema `assess` first, and also create a decoy table `dbo.portal_users` and a decoy `dbo.users`: assert that migrations and tests never read, write or alter them and that a name collision with `dbo.users` causes no problem.
- **Authored for the office:** `infra/azure/discovery/sql-inventory.sql`, the app-user and schema T-SQL (`scripts/db/create-app-user.sql`), unit-tested for syntax only.
- **Checkpoint:** **OC-2** (13 tables in schema `assess`; the existing `dbo` tables unchanged compared with OC-0).

### Phase 3: Container and first pipeline (A:3.x), into the EXISTING environment
- **Build:** Dockerfile, `.dockerignore`, App Insights wiring (no-op without connection string; sampling from `APPINSIGHTS_SAMPLING_PERCENT`), `scripts/e2e/smoke.sh`, E2E harness with `--target`, jobs `image` and guarded `deploy`. **Image repository name in the registry: `assess-api`** (override of the `api` name in A:3.5). The deploy job deploys **only** the app named by variable `API_APP_NAME`; it never touches the portal's apps.
- **Container size:** default **0.25 vCPU and 0.5 GiB**, min and max replicas 1, configurable through the plan (cost, B3 row 31).
- **Verify at home:** T2: image builds in CI, Trivy clean, container E2E (health, version header, request id) green; PR gating works; a deliberately failing test blocks the PR (A:3.9 a and d); the container exits non-zero with a bad `DATABASE_URL` and stops within 10 s of `SIGTERM`.
- **Authored for the office:** `infra/azure/containerapp-api.yaml` (probes, CPU and memory only; no env vars or secrets). The office creates the app from a placeholder image on port **80**, the real image listens on **8080**, so the deploy job runs `az containerapp ingress update -n <app> -g <rg> --target-port 8080` **before** updating the image.
- **Checkpoint:** **OC-3** (first real deploy, migrations run on the existing Azure SQL in schema `assess`, Application Insights shows requests, rollback proof).

### Phases 4 to 10 (A:4.x to A:10.x)
Build everything exactly as in A, with these differences:
- Tests are **dual-run** (B4.4) and carry tier tags. All cross-tenant, limits, DTO deep-scan, time-boundary and security tests are mandatory at T1 and T2.
- Live checks become `scripts/e2e/checks/NN-*.mjs` that work with both targets. Checks that need a real service declare `requires: ['ai']`, `['email']` or `['blob']`; with `local-container` they use the fakes or Azurite, with `azure` they use the real services.
- **Phase 5:** Blob is exercised for real in T2 through Azurite (real SDK). Azure Blob itself is T3.
- **Phase 6:** the Foundry adapter's implemented `v1` and `azure-deployments` styles are tested with HTTP interception, but neither is assumed compatible with the user-selected Phi Serverless API until verified (B3 row 27). Require an explicit supported style and keep live calls blocked until compatibility is proven. The approve rule is **equal to the configured count per section** (B3 row 23); the job engine race tests run on SQL in T2.
- **Phase 7:** ACS adapter tested with SDK mocks; the HTML email template is rendered to a file in CI as an artifact so the human can open and review it.
- **Phase 8:** the container E2E in CI runs the full candidate flow using the **test-only outbox route** (A:8.11). The human link-token step exists only at the office.
- **Phase 9:** AI marking tested with the fake and with HTTP interception; privacy and injection structure tests as in A:9.5.
- **Phase 10:** CSV and PDF exports fully verifiable at home, including the Devanagari font test.
- **Checkpoints:** **OC-4** (auth live), **OC-5** (Blob live), **OC-6** (verified Phi live generation), **OC-7** (real email), **OC-8** (candidate flow with real token, timer), **OC-9** (live AI marking), **OC-10** (live results and exports).

### Phase 11: Hardening (A:11.x), cost-aware
- **Build:** limits suite, fuzz suite, security tests, chaos tests (fakes), retention task, `docs/security.md`, KQL pack, `scripts/load/exam.js`, and `infra/azure/80-monitoring.sh` (authored, `--plan` in CI) with the **cheapest useful set** of alerts: failed requests, exceptions, job failures, restarts, plus the **budget alerts at 50, 80 and 100 percent of $25.00 ($12.50, $20.00, $25.00)**. The availability test is **optional** (the plan decides; it costs money). Add `AI_DAILY_TOKEN_CAP` (global safety cap) and `AI_MAX_OUTPUT_TOKENS`, and keep the per-tenant cap of 20 generation calls per day.
- **Changes to A:11.7 and A:11.8:** the **restore drill** becomes **read-only** (show `earliestRestoreDate` and retention); an actual point-in-time restore copies the shared portal database and costs money, so it is done **only if the database owner approves**, and the copy is deleted the same day. The **stress profile (100 users) is removed**; the load test has only the `target` profile (20 users) for at most 5 minutes, run **once**, after approval. Load-test CI smoke profile unchanged (5 users, 1 minute, against the CI container).
- **Verify at home:** T1 and T2 suites green.
- **Checkpoint:** **OC-11**.

### Phase 12: Full CI/CD (A:12.x)
- **Build:** the complete `deploy.yml`, `live-e2e.yml`, `rollback.yml`, `nightly.yml`, OpenAPI file and contract tests, coverage thresholds, `CODEOWNERS`, PR template, `dependabot.yml`, `docs/cicd.md`.
- **Verify at home:** proofs (a) to (e) of A:12.6 on the personal repo. Record run links in `docs/phase-reports/12-cicd.md`.
- **Authored for the office:** the deploy, smoke, live E2E, release-annotation and rollback stages (guarded).
- **Checkpoint:** **OC-12** (enable deploy, proofs f to h).

### Phase 13: Release and acceptance (A:13.x), within budget
- **Build:** `scripts/e2e/acceptance.mjs`, `scripts/db/seed-demo.mjs` (through the API), `docs/frontend-handover.md`, final document in the two-part form (B3 row 16). **Remove A:13.1** (the clean-slate rehearsal creates a second environment: too expensive and against zero-touch). Cost report: compare **actual** cost (from Cost Management, filled by the human) with the **$25 per month** ceiling; do not invent prices. `infra/azure/99-teardown.sh` (prints what it would delete first, asks for typed confirmation) deletes **only resources tagged `project=ai-assessment` and listed in the plan**, never a resource group and never the portal's resources.
- **Verify at home:** run the acceptance script against the CI container (`E2E_TARGET=local-container`).
- **Checkpoint:** **OC-13** (full acceptance, lock-down of the resources we created, handover).

## B8. Definition of Done for the home build (Home-DoD)

- [ ] All 37 endpoints implemented, in the OpenAPI file, covered by dual-run API tests (memory and SQL), and checked by the container E2E in CI.
- [ ] Every PDF limit has an automated test (A:11.1).
- [ ] Cross-tenant tests green on **both** backends.
- [ ] Candidate payload deep-scan green on both backends.
- [ ] Repository contract suite green on memory and SQL.
- [ ] Image builds in CI; Trivy and gitleaks clean; container E2E green.
- [ ] Pipeline proofs (a) to (e) recorded; deploy job exists, is guarded, and shows "deploy disabled" cleanly.
- [ ] Every Azure script passes `shellcheck` and `--plan`; every Azure adapter has mock tests; probe tool has unit tests.
- [ ] `docs/UNVERIFIED_AZURE_LEDGER.md` lists every Azure assumption with its checkpoint.
- [ ] `.env.azure.example` complete; no secrets or real resource names anywhere in git history.
- [ ] `docs/OFFICE_CONNECTION_AND_TESTING_GUIDE.md` matches what was built (B9).
- [ ] Phase 0 reconcile report closed; repository history scanned for secrets.
- [ ] Schema isolation tests (decoy `dbo` tables untouched) green on SQL.
- [ ] Approve rule "equal to configured count" tested.
- [ ] Both Foundry API styles covered by interception tests.
- [ ] `docs/PROVISIONING_PLAN.md` complete except the human's sign-off line.
- [ ] No frontend files created.

## B9. Keeping the office guide accurate (your duty)

The human will execute `docs/OFFICE_CONNECTION_AND_TESTING_GUIDE.md` without AI help. At the end of **every phase**:
1. Compare the guide's checkpoint for that phase with what you built: variable names, script names, workflow names, probe names, expected outputs, workflow inputs.
2. Edit the guide so every command, file path, secret name and expected output **exists and is exact**. Never leave a step the human cannot execute.
3. Add the new Azure assumptions to the ledger and cross-link them to the checkpoint.
4. In the phase report add "Guide updated: yes/no, sections changed".
At the end of Phase 13 produce the **handover bundle**: guide (as built), ledger, `.env.azure.example`, OpenAPI file, workflow list, and a one-page "first hour at the office" checklist at the top of the guide.

## B10. Stop conditions and what to ask the human

- **Hard stop after Phase 1 stage 1 until the human supplies the OC-0 report; hard stop after filling the plan until the human records `SIGN-OFF: APPROVED by`.** You never write that line. You may keep building Phases 2 to 13 at home meanwhile.
- Never ask for Azure credentials, keys or connection strings. If any appear in a message, tell the human to remove them and do not store or echo them.
- Ask the human only for: B3 row 2 items, a pasted CI log when `gh` is unavailable, a decision where A and B conflict, or a failing gate after three attempts.
- If a Prompt A step cannot be done without Docker or Azure, do **not** skip it silently: implement the authored or CI version, add it to the ledger, and name the checkpoint.

## B11. Your first reply and your final message

- **First reply:** at most 10 lines: the situation in your own words, the three tiers, the five biggest overrides, the list of checkpoint IDs, and "starting Phase 0". Then continue working without waiting.
- **Final message** (after Phase 13): at most 15 lines: Home-DoD status with the CI run link, number of ledger items still `UNVERIFIED`, list of office checkpoints (OC-1A to OC-13) all `PENDING`, the path of the guide, and the three riskiest unverified assumptions.

## B12. Session continuity: `docs/PROGRESS.md` (so the user never has to re-explain)

Create `docs/PROGRESS.md` right after your first reply and update it **at the end of every phase and before any session ends** (also when you stop because of a stop condition). Format:

```
# PROGRESS (maintained by the agent)
Last updated: <UTC date/time>   Current phase: <n>   Last commit: <sha>   Last CI run: <link or "none yet">

## Decisions in force (from the user; defaults if unanswered)
R1 globally unique email: <yes/no>   R5 min questions per section: <1 / equal to count>   R13 external api ingress until web exists: <yes/no>
gh CLI available and authenticated: <yes/no>

## Phase status
(Initial state: Phase 0 already exists in the repository (about 53 tests) and is marked `RECONCILE`; set it to `HOME-DONE` when the reconcile checklist is closed.)
| Phase | Status | Home gate (T1+T2) | CI run | Office checkpoint(s) | Office status |
|---|---|---|---|---|---|
| 0 | NOT STARTED / IN PROGRESS / HOME-DONE | PASS/FAIL | link | none | n/a |
| 1 | ... | ... | ... | OC-1A..1H | PENDING |
| ... one row per phase 0..13 ... |

Status words: NOT STARTED, IN PROGRESS, HOME-DONE (T1 and T2 green), OFFICE-PENDING, OFFICE-VERIFIED, BLOCKED.

## Unverified Azure items: <count> (see docs/UNVERIFIED_AZURE_LEDGER.md)
## Open questions for the user
## Next action (one sentence)
```
**Session start protocol:** read `docs/PROGRESS.md`, run `git status` and `git log -5`, state in one line where you are, continue from "Next action".
**Session end protocol:** commit, push the phase branch, update `docs/PROGRESS.md` and the guide, and write the "Next action".

## B13. Handling an office report

When the user pastes an office report (template in the guide, section 6):
0. **"office report OC-0"** (discovery output): fill `docs/PROVISIONING_PLAN.md` completely (modes, names, regions, SKUs, collision risks with existing tables, cost headroom questions), then stop for sign-off (B10).
1. Find the checkpoint rows in the ledger; set their status to `VERIFIED`, `FIXED-AT-OFFICE` or `FAILED` with the user's evidence.
2. If the report shows a defect, reproduce it at T1 or T2 where possible (a new failing test first), fix it, keep all tiers green, and tell the user which commit to pull and which checkpoint to re-run.
3. Fold every "what I changed that is not in the guide" item back into the guide and the scripts so the next person does not repeat it.
4. Update `docs/PROGRESS.md` (office status column) and state the next checkpoint the user can attempt.
5. Never claim a checkpoint passed unless the report shows its pass criteria (the guide's "Proceed when" line).

## B14. The guide's "Proceed when" rules are binding

Each office checkpoint in the guide has a **Proceed when (go/no-go)** line. Treat these as part of this specification: build the code, probes, workflows and test checks so that **each of those lines can actually be observed** by the human (for example "tokens_used > 0" requires that the job table stores tokens; "x-app-version equals the commit sha" requires that header). If a line cannot be observed with what exists, add what is missing and update the guide.

# END PROMPT B