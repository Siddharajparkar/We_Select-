"""Phase 4 E2E: a real uvicorn process, real HTTP, default (Secure) cookies, real Argon2 parameters."""

from __future__ import annotations

import re

import httpx
import pytest

pytestmark = pytest.mark.e2e
API = "/api/v1"
KEY = "dev-only-platform-key-change-me-00000"  # the development default; production refuses it
PW = "correct-horse-9"


def sid_from(resp: httpx.Response) -> str:
    m = re.search(r"sid=([^;]+)", resp.headers.get("set-cookie", ""))
    assert m, resp.headers
    return m.group(1)


def cookie(sid: str) -> dict[str, str]:
    # The cookie is Secure, so an http:// client would (correctly) not replay it; send it explicitly.
    return {"Cookie": f"sid={sid}"}


@pytest.fixture(scope="module")
def two_tenants(live_server: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for tag in ("a", "b"):
        r = httpx.post(
            f"{live_server}{API}/platform/tenants", headers={"X-Platform-Key": KEY},
            json={"name": f"E2E-{tag}", "adminName": "Admin", "adminEmail": f"admin@{tag}.e2e.example", "password": PW},
        )  # fmt: skip
        assert r.status_code == 201, r.text
        lr = httpx.post(f"{live_server}{API}/auth/login", json={"email": f"admin@{tag}.e2e.example", "password": PW})
        assert lr.status_code == 200
        out[tag] = {**r.json(), "sid": sid_from(lr), "set_cookie": lr.headers["set-cookie"]}
    return out


def test_login_cookie_attributes_over_real_http(two_tenants: dict[str, dict[str, str]]) -> None:
    c = two_tenants["a"]["set_cookie"].lower()
    assert "httponly" in c and "secure" in c and "samesite=lax" in c and "max-age=28800" in c and "path=/" in c


def test_me_users_and_logout_flow(live_server: str, two_tenants: dict[str, dict[str, str]]) -> None:
    sid = two_tenants["a"]["sid"]
    assert httpx.get(f"{live_server}{API}/auth/me", headers=cookie(sid)).json()["tenant"]["name"] == "E2E-a"
    assert len(httpx.get(f"{live_server}{API}/users", headers=cookie(sid)).json()) == 1
    other = httpx.post(f"{live_server}{API}/auth/login", json={"email": "admin@a.e2e.example", "password": PW})
    assert httpx.post(f"{live_server}{API}/auth/logout", headers=cookie(sid_from(other))).status_code == 204
    assert httpx.get(f"{live_server}{API}/auth/me", headers=cookie(sid_from(other))).status_code == 401
    assert httpx.get(f"{live_server}{API}/auth/me", headers=cookie(sid)).status_code == 200  # first session unaffected


def test_cross_tenant_over_real_http(live_server: str, two_tenants: dict[str, dict[str, str]]) -> None:
    a, b = two_tenants["a"], two_tenants["b"]
    r = httpx.patch(
        f"{live_server}{API}/users/{b['adminUserId']}", headers=cookie(a["sid"]), json={"status": "disabled"}
    )
    assert r.status_code == 404
    ids = {u["id"] for u in httpx.get(f"{live_server}{API}/users", headers=cookie(a["sid"])).json()}
    assert b["adminUserId"] not in ids


def test_platform_key_and_duplicate_email_over_real_http(
    live_server: str, two_tenants: dict[str, dict[str, str]]
) -> None:
    body = {"name": "Dup", "adminName": "D", "adminEmail": "ADMIN@A.E2E.EXAMPLE", "password": PW}
    assert httpx.post(f"{live_server}{API}/platform/tenants", json=body).status_code == 401
    r = httpx.post(f"{live_server}{API}/platform/tenants", json=body, headers={"X-Platform-Key": KEY})
    assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_EXISTS"


def test_lockout_over_real_http(live_server: str, two_tenants: dict[str, dict[str, str]]) -> None:
    body = {"email": "admin@b.e2e.example", "password": "wrong-password-1"}
    codes = [httpx.post(f"{live_server}{API}/auth/login", json=body).status_code for _ in range(5)]
    assert codes == [401] * 5
    r = httpx.post(f"{live_server}{API}/auth/login", json={**body, "password": PW})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
