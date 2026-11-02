"""Single source of truth for the three Postman collections (unit / integration / e2e).

``generate.py`` turns this into Postman v2.1 JSON (with pm.test scripts); ``run_collection.py`` executes
the *same* specification in Python (no Node, no newman). A test fails if the committed JSON drifts from this file.

Expectation keys (all optional):
    status              int or "{{var}}"
    body_json           exact JSON equality
    body_text           exact body text
    json_has            {"dotted.path": value}
    body_not_contains   [substrings that must NOT appear]
    headers_equal       {header: value | "{{var}}"}
    headers_not_equal   {header: "{{var}}"}
    headers_present     [header, ...]
    headers_match       {header: regex}
    save                {var: {"header": name} | {"json": "dotted.path"}}
    when_var            only evaluate the expectations if this variable is non-empty
Request keys: name, method, path, headers, body ({"json":..} | {"repeat":[char,count]}), pre_set ({var: template}).
"""

from __future__ import annotations

from typing import Any

UUID_RE = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
HEALTH = "/api/v1/health"

# Variables every collection starts with (also written to the environment file).
DEFAULT_VARIABLES: dict[str, str] = {
    "baseUrl": "http://localhost:8080",
    "expectedVersion": "",  # set to the deployed commit SHA to assert the new revision answered
    "docsStatus": "200",  # 200 in development (OpenAPI docs on), 404 in production (off)
}


def _req(name: str, method: str, path: str, **kw: Any) -> dict[str, Any]:
    return {"name": name, "method": method, "path": path, **kw}


# ═════════════════════════════════ UNIT: one endpoint, one behaviour each ═════════════════════════
UNIT: dict[str, Any] = {
    "name": "AI Assessment Platform - Phase 3 - UNIT",
    "description": (
        "Single-request contract checks of the Phase 0-3 API skeleton: health body, headers, error envelope, "
        "request-id handling, body limit. Each request is independent."
    ),
    "items": [
        _req(
            "U01 health returns the exact contract body",
            "GET",
            HEALTH,
            expect={
                "status": 200,
                "body_json": {"status": "ok"},
                "body_text": '{"status":"ok"}',
                "headers_match": {"content-type": r"^application/json"},
            },
        ),  # fmt: skip
        _req(
            "U02 health reports the app version header",
            "GET",
            HEALTH,
            expect={
                "status": 200,
                "headers_present": ["x-app-version"],
                "headers_match": {"x-app-version": r"^[A-Za-z0-9._\-]{1,64}$"},
            },
        ),  # fmt: skip
        _req(
            "U03 health is never cached",
            "GET",
            HEALTH,
            expect={
                "status": 200,
                "headers_equal": {"cache-control": "no-store"},
            },
        ),  # fmt: skip
        _req(
            "U04 security headers are present",
            "GET",
            HEALTH,
            expect={
                "status": 200,
                "headers_equal": {
                    "x-content-type-options": "nosniff",
                    "x-frame-options": "DENY",
                    "referrer-policy": "no-referrer",
                },
                "headers_present": ["strict-transport-security"],
            },
        ),  # fmt: skip
        _req(
            "U05 unknown route returns the 404 error envelope",
            "GET",
            "/api/v1/does-not-exist",
            expect={
                "status": 404,
                "body_json": {"error": {"code": "NOT_FOUND", "message": "Route not found"}},
            },
        ),  # fmt: skip
        _req(
            "U06 wrong method returns the 405 error envelope",
            "POST",
            HEALTH,
            expect={
                "status": 405,
                "json_has": {"error.code": "METHOD_NOT_ALLOWED"},
            },
        ),  # fmt: skip
        _req(
            "U07 a valid x-request-id is echoed",
            "GET",
            HEALTH,
            headers={"x-request-id": "unit-trace-123"},
            expect={
                "status": 200,
                "headers_equal": {"x-request-id": "unit-trace-123"},
            },
        ),  # fmt: skip
        _req(
            "U08 a request id is generated when absent",
            "GET",
            HEALTH,
            expect={
                "status": 200,
                "headers_match": {"x-request-id": UUID_RE},
            },
        ),  # fmt: skip
        _req(
            "U09 an unsafe x-request-id is replaced",
            "GET",
            HEALTH,
            headers={"x-request-id": "bad id;with spaces"},
            expect={
                "status": 200,
                "headers_match": {"x-request-id": UUID_RE},
            },
        ),  # fmt: skip
        _req(
            "U10 bodies over 1 MB are rejected with 413",
            "POST",
            HEALTH,
            body={"repeat": ["x", 1_100_000]},
            expect={
                "status": 413,
                "json_has": {"error.code": "PAYLOAD_TOO_LARGE"},
            },
        ),  # fmt: skip
        _req(
            "U11 error bodies are JSON, not HTML",
            "GET",
            "/api/v1/nope",
            expect={
                "status": 404,
                "headers_match": {"content-type": r"^application/json"},
                "body_not_contains": ["<html", "Traceback"],
            },
        ),  # fmt: skip
    ],
}

