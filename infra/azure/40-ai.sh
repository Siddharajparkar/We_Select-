#!/usr/bin/env bash
# infra/azure/40-ai.sh — Verify existing AI Foundry resource and deployment
# Phase 1, OC-1D. REUSE only — never creates or modifies the AI resource.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_run.sh"

RG="${RG:-<RG>}"
AIACC="${AIACC:-<AI_RESOURCE>}"             # existing AI Foundry account name
FOUNDRY_DEPLOYMENT="${FOUNDRY_DEPLOYMENT:-<AI_DEPLOYMENT_NAME>}"

MODE_AI="${MODE_AI:-reuse}"

echo "=== 40-ai.sh  MODE=${MODE_AI}  DRY_RUN=${DRY_RUN} ==="
echo "NOTE: This script is REUSE-only. The AI resource already exists."

case "${MODE_AI}" in
  skip)
    echo "SKIP: AI step skipped."
    ;;
  reuse)
    echo "--- Verifying AI Foundry account ---"
    run_read "az cognitiveservices account show -g '${RG}' -n '${AIACC}' --query '{name:name,kind:kind,location:location,sku:sku.name,endpoint:properties.endpoint,state:properties.provisioningState}' -o json"
    echo "--- Listing deployments (names only, no keys) ---"
    run_read "az cognitiveservices account deployment list -g '${RG}' -n '${AIACC}' --query '[].{name:name,model:properties.model.name,version:properties.model.version,sku:sku.name,capacity:sku.capacity}' -o table"
    echo "--- Confirm target deployment '${FOUNDRY_DEPLOYMENT}' exists ---"
    run_read "az cognitiveservices account deployment show -g '${RG}' -n '${AIACC}' --deployment-name '${FOUNDRY_DEPLOYMENT}' --query '{name:name,model:properties.model.name,version:properties.model.version,state:properties.provisioningState}' -o json 2>/dev/null || echo 'Deployment not found — check FOUNDRY_DEPLOYMENT value'"
    echo "REUSE: AI Foundry resource verified. Record real endpoint and deployment"
    echo "  name in your local notes (never commit to the repository)."
    echo "  Update FOUNDRY_ENDPOINT and FOUNDRY_DEPLOYMENT in Container App secrets."
    ;;
  *)
    echo "ERROR: Unknown MODE_AI='${MODE_AI}'. Use reuse|skip." >&2; exit 1;;
esac

echo "=== 40-ai.sh DONE ==="
