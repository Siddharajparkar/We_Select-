"""Shared fixtures for all phases.

* ``repos``   - repositories on the in-memory backend (SQLite, real FK/unique/check enforcement) and,
                when ``TEST_DATABASE_URL`` is set (CI tier T2), on a real SQL Server as well.
* ``client``  - FastAPI TestClient over an app wired with fakes.
* ``live_server`` (e2e) - a real uvicorn subprocess.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

# Filter out broken meta_path finders from external broken editable packages in site-packages
sys.meta_path = [
    finder for finder in sys.meta_path
    if "obliq_gst_backend" not in type(finder).__name__ and "obliq" not in getattr(finder, "__module__", "")
]

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, load_settings
from app.core.clock import FakeClock
from app.main import create_app
from app.providers import create_providers
from app.repositories import Repositories, create_repositories

START = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)

# Every env var the settings read; cleared so tests are hermetic.
ENV_KEYS = [
    "APP_ENV", "PORT", "REPO_BACKEND", "DB_SCHEMA", "DATABASE_URL", "SESSION_SECRET", "PLATFORM_KEY",
    "AI_MODE", "FOUNDRY_API_STYLE", "FOUNDRY_ENDPOINT", "FOUNDRY_KEY", "FOUNDRY_DEPLOYMENT",
    "FOUNDRY_API_VERSION", "AI_MAX_OUTPUT_TOKENS", "AI_DAILY_TOKEN_CAP", "EMAIL_MODE",
    "ACS_CONNECTION_STRING", "ACS_SENDER", "FILES_MODE", "BLOB_CONNECTION_STRING", "BLOB_CONTAINER",
    "APPLICATIONINSIGHTS_CONNECTION_STRING", "APPINSIGHTS_SAMPLING_PERCENT", "APP_BASE_URL",
    "API_INTERNAL_URL", "JOB_LOOP_ENABLED", "GIT_SHA", "RETENTION_DAYS", "COOKIE_SECURE",
    "ARGON2_MEMORY_KIB", "ARGON2_TIME_COST", "ARGON2_PARALLELISM", "AI_TIMEOUT_SECONDS",
    "DAILY_GENERATION_LIMIT", "JOB_MAX_CONCURRENT", "JOB_TICK_SECONDS", "JOB_STUCK_SECONDS",
    "JOB_RETRY_BASE_SECONDS", "JOB_SHUTDOWN_GRACE_SECONDS",
]  # fmt: skip


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(START)


_SQL_URL = os.environ.get("TEST_DATABASE_URL", "")
_TABLE_ORDER = [
    "audit_log",
    "scores",
    "responses",
    "attempts",
    "participants",
    "questions",
    "assessments",
    "jobs",
    "sessions",
    "login_attempts",
    "users",
    "tenants",
]  # fmt: skip  (children before parents)


@pytest.fixture(scope="session")
def _sql_repos_session() -> Iterator[Repositories]:
    if not _SQL_URL:
        pytest.skip("TEST_DATABASE_URL not set (SQL Server tests run in CI tier T2)")
    from app.migrations.runner import run_migrations

    repos = create_repositories("sql", database_url=_SQL_URL, schema="assess")
    run_migrations(repos.db.engine, "assess")
    yield repos
    repos.db.dispose()


@pytest.fixture(params=["memory", pytest.param("sql", marks=pytest.mark.sql)])
def repos(request: pytest.FixtureRequest, clock: FakeClock) -> Iterator[Repositories]:
    """Fresh repositories per test, on each available backend."""
    if request.param == "memory":
        yield create_repositories("memory", clock=clock)
        return
    base: Repositories = request.getfixturevalue("_sql_repos_session")
    from sqlalchemy import delete

    with base.db.begin() as conn:
        for name in _TABLE_ORDER:
            conn.execute(delete(base.tables[name]))
    yield Repositories(base.db, base.tables, clock)


@pytest.fixture
def mem_repos(clock: FakeClock) -> Repositories:
    """Always the in-memory backend (for tests that must not depend on SQL Server)."""
    return create_repositories("memory", clock=clock)


@pytest.fixture
def settings() -> Settings:
    # Light Argon2 parameters keep the suite fast; a unit test pins the production defaults.
    return load_settings(GIT_SHA="test-sha-123", ARGON2_MEMORY_KIB=1024, ARGON2_TIME_COST=1, JOB_LOOP_ENABLED=False)


@pytest.fixture
def app(settings: Settings, repos: Repositories, clock: FakeClock):  # type: ignore[no-untyped-def]
    """App over the ``repos`` fixture: every API test runs on the in-memory backend locally and,
    in CI (tier T2, ``-m sql``), on SQL Server too ("write once, run twice")."""
    return create_app(settings, repos=repos, providers=create_providers(settings), clock=clock)


@pytest.fixture
def client(app) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    with TestClient(app) as c:
        yield c


@pytest.fixture
def world(repos: Repositories):  # type: ignore[no-untyped-def]
    """A tenant with an admin user, an assessment, a question and a participant."""

    class World:
        pass

    w = World()
    w.repos = repos
    w.tenant = repos.tenants.create(name="Tenant Alpha")
    w.user = repos.users.create(w.tenant.id, name="Alice", email="alice@alpha.example", password_hash="h", role="admin")
    w.assessment = repos.assessments.create(
        w.tenant.id,
        title="Backend Engineer",
        sections=[{"type": "mcq", "domain": "Python", "difficulty": "easy", "count": 2}],
        created_by=w.user.id,
    )
    w.question = repos.questions.create(
        w.tenant.id, assessment_id=w.assessment.id, type="mcq", body="What is a closure?",
        options=["A", "B", "C", "D"], correct_answer="A", max_score=5, source="custom",
    )  # fmt: skip
    added, _, _ = repos.participants.create_many(
        w.tenant.id, w.assessment.id, [{"name": "Cand One", "email": "cand1@example.com"}]
    )
    w.participant = added[0]
    return w


# ── live server (e2e) ───────────────────────────────────────────────────────────────────────
def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def start_server(
    extra_env: dict[str, str] | None = None, port: int | None = None
) -> tuple[subprocess.Popen[bytes], str]:
    port = port or free_port()
    env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
    env.update({"PORT": str(port), "GIT_SHA": "e2e-sha-0001", "PYTHONUNBUFFERED": "1"})
    env.update(extra_env or {})
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1",
         "--port", str(port), "--timeout-graceful-shutdown", "10"],
        cwd=API_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )  # fmt: skip
    return proc, f"http://127.0.0.1:{port}"


def drain_output(proc: subprocess.Popen[bytes]) -> deque[bytes]:
    """Keep reading a long-lived server's output (a full pipe would block the server); returns the recent lines."""
    recent: deque[bytes] = deque(maxlen=200)

    def pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            recent.append(line)

    threading.Thread(target=pump, daemon=True).start()
    return recent


