"""Phase 0: HTTP contract of the app skeleton (health, envelope, headers, middleware)."""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import AppError
from app.main import create_app

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def test_health_returns_exact_contract_body(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert r.text == '{"status":"ok"}'
    assert r.headers["content-type"].startswith("application/json")


def test_health_sets_version_and_no_store_headers(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.headers["x-app-version"] == "test-sha-123"
    assert r.headers["cache-control"] == "no-store"


def test_request_id_generated_when_absent(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert UUID_RE.match(r.headers["x-request-id"])


def test_request_id_echoed_when_valid(client: TestClient) -> None:
    r = client.get("/api/v1/health", headers={"x-request-id": "trace-abc_123.4"})
    assert r.headers["x-request-id"] == "trace-abc_123.4"


@pytest.mark.parametrize("bad", ["has space", "x" * 200, "semi;colon", "new\tline"])
def test_request_id_replaced_when_unsafe(client: TestClient, bad: str) -> None:
    try:
        r = client.get("/api/v1/health", headers={"x-request-id": bad})
    except Exception:  # noqa: BLE001 - some clients refuse illegal header values outright
        return
    assert r.headers["x-request-id"] != bad
    assert UUID_RE.match(r.headers["x-request-id"])


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "NOT_FOUND", "message": "Route not found"}}
    assert r.headers["x-app-version"] == "test-sha-123"  # even errors carry the standard headers


def test_wrong_method_uses_error_envelope(client: TestClient) -> None:
    r = client.post("/api/v1/health")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_security_headers_present(client: TestClient) -> None:
    h = client.get("/api/v1/health").headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "no-referrer"
    assert "max-age" in h["strict-transport-security"]


def test_body_over_1mb_is_rejected_with_413(client: TestClient) -> None:
    r = client.post("/api/v1/health", content=b"x" * 1_100_000)
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


class Body(BaseModel):
    email: str
    age: int


def _app_with_extra_routes(app):  # type: ignore[no-untyped-def]
    @app.post("/api/v1/_t/validate")
    def validate(b: Body) -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/v1/_t/app-error")
    def app_error() -> None:
        raise AppError.conflict("EMAIL_EXISTS", "Email already registered", [{"field": "email"}])

    @app.get("/api/v1/_t/boom")
    def boom() -> None:
        raise RuntimeError("SELECT * FROM secrets WHERE password='hunter2'")

    return app


def test_validation_errors_become_400_validation_error_with_details(app) -> None:  # type: ignore[no-untyped-def]
    c = TestClient(_app_with_extra_routes(app))
    r = c.post("/api/v1/_t/validate", json={"email": "a@b.c", "age": "not-a-number"})
    assert r.status_code == 400
    body = r.json()["error"]
    assert body["code"] == "VALIDATION_ERROR"
    assert any(d["path"] == "age" for d in body["details"])


def test_app_error_is_rendered_with_envelope(app) -> None:  # type: ignore[no-untyped-def]
    r = TestClient(_app_with_extra_routes(app)).get("/api/v1/_t/app-error")
    assert r.status_code == 409
    assert r.json() == {
        "error": {"code": "EMAIL_EXISTS", "message": "Email already registered", "details": [{"field": "email"}]}
    }


def test_unhandled_exception_returns_500_without_leaking_internals(app, capsys) -> None:  # type: ignore[no-untyped-def]
    c = TestClient(_app_with_extra_routes(app), raise_server_exceptions=False)
    r = c.get("/api/v1/_t/boom")
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "INTERNAL", "message": "Internal server error"}}
    assert "hunter2" not in r.text and "SELECT" not in r.text
    assert r.headers["x-request-id"] and r.headers["x-app-version"] == "test-sha-123"
    logged = capsys.readouterr()
    assert "hunter2" not in logged.out + logged.err  # message text is not logged either


def test_access_log_has_required_fields_and_omits_query(client: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    client.get("/api/v1/health?token=SUPERSECRET&x=1", headers={"x-request-id": "log-test-1"})
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    entry = next(line for line in lines if line.get("requestId") == "log-test-1")
    assert entry["method"] == "GET" and entry["path"] == "/api/v1/health" and entry["status"] == 200
    assert isinstance(entry["durationMs"], (int, float))
    assert "SUPERSECRET" not in json.dumps(entry)


def test_openapi_docs_enabled_in_development_disabled_in_production(settings) -> None:  # type: ignore[no-untyped-def]
    dev = TestClient(create_app(settings))
    assert dev.get("/api/v1/openapi.json").status_code == 200
    from app.config import load_settings

    prod = load_settings(
        APP_ENV="production", AI_MODE="azure", EMAIL_MODE="azure", FILES_MODE="azure", REPO_BACKEND="sql",
        DATABASE_URL="Server=tcp:h,1433;Database=d;User ID=u;Password=p;", SESSION_SECRET="s" * 40,
        PLATFORM_KEY="p" * 40, FOUNDRY_ENDPOINT="https://x.invalid", FOUNDRY_KEY="k",
        ACS_CONNECTION_STRING="endpoint=x;accesskey=y", ACS_SENDER="a@b.invalid",
        BLOB_CONNECTION_STRING="UseDevelopmentStorage=true",
    )  # fmt: skip
    from app.providers import create_providers
    from app.repositories import create_repositories

    # Inject memory repos so no SQL connection is attempted; providers faked out for the same reason.
    app = create_app(prod, repos=create_repositories("memory"), providers=create_providers(settings))
    assert TestClient(app).get("/api/v1/openapi.json").status_code == 404
