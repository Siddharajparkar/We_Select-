"""Single source of truth for the Phase 4-6 Postman collections (unit / integration / e2e).

``generate46.py`` turns this into Postman v2.1 JSON (pm.test scripts); ``run46.py`` runs the *same* specification
in Python (no Node, no newman). A unit test fails if the committed JSON drifts from this file.

Scope: auth + tenants + users (phase 4), assessments (phase 5), generation/jobs/questions/approval (phase 6).
Not covered here: the multipart JD upload (Postman cannot attach files from a committed collection) - it is
covered by pytest and by ``scripts/e2e/run.py``.

Expectation keys (all optional):
    status                int
    json_has              {"dotted.path": value}        (list indexes allowed: "0.id")
    json_len              {"dotted.path": length}
    json_match            {"dotted.path": regex}
    headers_present       [header, ...]
    headers_match         {header: regex}
    body_not_contains     [substrings]
    save                  {var: {"json": path} | {"header": h} | {"header_regex": [h, regex]}}
Request keys: name, method, path, headers, body ({"json": ...}), pre_set ({var: template}), wait_var (seconds to
wait before sending, taken from a variable - used to let the background job finish).
Variables in paths, headers and JSON bodies are written ``{{name}}``.
"""

from __future__ import annotations

from typing import Any

P = "/api/v1"
ZERO = "00000000-0000-4000-8000-000000000000"
JD = " ".join(f"skill{i}" for i in range(110))  # >= 100 words, the minimum for generation
SECTIONS = [{"type": "mcq", "domain": "Python", "difficulty": "medium", "count": 3}]
ASSESSMENT = {"title": "Postman Assessment", "jobDescription": JD, "durationMinutes": 30, "passingScore": 50,
              "sections": SECTIONS}  # fmt: skip

DEFAULT_VARIABLES: dict[str, str] = {
    "baseUrl": "http://localhost:8080",
    "platformKey": "dev-only-platform-key-change-me-00000",  # local default; use the real key (never commit it) elsewhere
    "password": "correct-horse-9",
    "waitSeconds": "3",  # background job tick is 2 s; raise it when the real AI is used
    "runId": "",
}
ENVIRONMENT_FILE = "AssessPlatform_Phase4to6_Local.postman_environment.json"


def _req(name: str, method: str, path: str, **kw: Any) -> dict[str, Any]:
    return {"name": name, "method": method, "path": path, **kw}


def _cookie(var: str) -> dict[str, str]:
    return {"Cookie": "sid={{" + var + "}}"}


def _tenant(label: str, var_prefix: str, first: bool = False) -> dict[str, Any]:
    return _req(
        f"{label} create tenant {var_prefix.upper()}", "POST", f"{P}/platform/tenants",
        headers={"X-Platform-Key": "{{platformKey}}"},
        body={"json": {"name": f"Tenant {var_prefix} {{{{runId}}}}", "adminName": f"Admin {var_prefix}",
                       "adminEmail": f"{var_prefix}-{{{{runId}}}}@p46.example", "password": "{{password}}"}},
        **({"pre_set": {"runId": "{{$guid}}"}} if first else {}),
        expect={"status": 201, "json_match": {"tenantId": r"^[0-9a-f-]{36}$"},
                "save": {f"tenantId{var_prefix}": {"json": "tenantId"}}},
    )  # fmt: skip


def _login(label: str, var_prefix: str, email: str) -> dict[str, Any]:
    return _req(
        f"{label} login {var_prefix.upper()}", "POST", f"{P}/auth/login",
        body={"json": {"email": email, "password": "{{password}}"}},
        expect={"status": 200, "headers_match": {"set-cookie": r"sid=[^;]+;.*HttpOnly"},
                "save": {f"sid{var_prefix}": {"header_regex": ["set-cookie", r"sid=([^;]+)"]}}},
    )  # fmt: skip


