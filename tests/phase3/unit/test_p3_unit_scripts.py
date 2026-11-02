"""Phase 3 unit: smoke.sh and the live E2E harness behave correctly against a stub server."""

from __future__ import annotations

import http.server
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SMOKE = REPO / "scripts" / "e2e" / "smoke.sh"
RUNNER = REPO / "scripts" / "e2e" / "run.py"


class _Handler(http.server.BaseHTTPRequestHandler):
    body = b'{"status":"ok"}'
    version = "sha-new"
    status = 200

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(self.status)
        self.send_header("content-type", "application/json")
        self.send_header("x-app-version", self.version)
        self.send_header("x-request-id", self.headers.get("x-request-id", "gen"))
        self.send_header("x-content-type-options", "nosniff")
        self.send_header("cache-control", "no-store")
        self.end_headers()
        if self.path.endswith("health"):
            self.wfile.write(self.body)
        else:
            self.wfile.write(b'{"error":{"code":"NOT_FOUND","message":"Route not found"}}')

    def log_message(self, *a: object) -> None:
        pass


@pytest.fixture
def stub() -> Iterator[tuple[str, type[_Handler]]]:
    handler = type("H", (_Handler,), {})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", handler
    srv.shutdown()


def smoke(url: str, expected: str, timeout: str = "3") -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "API_URL": url, "EXPECTED_VERSION": expected, "SMOKE_TIMEOUT_S": timeout, "SMOKE_SLEEP_S": "1"}
    return subprocess.run(["bash", str(SMOKE)], env=env, capture_output=True, text=True, timeout=30)  # noqa: S603,S607


def test_smoke_passes_when_new_revision_answers(stub) -> None:  # type: ignore[no-untyped-def]
    url, _ = stub
    r = smoke(url, "sha-new")
    assert r.returncode == 0 and "SMOKE PASS" in r.stdout


def test_smoke_fails_when_old_revision_is_still_answering(stub) -> None:  # type: ignore[no-untyped-def]
    url, h = stub
    h.version = "sha-OLD"
    r = smoke(url, "sha-new")
    assert r.returncode == 1 and "SMOKE FAIL" in r.stderr and "sha-OLD" in r.stdout


def test_smoke_fails_on_wrong_body_and_on_error_status(stub) -> None:  # type: ignore[no-untyped-def]
    url, h = stub
    h.body = b'{"status":"degraded"}'
    assert smoke(url, "sha-new").returncode == 1
    h.body, h.status = b'{"status":"ok"}', 503
    assert smoke(url, "sha-new").returncode == 1


def test_smoke_retries_until_service_comes_up(stub) -> None:  # type: ignore[no-untyped-def]
    url, h = stub
    h.status = 503

    def recover() -> None:
        import time

        time.sleep(1.5)
        h.status = 200

    threading.Thread(target=recover, daemon=True).start()
    r = smoke(url, "sha-new", timeout="10")
    assert r.returncode == 0 and "waiting" in r.stdout


def test_smoke_requires_its_inputs() -> None:
    env = {k: v for k, v in os.environ.items() if k not in {"API_URL", "EXPECTED_VERSION"}}
    r = subprocess.run(["bash", str(SMOKE)], env=env, capture_output=True, text=True)  # noqa: S603,S607
    assert r.returncode != 0 and "API_URL is required" in r.stderr


def test_smoke_is_strict_bash() -> None:
    text = SMOKE.read_text()
    assert text.startswith("#!/usr/bin/env bash") and "set -euo pipefail" in text


def harness(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), "--base-url", url, *args], capture_output=True, text=True, timeout=60
    )  # noqa: S603


def test_harness_passes_against_a_conforming_server(stub) -> None:  # type: ignore[no-untyped-def]
    url, h = stub

    # the stub is not the real API: only phase 0/health-level checks that it can satisfy
    r = harness(url, "--upto", "0")
    assert "phase00 health_returns_contract_body" in r.stdout
    assert "PASS phase00 health_returns_contract_body" in r.stdout


def test_harness_fails_when_expected_version_differs(stub) -> None:  # type: ignore[no-untyped-def]
    url, h = stub
    r = harness(url, "--upto", "3", "--expected-version", "some-other-sha")
    assert r.returncode == 1
    assert "FAIL phase03 version_matches_expected_when_given" in r.stdout
    assert "old revision still answering" in r.stdout


def test_harness_upto_limits_phases(stub) -> None:  # type: ignore[no-untyped-def]
    url, _ = stub
    r = harness(url, "--upto", "0")
    assert "phase03" not in r.stdout and "phase00" in r.stdout


def test_harness_reports_network_errors_as_failures() -> None:
    r = harness("http://127.0.0.1:9", "--upto", "0")
    assert r.returncode == 1 and "FAIL phase00" in r.stdout and "network" in r.stdout
