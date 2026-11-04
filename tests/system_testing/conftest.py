"""Shared setup for the system test suite (tests/system_testing).

What lives here: marker registration, the "run only when asked" gate, settings loading (environment first, then
api/.env.local, the same file the app uses), an HTTP helper, the test tenants, and the cleanup of everything the
suite creates (all test data is named with the prefix ``systemtest_``).

Secrets are never printed: use ``mask()`` for anything that could be one.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import sys
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import pytest
from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[2]
API_ENV_FILE = REPO_ROOT / "api" / ".env.local"
AZURE_CONFIG_FILE = REPO_ROOT / "config" / "azure.local.env"
PREFIX = "systemtest_"
DEFAULT_BASE_URL = "http://127.0.0.1:8080"  # the project's default port (python -m app.main / scripts/dev/run.py)

MARKERS = {
    "preflight": "pre-flight checks: environment, Python, dependencies, Azure sign-in",
    "azure": "one connectivity check per Azure service the application uses (safe, non-destructive)",
    "health": "the API server is reachable and answers the health and documentation routes",
    "api": "every endpoint group, with realistic test data (success and error cases)",
    "e2e": "complete workflows across several endpoints and the Azure services behind them",
    "cleanup": "removes every systemtest_ object created by the suite",
}

with contextlib.suppress(Exception):  # emoji in step messages must never crash a run on a legacy Windows console
    sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]


def pytest_configure(config: pytest.Config) -> None:
    for name, text in MARKERS.items():
        config.addinivalue_line("markers", f"{name}: {text}")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """System tests need a running server and real Azure. Run them only when asked, so the ordinary
    `pytest tests` (and CI) skips them instead of failing."""
    asked = os.environ.get("RUN_SYSTEM_TESTS") == "1" or any(
        "system_testing" in str(arg).replace("\\", "/") for arg in config.invocation_params.args
    )
    if asked:
        return
    skip = pytest.mark.skip(
        reason="system tests need a running API server and real Azure; run: pytest tests/system_testing -v -s"
    )
    for item in items:
        if "system_testing" in str(item.path).replace("\\", "/"):
            item.add_marker(skip)


# ── settings ────────────────────────────────────────────────────────────────────────────────────────
def mask(value: str | None) -> str:
    """Show just enough to recognise a value (never a full secret)."""
    v = value or ""
    if not v:
        return "(not set)"
    return v[:3] + "***" if len(v) > 6 else "***"


class Env:
    """Settings: process environment first, then api/.env.local, then config/azure.local.env (names only)."""

    def __init__(self) -> None:
        self.api: dict[str, str | None] = {}
        self.names: dict[str, str | None] = {}
        if API_ENV_FILE.is_file():
            self.api = dotenv_values(API_ENV_FILE, encoding="utf-8-sig")
        if AZURE_CONFIG_FILE.is_file():
            self.names = dotenv_values(AZURE_CONFIG_FILE, encoding="utf-8-sig")

    def get(self, name: str, default: str = "") -> str:
        return os.environ.get(name) or self.api.get(name) or self.names.get(name) or default

    def require(self, name: str, why: str) -> str:
        value = self.get(name)
        if not value:
            pytest.skip(f"{name} is not set ({why}); this service is not configured on this machine")
        return value


class Tracker:
    """What the run created, so cleanup knows whether it has work to do."""

    def __init__(self) -> None:
        self.touched = False
        self.blobs: list[str] = []


@pytest.fixture(scope="session")
def env() -> Env:
    return Env()


@pytest.fixture(scope="session")
def say() -> Callable[[str], None]:
    def _say(message: str) -> None:
        print(f"      {message}")

    return _say


@pytest.fixture(scope="session")
def tracker() -> Tracker:
    return Tracker()


@pytest.fixture(scope="session")
def run_id() -> str:
    return f"{PREFIX}{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="session")
def base_url(env: Env) -> str:
    return env.get("BASE_URL", DEFAULT_BASE_URL).rstrip("/")


@pytest.fixture(scope="session")
def client(base_url: str) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=base_url, timeout=60.0, follow_redirects=False) as c:
        yield c


@pytest.fixture(scope="session")
def api(client: httpx.Client) -> Callable[..., httpx.Response]:
    """``api("GET", "/users", sid)``: sends one request. A session travels ONLY in the explicit Cookie header; the
    client's cookie jar is cleared first (over https it would replay a Secure cookie and hide 'no session' bugs)."""

    def call(method: str, path: str, sid: str | None = None, **kw: Any) -> httpx.Response:
        headers = dict(kw.pop("headers", {}))
        if sid:
            headers["Cookie"] = f"sid={sid}"
        client.cookies.clear()
        url = path if path.startswith("/api/") else f"/api/v1{path}"
        return client.request(method, url, headers=headers, **kw)

    return call


