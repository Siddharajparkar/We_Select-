#!/usr/bin/env bash
# Post-deploy smoke test (Prompt A 3.6).
# Retries for up to 120 s (5 s sleeps): /api/v1/health must return {"status":"ok"}, and the
# x-app-version header must equal EXPECTED_VERSION - proving the NEW revision answered.
#
# Usage: API_URL=https://<fqdn> EXPECTED_VERSION=<git sha> bash scripts/e2e/smoke.sh
set -euo pipefail

: "${API_URL:?API_URL is required}"
: "${EXPECTED_VERSION:?EXPECTED_VERSION is required}"
TIMEOUT_S="${SMOKE_TIMEOUT_S:-120}"
SLEEP_S="${SMOKE_SLEEP_S:-5}"
URL="${API_URL%/}/api/v1/health"

deadline=$((SECONDS + TIMEOUT_S))
last="no response"
while [ "${SECONDS}" -lt "${deadline}" ]; do
  hdr="$(mktemp)"
  if body="$(curl --fail --silent --show-error --max-time 10 -D "${hdr}" "${URL}" 2>&1)"; then
    version="$(grep -i '^x-app-version:' "${hdr}" | head -n1 | cut -d: -f2- | tr -d '[:space:]')"
    if [ "${body}" = '{"status":"ok"}' ] && [ "${version}" = "${EXPECTED_VERSION}" ]; then
      echo "SMOKE PASS: ${URL} version=${version}"
      rm -f "${hdr}"
      exit 0
    fi
    last="body=${body} version=${version:-none} (expected ${EXPECTED_VERSION})"
  else
    last="${body}"
  fi
  rm -f "${hdr}"
  echo "smoke: waiting... ${last}"
  sleep "${SLEEP_S}"
done

echo "SMOKE FAIL after ${TIMEOUT_S}s: ${last}" >&2
exit 1
