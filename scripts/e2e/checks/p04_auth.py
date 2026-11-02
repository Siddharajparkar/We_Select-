"""Phase 4 live checks: endpoints 1-7 against a running API (two throw-away tenants, E2E-A and E2E-B)."""

from __future__ import annotations

import re
import uuid

PW = "E2e-Passw0rd-" + uuid.uuid4().hex[:8]  # random per run; never printed


def _sid(resp) -> str:  # type: ignore[no-untyped-def]
    m = re.search(r"sid=([^;]+)", resp.headers.get("set-cookie", ""))
    assert m, "login did not set the sid cookie"
    return m.group(1)


def create_tenants_and_login(ctx):  # type: ignore[no-untyped-def]
    run = uuid.uuid4().hex[:10]
    for tag in ("A", "B"):
        email = f"e2e-{tag.lower()}-{run}@e2e.example"
        r = ctx.request(
            "POST", "/api/v1/platform/tenants", headers={"X-Platform-Key": ctx.platform_key},
            json={"name": f"E2E-{tag}", "adminName": f"E2E Admin {tag}", "adminEmail": email, "password": PW},
        )  # fmt: skip
        assert r.status_code == 201, f"create tenant {tag}: status {r.status_code}"
        lr = ctx.request("POST", "/api/v1/auth/login", json={"email": email, "password": PW})
        assert lr.status_code == 200, f"login {tag}: status {lr.status_code}"
        ctx.state[tag] = {**r.json(), "email": email, "sid": _sid(lr), "set_cookie": lr.headers["set-cookie"]}


def login_cookie_is_httponly_secure_lax(ctx):  # type: ignore[no-untyped-def]
    c = ctx.state["A"]["set_cookie"].lower()
    for attr in ("httponly", "secure", "samesite=lax", "path=/", "max-age=28800"):
        assert attr in c, f"cookie missing {attr}"


def me_returns_user_and_tenant(ctx):  # type: ignore[no-untyped-def]
    a = ctx.state["A"]
    r = ctx.request("GET", "/api/v1/auth/me", a["sid"])
    assert r.status_code == 200 and r.json()["tenant"]["id"] == a["tenantId"], f"status {r.status_code}"


def unauthenticated_requests_are_401(ctx):  # type: ignore[no-untyped-def]
    for method, path in (("GET", "/api/v1/auth/me"), ("GET", "/api/v1/users"), ("POST", "/api/v1/auth/logout")):
        assert ctx.request(method, path).status_code == 401, f"{method} {path} should be 401"


def wrong_password_is_401(ctx):  # type: ignore[no-untyped-def]
    r = ctx.request(
        "POST", "/api/v1/auth/login", json={"email": f"nobody-{uuid.uuid4().hex[:8]}@e2e.example", "password": "x"}
    )
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS", f"status {r.status_code}"


def users_lists_only_own_tenant(ctx):  # type: ignore[no-untyped-def]
    a, b = ctx.state["A"], ctx.state["B"]
    ids = {u["id"] for u in ctx.request("GET", "/api/v1/users", a["sid"]).json()}
    assert a["adminUserId"] in ids and b["adminUserId"] not in ids, "user list is not tenant-scoped"


def cross_tenant_patch_is_404(ctx):  # type: ignore[no-untyped-def]
    a, b = ctx.state["A"], ctx.state["B"]
    r = ctx.request("PATCH", f"/api/v1/users/{b['adminUserId']}", a["sid"], json={"status": "disabled"})
    assert r.status_code == 404, f"status {r.status_code}"


def create_user_and_duplicate_email_409(ctx):  # type: ignore[no-untyped-def]
    a = ctx.state["A"]
    email = f"rec-{uuid.uuid4().hex[:8]}@e2e.example"
    body = {"name": "Recruiter", "email": email, "role": "recruiter", "password": PW}
    assert ctx.request("POST", "/api/v1/users", a["sid"], json=body).status_code == 201
    r = ctx.request("POST", "/api/v1/users", a["sid"], json={**body, "email": email.upper()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_EXISTS", f"status {r.status_code}"
    rc = ctx.request("POST", "/api/v1/auth/login", json={"email": email, "password": PW})
    assert rc.status_code == 200
    assert ctx.request("GET", "/api/v1/users", _sid(rc)).status_code == 403, "recruiter must not list users"
    ctx.state["recruiter"] = {"email": email, "sid": _sid(rc)}


def logout_invalidates_the_session(ctx):  # type: ignore[no-untyped-def]
    b = ctx.state["B"]
    lr = ctx.request("POST", "/api/v1/auth/login", json={"email": b["email"], "password": PW})
    sid = _sid(lr)
    assert ctx.request("POST", "/api/v1/auth/logout", sid).status_code == 204
    assert ctx.request("GET", "/api/v1/auth/me", sid).status_code == 401, "session still valid after logout"


CHECKS = [
    create_tenants_and_login,
    login_cookie_is_httponly_secure_lax,
    me_returns_user_and_tenant,
    unauthenticated_requests_are_401,
    wrong_password_is_401,
    users_lists_only_own_tenant,
    cross_tenant_patch_is_404,
    create_user_and_duplicate_email_409,
    logout_invalidates_the_session,
]
