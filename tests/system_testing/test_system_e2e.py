"""System test suite: proves the complete backend works end to end, including every Azure service it uses.

Run from the repository root (the API server must be running for the health, api and e2e groups):

    pytest tests/system_testing -v -s                 # everything, as a checklist
    pytest tests/system_testing -v -s -m preflight    # one group: preflight | azure | health | api | e2e

Order of the story: 1 pre-flight, 2 Azure service connectivity, 3 server health, 4 API endpoints, 5 end-to-end
workflows, 6 cleanup. Everything created is named ``systemtest_...`` and removed at the end (even after a failure).
Nothing existing is modified or deleted; secrets are never printed. See tests/system_testing/TEST.md.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import shutil
import socket
import subprocess
import sys
import textwrap
import time
import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx
import pytest

Api = Callable[..., httpx.Response]
Say = Callable[[str], None]
PREFIX = "systemtest_"  # every object this suite creates starts with this, so cleanup can find it


def mask(value: str | None) -> str:
    """Show just enough to recognise a value, never a full secret."""
    v = value or ""
    return "(not set)" if not v else (v[:3] + "***" if len(v) > 6 else "***")


def new_password() -> str:
    import secrets

    return "Systemtest-" + secrets.token_urlsafe(9) + "9!"


# the nine application secrets that must exist in Key Vault (names only)
EXPECTED_SECRETS = {
    "database-url",
    "session-secret",
    "platform-key",
    "foundry-endpoint",
    "foundry-key",
    "acs-connection-string",
    "acs-sender",
    "blob-connection-string",
    "appinsights-connection-string",
}
AZURE_VARIABLES = [
    "DATABASE_URL",
    "BLOB_CONNECTION_STRING",
    "FOUNDRY_ENDPOINT",
    "FOUNDRY_KEY",
    "FOUNDRY_DEPLOYMENT",
    "FOUNDRY_API_STYLE",
    "ACS_CONNECTION_STRING",
    "ACS_SENDER",
    "APPLICATIONINSIGHTS_CONNECTION_STRING",
    "SESSION_SECRET",
    "PLATFORM_KEY",
]
STATE: dict[str, Any] = {}  # shared between the numbered end-to-end tests

JD_LINES = textwrap.wrap(
    "Senior Backend Engineer. We are hiring a senior backend engineer to design, build and operate Python web "
    "services on Microsoft Azure. You will own REST APIs written with FastAPI, model relational data in SQL Server, "
    "write background jobs, add automated tests, review code, and improve the reliability, security and "
    "observability of production systems. Strong communication, mentoring and a habit of measuring results are "
    "important for this role. Experience with containers, continuous delivery pipelines, structured logging and "
    "incident response is a clear advantage. You will work closely with product managers and other engineers to "
    "plan, deliver and maintain features that customers rely on every day. Requirements include solid SQL skills, "
    "clear written English, testing discipline and the ability to explain technical trade-offs to colleagues.",
    width=88,
)
JD_TEXT = " ".join(JD_LINES)
SECTIONS_ONE_MCQ = [{"type": "mcq", "domain": "Python", "difficulty": "easy", "count": 1}]
SECTIONS_AI = [
    {"type": "mcq", "domain": "Python", "difficulty": "medium", "count": 2},
    {"type": "descriptive", "domain": "System design", "difficulty": "medium", "count": 1},
]


# ── small helpers ─────────────────────────────────────────────────────────────────────────────────
def make_pdf(lines: list[str]) -> bytes:
    """A minimal single-page PDF with the given text lines (no extra libraries needed)."""

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    body = "BT /F1 10 Tf 40 760 Td 12 TL " + " ".join(f"({esc(x)}) Tj T*" for x in lines) + " ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(body)} >>\nstream\n{body}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def need(key: str) -> Any:
    """An end-to-end step that depends on an earlier one: skip (with the reason) if that one did not complete."""
    if key not in STATE:
        pytest.skip(f"depends on an earlier end-to-end step that did not complete ({key} missing)")
    return STATE[key]


def wait_job(api: Api, sid: str, job_id: str, say: Say, timeout: int = 240) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        r = api("GET", f"/jobs/{job_id}", sid)
        assert r.status_code == 200, f"job poll returned HTTP {r.status_code}"
        last = r.json()
        if last["status"] in ("done", "failed"):
            return last
        time.sleep(2)
    raise AssertionError(f"job {job_id} still '{last.get('status')}' after {timeout}s")


def new_assessment(api: Api, sid: str, run_id: str, *, jd: str | None, sections: list[dict[str, Any]]) -> str:
    r = api(
        "POST",
        "/assessments",
        sid,
        json={
            "title": f"{run_id} assessment",
            "jobDescription": jd,
            "durationMinutes": 30,
            "passingScore": 50,
            "sections": sections,
        },
    )
    assert r.status_code == 201, f"create assessment: HTTP {r.status_code} {r.text[:120]}"
    return str(r.json()["id"])


def az(*args: str, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    exe = shutil.which("az")
    if not exe:
        pytest.skip("Azure CLI (az) is not installed on this machine")
    return subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout, check=False)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 1. PRE-FLIGHT
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.preflight
class TestPreflight:
    def test_01_environment_variables_are_present(self, env: Any, base_url: str, say: Say) -> None:
        """Every setting the Azure-connected app needs is present (names shown, values masked)."""
        present = {n: bool(env.get(n)) for n in AZURE_VARIABLES}
        for name, ok in present.items():
            say(f"{'✅' if ok else '⚠️ '} {name}: {mask(env.get(name)) if ok else 'missing'}")
        say(f"ℹ️  API under test: {base_url}")
        if not any(present.values()):
            pytest.skip("no Azure settings found: offline mode (fake providers); Azure tests will be skipped")
        missing = [n for n, ok in present.items() if not ok]
        assert not missing, f"partly configured: missing {missing}. Run: python scripts/dev/setup.py"

    def test_02_python_and_key_dependencies(self, env: Any, say: Say) -> None:
        """Python is new enough and the libraries the app and the tests need are installed."""
        assert sys.version_info >= (3, 11), f"Python 3.11+ required, found {sys.version.split()[0]}"
        say(f"✅ Python {sys.version.split()[0]}")
        for module, dist in [
            ("fastapi", "fastapi"),
            ("uvicorn", "uvicorn"),
            ("pydantic", "pydantic"),
            ("sqlalchemy", "sqlalchemy"),
            ("pyodbc", "pyodbc"),
            ("httpx", "httpx"),
            ("azure.storage.blob", "azure-storage-blob"),
            ("pypdf", "pypdf"),
            ("pytest", "pytest"),
        ]:
            importlib.import_module(module)
            say(f"✅ {dist} {importlib.metadata.version(dist)}")
        if env.get("DATABASE_URL"):
            import pyodbc

            drivers = [d for d in pyodbc.drivers() if "ODBC Driver 18" in d]
            assert drivers, "ODBC Driver 18 for SQL Server is not installed (needed to reach Azure SQL)"
            say(f"✅ {drivers[0]}")

    def test_03_azure_sign_in(self, say: Say) -> None:
        """You are signed in to Azure with the Azure CLI (used by the setup scripts; the app itself uses keys)."""
        state = az("account", "show", "--query", "state", "-o", "tsv")
        assert state.returncode == 0, "not signed in to Azure: run `az login`"
        assert state.stdout.strip() == "Enabled", f"subscription state is '{state.stdout.strip()}'"
        name = az("account", "show", "--query", "name", "-o", "tsv").stdout.strip()
        say(f"✅ Azure CLI signed in; subscription '{name}' is Enabled")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 2. AZURE SERVICE CONNECTIVITY (each: connect, then one minimal, safe operation)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.azure
class TestAzureServices:
    def test_04_azure_sql_connect_and_read_schema(self, env: Any, sql_engine: Any, say: Say) -> None:
        """Azure SQL accepts our least-privilege login, answers a query and holds the application schema."""
        env.require("DATABASE_URL", "Azure SQL connection")
        from sqlalchemy import text

        schema = env.get("DB_SCHEMA", "assess")
        started = time.perf_counter()
        with sql_engine.connect() as conn:
            database = conn.execute(text("SELECT DB_NAME()")).scalar()
            assert conn.execute(text("SELECT 1")).scalar() == 1
            tables = conn.execute(
                text(
                    "SELECT COUNT(*) FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id WHERE s.name = :s"
                ),
                {"s": schema},
            ).scalar()
        ms = round((time.perf_counter() - started) * 1000)
        server = env.get("DATABASE_URL").split("Server=", 1)[-1].split(";")[0].replace("tcp:", "").split(",")[0]
        say(f"✅ Connected to Azure SQL: database '{database}' on server '{server.split('.')[0]}' ({ms} ms)")
        say(f"✅ schema '{schema}' has {tables} tables")
        assert tables >= 13, f"expected at least 13 tables in schema {schema}, found {tables} (migrations not applied?)"

    def test_05_azure_blob_storage_upload_and_delete(
        self, env: Any, blob_container: Any, tracker: Any, say: Say
    ) -> None:
        """Blob Storage: the job-description container exists, is private, and a test file can be written, read and deleted."""
        env.require("BLOB_CONNECTION_STRING", "Azure Blob Storage connection")
        props = blob_container.get_container_properties()
        assert props.public_access is None, "the container allows public access"
        name = f"{PREFIX}probe/{uuid.uuid4().hex}.txt"
        tracker.blobs.append(name)
        payload = b"system test file - safe to delete"
        blob = blob_container.get_blob_client(name)
        blob.upload_blob(payload)
        assert blob.download_blob().readall() == payload
        blob.delete_blob()
        assert not blob.exists()
        tracker.blobs.remove(name)
        say(f"✅ Azure Blob Storage: account '{blob_container.account_name}', container '{props.name}' is private")
        say("✅ wrote, read back and deleted one test file")

    def test_06_azure_ai_foundry_model_answers(self, env: Any, say: Say) -> None:
        """Azure AI Foundry: the deployed model answers a tiny chat request using the same call as the app."""
        endpoint = env.require("FOUNDRY_ENDPOINT", "Azure AI endpoint")
        key = env.require("FOUNDRY_KEY", "Azure AI key")
        deployment = env.require("FOUNDRY_DEPLOYMENT", "model deployment name")
        from app.tools.probe import foundry_url

        url = foundry_url(endpoint, deployment, env.get("FOUNDRY_API_STYLE", "v1"), env.get("FOUNDRY_API_VERSION"))
        body = {
            "model": deployment,
            "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
            "max_tokens": 16,
            "temperature": 0,
        }
        last: httpx.Response | None = None
        for attempt in range(3):  # the model occasionally stalls or rate-limits; a retry is normal
            try:
                last = httpx.post(url, json=body, headers={"api-key": key}, timeout=45)
            except httpx.TimeoutException:
                continue
            if last.status_code == 429:
                time.sleep(6)
                continue
            break
        assert last is not None, "the AI service did not answer within 3 attempts (timeouts)"
        assert last.status_code == 200, f"AI service returned HTTP {last.status_code}"
        data = last.json()
        assert isinstance(data["choices"][0]["message"]["content"], str)
        say(
            f"✅ Azure AI Foundry: deployment '{deployment}' answered; tokens used: {data.get('usage', {}).get('total_tokens')}"
        )

    def test_07_application_insights_is_reachable(self, env: Any, say: Say) -> None:
        """Application Insights: the connection string is well-formed and its ingestion endpoint is reachable (nothing is sent)."""
        conn = env.require("APPLICATIONINSIGHTS_CONNECTION_STRING", "telemetry")
        parts = dict(p.split("=", 1) for p in conn.split(";") if "=" in p)
        assert parts.get("InstrumentationKey"), "connection string has no InstrumentationKey"
        endpoint = parts.get("IngestionEndpoint", "")
        assert endpoint.startswith("https://"), "connection string has no https IngestionEndpoint"
        host = urlparse(endpoint).hostname or ""
        socket.getaddrinfo(host, 443)
        reply = httpx.post(endpoint.rstrip("/") + "/v2/track", content=b"[]", timeout=20)
        assert reply.status_code < 500, f"ingestion endpoint answered HTTP {reply.status_code}"
        say(f"✅ Application Insights: key {mask(parts['InstrumentationKey'])}, ingestion host '{host}' reachable")

    def test_08_azure_communication_services_email_is_configured(self, env: Any, say: Say) -> None:
        """Communication Services (email): connection string and sender are valid and the service host is reachable. No email is sent."""
        conn = env.require("ACS_CONNECTION_STRING", "Azure Communication Services")
        sender = env.require("ACS_SENDER", "email sender address")
        parts = dict(p.split("=", 1) for p in conn.split(";") if "=" in p)
        endpoint = parts.get("endpoint", "")
        assert endpoint.startswith("https://") and parts.get("accesskey"), "malformed ACS connection string"
        host = urlparse(endpoint).hostname or ""
        socket.getaddrinfo(host, 443)
        assert "@" in sender and sender.lower().endswith(".azurecomm.net"), (
            "sender is not an Azure-managed domain address"
        )
        reply = httpx.get(endpoint, timeout=20)
        assert reply.status_code < 500
        say(
            f"✅ Communication Services: host '{host}' reachable; sender {mask(sender)} (no email sent; invitations arrive in Phase 7)"
        )

    def test_09_azure_key_vault_has_the_application_secrets(self, env: Any, say: Say) -> None:
        """Key Vault: you can list the vault and all nine application secrets exist (names only; values are never read)."""
        vault = env.get("AZ_KEY_VAULT")
        if not vault:
            pytest.skip("AZ_KEY_VAULT is not set in config/azure.local.env")
        r = az("keyvault", "secret", "list", "--vault-name", vault, "--query", "[].name", "-o", "tsv")
        assert r.returncode == 0, (
            "cannot list Key Vault secrets (role 'Key Vault Secrets User' missing or not signed in?)"
        )
        names = {n.strip() for n in r.stdout.splitlines() if n.strip()}
        missing = EXPECTED_SECRETS - names
        assert not missing, f"missing secrets in Key Vault: {sorted(missing)}"
        say(f"✅ Azure Key Vault '{vault}': all {len(EXPECTED_SECRETS)} application secrets present (names only)")

    def test_10_azure_container_app_and_registry_are_healthy(self, env: Any, say: Say) -> None:
        """Container Apps and Container Registry: the API app is running and its image is in the registry (read-only)."""
        group, app, registry = env.get("AZ_RESOURCE_GROUP"), env.get("AZ_APP"), env.get("AZ_ACR")
        if not (group and app and registry):
            pytest.skip("AZ_RESOURCE_GROUP / AZ_APP / AZ_ACR are not set in config/azure.local.env")
        state = az("containerapp", "show", "-g", group, "-n", app, "--query", "properties.runningStatus", "-o", "tsv")
        assert state.returncode == 0, "cannot read the Container App (not signed in or no permission)"
        assert state.stdout.strip() == "Running", f"Container App status is '{state.stdout.strip()}'"
        image = az(
            "containerapp",
            "show",
            "-g",
            group,
            "-n",
            app,
            "--query",
            "properties.template.containers[0].image",
            "-o",
            "tsv",
        )
        tag = image.stdout.strip().rsplit(":", 1)[-1]
        tags = az("acr", "repository", "show-tags", "-n", registry, "--repository", app, "-o", "tsv")
        assert tag in tags.stdout.split(), "the running image tag is not in the registry"
        say(f"✅ Container App '{app}' is Running; image tag {tag[:7]}… is in registry '{registry}'")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 3. SERVER HEALTH
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.health
class TestServerHealth:
    def test_11_server_is_reachable(self, base_url: str, api: Api, say: Say) -> None:
        """The API server answers at BASE_URL."""
        last: Exception | None = None
        for _ in range(3):
            try:
                r = api("GET", "/health")
                say(f"✅ server reachable at {base_url} (HTTP {r.status_code})")
                return
            except httpx.HTTPError as exc:
                last = exc
                time.sleep(2)
        pytest.fail(f"server not reachable at {base_url} ({type(last).__name__}). Start it: python scripts/dev/run.py")

    def test_12_health_endpoint_contract(self, api: Api, say: Say) -> None:
        """GET /api/v1/health returns {"status":"ok"} plus the version and request-id headers and security headers."""
        r = api("GET", "/health")
        assert r.status_code == 200 and r.json() == {"status": "ok"}
        assert r.headers.get("x-app-version"), "x-app-version header missing"
        assert r.headers.get("x-request-id"), "x-request-id header missing"
        assert r.headers.get("x-content-type-options") == "nosniff"
        say(f"✅ health ok; running version '{r.headers['x-app-version'][:12]}'")

    def test_13_openapi_documentation_loads(self, api: Api, say: Say) -> None:
        """/api/v1/docs and /api/v1/openapi.json load (production deliberately hides them: 404 is then the correct answer)."""
        docs = api("GET", "/api/v1/docs")
        spec = api("GET", "/api/v1/openapi.json")
        if docs.status_code == 200:
            assert "swagger" in docs.text.lower()
            paths = spec.json()["paths"]
            assert "/api/v1/health" in paths
            say(f"✅ interactive docs load; OpenAPI lists {len(paths)} paths")
        else:
            assert docs.status_code == 404 and spec.status_code == 404
            assert docs.json()["error"]["code"] == "NOT_FOUND"
            say("✅ docs are disabled (production mode): /docs and /openapi.json return 404 as designed")

    def test_14_unknown_route_uses_the_error_envelope(self, api: Api, say: Say) -> None:
        """Errors always use one shape: {"error": {"code", "message"}}."""
        r = api("GET", "/system-test-no-such-route")
        assert r.status_code == 404
        body = r.json()["error"]
        assert body["code"] == "NOT_FOUND" and body["message"]
        say("✅ unknown route -> 404 with the standard error envelope")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 4. API ENDPOINTS (each group: success path + at least one validation / error case)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.api
class TestApiPlatformAndAuth:
    def test_15_platform_rejects_a_missing_or_wrong_key(self, api: Api, say: Say) -> None:
        """POST /platform/tenants is protected by the platform key: no key or a wrong key -> 401."""
        body = {
            "name": f"{PREFIX}x",
            "adminName": "x x",
            "adminEmail": f"{PREFIX}x@systemtest.example",
            "password": new_password(),
        }
        assert api("POST", "/platform/tenants", json=body).status_code == 401
        assert api("POST", "/platform/tenants", headers={"X-Platform-Key": "wrong"}, json=body).status_code == 401
        say("✅ tenant creation without a valid platform key -> 401")

    def test_16_platform_validates_input(self, api: Api, platform_key: str, tracker: Any, say: Say) -> None:
        """A weak password is rejected with 400 and per-field details."""
        r = api(
            "POST",
            "/platform/tenants",
            headers={"X-Platform-Key": platform_key},
            json={
                "name": f"{PREFIX}weak",
                "adminName": "x x",
                "adminEmail": f"{PREFIX}weak@systemtest.example",
                "password": "short",
            },
        )
        tracker.touched = True
        assert r.status_code == 400
        assert r.json()["error"]["details"], "validation errors should list the offending fields"
        say("✅ weak password -> 400 with field details")

    def test_17_platform_creates_a_company_and_its_admin(
        self, api: Api, platform_key: str, run_id: str, tracker: Any, login: Any, say: Say
    ) -> None:
        """POST /platform/tenants creates a company and its first admin, who can then log in."""
        email, password = f"{run_id}_c@systemtest.example", new_password()
        r = api(
            "POST",
            "/platform/tenants",
            headers={"X-Platform-Key": platform_key},
            json={
                "name": f"{run_id}_company_c",
                "adminName": f"{run_id} admin c",
                "adminEmail": email,
                "password": password,
            },
        )
        tracker.touched = True
        assert r.status_code == 201, f"HTTP {r.status_code}"
        assert uuid.UUID(r.json()["tenantId"]) and uuid.UUID(r.json()["adminUserId"])
        sid, _ = login(email, password)
        assert api("GET", "/auth/me", sid).json()["user"]["role"] == "admin"
        say("✅ company created (ids returned); its admin logged in with role 'admin'")

    def test_18_login_sets_a_safe_session_cookie(self, accounts: Any, env: Any, say: Say) -> None:
        """POST /auth/login sets an HttpOnly, SameSite=Lax, 8-hour session cookie (Secure unless the dev server turns it off)."""
        cookie = accounts["a"]["cookie"].lower()
        for attribute in ("httponly", "samesite=lax", "path=/", "max-age=28800"):
            assert attribute in cookie, f"cookie lacks {attribute}"
        if env.get("COOKIE_SECURE", "true").lower() != "false":
            assert "secure" in cookie, "cookie is not marked Secure"
        say("✅ session cookie: HttpOnly, SameSite=Lax, 8 h lifetime" + (", Secure" if "secure" in cookie else ""))

    def test_19_me_returns_the_caller_and_company(self, api: Api, accounts: Any, say: Say) -> None:
        """GET /auth/me returns who is signed in and for which company (the tenant comes from the session)."""
        a = accounts["a"]
        r = api("GET", "/auth/me", a["sid"])
        assert r.status_code == 200
        assert r.json()["tenant"]["id"] == a["tenantId"] and r.json()["user"]["role"] == "admin"
        say(f"✅ /auth/me -> admin of '{r.json()['tenant']['name']}'")

    def test_20_wrong_password_and_missing_session_are_401(self, api: Api, accounts: Any, say: Say) -> None:
        """A wrong password and a request with no session are both refused with 401 (and the standard error body)."""
        r = api("POST", "/auth/login", json={"email": accounts["a"]["email"], "password": "definitely-wrong-1!"})
        assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"
        assert api("GET", "/auth/me").status_code == 401
        assert api("GET", "/users").status_code == 401
        say("✅ wrong password -> 401 INVALID_CREDENTIALS; no session -> 401")

    def test_21_logout_ends_the_session(self, api: Api, accounts: Any, login: Any, say: Say) -> None:
        """POST /auth/logout invalidates the session on the server."""
        sid, _ = login(accounts["a"]["email"], accounts["a"]["password"])
        assert api("POST", "/auth/logout", sid).status_code == 204
        assert api("GET", "/auth/me", sid).status_code == 401
        say("✅ logout -> 204; the old session no longer works")


@pytest.mark.api
class TestApiUsers:
    def test_22_admin_lists_and_creates_users(self, api: Api, accounts: Any, run_id: str, say: Say) -> None:
        """GET /users lists the company's users; POST /users creates a recruiter."""
        a = accounts["a"]
        users = api("GET", "/users", a["sid"])
        assert users.status_code == 200 and a["adminUserId"] in {u["id"] for u in users.json()}
        email, password = f"{run_id}_recruiter@systemtest.example", new_password()
        r = api(
            "POST",
            "/users",
            a["sid"],
            json={"name": f"{run_id} recruiter", "email": email, "role": "recruiter", "password": password},
        )
        assert r.status_code == 201 and uuid.UUID(r.json()["id"])
        listed = {u["id"]: u for u in api("GET", "/users", a["sid"]).json()}
        assert listed[r.json()["id"]]["role"] == "recruiter" and listed[r.json()["id"]]["status"] == "active"
        a["recruiter"] = {"id": r.json()["id"], "email": email, "password": password}
        say("✅ listed users; created a recruiter in company A")

    def test_23_duplicate_email_is_409_across_companies(self, api: Api, accounts: Any, say: Say) -> None:
        """Emails are globally unique: reusing one (even from another company) -> 409."""
        recruiter = accounts["a"].get("recruiter")
        if not recruiter:
            pytest.skip("depends on test_22 (recruiter not created)")
        r = api(
            "POST",
            "/users",
            accounts["b"]["sid"],
            json={
                "name": "dup dup",
                "email": recruiter["email"].upper(),
                "role": "recruiter",
                "password": new_password(),
            },
        )
        assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_EXISTS"
        say("✅ same email in another company (different letter case) -> 409 EMAIL_EXISTS")

    def test_24_a_recruiter_cannot_list_users(self, api: Api, accounts: Any, login: Any, say: Say) -> None:
        """Role check: recruiters may not use the admin-only /users endpoints (403)."""
        recruiter = accounts["a"].get("recruiter")
        if not recruiter:
            pytest.skip("depends on test_22 (recruiter not created)")
        sid, _ = login(recruiter["email"], recruiter["password"])
        assert api("GET", "/users", sid).status_code == 403
        say("✅ recruiter -> GET /users is 403")

    def test_25_user_patch_rules(self, api: Api, accounts: Any, say: Say) -> None:
        """PATCH /users/{id}: an admin can disable a user, bad values are 400, and another company's user is 404."""
        recruiter = accounts["a"].get("recruiter")
        if not recruiter:
            pytest.skip("depends on test_22 (recruiter not created)")
        a, b = accounts["a"], accounts["b"]
        assert api("PATCH", f"/users/{recruiter['id']}", a["sid"], json={"role": "boss"}).status_code == 400
        assert api("PATCH", f"/users/{recruiter['id']}", b["sid"], json={"status": "disabled"}).status_code == 404
        r = api("PATCH", f"/users/{recruiter['id']}", a["sid"], json={"status": "disabled"})
        assert r.status_code == 200 and r.json()["status"] == "disabled"
        say("✅ invalid role -> 400; other company -> 404; admin disables the recruiter -> 200")


