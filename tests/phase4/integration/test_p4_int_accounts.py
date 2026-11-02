"""Phase 4 integration: endpoints 4-7 (tenants, users), role matrix, R1, cross-tenant, last-admin guard."""

from __future__ import annotations

import pytest

from app.core.clock import FakeClock
from conftest import API, PASSWORD, Account


# ── endpoint 4: POST /platform/tenants ─────────────────────────────────────────────────────
def body(email: str = "boss@new.example", **over: object) -> dict[str, object]:
    return {"name": "New Co", "adminName": "Boss", "adminEmail": email, "password": PASSWORD, **over}


def test_platform_key_missing_wrong_and_right(new_client, platform_headers) -> None:  # type: ignore[no-untyped-def]
    c = new_client()
    assert c.post(f"{API}/platform/tenants", json=body()).status_code == 401
    assert c.post(f"{API}/platform/tenants", json=body(), headers={"X-Platform-Key": "wrong"}).status_code == 401
    r = c.post(f"{API}/platform/tenants", json=body(), headers=platform_headers)
    assert r.status_code == 201 and set(r.json()) == {"tenantId", "adminUserId"}


def test_wrong_key_wins_over_a_bad_body(new_client) -> None:  # type: ignore[no-untyped-def]
    r = new_client().post(f"{API}/platform/tenants", json={}, headers={"X-Platform-Key": "wrong"})
    assert r.status_code == 401  # nothing about the schema leaks to unauthenticated callers