# ═══════════════════════ INTEGRATION: cross-cutting behaviour across several requests ══════════════
INTEGRATION: dict[str, Any] = {
    "name": "AI Assessment Platform - Phase 3 - INTEGRATION",
    "description": (
        "Phases 0-3 working together over HTTP: the same version and request-id behaviour on success and error "
        "paths, no leakage, stable service under repeated and abusive calls. Requests run in order and share variables."
    ),
    "items": [
        _req(
            "I01 capture version and request id from health",
            "GET",
            HEALTH,
            expect={
                "status": 200,
                "save": {"version": {"header": "x-app-version"}, "firstRequestId": {"header": "x-request-id"}},
                "headers_present": ["x-app-version", "x-request-id"],
            },
        ),  # fmt: skip
        _req(
            "I02 second request gets a different generated id",
            "GET",
            HEALTH,
            expect={
                "status": 200,
                "headers_not_equal": {"x-request-id": "{{firstRequestId}}"},
                "headers_equal": {"x-app-version": "{{version}}"},
            },
        ),  # fmt: skip
        _req(
            "I03 version header is identical on a 404",
            "GET",
            "/api/v1/missing",
            expect={
                "status": 404,
                "headers_equal": {"x-app-version": "{{version}}"},
            },
        ),  # fmt: skip
        _req(
            "I04 version header is identical on a 405",
            "DELETE",
            HEALTH,
            expect={
                "status": 405,
                "headers_equal": {"x-app-version": "{{version}}"},
            },
        ),  # fmt: skip
        _req(
            "I05 version header is identical on a 413",
            "POST",
            HEALTH,
            body={"repeat": ["y", 1_100_000]},
            expect={
                "status": 413,
                "headers_equal": {"x-app-version": "{{version}}"},
            },
        ),  # fmt: skip
        _req(
            "I06 the same request id flows through an error path",
            "GET",
            "/api/v1/missing",
            headers={"x-request-id": "integration-trace-777"},
            expect={
                "status": 404,
                "headers_equal": {"x-request-id": "integration-trace-777"},
            },
        ),  # fmt: skip
        _req(
            "I07 error responses keep the security headers",
            "GET",
            "/api/v1/missing",
            expect={
                "status": 404,
                "headers_equal": {"x-content-type-options": "nosniff", "x-frame-options": "DENY"},
            },
        ),  # fmt: skip
        _req(
            "I08 errors never leak internals",
            "GET",
            "/api/v1/missing",
            expect={
                "status": 404,
                "body_not_contains": ["Traceback", "SELECT", "sqlalchemy", "pyodbc", 'File "'],
            },
        ),  # fmt: skip
        _req(
            "I09 query strings are ignored and never reflected",
            "GET",
            HEALTH + "?token=SUPERSECRET&x=1",
            expect={
                "status": 200,
                "body_json": {"status": "ok"},
                "body_not_contains": ["SUPERSECRET"],
            },
        ),  # fmt: skip
        _req(
            "I10 service still healthy after the abusive calls above",
            "GET",
            HEALTH,
            expect={
                "status": 200,
                "body_json": {"status": "ok"},
                "headers_equal": {"x-app-version": "{{version}}"},
            },
        ),  # fmt: skip
        _req(
            "I11 repeated health calls are idempotent (1/2)",
            "GET",
            HEALTH,
            expect={"status": 200, "body_text": '{"status":"ok"}'},
        ),
        _req(
            "I12 repeated health calls are idempotent (2/2)",
            "GET",
            HEALTH,
            expect={"status": 200, "body_text": '{"status":"ok"}'},
        ),
    ],
}