@pytest.mark.api
class TestApiAssessments:
    def test_26_create_list_get_and_patch(self, api: Api, accounts: Any, run_id: str, say: Say) -> None:
        """Assessments: create (draft), list, read back, and edit."""
        sid = accounts["a"]["sid"]
        aid = new_assessment(api, sid, run_id, jd="A short placeholder description.", sections=SECTIONS_ONE_MCQ)
        assert aid in {x["id"] for x in api("GET", "/assessments", sid).json()}
        got = api("GET", f"/assessments/{aid}", sid)
        assert got.status_code == 200 and got.json()["status"] == "draft" and got.json()["sections"] == SECTIONS_ONE_MCQ
        edited = api("PATCH", f"/assessments/{aid}", sid, json={"title": f"{run_id} renamed"})
        assert edited.status_code == 200 and edited.json()["title"] == f"{run_id} renamed"
        assert api("PATCH", f"/assessments/{aid}", sid, json={}).status_code == 400
        say("✅ created a draft; listed, read, renamed it; an empty edit -> 400")

    def test_27_assessment_validation_errors(self, api: Api, accounts: Any, run_id: str, say: Say) -> None:
        """Bad input is refused with 400: a duration below the minimum, and no sections."""
        sid = accounts["a"]["sid"]
        base = {"title": f"{run_id} bad", "durationMinutes": 30, "passingScore": 50, "sections": SECTIONS_ONE_MCQ}
        assert api("POST", "/assessments", sid, json={**base, "durationMinutes": 1}).status_code == 400
        assert api("POST", "/assessments", sid, json={**base, "sections": []}).status_code == 400
        say("✅ duration 1 minute -> 400; zero sections -> 400")

    def test_28_pdf_upload_extracts_the_text(self, api: Api, accounts: Any, run_id: str, say: Say) -> None:
        """POST /assessments/{id}/jd-file: a real PDF is accepted, its text extracted and stored."""
        sid = accounts["a"]["sid"]
        aid = new_assessment(api, sid, run_id, jd=None, sections=SECTIONS_ONE_MCQ)
        r = api(
            "POST",
            f"/assessments/{aid}/jd-file",
            sid,
            files={"file": ("systemtest-jd.pdf", make_pdf(JD_LINES), "application/pdf")},
        )
        assert r.status_code == 200, f"upload: HTTP {r.status_code} {r.text[:120]}"
        assert "FastAPI" in r.json()["jobDescription"] and r.json()["wordCount"] >= 100
        assert api("GET", f"/assessments/{aid}", sid).json()["jdFileName"] == "systemtest-jd.pdf"
        say(f"✅ PDF uploaded; {r.json()['wordCount']} words extracted and saved with the assessment")

    def test_29_bad_files_are_rejected(self, api: Api, accounts: Any, run_id: str, say: Say) -> None:
        """A file that is not really a PDF, and a file over 2 MB, are refused with 400."""
        sid = accounts["a"]["sid"]
        aid = new_assessment(api, sid, run_id, jd=None, sections=SECTIONS_ONE_MCQ)
        fake = api(
            "POST", f"/assessments/{aid}/jd-file", sid, files={"file": ("evil.pdf", b"MZ not a pdf", "application/pdf")}
        )
        big = api("POST", f"/assessments/{aid}/jd-file", sid, files={"file": ("big.txt", b"a" * (2 * 1024 * 1024 + 1))})
        assert fake.status_code == 400 and big.status_code == 400
        say("✅ disguised executable -> 400; file over 2 MB -> 400")

    def test_30_a_draft_cannot_be_closed(self, api: Api, accounts: Any, run_id: str, say: Say) -> None:
        """POST /assessments/{id}/close only applies to approved or open assessments: a draft -> 409."""
        sid = accounts["a"]["sid"]
        aid = new_assessment(api, sid, run_id, jd=None, sections=SECTIONS_ONE_MCQ)
        assert api("POST", f"/assessments/{aid}/close", sid).status_code == 409
        say("✅ closing a draft -> 409")

    def test_31_delete_a_draft(self, api: Api, accounts: Any, run_id: str, say: Say) -> None:
        """DELETE /assessments/{id}: a draft is deleted (204) and is then gone (404)."""
        sid = accounts["a"]["sid"]
        aid = new_assessment(api, sid, run_id, jd=None, sections=SECTIONS_ONE_MCQ)
        assert api("DELETE", f"/assessments/{aid}", sid).status_code == 204
        assert api("GET", f"/assessments/{aid}", sid).status_code == 404
        say("✅ draft deleted -> 204, then 404")

    def test_32_another_company_gets_404(self, api: Api, accounts: Any, run_id: str, say: Say) -> None:
        """Tenant isolation: company B cannot read, delete or close company A's assessment (404, not 403)."""
        aid = new_assessment(api, accounts["a"]["sid"], run_id, jd=None, sections=SECTIONS_ONE_MCQ)
        b = accounts["b"]["sid"]
        for method, suffix in (("GET", ""), ("DELETE", ""), ("POST", "/close")):
            assert api(method, f"/assessments/{aid}{suffix}", b).status_code == 404, f"{method}{suffix}"
        assert aid not in {x["id"] for x in api("GET", "/assessments", b).json()}
        say("✅ company B: GET/DELETE/close on A's assessment -> 404; A's assessment absent from B's list")


