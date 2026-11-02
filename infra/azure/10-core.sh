#!/usr/bin/env bash
# infra/azure/10-core.sh — Verify / create core infrastructure
# Phase 1, OC-1A: Log Analytics, Application Insights, budget.
# ─────────────────────────────────────────────────────────────
# Requires: source ../_run.sh  (sign-off gate + DRY_RUN)
# MODE_CORE: reuse | create | skip
# ─────────────────────────────────────────────────────────────
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/azure/_run.sh
source "${SCRIPT_DIR}/_run.sh"

# ── Variables (set in Cloud Shell; placeholders committed, real values local)
RG="${RG:-<RG>}"
LOC_APP="${LOC_APP:-eastus}"
LAW="${LAW:-<LAW>}"          # Log Analytics workspace name
APPI="${APPI:-<APPI>}"       # Application Insights name
BUDGET_NAME="${BUDGET_NAME:-assess-api-budget}"
BUDGET_AMOUNT="${BUDGET_AMOUNT:-25}"
BUDGET_EMAIL="${BUDGET_EMAIL:-<BUDGET_EMAIL>}"   # filled at office, never committed

MODE_CORE="${MODE_CORE:-reuse}"

echo "=== 10-core.sh  MODE=${MODE_CORE}  DRY_RUN=${DRY_RUN} ==="

case "${MODE_CORE}" in
  skip)
    echo "SKIP: Core infrastructure skipped."
    ;;
  reuse)
    echo "--- Verifying Log Analytics workspace ---"
    run_read "az monitor log-analytics workspace show -g '${RG}' -n '${LAW}' --query '{name:name,location:location,sku:sku,retentionInDays:retentionInDays}' -o json"
    echo "--- Verifying Application Insights ---"
    run_read "az monitor app-insights component show -g '${RG}' --app '${APPI}' --query '{name:name,location:location,instrumentationKey:\"[MASKED]\",connectionString:\"[MASKED]\"}' -o json 2>/dev/null || az resource show -g '${RG}' --resource-type Microsoft.Insights/components -n '${APPI}' --query '{name:name,location:location}' -o json"
    echo "REUSE: Core infrastructure verified."
    ;;
  create)
    echo "--- Creating Log Analytics workspace ---"
    run "az monitor log-analytics workspace create -g '${RG}' -n '${LAW}' -l '${LOC_APP}' --sku PerGB2018 --retention-time 30"
    echo "--- Creating Application Insights ---"
    run "az monitor app-insights component create -g '${RG}' -n '${APPI}' -l '${LOC_APP}' --application-type web --workspace \"\$(az monitor log-analytics workspace show -g '${RG}' -n '${LAW}' --query customerId -o tsv)\""
    echo "--- Creating budget (alerts at 50%, 80%, 100%) ---"
    run "az consumption budget create --resource-group '${RG}' --budget-name '${BUDGET_NAME}' --amount ${BUDGET_AMOUNT} --category Cost --time-grain Monthly --notifications '{\"alert50\":{\"enabled\":true,\"operator\":\"GreaterThanOrEqualTo\",\"threshold\":50,\"contactEmails\":[\"${BUDGET_EMAIL}\"],\"thresholdType\":\"Actual\"},\"alert80\":{\"enabled\":true,\"operator\":\"GreaterThanOrEqualTo\",\"threshold\":80,\"contactEmails\":[\"${BUDGET_EMAIL}\"],\"thresholdType\":\"Actual\"},\"alert100\":{\"enabled\":true,\"operator\":\"GreaterThanOrEqualTo\",\"threshold\":100,\"contactEmails\":[\"${BUDGET_EMAIL}\"],\"thresholdType\":\"Actual\"}}'"
    echo "CREATE: Core infrastructure created."
    ;;
  *)
    echo "ERROR: Unknown MODE_CORE='${MODE_CORE}'. Use reuse|create|skip." >&2
    exit 1
    ;;
esac

echo "=== 10-core.sh DONE ==="