def wait_ready(base_url: str, proc: subprocess.Popen[bytes], timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            if httpx.get(f"{base_url}/api/v1/health", timeout=1.0).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise TimeoutError("server did not become ready")


@pytest.fixture(scope="session")
def live_server() -> Iterator[str]:
    proc, base = start_server()
    drain_output(proc)
    try:
        wait_ready(base, proc)
        yield base
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()


# ── authenticated API helpers (Phase 4+) ────────────────────────────────────────────────────
PASSWORD = "correct-horse-9"
API = "/api/v1"


@dataclass
class Account:
    """A tenant's admin, already logged in on its own cookie jar."""

    client: TestClient
    tenant_id: str
    admin_id: str
    email: str
    password: str


@pytest.fixture
def platform_headers(settings: Settings) -> dict[str, str]:
    return {"X-Platform-Key": settings.PLATFORM_KEY}


@pytest.fixture
def new_client(app) -> Callable[[], TestClient]:  # type: ignore[no-untyped-def]
    """Independent cookie jars over the same app (HTTPS base so Secure cookies are sent back).
    Not used as a context manager on purpose: lifespan (and its repo disposal) runs once, in ``client``."""

    def make() -> TestClient:
        return TestClient(app, base_url="https://testserver")

    return make


@pytest.fixture
def create_account(new_client, platform_headers):  # type: ignore[no-untyped-def]
    counter = {"n": 0}

    def make(name: str | None = None, email: str | None = None) -> Account:
        counter["n"] += 1
        name = name or f"Tenant {counter['n']}"
        email = email or f"admin{counter['n']}@tenant{counter['n']}.example"
        c = new_client()
        r = c.post(
            f"{API}/platform/tenants", headers=platform_headers,
            json={"name": name, "adminName": f"Admin {counter['n']}", "adminEmail": email, "password": PASSWORD},
        )  # fmt: skip
        assert r.status_code == 201, r.text
        body = r.json()
        r = c.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        return Account(c, body["tenantId"], body["adminUserId"], email, PASSWORD)

    return make


@pytest.fixture
def tenant_a(create_account) -> Account:  # type: ignore[no-untyped-def]
    return create_account("Tenant A", "admin@a.example")


@pytest.fixture
def tenant_b(create_account) -> Account:  # type: ignore[no-untyped-def]
    return create_account("Tenant B", "admin@b.example")


@pytest.fixture
def recruiter(tenant_a: Account, new_client) -> Account:  # type: ignore[no-untyped-def]
    """A recruiter in tenant A, logged in on a separate cookie jar."""
    email = "recruiter@a.example"
    r = tenant_a.client.post(
        f"{API}/users", json={"name": "Rita", "email": email, "role": "recruiter", "password": PASSWORD}
    )
    assert r.status_code == 201, r.text
    c = new_client()
    assert c.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    return Account(c, tenant_a.tenant_id, r.json()["id"], email, PASSWORD)