@pytest.mark.api
class TestApiQuestionsAndGeneration:
    def test_33_questions_add_edit_delete_and_validate(self, api: Api, accounts: Any, run_id: str, say: Say) -> None:
        """Questions: add a multiple-choice question by hand, edit it, delete it; invalid questions are refused (400)."""
        sid = accounts["a"]["sid"]
        aid = new_assessment(api, sid, run_id, jd=None, sections=SECTIONS_ONE_MCQ)
        assert api("GET", f"/assessments/{aid}/questions", sid).json() == []
        good = {
            "sectionIndex": 0,
            "type": "mcq",
            "body": "Which keyword defines a function in Python?",
            "options": ["def", "func", "fn", "lambda"],
            "correctAnswer": "A",
        }
        assert (
            api("POST", f"/assessments/{aid}/questions", sid, json={**good, "options": ["a", "b", "c"]}).status_code
            == 400
        )
        created = api("POST", f"/assessments/{aid}/questions", sid, json=good)
        assert created.status_code == 201
        qid = created.json()["id"]
        edited = api("PATCH", f"/questions/{qid}", sid, json={"body": "Which keyword defines a function?"})
        assert edited.status_code == 200 and edited.json()["body"] == "Which keyword defines a function?"
        assert api("DELETE", f"/questions/{qid}", sid).status_code == 204
        assert api("GET", f"/assessments/{aid}/questions", sid).json() == []
        say("✅ question added (3 options -> 400), edited, deleted")

    def test_34_approval_needs_complete_sections_then_freezes(
        self, api: Api, accounts: Any, run_id: str, say: Say
    ) -> None:
        """POST /assessments/{id}/approve: refused with no questions (409) or an incomplete section (409); afterwards frozen."""
        sid = accounts["a"]["sid"]
        two_mcq = [{"type": "mcq", "domain": "Python", "difficulty": "easy", "count": 2}]
        aid = new_assessment(api, sid, run_id, jd=None, sections=two_mcq)
        none_yet = api("POST", f"/assessments/{aid}/approve", sid)
        assert none_yet.status_code == 409 and none_yet.json()["error"]["code"] == "NO_QUESTIONS"

        def mcq(body: str) -> dict[str, Any]:
            return {
                "sectionIndex": 0,
                "type": "mcq",
                "body": body,
                "options": ["break", "pass", "skip", "stop"],
                "correctAnswer": "A",
            }

        first = api("POST", f"/assessments/{aid}/questions", sid, json=mcq("Which statement ends a loop early?"))
        assert first.status_code == 201
        short = api("POST", f"/assessments/{aid}/approve", sid)
        assert short.status_code == 409 and short.json()["error"]["code"] == "SECTION_INCOMPLETE"
        assert (
            api(
                "POST", f"/assessments/{aid}/questions", sid, json=mcq("Which statement skips an iteration?")
            ).status_code
            == 201
        )
        ok = api("POST", f"/assessments/{aid}/approve", sid)
        assert ok.status_code == 200 and ok.json()["questionCount"] == 2
        assert api("PATCH", f"/questions/{first.json()['id']}", sid, json={"body": "late edit"}).status_code == 409
        assert api("POST", f"/assessments/{aid}/generate", sid, json={}).status_code == 409
        say("✅ approve with no questions -> 409 NO_QUESTIONS; with a short section -> 409 SECTION_INCOMPLETE")
        say("✅ approved once complete; afterwards edits and regeneration -> 409 (frozen)")

    def test_35_generation_request_rules_without_calling_the_ai(
        self, api: Api, accounts: Any, run_id: str, say: Say
    ) -> None:
        """POST /assessments/{id}/generate refuses a too-short description (422), unknown ids (404) and bad section numbers (400)."""
        sid = accounts["a"]["sid"]
        short = new_assessment(api, sid, run_id, jd="too short", sections=SECTIONS_ONE_MCQ)
        r = api("POST", f"/assessments/{short}/generate", sid, json={})
        assert r.status_code == 422 and r.json()["error"]["code"] == "JD_TOO_SHORT"
        zero = "00000000-0000-4000-8000-000000000000"
        assert api("POST", f"/assessments/{zero}/generate", sid, json={}).status_code == 404
        assert api("GET", f"/jobs/{zero}", sid).status_code == 404
        long_jd = new_assessment(api, sid, run_id, jd=JD_TEXT, sections=SECTIONS_ONE_MCQ)
        assert api("POST", f"/assessments/{long_jd}/generate", sid, json={"sectionIndexes": [7]}).status_code == 400
        say("✅ short description -> 422 JD_TOO_SHORT; unknown assessment/job -> 404; section 7 of 1 -> 400")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 5. END-TO-END WORKFLOWS (one real AI generation in the whole suite)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.e2e
