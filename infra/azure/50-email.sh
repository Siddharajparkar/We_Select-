#!/usr/bin/env bash
# infra/azure/50-email.sh — Verify / create Azure Communication Services
# Phase 1, OC-1E. Azure-managed email domain (decision h).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_run.sh"

RG="${RG:-<RG>}"
LOC_APP="${LOC_APP:-eastus}"
ACS="${ACS:-<ACS>}"                     # ACS resource name (assess-acs-<suffix>)
ACS_EMAIL="${ACS_EMAIL:-<ACS_EMAIL>}"   # Email Communication Services name

MODE_EMAIL="${MODE_EMAIL:-create}"

echo "=== 50-email.sh  MODE=${MODE_EMAIL}  DRY_RUN=${DRY_RUN} ==="

case "${MODE_EMAIL}" in
  skip)
    echo "SKIP: Email step skipped."
    ;;
  reuse)
    echo "--- Verifying ACS resource ---"
    run_read "az communication show -g '${RG}' -n '${ACS}' --query '{name:name,location:location,dataLocation:properties.dataLocation,state:properties.provisioningState}' -o json 2>/dev/null || az resource show -g '${RG}' --resource-type Microsoft.Communication/CommunicationServices -n '${ACS}' --query '{name:name}' -o json"
    echo "REUSE: ACS verified."
    ;;
  create)
    echo "--- Creating Communication Services resource ---"
    run "az communication create -g '${RG}' -n '${ACS}' -l global --data-location unitedstates"
    echo "--- Creating Email Communication Services ---"
    run "az communication email create -g '${RG}' -n '${ACS_EMAIL}' -l '${LOC_APP}'"
    echo "--- Adding Azure-managed domain (decision h) ---"
    run "az communication email domain create -g '${RG}' -n 'AzureManagedDomain' --email-service-name '${ACS_EMAIL}' -l '${LOC_APP}' --domain-management AzureManaged"
    echo "--- Linking email domain to ACS ---"
    run "az communication link-notification-hub -g '${RG}' -n '${ACS}' --connection-string \"\$(az communication list-key -g '${RG}' -n '${ACS}' --query primaryConnectionString -o tsv 2>/dev/null || echo '<connection-string>')\" --hub-name '${ACS_EMAIL}'"
    echo "CREATE: ACS and email domain created."
    echo "  Record the sender address: DoNotReply@<domain>.azurecomm.net"
    echo "  Add as Container App secret ACS_SENDER (never commit)."
    ;;
  *)
    echo "ERROR: Unknown MODE_EMAIL='${MODE_EMAIL}'. Use reuse|create|skip." >&2; exit 1;;
esac

echo "=== 50-email.sh DONE ==="