def _create_assessment(label: str, sid: str, var: str = "assessmentId") -> dict[str, Any]:
    return _req(
        f"{label} create assessment", "POST", f"{P}/assessments", headers=_cookie(sid), body={"json": ASSESSMENT},
        expect={"status": 201, "json_has": {"status": "draft"}, "save": {var: {"json": "id"}}},
    )  # fmt: skip


def _generate_and_wait(label: str, sid: str, aid: str = "assessmentId") -> list[dict[str, Any]]:
    return [
        _req(f"{label} start generation", "POST", f"{P}/assessments/{{{{{aid}}}}}/generate", headers=_cookie(sid),
             body={"json": {}}, expect={"status": 202, "json_has": {"status": "queued"}, "save": {"jobId": {"json": "jobId"}}}),
        _req(f"{label}+ job finishes", "GET", f"{P}/jobs/{{{{jobId}}}}", headers=_cookie(sid), wait_var="waitSeconds",
             expect={"status": 200, "json_has": {"status": "done", "type": "generate", "result.questionsCreated": 3}}),
    ]  # fmt: skip


# ═════════════════════════════════ UNIT: one request, one behaviour ═════════════════════════════════
_WALL = [
    ("GET", f"{P}/auth/me"), ("GET", f"{P}/users"), ("GET", f"{P}/assessments"), ("POST", f"{P}/assessments"),
    ("GET", f"{P}/assessments/{ZERO}"), ("POST", f"{P}/assessments/{ZERO}/generate"),
    ("POST", f"{P}/assessments/{ZERO}/approve"), ("GET", f"{P}/assessments/{ZERO}/questions"),
    ("GET", f"{P}/jobs/{ZERO}"), ("PATCH", f"{P}/questions/{ZERO}"), ("DELETE", f"{P}/questions/{ZERO}"),
    ("POST", f"{P}/questions/{ZERO}/regenerate"),
]  # fmt: skip

UNIT: dict[str, Any] = {
    "name": "AI Assessment Platform - Phases 4-6 - UNIT",
    "description": "Single-request contract checks for auth, tenants, assessments and generation that need no state: "
                   "the authentication wall, validation errors and the platform key.",  # fmt: skip
    "items": [
        *[
            _req(f"U{n:02d} {m} {p.replace(P, '')} needs a session", m, p,
                 expect={"status": 401, "json_has": {"error.code": "UNAUTHENTICATED"}})
            for n, (m, p) in enumerate(_WALL, 1)
        ],
        _req("U13 login with an empty body is a validation error", "POST", f"{P}/auth/login", body={"json": {}},
             expect={"status": 400, "json_has": {"error.code": "VALIDATION_ERROR"}}),
        _req("U14 login with an unknown account gives the generic 401", "POST", f"{P}/auth/login",
             body={"json": {"email": "nobody@p46.example", "password": "whatever-123"}},
             expect={"status": 401, "json_has": {"error.code": "INVALID_CREDENTIALS"}, "body_not_contains": ["nobody"]}),
        _req("U15 creating a tenant without the platform key is refused", "POST", f"{P}/platform/tenants",
             body={"json": {"name": "X", "adminName": "A", "adminEmail": "x@p46.example", "password": "{{password}}"}},
             expect={"status": 401}),
        _req("U16 creating a tenant with a wrong platform key is refused", "POST", f"{P}/platform/tenants",
             headers={"X-Platform-Key": "wrong-key"},
             body={"json": {"name": "X", "adminName": "A", "adminEmail": "x@p46.example", "password": "{{password}}"}},
             expect={"status": 401, "body_not_contains": ["wrong-key"]}),
        _req("U17 responses carry the version and request id", "GET", f"{P}/auth/me",
             expect={"status": 401, "headers_present": ["x-app-version", "x-request-id"]}),
    ],
}  # fmt: skip

