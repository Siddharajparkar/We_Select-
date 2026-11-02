"""Phase 3 end-to-end: a REAL uvicorn process, driven over HTTP by pytest, the E2E harness, smoke.sh and the Postman runner."""

from __future__ import annotations

import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

from conftest import start_server, wait_ready

pytestmark = pytest.mark.e2e

REPO = Path(__file__).resolve().parents[3]
POSTMAN = REPO / "tests" / "phase3" / "postman"
VERSION = "e2e-sha-0001"  # set by conftest.start_server


def test_health_over_a_real_socket(live_server: str) -> None:
    r = httpx.get(f"{live_server}/api/v1/health")
    assert r.status_code == 200 and r.text == '{"status":"ok"}'
    assert r.headers["x-app-version"] == VERSION


def test_error_paths_over_a_real_socket(live_server: str) -> None:
    assert httpx.get(f"{live_server}/api/v1/nope").json() == {
        "error": {"code": "NOT_FOUND", "message": "Route not found"}
    }
    assert httpx.post(f"{live_server}/api/v1/health", content=b"x" * 1_200_000).status_code == 413
    assert httpx.get(f"{live_server}/api/v1/health").status_code == 200  # still serving


def test_fifty_concurrent_requests_all_succeed(live_server: str) -> None:
    with ThreadPoolExecutor(max_workers=10) as pool:
        codes = list(pool.map(lambda _: httpx.get(f"{live_server}/api/v1/health").status_code, range(50)))
    assert codes == [200] * 50


def test_graceful_json_access_log_is_written_to_stdout() -> None:
    proc, base = start_server()
    try:
        wait_ready(base, proc)
        httpx.get(f"{base}/api/v1/health", headers={"x-request-id": "log-e2e-1"})
    finally:
        proc.terminate()
        out, _ = proc.communicate(timeout=15)
    assert b'"requestId": "log-e2e-1"' in out and b'"path": "/api/v1/health"' in out


def test_e2e_harness_passes_with_expected_version(live_server: str) -> None:
    r = subprocess.run([sys.executable, str(REPO / "scripts/e2e/run.py"), "--base-url", live_server, "--upto", "3", "--expected-version", VERSION],  # noqa: S603
                       capture_output=True, text=True, timeout=60)  # fmt: skip
    assert r.returncode == 0, r.stdout + r.stderr
    assert "E2E PASS: 9/9" in r.stdout


def test_e2e_harness_detects_a_stale_revision(live_server: str) -> None:
    r = subprocess.run([sys.executable, str(REPO / "scripts/e2e/run.py"), "--base-url", live_server, "--expected-version", "previous-sha"],  # noqa: S603
                       capture_output=True, text=True, timeout=60)  # fmt: skip
    assert r.returncode == 1 and "old revision still answering" in r.stdout


def test_smoke_script_against_the_real_server(live_server: str) -> None:
    ok = subprocess.run(["bash", str(REPO / "scripts/e2e/smoke.sh")], capture_output=True, text=True, timeout=30,  # noqa: S603,S607
                        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "API_URL": live_server, "EXPECTED_VERSION": VERSION})  # fmt: skip
    assert ok.returncode == 0 and "SMOKE PASS" in ok.stdout
    bad = subprocess.run(["bash", str(REPO / "scripts/e2e/smoke.sh")], capture_output=True, text=True, timeout=30,  # noqa: S603,S607
                         env={"PATH": "/usr/bin:/bin:/usr/local/bin", "API_URL": live_server, "EXPECTED_VERSION": "nope", "SMOKE_TIMEOUT_S": "2", "SMOKE_SLEEP_S": "1"})  # fmt: skip
    assert bad.returncode == 1


@pytest.mark.parametrize("collection", ["unit", "integration", "e2e"])
def test_postman_collections_pass_against_the_real_server(live_server: str, collection: str) -> None:
    r = subprocess.run([sys.executable, str(POSTMAN / "run_collection.py"), "--base-url", live_server, "--collection", collection,  # noqa: S603
                        "--expected-version", VERSION, "--docs-status", "200"], capture_output=True, text=True, timeout=60)  # fmt: skip
    assert r.returncode == 0, r.stdout + r.stderr
    assert "assertions passed" in r.stdout and "FAIL" not in r.stdout


def test_postman_e2e_fails_when_the_deployed_version_is_wrong(live_server: str) -> None:
    r = subprocess.run([sys.executable, str(POSTMAN / "run_collection.py"), "--base-url", live_server, "--collection", "e2e",  # noqa: S603
                        "--expected-version", "someone-elses-sha"], capture_output=True, text=True, timeout=60)  # fmt: skip
    assert r.returncode == 1 and "x-app-version" in r.stdout


# ── process lifecycle ─────────────────────────────────────────────────────────────────────
def test_sigterm_stops_the_server_within_10_seconds() -> None:
    proc, base = start_server()
    wait_ready(base, proc)
    started = time.time()
    proc.terminate()
    out, _ = proc.communicate(timeout=15)
    # uvicorn >= 0.29 finishes its graceful shutdown (lifespan runs) and then re-raises SIGTERM,
    # so the exit status is 0 or "killed by SIGTERM" (-15 here, 143 in a container) - never a crash.
    assert time.time() - started < 10 and proc.returncode in (0, -15)
    assert b"shutdown complete" in out, "lifespan shutdown (engine dispose) must run on SIGTERM"


def test_invalid_production_config_exits_non_zero_without_leaking_secrets() -> None:
    proc, _ = start_server({"APP_ENV": "production", "SESSION_SECRET": "ProdSecretValueXYZ"})
    out, _ = proc.communicate(timeout=30)
    assert proc.returncode != 0
    assert b"AI_MODE must be 'azure' in production" in out and b"ProdSecretValueXYZ" not in out


def test_unreachable_database_exits_non_zero_without_leaking_the_password() -> None:
    pytest.importorskip("pyodbc", reason="pyodbc/ODBC driver not available on this machine (runs in CI)")
    proc, _ = start_server(
        {
            "REPO_BACKEND": "sql",
            "DATABASE_URL": "Server=tcp:127.0.0.1,1;Database=d;User ID=u;Password=SuperSecretPw9;Connection Timeout=2",
        }
    )
    out, _ = proc.communicate(timeout=120)
    assert proc.returncode != 0
    assert b"SuperSecretPw9" not in out
