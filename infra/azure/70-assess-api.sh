#!/usr/bin/env bash
# infra/azure/70-assess-api.sh — Create assess-api Container App + OIDC identity
# Phase 1, OC-1F. Creates ONLY assess-api; never touches the portal's apps.
# ─────────────────────────────────────────────────────────────────────────────
# Steps:
#   1. Verify / create the Container Apps environment (REUSE if it exists).
#   2. Create the assess-api container app from a placeholder image.
#   3. Create a user-assigned managed identity for the app.
#   4. Assign AcrPull to the managed identity on the registry.
#   5. Assign Contributor to the managed identity on the assess-api app only.
#   6. Create a GitHub federated credential for the OIDC deploy flow.
#   7. Print the client-id, tenant-id, subscription-id for GitHub secrets.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_run.sh"

RG="${RG:-<RG>}"
LOC_APP="${LOC_APP:-eastus}"
CAE="${CAE:-<CAE>}"                        # Container Apps environment name
ACR="${ACR:-<ACR>}"                        # container registry
API_APP="${API_APP:-assess-api}"           # the new container app (B3 row 28)
IDENTITY_NAME="${IDENTITY_NAME:-assess-api-identity}"
GITHUB_REPO="${GITHUB_REPO:-Siddharajparkar/We_Select-}"    # B3 row 29
GITHUB_BRANCH="${GITHUB_BRANCH:-main}"

MODE_CAE="${MODE_CAE:-reuse}"     # Container Apps environment: reuse|create
MODE_API="${MODE_API:-create}"    # assess-api container app: create|skip

echo "=== 70-assess-api.sh  MODE_CAE=${MODE_CAE}  MODE_API=${MODE_API}  DRY_RUN=${DRY_RUN} ==="
echo "SCOPE: This script only touches '${API_APP}'. Portal apps are never modified."

# ── Container Apps environment
case "${MODE_CAE}" in
  reuse)
    echo "--- Verifying Container Apps environment ---"
    run_read "az containerapp env show -g '${RG}' -n '${CAE}' --query '{name:name,location:location,provisioningState:properties.provisioningState}' -o json"
    ;;
  create)
    echo "--- Creating Container Apps environment ---"
    run "az containerapp env create -g '${RG}' -n '${CAE}' -l '${LOC_APP}'"
    ;;
  skip) echo "SKIP: CAE step skipped." ;;
esac

# ── assess-api app
case "${MODE_API}" in
  skip) echo "SKIP: API app step skipped." ;;
  create)
    echo "--- Creating user-assigned managed identity ---"
    run "az identity create -g '${RG}' -n '${IDENTITY_NAME}' -l '${LOC_APP}'"

    echo "--- Creating assess-api container app (placeholder image, port 8080) ---"
    run "az containerapp create \
      -g '${RG}' \
      -n '${API_APP}' \
      --environment '${CAE}' \
      --image 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest' \
      --target-port 8080 \
      --ingress external \
      --cpu 0.25 \
      --memory 0.5Gi \
      --min-replicas 1 \
      --max-replicas 1 \
      --user-assigned \"\$(az identity show -g '${RG}' -n '${IDENTITY_NAME}' --query id -o tsv 2>/dev/null || echo '<IDENTITY_ID>')\""

    echo "--- Assigning AcrPull to managed identity on the registry ---"
    run "az role assignment create \
      --role AcrPull \
      --assignee \"\$(az identity show -g '${RG}' -n '${IDENTITY_NAME}' --query principalId -o tsv 2>/dev/null || echo '<PRINCIPAL_ID>')\" \
      --scope \"\$(az acr show -g '${RG}' -n '${ACR}' --query id -o tsv 2>/dev/null || echo '<ACR_ID>')\""

    echo "--- Assigning Contributor to managed identity on assess-api only (B3 row 29) ---"
    run "az role assignment create \
      --role Contributor \
      --assignee \"\$(az identity show -g '${RG}' -n '${IDENTITY_NAME}' --query principalId -o tsv 2>/dev/null || echo '<PRINCIPAL_ID>')\" \
      --scope \"\$(az containerapp show -g '${RG}' -n '${API_APP}' --query id -o tsv 2>/dev/null || echo '<APP_ID>')\""

    echo "--- Creating GitHub OIDC federated credential ---"
    run "az identity federated-credential create \
      -g '${RG}' \
      --identity-name '${IDENTITY_NAME}' \
      -n 'github-deploy' \
      --issuer 'https://token.actions.githubusercontent.com' \
      --subject 'repo:${GITHUB_REPO}:ref:refs/heads/${GITHUB_BRANCH}' \
      --audiences 'api://AzureADTokenExchange'"

    echo ""
    echo "=== RECORD THESE VALUES AS GITHUB SECRETS (never commit them) ==="
    run_read "echo \"AZURE_CLIENT_ID=\$(az identity show -g '${RG}' -n '${IDENTITY_NAME}' --query clientId -o tsv 2>/dev/null || echo '<CLIENT_ID>')\""
    run_read "echo \"AZURE_TENANT_ID=\$(az account show --query tenantId -o tsv 2>/dev/null || echo '<TENANT_ID>')\""
    run_read "echo \"AZURE_SUBSCRIPTION_ID=\$(az account show --query id -o tsv 2>/dev/null || echo '<SUBSCRIPTION_ID>')\""
    echo "Add these three as GitHub repository secrets via Settings → Secrets."
    ;;
esac

echo "=== 70-assess-api.sh DONE ==="
