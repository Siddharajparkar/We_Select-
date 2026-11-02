# Runbook (assess-api)

All commands run in Azure Cloud Shell on the organisation laptop. Use placeholders; never paste secrets anywhere.

## Health
`curl -s https://<APP_FQDN>/api/v1/health` returns `{"status":"ok"}`; `x-app-version` shows the deployed commit.

## Roll back manually
1. `az containerapp revision list -g <RG> -n assess-api -o table`
2. Previous image: `az containerapp show -g <RG> -n assess-api --query properties.template.containers[0].image -o tsv` (compare with the workflow log).
3. `az containerapp update -g <RG> -n assess-api --image <ACR>.azurecr.io/assess-api:<PREVIOUS_SHA>`
4. Re-check health and `x-app-version`.
The `rollback.yml` workflow does the same from GitHub when `vars.AZURE_DEPLOY_ENABLED == 'true'`.

## Logs
`az containerapp logs show -g <RG> -n assess-api --follow` or Log Analytics. Logs are JSON, one per line, secrets redacted, every line carries `requestId` when available.

## Migrations
Run automatically at startup under `sp_getapplock`. Manual: `python -m app.migrations.runner` with `DATABASE_URL` set in the session (never echoed).

## Exit codes
Exit 143 / -15 after SIGTERM is normal (graceful shutdown: 8 s for open requests, then up to 20 s for running background jobs).

## Background jobs (generation)
`SELECT TOP 20 id, type, status, attempts, error, run_after, tokens_used FROM assess.jobs ORDER BY created_at DESC;`
- `queued` with `run_after` in the future: waiting for the retry back-off (5 s x attempt, or the AI's Retry-After).
- `running` for more than 5 minutes: the worker died; the loop re-queues it at start-up and every minute.
- `failed`: `error` is a readable message, `result_json` holds `{"code": ...}` (`AI_OUTPUT_INVALID`, `AI_TIMEOUT`, `CONFLICT`, ...).
Log lines: `job_started`, `job_done`, `job_retry`, `job_failed`, `job_recovered` (ids, types, durations, tokens; never prompts or job descriptions).
Switch the loop off with `JOB_LOOP_ENABLED=false` (jobs then stay queued).