# ═════════════════ INTEGRATION: isolation and rules across tenants (stateful, ordered) ═════════════════
INTEGRATION: dict[str, Any] = {
    "name": "AI Assessment Platform - Phases 4-6 - INTEGRATION",
    "description": "Two tenants, one assessment: tenant isolation (404), validation order, the generation job, "
                   "question review and the approval freeze. Requests run in order and share variables.",  # fmt: skip
    "items": [
        _tenant("I01", "a", first=True),
        _tenant("I02", "b"),
        _login("I03", "a", "a-{{runId}}@p46.example"),
        _login("I04", "b", "b-{{runId}}@p46.example"),
        _req("I05 /auth/me returns the caller and the tenant", "GET", f"{P}/auth/me", headers=_cookie("sida"),
             expect={"status": 200, "json_has": {"user.role": "admin"}, "json_match": {"tenant.name": r"^Tenant a "}}),
        _create_assessment("I06", "sida"),
        _req("I07 tenant B cannot read tenant A's assessment", "GET", f"{P}/assessments/{{{{assessmentId}}}}",
             headers=_cookie("sidb"), expect={"status": 404, "json_has": {"error.code": "NOT_FOUND"}}),
        _req("I08 a malformed id is a validation error, not a 404", "GET", f"{P}/assessments/not-a-uuid",
             headers=_cookie("sida"), expect={"status": 400, "json_has": {"error.code": "VALIDATION_ERROR"}}),
        _req("I09 invalid section numbers are rejected before queueing", "POST",
             f"{P}/assessments/{{{{assessmentId}}}}/generate", headers=_cookie("sida"),
             body={"json": {"sectionIndexes": [9]}}, expect={"status": 400, "json_has": {"error.code": "VALIDATION_ERROR"}}),
        _req("I10 tenant B cannot start generation", "POST", f"{P}/assessments/{{{{assessmentId}}}}/generate",
             headers=_cookie("sidb"), body={"json": {}}, expect={"status": 404}),
        *_generate_and_wait("I11", "sida"),
        _req("I13 tenant B cannot read the job", "GET", f"{P}/jobs/{{{{jobId}}}}", headers=_cookie("sidb"),
             expect={"status": 404}),
        _req("I14 questions were created with answers for staff", "GET",
             f"{P}/assessments/{{{{assessmentId}}}}/questions", headers=_cookie("sida"),
             expect={"status": 200, "json_len": {"": 3}, "json_has": {"0.source": "ai", "0.status": "draft"},
                     "json_match": {"0.correctAnswer": r"^[A-D]$"}, "save": {"questionId": {"json": "0.id"}}}),
        _req("I15 tenant B cannot list or edit them", "PATCH", f"{P}/questions/{{{{questionId}}}}",
             headers=_cookie("sidb"), body={"json": {"body": "hijack"}}, expect={"status": 404}),
        _req("I16 an invalid edit is rejected", "PATCH", f"{P}/questions/{{{{questionId}}}}", headers=_cookie("sida"),
             body={"json": {"options": ["only", "two"]}}, expect={"status": 400}),
        _req("I17 a valid edit is applied", "PATCH", f"{P}/questions/{{{{questionId}}}}", headers=_cookie("sida"),
             body={"json": {"body": "Reviewed wording?"}}, expect={"status": 200, "json_has": {"body": "Reviewed wording?"}}),
        _req("I18 approving an unknown assessment is a 404", "POST", f"{P}/assessments/{ZERO}/approve",
             headers=_cookie("sida"), expect={"status": 404}),
        _req("I19 approve", "POST", f"{P}/assessments/{{{{assessmentId}}}}/approve", headers=_cookie("sida"),
             expect={"status": 200, "json_has": {"status": "approved", "questionCount": 3}}),
        _req("I20 an approved assessment cannot be edited", "PATCH", f"{P}/questions/{{{{questionId}}}}",
             headers=_cookie("sida"), body={"json": {"body": "late"}}, expect={"status": 409}),
        _req("I21 an approved assessment cannot be regenerated", "POST",
             f"{P}/assessments/{{{{assessmentId}}}}/generate", headers=_cookie("sida"), body={"json": {}},
             expect={"status": 409, "json_has": {"error.code": "CONFLICT"}}),
    ],
}  # fmt: skip