@pytest.fixture(scope="session")
def platform_key(env: Env, base_url: str) -> str:
    key = env.get("PLATFORM_KEY")
    if key:
        return key
    if urlparse(base_url).hostname in ("127.0.0.1", "localhost"):
        from app.config import Settings  # the documented development default, only for a local server

        return str(Settings.model_fields["PLATFORM_KEY"].default)
    pytest.skip("PLATFORM_KEY is not set (needed to create test tenants on a remote server)")


def new_password() -> str:
    return "Systemtest-" + secrets.token_urlsafe(9) + "9!"


def login_session(api: Callable[..., httpx.Response], email: str, password: str) -> tuple[str, str]:
    """Log in; returns (sid, raw Set-Cookie header)."""
    import re

    r = api("POST", "/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed: HTTP {r.status_code}"
    cookie = r.headers.get("set-cookie", "")
    m = re.search(r"sid=([^;]+)", cookie)
    assert m, "login did not set the sid cookie"
    return m.group(1), cookie


@pytest.fixture(scope="session")
def login(api: Callable[..., httpx.Response]) -> Callable[[str, str], tuple[str, str]]:
    return lambda email, password: login_session(api, email, password)


@pytest.fixture(scope="session")
def accounts(
    api: Callable[..., httpx.Response], platform_key: str, run_id: str, tracker: Tracker, say: Callable[[str], None]
) -> dict[str, dict[str, str]]:
    """Two isolated test companies (A and B), each with an admin who is logged in."""
    out: dict[str, dict[str, str]] = {}
    for tag in ("a", "b"):
        email = f"{run_id}_{tag}@systemtest.example"
        password = new_password()
        r = api(
            "POST",
            "/platform/tenants",
            headers={"X-Platform-Key": platform_key},
            json={
                "name": f"{run_id}_company_{tag}",
                "adminName": f"{run_id} admin {tag}",
                "adminEmail": email,
                "password": password,
            },
        )
        tracker.touched = True
        assert r.status_code == 201, f"could not create test company {tag}: HTTP {r.status_code} {r.text[:120]}"
        sid, cookie = login_session(api, email, password)
        out[tag] = {
            **r.json(),
            "email": email,
            "password": password,
            "sid": sid,
            "cookie": cookie,
            "name": f"{run_id}_company_{tag}",
        }
    say(f"test companies ready: {out['a']['name']}, {out['b']['name']}")
    return out


# ── optional Azure clients (None when the service is not configured on this machine) ─────────────────────
def make_engine(env: Env) -> Any:
    url = env.get("DATABASE_URL")
    if not url:
        return None
    from sqlalchemy import create_engine

    from app.db.engine import build_sqlalchemy_url, login_timeout_seconds

    return create_engine(build_sqlalchemy_url(url), connect_args={"timeout": login_timeout_seconds(url)})


def make_container(env: Env) -> Any:
    conn = env.get("BLOB_CONNECTION_STRING")
    if not conn:
        return None
    from azure.storage.blob import BlobServiceClient

    return BlobServiceClient.from_connection_string(conn).get_container_client(env.get("BLOB_CONTAINER", "jd-files"))


@pytest.fixture(scope="session")
def sql_engine(env: Env) -> Iterator[Any]:
    engine = make_engine(env)
    yield engine
    if engine is not None:
        engine.dispose()


@pytest.fixture(scope="session")
def blob_container(env: Env) -> Any:
    return make_container(env)


# ── cleanup ─────────────────────────────────────────────────────────────────────────────────────────
# Deleted in this order (children first); any other table with a tenant_id column is handled before `tenants`.
_DELETE_ORDER = (
    "scores",
    "responses",
    "attempts",
    "participants",
    "questions",
    "jobs",
    "audit_log",
    "sessions",
    "assessments",
    "users",
)


def cleanup_systemtest_data(env: Env, tracker: Tracker) -> dict[str, Any]:
    """Remove everything named ``systemtest_`` (this run and any aborted earlier run). Safe to call twice.

    Returns counts and ``remaining_tenants`` (None when no database is configured). Only rows whose company name
    starts with the prefix are touched; nothing else in the database or the storage container is read or changed.
    """
    from sqlalchemy import bindparam, text

    summary: dict[str, Any] = {
        "tenants": 0,
        "blobs": 0,
        "login_attempts": 0,
        "remaining_tenants": None,
        "remaining_blobs": None,
        "blob_errors": 0,
        "notes": [],
    }
    tenant_ids: list[str] = []
    engine = make_engine(env)
    if engine is not None:
        schema = env.get("DB_SCHEMA", "assess")
        if not schema.replace("_", "").isalnum():
            raise ValueError("DB_SCHEMA must be a plain identifier")
        pattern = f"{PREFIX.replace('_', '[_]')}%"
        try:
            with engine.begin() as conn:
                rows = conn.execute(
                    text(f"SELECT CAST(id AS NVARCHAR(36)) FROM [{schema}].[tenants] WHERE name LIKE :p"),
                    {"p": pattern},
                ).fetchall()
                tenant_ids = [str(r[0]) for r in rows]
                if tenant_ids:
                    with_tenant = {
                        str(r[0])
                        for r in conn.execute(
                            text(
                                "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                                "WHERE TABLE_SCHEMA = :s AND COLUMN_NAME = 'tenant_id'"
                            ),
                            {"s": schema},
                        )
                    }
                    ordered = [t for t in _DELETE_ORDER if t in with_tenant]
                    ordered += sorted(with_tenant - set(ordered) - {"tenants"})
                    for table in ordered:
                        conn.execute(
                            text(f"DELETE FROM [{schema}].[{table}] WHERE tenant_id IN :ids").bindparams(
                                bindparam("ids", expanding=True)
                            ),
                            {"ids": tenant_ids},
                        )
                    conn.execute(
                        text(f"DELETE FROM [{schema}].[tenants] WHERE id IN :ids").bindparams(
                            bindparam("ids", expanding=True)
                        ),
                        {"ids": tenant_ids},
                    )
                summary["tenants"] = len(tenant_ids)
                res = conn.execute(text(f"DELETE FROM [{schema}].[login_attempts] WHERE email LIKE :p"), {"p": pattern})
                summary["login_attempts"] = int(res.rowcount or 0)
            with engine.connect() as conn:
                summary["remaining_tenants"] = int(
                    conn.execute(
                        text(f"SELECT COUNT(*) FROM [{schema}].[tenants] WHERE name LIKE :p"), {"p": pattern}
                    ).scalar()
                    or 0
                )
        finally:
            engine.dispose()
    else:
        summary["notes"].append(
            "DATABASE_URL not set: database cleanup skipped (a server in memory mode keeps nothing)"
        )

    container = make_container(env)
    if container is not None:
        # SQL Server prints GUIDs in upper case but the app writes lower-case blob paths (names are case-sensitive).
        tenant_prefixes = [f"{tid.lower()}/" for tid in tenant_ids]
        suite_files = ("systemtest-jd.pdf", "systemtest-blob.pdf")  # file names only this suite uploads

        def doomed() -> set[str]:
            names = set(tracker.blobs)
            for prefix in tenant_prefixes:  # job-description files live at <tenantId>/<assessmentId>/<file>
                names.update(b.name for b in container.list_blobs(name_starts_with=prefix))
            names.update(b.name for b in container.list_blobs(name_starts_with=PREFIX))
            # leftovers of an aborted earlier run: a company that is already gone, but its test file remains
            names.update(b.name for b in container.list_blobs() if b.name.rsplit("/", 1)[-1] in suite_files)
            return names

        errors = 0
        for name in sorted(doomed()):
            try:
                container.delete_blob(name)
                summary["blobs"] += 1
            except Exception:
                errors += 1
        tracker.blobs.clear()
        summary["blob_errors"] = errors
        summary["remaining_blobs"] = len(doomed())
    else:
        summary["notes"].append("BLOB_CONNECTION_STRING not set: storage cleanup skipped")
    return summary


@pytest.fixture(scope="session")
def cleanup(env: Env, tracker: Tracker) -> Callable[[], dict[str, Any]]:
    return lambda: cleanup_systemtest_data(env, tracker)


@pytest.fixture(scope="session", autouse=True)
def _final_cleanup(env: Env, tracker: Tracker) -> Iterator[None]:
    """Safety net: runs when the session ends, even if tests failed or were interrupted."""
    yield
    if tracker.touched or tracker.blobs:
        try:
            summary = cleanup_systemtest_data(env, tracker)
            print(
                f"\n   cleanup (end of session): {summary['tenants']} test companies, {summary['blobs']} blobs removed"
            )
        except Exception as exc:  # never hide the test results behind a cleanup problem; say what is left
            print(
                f"\n   ⚠️ cleanup could not finish ({type(exc).__name__}); run: pytest tests/system_testing -m cleanup"
            )
