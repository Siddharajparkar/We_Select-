#!/usr/bin/env bash
# scripts/run-plan.sh — Runs all provisioning scripts in DRY_RUN=1 mode to generate plan output
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export DRY_RUN=1

scripts=(
  "${REPO_ROOT}/infra/azure/10-core.sh"
  "${REPO_ROOT}/infra/azure/20-sql.sh"
  "${REPO_ROOT}/infra/azure/30-blob.sh"
  "${REPO_ROOT}/infra/azure/40-ai.sh"
  "${REPO_ROOT}/infra/azure/50-email.sh"
  "${REPO_ROOT}/infra/azure/60-registry.sh"
  "${REPO_ROOT}/infra/azure/70-assess-api.sh"
  "${REPO_ROOT}/infra/azure/80-assess-api-config.sh"
)

echo "# Phase 1 Dry-Run Provisioning Plan Output"
echo "# Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "# Mode: DRY_RUN=1 (no writes executed, sign-off gate enforced)"
echo ""

echo "================================================================================"
echo "PART 1: DEFAULT / REUSE MODES (verification of existing shared resources)"
echo "================================================================================"
echo ""

for s in "${scripts[@]}"; do
  echo "--- $(basename "$s") ---"
  bash "$s"
  echo ""
done

echo "================================================================================"
echo "PART 2: CREATE MODES (targeted creation of new dedicated resources only)"
echo "================================================================================"
echo ""

MODE_CORE=create bash "${REPO_ROOT}/infra/azure/10-core.sh"
echo ""
MODE_BLOB=create bash "${REPO_ROOT}/infra/azure/30-blob.sh"
echo ""
MODE_EMAIL=create bash "${REPO_ROOT}/infra/azure/50-email.sh"
echo ""
MODE_REGISTRY=create bash "${REPO_ROOT}/infra/azure/60-registry.sh"
echo ""
bash "${REPO_ROOT}/infra/azure/70-assess-api.sh"
echo ""
