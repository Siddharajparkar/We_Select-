"""Phase 6 end-to-end against the BUILT IMAGE on SQL Server (GitHub Actions only; needs Docker + TEST_DATABASE_URL).

Runs the same live harness that is used against Azure (`scripts/e2e/run.py --upto 6`) so a green CI means the
image, the migrations (0001-0003), the real T-SQL job claim, the background loop and every endpoint work together.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest

from conftest import free_port

pytestmark = pytest.mark.container
IMAGE = os.environ.get("E2E_IMAGE")
DB_URL = os.environ.get("TEST_DATABASE_URL", "")
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _need_docker() -> None:
    if not IMAGE or not DB_URL or not shutil.which("docker"):
        pytest.skip("container tests need docker, E2E_IMAGE and TEST_DATABASE_URL (CI only)")


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=180)  # noqa: S603,S607


def test_full_harness_through_phase_6_against_the_container() -> None:
    port, name = free_port(), f"assess-p6-{uuid.uuid4().hex[:8]}"
    env = {
        "APP_ENV": "development", "REPO_BACKEND": "sql", "DATABASE_URL": DB_URL, "AI_MODE": "fake",
        "EMAIL_MODE": "fake", "FILES_MODE": "memory", "GIT_SHA": "p6-container", "PORT": str(port),
    }  # fmt: skip
    args = ["run", "-d", "--name", name, "--network", "host"]
    for k, v in env.items():
        args += ["-e", f"{k}={v}"]
    docker(*args, IMAGE)  # type: ignore[arg-type]
    try:
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                if httpx.get(f"http://127.0.0.1:{port}/api/v1/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(1)
        else:
            raise AssertionError(f"never healthy: {docker('logs', name, check=False).stdout[-800:]}")
        r = subprocess.run(  # noqa: S603
            [sys.executable, str(ROOT / "scripts/e2e/run.py"), "--base-url", f"http://127.0.0.1:{port}",
             "--upto", "6", "--expected-version", "p6-container"],
            capture_output=True, text=True, timeout=300, check=False,
        )  # fmt: skip
        assert r.returncode == 0 and "FAIL" not in r.stdout, (
            r.stdout[-2000:] + docker("logs", name, check=False).stdout[-1500:]
        )
        assert "phase06 generate_all_sections" in r.stdout
        logs = docker("logs", name, check=False).stdout
        assert "job_done" in logs and "job_failed" not in logs
        assert "Password=" not in logs
    finally:
        docker("rm", "-f", name, check=False)
