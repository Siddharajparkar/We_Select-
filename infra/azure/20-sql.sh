#!/usr/bin/env bash
# infra/azure/20-sql.sh — Verify existing SQL, create assess schema and app user
# Phase 1, OC-1B: schema + app user inside the EXISTING database.
# ─────────────────────────────────────────────────────────────────────────────
# The SQL server and database are NEVER created here (they are existing).
# Only DB-CHANGE actions: schema assess + app user owning that schema.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/azure/_run.sh
source "${SCRIPT_DIR}/_run.sh"

RG_SQL="${RG_SQL:-<RG_SQL>}"
SQLSRV="${SQLSRV:-<SQL_SERVER>}"
SQLDB="${SQLDB:-<SQL_DATABASE>}"
DB_APP_USER="${DB_APP_USER:-assess_app}"
DB_APP_PASS="${DB_APP_PASS:-<from-keyvault-or-env>}"   # never committed
DB_SCHEMA="${DB_SCHEMA:-assess}"

MODE_SQL="${MODE_SQL:-reuse}"

echo "=== 20-sql.sh  MODE=${MODE_SQL}  DRY_RUN=${DRY_RUN} ==="

case "${MODE_SQL}" in
  skip)
    echo "SKIP: SQL step skipped."
    ;;
  reuse)
    echo "--- Verifying SQL server ---"
    run_read "az sql server show -g '${RG_SQL}' -n '${SQLSRV}' --query '{name:name,location:location,fullyQualifiedDomainName:fullyQualifiedDomainName,state:state}' -o json"
    echo "--- Verifying SQL database ---"
    run_read "az sql db show -g '${RG_SQL}' -s '${SQLSRV}' -n '${SQLDB}' --query '{name:name,edition:edition,status:status}' -o json"
    echo "REUSE: SQL server and database verified (read-only)."
    echo "NOTE: Schema '${DB_SCHEMA}' and app user '${DB_APP_USER}' must be created"
    echo "  via scripts/db/create-app-user.sql in the Portal Query Editor (OC-1B)."
    ;;
  db-change)
    echo "--- Schema and app-user creation is done in the Portal Query Editor ---"
    echo "--- Run: scripts/db/create-app-user.sql (see OC-1B in the office guide) ---"
    echo "--- This script cannot execute T-SQL directly from Cloud Shell ---"
    echo "--- without storing credentials (forbidden). ---"
    echo "DB-CHANGE: Instructions printed. Execute SQL manually per guide."
    ;;
  *)
    echo "ERROR: Unknown MODE_SQL='${MODE_SQL}'. Use reuse|db-change|skip." >&2
    exit 1
    ;;
esac

echo "=== 20-sql.sh DONE ==="
