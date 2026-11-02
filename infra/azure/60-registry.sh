#!/usr/bin/env bash
# infra/azure/60-registry.sh — Verify / create Container Registry
# Phase 1, OC-1A (ACR portion). REUSE if the portal already has one.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_run.sh"

RG="${RG:-<RG>}"
LOC_APP="${LOC_APP:-eastus}"
ACR="${ACR:-<ACR>}"      # container registry name
MODE_ACR="${MODE_ACR:-${MODE_REGISTRY:-create}}"

echo "=== 60-registry.sh  MODE=${MODE_ACR}  DRY_RUN=${DRY_RUN} ==="

case "${MODE_ACR}" in
  skip)
    echo "SKIP: Registry step skipped."
    ;;
  reuse)
    echo "--- Verifying ACR ---"
    run_read "az acr show -g '${RG}' -n '${ACR}' --query '{name:name,location:location,sku:sku.name,loginServer:loginServer,adminUserEnabled:adminUserEnabled}' -o json"
    echo "REUSE: Registry verified."
    ;;
  create)
    echo "--- Creating Container Registry (Basic SKU, cost-optimal for \$25 ceiling) ---"
    run "az acr create -g '${RG}' -n '${ACR}' -l '${LOC_APP}' --sku Basic --admin-enabled false"
    echo "CREATE: Registry created. Login server: ${ACR}.azurecr.io"
    ;;
  *)
    echo "ERROR: Unknown MODE_ACR='${MODE_ACR}'. Use reuse|create|skip." >&2; exit 1;;
esac

echo "=== 60-registry.sh DONE ==="