class TestEndToEnd:
    def test_36_e2e_create_assessment_and_upload_job_description(
        self, api: Api, accounts: Any, run_id: str, say: Say
    ) -> None:
        """API -> service -> Azure Blob + SQL: a recruiter creates an assessment and uploads a job-description PDF."""
        a = accounts["a"]
        aid = new_assessment(api, a["sid"], run_id, jd=None, sections=SECTIONS_AI)
        r = api(
            "POST",
            f"/assessments/{aid}/jd-file",
            a["sid"],
            files={"file": ("systemtest-jd.pdf", make_pdf(JD_LINES), "application/pdf")},
        )
        assert r.status_code == 200 and r.json()["wordCount"] >= 100
        STATE["assessment_id"] = aid
        say(
            f"✅ assessment created ({len(SECTIONS_AI)} sections) and job description saved ({r.json()['wordCount']} words)"
        )

    def test_37_e2e_generate_questions_with_the_ai_model(self, api: Api, accounts: Any, say: Say) -> None:
        """API -> background job -> AI model -> validator -> SQL: questions are generated, validated and stored."""
        aid, sid = need("assessment_id"), accounts["a"]["sid"]
        started = api("POST", f"/assessments/{aid}/generate", sid, json={})
        assert started.status_code == 202 and started.json()["status"] == "queued"
        job = wait_job(api, sid, started.json()["jobId"], say)
        assert job["status"] == "done", f"generation job failed: {job.get('error')} ({job.get('errorCode')})"
        assert job["result"]["questionsCreated"] == 3
        questions = api("GET", f"/assessments/{aid}/questions", sid).json()
        assert [q["type"] for q in questions] == ["mcq", "mcq", "descriptive"]
        for q in questions[:2]:
            assert (
                len(q["options"]) == 4 and len({o.lower() for o in q["options"]}) == 4 and q["correctAnswer"] in "ABCD"
            )
        assert questions[2]["rubric"] and 1 <= questions[2]["maxScore"] <= 20
        STATE["questions"] = questions
        STATE["generate_job_id"] = started.json()["jobId"]
        say(f"✅ job done: 3 valid questions (2 multiple-choice, 1 descriptive); tokens used: {job['tokensUsed']}")

    def test_38_e2e_review_edit_and_regenerate(self, api: Api, accounts: Any, say: Say) -> None:
        """A reviewer edits one question and asks the AI to regenerate another; ids and order are preserved."""
        aid, sid, before = need("assessment_id"), accounts["a"]["sid"], need("questions")
        edited = api(
            "PATCH",
            f"/questions/{before[0]['id']}",
            sid,
            json={"body": "Edited by the system test: which option is correct?"},
        )
        assert edited.status_code == 200
        again = api("POST", f"/questions/{before[1]['id']}/regenerate", sid)
        assert again.status_code == 202
        job = wait_job(api, sid, again.json()["jobId"], say)
        assert job["status"] == "done", f"regeneration failed: {job.get('error')}"
        after = api("GET", f"/assessments/{aid}/questions", sid).json()
        assert [q["id"] for q in after] == [q["id"] for q in before], "regeneration must keep ids and order"
        assert after[0]["body"].startswith("Edited by the system test") and after[1]["body"] != before[1]["body"]
        STATE["regenerate_job_id"] = again.json()["jobId"]
        say("✅ question 1 edited; question 2 regenerated by the AI (same id and position, new text)")

    def test_39_e2e_approve_freeze_and_close(self, api: Api, accounts: Any, say: Say) -> None:
        """Approve the reviewed assessment (it becomes read-only) and close it."""
        aid, sid = need("assessment_id"), accounts["a"]["sid"]
        approved = api("POST", f"/assessments/{aid}/approve", sid)
        assert approved.status_code == 200 and approved.json()["questionCount"] == 3
        qid = api("GET", f"/assessments/{aid}/questions", sid).json()[0]["id"]
        assert api("PATCH", f"/questions/{qid}", sid, json={"body": "too late"}).status_code == 409
        closed = api("POST", f"/assessments/{aid}/close", sid)
        assert closed.status_code == 200
        assert api("GET", f"/assessments/{aid}", sid).json()["status"] == "closed"
        say("✅ approved (3 questions), frozen against edits, then closed")

    def test_40_e2e_job_description_file_lands_in_blob_and_is_removed(
        self, api: Api, accounts: Any, run_id: str, blob_container: Any, tracker: Any, say: Say
    ) -> None:
        """The uploaded PDF is stored in Azure Blob Storage at <tenant>/<assessment>/<file> and removed when the draft is deleted."""
        a = accounts["a"]
        aid = new_assessment(api, a["sid"], run_id, jd=None, sections=SECTIONS_ONE_MCQ)
        up = api(
            "POST",
            f"/assessments/{aid}/jd-file",
            a["sid"],
            files={"file": ("systemtest-blob.pdf", make_pdf(JD_LINES), "application/pdf")},
        )
        assert up.status_code == 200
        file_name = api("GET", f"/assessments/{aid}", a["sid"]).json()["jdFileName"]
        name = f"{a['tenantId']}/{aid}/{file_name}"
        if blob_container is None:
            assert api("DELETE", f"/assessments/{aid}", a["sid"]).status_code == 204
            pytest.skip("BLOB_CONNECTION_STRING not set: API steps passed, the Azure Blob check was skipped")
        tracker.blobs.append(name)
        assert blob_container.get_blob_client(name).exists(), "the uploaded file is not in Azure Blob Storage"
        say(f"✅ file found in Blob Storage at <tenant>/<assessment>/{name.rsplit('/', 1)[-1]}")
        assert api("DELETE", f"/assessments/{aid}", a["sid"]).status_code == 204
        assert not blob_container.get_blob_client(name).exists(), "the file was not removed with the assessment"
        tracker.blobs.remove(name)
        say("✅ deleting the draft removed the file from Blob Storage")

    def test_41_e2e_tenant_isolation_holds_across_the_stack(self, api: Api, accounts: Any, say: Say) -> None:
        """Company B cannot reach company A's assessment, questions or jobs through any endpoint."""
        aid, qs, b = need("assessment_id"), need("questions"), accounts["b"]["sid"]
        job_id = STATE.get("generate_job_id", "00000000-0000-4000-8000-000000000000")
        probes = [
            ("GET", f"/assessments/{aid}"),
            ("GET", f"/assessments/{aid}/questions"),
            ("POST", f"/assessments/{aid}/generate"),
            ("POST", f"/assessments/{aid}/approve"),
            ("PATCH", f"/questions/{qs[0]['id']}"),
            ("DELETE", f"/questions/{qs[0]['id']}"),
            ("POST", f"/questions/{qs[0]['id']}/regenerate"),
            ("GET", f"/jobs/{job_id}"),
        ]
        for method, path in probes:
            kw = {"json": {"body": "x"}} if method in ("PATCH", "POST") else {}
            assert api(method, path, b, **kw).status_code == 404, f"{method} {path} leaked across companies"
        say(f"✅ {len(probes)} cross-company attempts all returned 404")

    def test_42_e2e_what_the_api_wrote_is_in_azure_sql(
        self, accounts: Any, sql_engine: Any, env: Any, say: Say
    ) -> None:
        """API -> SQL: read the rows back from Azure SQL (admin user, assessment, questions, jobs with token usage, audit trail)."""
        env.require("DATABASE_URL", "Azure SQL connection")
        aid = need("assessment_id")
        from sqlalchemy import text

        schema, tid = env.get("DB_SCHEMA", "assess"), accounts["a"]["tenantId"]

        def count(conn: Any, sql: str, **params: Any) -> int:
            return int(conn.execute(text(sql), {"t": tid, **params}).scalar() or 0)

        with sql_engine.connect() as conn:
            if count(conn, f"SELECT COUNT(*) FROM [{schema}].[tenants] WHERE id = :t") == 0:
                pytest.skip("the company is not in this database: the API server is probably in memory mode")
            assert count(conn, f"SELECT COUNT(*) FROM [{schema}].[users] WHERE tenant_id = :t") >= 1
            assert (
                count(
                    conn,
                    f"SELECT COUNT(*) FROM [{schema}].[assessments] WHERE tenant_id = :t AND id = :a AND status = 'closed'",
                    a=aid,
                )
                == 1
            )
            assert (
                count(
                    conn,
                    f"SELECT COUNT(*) FROM [{schema}].[questions] WHERE tenant_id = :t AND assessment_id = :a",
                    a=aid,
                )
                == 3
            )
            assert count(conn, f"SELECT COUNT(*) FROM [{schema}].[jobs] WHERE tenant_id = :t AND status = 'done'") >= 2
            tokens = count(conn, f"SELECT COALESCE(SUM(tokens_used), 0) FROM [{schema}].[jobs] WHERE tenant_id = :t")
            actions = {
                str(r[0])
                for r in conn.execute(
                    text(f"SELECT action FROM [{schema}].[audit_log] WHERE tenant_id = :t"), {"t": tid}
                )
            }
        assert {"assessment.create", "assessment.close"} <= actions, f"audit trail incomplete: {sorted(actions)}"
        say(
            f"✅ Azure SQL holds the data: admin user, closed assessment, 3 questions, 2 finished jobs ({tokens} AI tokens recorded)"
        )
        say(f"✅ audit trail has {len(actions)} kinds of events, including assessment.create and assessment.close")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 6. CLEANUP
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.e2e
@pytest.mark.cleanup
class TestCleanup:
    def test_43_cleanup_removes_all_systemtest_data(self, cleanup: Callable[[], dict[str, Any]], say: Say) -> None:
        """Every company, row and file named systemtest_ is removed from Azure SQL and Blob Storage (also runs after failures)."""
        summary = cleanup()
        for note in summary["notes"]:
            say(f"ℹ️  {note}")
        if summary["remaining_blobs"] is not None:
            assert summary["blob_errors"] == 0, f"{summary['blob_errors']} test files could not be deleted from storage"
            assert summary["remaining_blobs"] == 0, f"{summary['remaining_blobs']} test files are still in storage"
        if summary["remaining_tenants"] is not None:
            assert summary["remaining_tenants"] == 0, (
                f"{summary['remaining_tenants']} test companies are still in the database"
            )
        say(
            f"✅ removed {summary['tenants']} test companies, {summary['login_attempts']} login records and "
            f"{summary['blobs']} files; remaining: {summary['remaining_tenants']} companies, {summary['remaining_blobs']} files"
        )