# ═════════════════════════ E2E: the deploy-verification journey (also used against Azure) ═══════════
E2E: dict[str, Any] = {
    "name": "AI Assessment Platform - Phase 3 - E2E",
    "description": (
        "End-to-end journey used locally and after every deploy: the new revision answers (version = commit SHA), "
        "request ids round-trip, errors are well-formed, docs exposure matches the environment, and the service "
        "stays healthy. Set baseUrl, expectedVersion (commit SHA) and docsStatus (404 in production) in the environment."
    ),
    "items": [
        _req(
            "E01 service is up",
            "GET",
            HEALTH,
            expect={
                "status": 200,
                "body_json": {"status": "ok"},
                "save": {"deployedVersion": {"header": "x-app-version"}},
            },
        ),  # fmt: skip
        _req(
            "E02 the NEW revision answered (version equals expectedVersion)",
            "GET",
            HEALTH,
            expect={
                "status": 200,
                "when_var": "expectedVersion",
                "headers_equal": {"x-app-version": "{{expectedVersion}}"},
            },
        ),  # fmt: skip
        _req(
            "E03 request id round-trips",
            "GET",
            HEALTH,
            headers={"x-request-id": "{{traceId}}"},
            pre_set={"traceId": "e2e-{{$guid}}"},
            expect={
                "status": 200,
                "headers_equal": {"x-request-id": "{{traceId}}", "x-app-version": "{{deployedVersion}}"},
            },
        ),  # fmt: skip
        _req(
            "E04 unknown route is a clean 404 envelope with the same version",
            "GET",
            "/api/v1/e2e-not-found",
            expect={
                "status": 404,
                "json_has": {"error.code": "NOT_FOUND"},
                "headers_equal": {"x-app-version": "{{deployedVersion}}"},
            },
        ),  # fmt: skip
        _req(
            "E05 oversized body is rejected and does not hurt the service",
            "POST",
            HEALTH,
            body={"repeat": ["z", 1_100_000]},
            expect={"status": 413, "json_has": {"error.code": "PAYLOAD_TOO_LARGE"}},
        ),
        _req(
            "E06 OpenAPI docs exposure matches the environment",
            "GET",
            "/api/v1/openapi.json",
            expect={
                "status": "{{docsStatus}}",
            },
        ),  # fmt: skip
        _req(
            "E07 service still healthy at the end of the journey",
            "GET",
            HEALTH,
            expect={
                "status": 200,
                "body_json": {"status": "ok"},
                "headers_equal": {"x-app-version": "{{deployedVersion}}"},
            },
        ),  # fmt: skip
    ],
}

COLLECTIONS: dict[str, tuple[str, dict[str, Any]]] = {
    "unit": ("AssessPlatform_Phase3_Unit.postman_collection.json", UNIT),
    "integration": ("AssessPlatform_Phase3_Integration.postman_collection.json", INTEGRATION),
    "e2e": ("AssessPlatform_Phase3_E2E.postman_collection.json", E2E),
}
ENVIRONMENT_FILE = "AssessPlatform_Local.postman_environment.json"
