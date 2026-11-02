#!/usr/bin/env bash
# infra/azure/80-assess-api-config.sh — apply probes/resources/scale from assess-api.containerapp.yaml.
# Touches ONLY the assess-api app. DRY_RUN=1 by default; writes need the human SIGN-OFF line (see _run.sh).
# Secret VALUES are never handled here: a human sets them in the portal; the YAML only references names.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_run.sh"

RG="${RG:-<RG>}"
API_APP="${API_APP:-assess-api}"
YAML_FILE="${YAML_FILE:-${SCRIPT_DIR}/assess-api.containerapp.yaml}"

echo "=== 80-assess-api-config.sh  DRY_RUN=${DRY_RUN} ==="
echo "SCOPE: only '${API_APP}' is modified."

run_read "az containerapp show -g '${RG}' -n '${API_APP}' --query '{name:name,state:properties.provisioningState,fqdn:properties.configuration.ingress.fqdn}' -o json"
run "az containerapp update -g '${RG}' -n '${API_APP}' --yaml '${YAML_FILE}'"

echo "=== 80-assess-api-config.sh DONE ==="
