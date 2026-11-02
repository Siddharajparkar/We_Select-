#!/usr/bin/env bash
# infra/azure/30-blob.sh — Verify / create Blob Storage for jd-files
# Phase 1, OC-1C.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_run.sh"

RG="${RG:-<RG>}"
LOC_APP="${LOC_APP:-eastus}"
STG="${STG:-<STG>}"                  # storage account name
BLOB_CONTAINER="${BLOB_CONTAINER:-jd-files}"
MODE_BLOB="${MODE_BLOB:-create}"

echo "=== 30-blob.sh  MODE=${MODE_BLOB}  DRY_RUN=${DRY_RUN} ==="

case "${MODE_BLOB}" in
  skip)
    echo "SKIP: Blob storage step skipped."
    ;;
  reuse)
    echo "--- Verifying storage account ---"
    run_read "az storage account show -g '${RG}' -n '${STG}' --query '{name:name,location:location,sku:sku.name,allowBlobPublicAccess:allowBlobPublicAccess,minimumTlsVersion:minimumTlsVersion}' -o json"
    echo "--- Verifying container ---"
    run_read "az storage container show -n '${BLOB_CONTAINER}' --account-name '${STG}' --auth-mode login --query '{name:name,publicAccess:properties.publicAccess}' -o json 2>/dev/null || echo 'container not found — may need MODE_BLOB=create'"
    echo "REUSE: Blob storage verified."
    ;;
  create)
    echo "--- Creating storage account (Standard LRS, no public blob access) ---"
    run "az storage account create -g '${RG}' -n '${STG}' -l '${LOC_APP}' --sku Standard_LRS --kind StorageV2 --allow-blob-public-access false --min-tls-version TLS1_2 --https-only true"
    echo "--- Creating private blob container: ${BLOB_CONTAINER} ---"
    run "az storage container create -n '${BLOB_CONTAINER}' --account-name '${STG}' --auth-mode login --public-access off"
    echo "CREATE: Blob storage and container created."
    ;;
  *)
    echo "ERROR: Unknown MODE_BLOB='${MODE_BLOB}'. Use reuse|create|skip." >&2; exit 1;;
esac

echo "=== 30-blob.sh DONE ==="
