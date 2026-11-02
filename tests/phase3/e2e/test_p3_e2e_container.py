"""Phase 3 end-to-end against the BUILT IMAGE (GitHub Actions only: needs Docker, E2E_IMAGE and TEST_DATABASE_URL).

Developer machines have no Docker, so these skip locally and run in the `container` CI job.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import uuid

import httpx
import pytest

from conftest import free_port

pytestmark = pytest.mark.container

IMAGE = os.environ.get("E2E_IMAGE")
DB_URL = os.environ.get("TEST_DATABASE_URL", "")
EXPECTED = os.environ.get("E2E_EXPECTED_VERSION", "")


@pytest.fixture(autouse=True)
def _need_docker() -> None:
    if not IMAGE or not DB_URL or not shutil.which("docker"):
        pytest.skip("container tests need docker, E2E_IMAGE and TEST_DATABASE_URL (CI only)")


def docker(*args: str, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=timeout)  # noqa: S603,S607


def run_container(env: dict[str, str], port: int) -> str:
    name = f"assess-e2e-{uuid.uuid4().hex[:8]}"
    args = ["run", "-d", "--name", name, "--network", "host", "-e", f"PORT={port}"]
    for k, v in env.items():
        args += ["-e", f"{k}={v}"]
    docker(*args, IMAGE)  # type: ignore[arg-type]
    return name


def wait_healthy(port: int, name: str, timeout: int = 90) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = docker("inspect", "-f", "{{.State.Running}}", name, check=False).stdout.strip()
        if state != "true":
            raise AssertionError(f"container stopped: {docker('logs', name, check=False).stdout[-800:]}")
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/v1/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(1)
    raise TimeoutError("container never became healthy")


PROD_ENV = {
    "REPO_BACKEND": "sql", "AI_MODE": "fake", "EMAIL_MODE": "fake", "FILES_MODE": "memory",
    "APP_ENV": "development",  # production would (correctly) refuse fakes; the image defaults to production
}  # fmt: skip


def test_container_serves_health_with_the_commit_sha_and_applies_migrations() -> None:
    port = free_port()
    name = run_container({**PROD_ENV, "DATABASE_URL": DB_URL, "GIT_SHA": EXPECTED or "ci"}, port)
    try:
        wait_healthy(port, name)
        r = httpx.get(f"http://127.0.0.1:{port}/api/v1/health")
        assert r.text == '{"status":"ok"}' and r.headers["x-app-version"] == (EXPECTED or "ci")
        logs = docker("logs", name).stdout
        assert "migrations applied" in logs and "config ok" in logs
        assert re.search(r"Password=[^*]", logs) is None
        from sqlalchemy import text

        from app.db.engine import create_sql_database

        db = create_sql_database(DB_URL)
        with db.engine.connect() as conn:
            versions = [row[0] for row in conn.execute(text("SELECT version FROM [assess].[schema_migrations]"))]
        db.dispose()
        from app.migrations.runner import discover

        assert sorted(versions) == [m.version for m in discover()]
    finally:
        docker("rm", "-f", name, check=False)


def test_container_runs_as_non_root_and_stops_on_sigterm_within_10s() -> None:
    port = free_port()
    name = run_container({**PROD_ENV, "DATABASE_URL": DB_URL}, port)
    try:
        wait_healthy(port, name)
        assert docker("exec", name, "id", "-u").stdout.strip() == "10001"
        started = time.time()
        docker("stop", "-t", "10", name)
        assert time.time() - started < 10
        assert docker("inspect", "-f", "{{.State.ExitCode}}", name).stdout.strip() in {"0", "143"}
    finally:
        docker("rm", "-f", name, check=False)


def test_container_exits_non_zero_when_database_url_is_invalid() -> None:
    port = free_port()
    name = run_container(
        {
            **PROD_ENV,
            "DATABASE_URL": "Server=tcp:127.0.0.1,1;Database=d;User ID=u;Password=NopeNope123;Connection Timeout=2",
        },
        port,
    )
    try:
        deadline = time.time() + 120
        while time.time() < deadline and docker("inspect", "-f", "{{.State.Running}}", name).stdout.strip() == "true":
            time.sleep(2)
        assert docker("inspect", "-f", "{{.State.Running}}", name).stdout.strip() == "false"
        assert docker("inspect", "-f", "{{.State.ExitCode}}", name).stdout.strip() != "0"
        assert "NopeNope123" not in docker("logs", name, check=False).stdout
    finally:
        docker("rm", "-f", name, check=False)


def test_container_refuses_fakes_in_production_mode() -> None:
    port = free_port()
    name = run_container(
        {"APP_ENV": "production", "DATABASE_URL": DB_URL, "REPO_BACKEND": "sql"}, port
    )  # AI/EMAIL/FILES fakes
    try:
        time.sleep(8)
        assert docker("inspect", "-f", "{{.State.Running}}", name).stdout.strip() == "false"
        assert "must be 'azure' in production" in docker("logs", name, check=False).stdout
    finally:
        docker("rm", "-f", name, check=False)