# ══════════════════ E2E: the golden path of one recruiter, start to finish ══════════════════
E2E: dict[str, Any] = {
    "name": "AI Assessment Platform - Phases 4-6 - E2E",
    "description": "Admin creates a tenant, adds a recruiter; the recruiter creates an assessment, generates and "
                   "reviews questions (edit, regenerate, add own), approves, closes, and signs out.",  # fmt: skip
    "items": [
        _req("E01 health", "GET", f"{P}/health", expect={"status": 200, "json_has": {"status": "ok"}}),
        _tenant("E02", "a", first=True),
        _login("E03", "a", "a-{{runId}}@p46.example"),
        _req("E04 admin adds a recruiter", "POST", f"{P}/users", headers=_cookie("sida"),
             body={"json": {"name": "Rita Recruiter", "email": "rita-{{runId}}@p46.example", "role": "recruiter",
                            "password": "{{password}}"}}, expect={"status": 201, "json_match": {"id": r"^[0-9a-f-]{36}$"}}),
        _login("E05", "r", "rita-{{runId}}@p46.example"),
        _create_assessment("E06", "sidr"),
        *_generate_and_wait("E07", "sidr"),
        _req("E09 review: list questions", "GET", f"{P}/assessments/{{{{assessmentId}}}}/questions", headers=_cookie("sidr"),
             expect={"status": 200, "json_len": {"": 3}, "save": {"q0": {"json": "0.id"}, "q1": {"json": "1.id"},
                                                                   "q2": {"json": "2.id"}}}),
        _req("E10 review: delete one question", "DELETE", f"{P}/questions/{{{{q2}}}}", headers=_cookie("sidr"),
             expect={"status": 204}),
        _req("E11 approval is refused while a section is short", "POST", f"{P}/assessments/{{{{assessmentId}}}}/approve",
             headers=_cookie("sidr"), expect={"status": 409, "json_has": {"error.code": "SECTION_INCOMPLETE"}}),
        _req("E12 review: add an own question", "POST", f"{P}/assessments/{{{{assessmentId}}}}/questions",
             headers=_cookie("sidr"),
             body={"json": {"sectionIndex": 0, "type": "mcq", "body": "Which keyword defines a function?",
                            "options": ["def", "fun", "func", "lambda"], "correctAnswer": "A"}},
             expect={"status": 201, "json_has": {"source": "custom"}}),
        _req("E13 review: regenerate an AI question", "POST", f"{P}/questions/{{{{q1}}}}/regenerate",
             headers=_cookie("sidr"), expect={"status": 202, "save": {"jobId2": {"json": "jobId"}}}),
        _req("E14 regeneration finishes", "GET", f"{P}/jobs/{{{{jobId2}}}}", headers=_cookie("sidr"),
             wait_var="waitSeconds", expect={"status": 200, "json_has": {"status": "done"}}),
        _req("E15 approve", "POST", f"{P}/assessments/{{{{assessmentId}}}}/approve", headers=_cookie("sidr"),
             expect={"status": 200, "json_has": {"status": "approved", "questionCount": 3}}),
        _req("E16 the approved assessment shows up approved", "GET", f"{P}/assessments?status=approved",
             headers=_cookie("sidr"), expect={"status": 200, "json_has": {"0.status": "approved"}}),
        _req("E17 close", "POST", f"{P}/assessments/{{{{assessmentId}}}}/close", headers=_cookie("sidr"),
             expect={"status": 200, "json_has": {"status": "closed"}}),
        _req("E18 sign out", "POST", f"{P}/auth/logout", headers=_cookie("sidr"), expect={"status": 204}),
        _req("E19 the old session no longer works", "GET", f"{P}/auth/me", headers=_cookie("sidr"),
             expect={"status": 401}),
    ],
}  # fmt: skip

COLLECTIONS: dict[str, tuple[str, dict[str, Any]]] = {
    "unit": ("AssessPlatform_Phase4to6_Unit.postman_collection.json", UNIT),
    "integration": ("AssessPlatform_Phase4to6_Integration.postman_collection.json", INTEGRATION),
    "e2e": ("AssessPlatform_Phase4to6_E2E.postman_collection.json", E2E),
}