def test_new_tenant_admin_can_log_in(new_client, platform_headers) -> None:  # type: ignore[no-untyped-def]
    c = new_client()
    c.post(f"{API}/platform/tenants", json=body(), headers=platform_headers)
    r = c.post(f"{API}/auth/login", json={"email": "boss@new.example", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin" and r.json()["tenant"]["name"] == "New Co"


@pytest.mark.parametrize(
    "over",
    [{"name": ""}, {"adminName": " "}, {"adminEmail": "not-an-email"}, {"password": "short"}, {"password": "x" * 129}],
)
def test_tenant_body_validation(new_client, platform_headers, over: dict[str, object]) -> None:  # type: ignore[no-untyped-def]
    r = new_client().post(f"{API}/platform/tenants", json=body(**over), headers=platform_headers)
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_duplicate_email_is_409_case_insensitive_and_creates_nothing(  # type: ignore[no-untyped-def]
    new_client, platform_headers, repos
) -> None:
    c = new_client()
    assert c.post(f"{API}/platform/tenants", json=body("dup@x.example"), headers=platform_headers).status_code == 201
    r = c.post(f"{API}/platform/tenants", json=body("DUP@X.example", name="Second"), headers=platform_headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_EXISTS"
    assert [t.name for t in repos.tenants.list()] == ["New Co"]  # the failed attempt rolled back


def test_tenant_creation_is_audited(new_client, platform_headers, repos) -> None:  # type: ignore[no-untyped-def]
    tid = new_client().post(f"{API}/platform/tenants", json=body(), headers=platform_headers).json()["tenantId"]
    entries = repos.audit.list_by_entity(tid, "tenant", tid)
    assert [e.action for e in entries] == ["tenant.create"]


def test_platform_route_is_rate_limited_to_10_per_minute_per_ip(new_client, clock: FakeClock) -> None:  # type: ignore[no-untyped-def]
    c = new_client()
    for _ in range(10):
        assert c.post(f"{API}/platform/tenants", json={}, headers={"X-Platform-Key": "bad"}).status_code == 401
    r = c.post(f"{API}/platform/tenants", json={}, headers={"X-Platform-Key": "bad"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED" and "retry-after" in r.headers
    clock.advance(seconds=60)
    assert c.post(f"{API}/platform/tenants", json={}, headers={"X-Platform-Key": "bad"}).status_code == 401


# ── endpoints 5-7: users ───────────────────────────────────────────────────────────────────
def test_admin_lists_only_their_tenant(tenant_a: Account, tenant_b: Account) -> None:
    rows = tenant_a.client.get(f"{API}/users").json()
    assert [r["id"] for r in rows] == [tenant_a.admin_id]
    assert set(rows[0]) == {"id", "name", "email", "role", "status"}  # no hash, no tenant id
    assert tenant_b.admin_id not in {r["id"] for r in rows}


def test_create_user_then_login_as_them(tenant_a: Account, new_client) -> None:  # type: ignore[no-untyped-def]
    r = tenant_a.client.post(
        f"{API}/users", json={"name": "Rita", "email": "Rita@A.example", "role": "recruiter", "password": PASSWORD}
    )
    assert r.status_code == 201 and list(r.json()) == ["id"]
    login = new_client().post(f"{API}/auth/login", json={"email": "rita@a.example", "password": PASSWORD})
    assert login.status_code == 200 and login.json()["user"]["role"] == "recruiter"


def test_create_user_email_exists_across_tenants_r1(tenant_a: Account, tenant_b: Account) -> None:
    r = tenant_a.client.post(
        f"{API}/users", json={"name": "X", "email": tenant_b.email.upper(), "role": "admin", "password": PASSWORD}
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_EXISTS"


@pytest.mark.parametrize(
    "over",
    [{"role": "reviewer"}, {"role": "owner"}, {"email": "bad"}, {"password": "short"}, {"name": ""}],
)
def test_create_user_validation(tenant_a: Account, over: dict[str, object]) -> None:
    payload = {"name": "N", "email": "n@a.example", "role": "recruiter", "password": PASSWORD, **over}
    r = tenant_a.client.post(f"{API}/users", json=payload)
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_role_matrix_recruiter_gets_403_everywhere_in_users(tenant_a: Account, recruiter: Account) -> None:
    rc = recruiter.client
    assert rc.get(f"{API}/users").status_code == 403
    assert (
        rc.post(
            f"{API}/users", json={"name": "N", "email": "n@a.example", "role": "admin", "password": PASSWORD}
        ).status_code
        == 403
    )
    assert rc.patch(f"{API}/users/{tenant_a.admin_id}", json={"role": "recruiter"}).status_code == 403
    assert rc.get(f"{API}/users").json()["error"]["code"] == "FORBIDDEN"


def test_role_matrix_anonymous_gets_401(new_client, tenant_a: Account) -> None:  # type: ignore[no-untyped-def]
    c = new_client()
    assert c.get(f"{API}/users").status_code == 401
    assert c.post(f"{API}/users", json={}).status_code == 401
    assert c.patch(f"{API}/users/{tenant_a.admin_id}", json={"role": "admin"}).status_code == 401


def test_patch_role_and_status(tenant_a: Account, recruiter: Account) -> None:
    r = tenant_a.client.patch(f"{API}/users/{recruiter.admin_id}", json={"role": "admin"})
    assert r.status_code == 200 and r.json()["role"] == "admin" and r.json()["status"] == "active"
    r = tenant_a.client.patch(f"{API}/users/{recruiter.admin_id}", json={"role": "recruiter", "status": "disabled"})
    assert r.json()["role"] == "recruiter" and r.json()["status"] == "disabled"


def test_patch_requires_a_field_and_a_valid_value(tenant_a: Account, recruiter: Account) -> None:
    url = f"{API}/users/{recruiter.admin_id}"
    assert tenant_a.client.patch(url, json={}).status_code == 400
    assert tenant_a.client.patch(url, json={"role": "root"}).status_code == 400
    assert tenant_a.client.patch(url, json={"status": "deleted"}).status_code == 400


def test_malformed_user_id_is_400_unknown_is_404(tenant_a: Account) -> None:
    assert tenant_a.client.patch(f"{API}/users/not-a-uuid", json={"role": "admin"}).status_code == 400
    r = tenant_a.client.patch(f"{API}/users/{'0' * 8}-0000-4000-8000-{'0' * 12}", json={"role": "admin"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_last_admin_cannot_be_disabled_or_demoted(tenant_a: Account) -> None:
    url = f"{API}/users/{tenant_a.admin_id}"
    for payload in ({"status": "disabled"}, {"role": "recruiter"}):
        r = tenant_a.client.patch(url, json=payload)
        assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"
    assert tenant_a.client.get(f"{API}/auth/me").status_code == 200  # still active


def test_with_a_second_admin_the_first_may_step_down(tenant_a: Account, recruiter: Account) -> None:
    tenant_a.client.patch(f"{API}/users/{recruiter.admin_id}", json={"role": "admin"})
    assert tenant_a.client.patch(f"{API}/users/{tenant_a.admin_id}", json={"role": "recruiter"}).status_code == 200
    # ...but now the former recruiter is the last admin
    r = recruiter.client.patch(f"{API}/users/{recruiter.admin_id}", json={"status": "disabled"})
    assert r.status_code == 409


def test_user_changes_are_audited(tenant_a: Account, recruiter: Account, repos) -> None:  # type: ignore[no-untyped-def]
    tenant_a.client.patch(f"{API}/users/{recruiter.admin_id}", json={"role": "admin"})
    actions = [e.action for e in repos.audit.list_by_entity(tenant_a.tenant_id, "user", recruiter.admin_id)]
    assert sorted(actions) == ["user.create", "user.update"]  # same FakeClock instant: order is by id


# ── cross-tenant (required by the PDF; runs in CI) ─────────────────────────────────────────
def test_cross_tenant_patch_is_404_and_changes_nothing(tenant_a: Account, tenant_b: Account) -> None:
    r = tenant_a.client.patch(f"{API}/users/{tenant_b.admin_id}", json={"status": "disabled"})
    assert r.status_code == 404
    assert tenant_b.client.get(f"{API}/auth/me").status_code == 200  # B's admin untouched
    users_b = tenant_b.client.get(f"{API}/users").json()
    assert users_b[0]["status"] == "active"


def test_cross_tenant_list_never_contains_other_tenants(tenant_a: Account, tenant_b: Account) -> None:
    tenant_b.client.post(
        f"{API}/users", json={"name": "B2", "email": "b2@b.example", "role": "recruiter", "password": PASSWORD}
    )
    ids_a = {u["id"] for u in tenant_a.client.get(f"{API}/users").json()}
    ids_b = {u["id"] for u in tenant_b.client.get(f"{API}/users").json()}
    assert ids_a.isdisjoint(ids_b) and len(ids_b) == 2


def test_body_cannot_smuggle_a_tenant_id(tenant_a: Account, tenant_b: Account) -> None:
    r = tenant_a.client.post(
        f"{API}/users",
        json={
            "name": "S",
            "email": "s@a.example",
            "role": "recruiter",
            "password": PASSWORD,
            "tenantId": tenant_b.tenant_id,
        },
    )
    assert r.status_code == 201
    assert "s@a.example" in {u["email"] for u in tenant_a.client.get(f"{API}/users").json()}
    assert "s@a.example" not in {u["email"] for u in tenant_b.client.get(f"{API}/users").json()}
