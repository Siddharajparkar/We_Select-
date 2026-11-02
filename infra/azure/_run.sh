#!/usr/bin/env bash
# infra/azure/_run.sh — shared run wrapper and sign-off guard
# ─────────────────────────────────────────────────────────────────────────────
# Source this file at the top of every provisioning script:
#   source "$(dirname "$0")/../_run.sh"
#
# Features:
#   1. DRY_RUN=1 (default): prints commands, does not execute.
#   2. SIGN-OFF GATE: refuses to write any Azure resource until
#      docs/PROVISIONING_PLAN.md contains a line starting with
#      "SIGN-OFF: APPROVED by" (B7 Phase 1 item 4 / B3 row 24).
#   3. Logging: every command (or dry-run) is printed with a timestamp.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

DRY_RUN="${DRY_RUN:-1}"
REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || echo ".")"
PLAN_FILE="${REPO_ROOT}/docs/PROVISIONING_PLAN.md"

# ── Sign-off gate ─────────────────────────────────────────────────────────────
# Called automatically before any write command.
_assert_signoff() {
  if [ ! -f "${PLAN_FILE}" ]; then
    echo "ERROR: ${PLAN_FILE} not found." >&2
    echo "  The provisioning plan must exist and be approved before any resource" >&2
    echo "  is created or modified." >&2
    exit 1
  fi

  if ! grep -qE '^SIGN-OFF: APPROVED by' "${PLAN_FILE}"; then
    echo "ERROR: No sign-off found in ${PLAN_FILE}." >&2
    echo "  The human must review the plan and write:" >&2
    echo "    SIGN-OFF: APPROVED by <name> on <date>" >&2
    echo "  before any write operations may proceed." >&2
    echo "" >&2
    echo "  Current status line:" >&2
    grep -E '^SIGN-OFF' "${PLAN_FILE}" 2>/dev/null || echo "  (no SIGN-OFF line found)" >&2
    exit 1
  fi
}

# ── run: execute a read-only command (always runs, even in DRY_RUN=1)
run_read() {
  local ts
  ts="$(date -u '+%H:%M:%S')"
  echo "[${ts} READ] $*"
  if [ "${DRY_RUN}" != "1" ]; then
    eval "$*"
  fi
}

# ── run: execute a WRITE command (requires sign-off; dry-run prints only)
run() {
  local ts
  ts="$(date -u '+%H:%M:%S')"
  if [ "${DRY_RUN}" = "1" ]; then
    echo "[${ts} DRY-RUN] $*"
  else
    _assert_signoff
    echo "[${ts} EXEC] $*"
    eval "$*"
  fi
}

# ── plan: same as run but with a "[PLAN]" prefix (used in --plan mode)
plan() {
  local ts
  ts="$(date -u '+%H:%M:%S')"
  echo "[${ts} PLAN] $*"
}

echo "[_run.sh] DRY_RUN=${DRY_RUN}  PLAN_FILE=${PLAN_FILE}"
