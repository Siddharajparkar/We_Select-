"""Phase 4 integration: endpoints 1-3 over HTTP (TestClient, in-memory repositories, fake clock)."""

from __future__ import annotations

from app.core.clock import FakeClock
from conftest import API, PASSWORD, Account


def login(client, email, password=PASSWORD):  # type: ignore[no-untyped-def]
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


def test_login_success_sets_a_cookie_with_all_attributes(tenant_a: Account, new_client) -> None:  # type: ignore[no-untyped-def]
    r = login(new_client(), tenant_a.email.upper())  # email is case-insensitive
    assert r.status_code == 200
    body = r.json()
    assert body["user"] == {"id": tenant_a.admin_id, "name": "Admin 1", "role": "admin"}
    assert body["tenant"]["id"] == tenant_a.tenant_id
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("sid=")
    low = cookie.lower()
    assert "httponly" in low and "secure" in low and "samesite=lax" in low and "path=/" in low
    assert "max-age=28800" in low
    assert "password" not in r.text


def test_login_response_never_exposes_hashes(tenant_a: Account, new_client) -> None:  # type: ignore[no-untyped-def]
    text = login(new_client(), tenant_a.email).text.lower()
    assert "hash" not in text and "argon" not in text


def test_wrong_password_and_unknown_email_have_identical_bodies(tenant_a: Account, new_client) -> None:  # type: ignore[no-untyped-def]
    c = new_client()
    wrong = login(c, tenant_a.email, "definitely-wrong-1")
    unknown = login(c, "nobody@nowhere.example")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert "set-cookie" not in wrong.headers


def test_disabled_user_cannot_log_in_and_gets_the_same_401(tenant_a: Account, recruiter: Account, new_client) -> None:  # type: ignore[no-untyped-def]
    assert tenant_a.client.patch(f"{API}/users/{recruiter.admin_id}", json={"status": "disabled"}).status_code == 200
    r = login(new_client(), recruiter.email)
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_five_failures_then_429_even_with_the_right_password(tenant_a: Account, new_client) -> None:  # type: ignore[no-untyped-def]
    c = new_client()
    for _ in range(5):
        assert login(c, tenant_a.email, "wrong-password-1").status_code == 401
    r = login(c, tenant_a.email)  # right password
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"
    assert int(r.headers["retry-after"]) == 600


def test_lockout_lifts_after_ten_minutes(tenant_a: Account, new_client, clock: FakeClock) -> None:  # type: ignore[no-untyped-def]
    c = new_client()
    for _ in range(5):
        login(c, tenant_a.email, "wrong-password-1")
    clock.advance(minutes=10)
    assert login(c, tenant_a.email).status_code == 200


def test_login_validates_the_body(new_client) -> None:  # type: ignore[no-untyped-def]
    c = new_client()
    for body in ({}, {"email": "a@b.example"}, {"password": "x"}, {"email": "", "password": "x"}):
        r = c.post(f"{API}/auth/login", json=body)
        assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_me_returns_user_and_tenant(tenant_a: Account) -> None:
    r = tenant_a.client.get(f"{API}/auth/me")
    assert r.status_code == 200
    assert r.json()["user"]["id"] == tenant_a.admin_id and r.json()["tenant"]["id"] == tenant_a.tenant_id


def test_me_without_cookie_is_401(new_client) -> None:  # type: ignore[no-untyped-def]
    r = new_client().get(f"{API}/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHENTICATED"


def test_tampered_cookie_is_401(tenant_a: Account, new_client) -> None:  # type: ignore[no-untyped-def]
    value = tenant_a.client.cookies["sid"]
    c = new_client()
    c.cookies.set("sid", value[:-3] + "AAA")
    assert c.get(f"{API}/auth/me").status_code == 401


def test_logout_then_me_is_401_and_cookie_cleared(tenant_a: Account) -> None:
    old = tenant_a.client.cookies["sid"]
    r = tenant_a.client.post(f"{API}/auth/logout")
    assert r.status_code == 204 and r.content == b""
    assert 'sid=""' in r.headers["set-cookie"] or "max-age=0" in r.headers["set-cookie"].lower()
    tenant_a.client.cookies.set("sid", old)  # replay the old cookie: the session row is gone
    assert tenant_a.client.get(f"{API}/auth/me").status_code == 401


def test_logout_anonymous_is_401(new_client) -> None:  # type: ignore[no-untyped-def]
    assert new_client().post(f"{API}/auth/logout").status_code == 401


def test_idle_session_expires_after_30_minutes(tenant_a: Account, clock: FakeClock) -> None:
    clock.advance(minutes=30)
    assert tenant_a.client.get(f"{API}/auth/me").status_code == 200
    clock.advance(minutes=30, seconds=1)
    assert tenant_a.client.get(f"{API}/auth/me").status_code == 401


def test_absolute_session_expires_after_8_hours_despite_activity(tenant_a: Account, clock: FakeClock) -> None:
    for _ in range(16):
        clock.advance(minutes=29)
        assert tenant_a.client.get(f"{API}/auth/me").status_code == 200
    clock.advance(minutes=17)  # 8 h 01 min since login
    assert tenant_a.client.get(f"{API}/auth/me").status_code == 401


def test_disabling_a_user_kills_their_live_session_immediately(tenant_a: Account, recruiter: Account) -> None:
    assert recruiter.client.get(f"{API}/auth/me").status_code == 200
    tenant_a.client.patch(f"{API}/users/{recruiter.admin_id}", json={"status": "disabled"})
    assert recruiter.client.get(f"{API}/auth/me").status_code == 401


def test_two_logins_make_two_independent_sessions(tenant_a: Account, new_client) -> None:  # type: ignore[no-untyped-def]
    other = new_client()
    assert login(other, tenant_a.email).status_code == 200
    tenant_a.client.post(f"{API}/auth/logout")
    assert other.get(f"{API}/auth/me").status_code == 200


def test_every_error_uses_the_envelope_and_carries_request_headers(new_client, tenant_a: Account) -> None:  # type: ignore[no-untyped-def]
    c = new_client()
    responses = [
        c.get(f"{API}/auth/me"),
        login(c, "x@y.example", "nope"),
        c.post(f"{API}/auth/login", json={}),
        c.get(f"{API}/users"),
        c.get(f"{API}/nope"),
        c.post(f"{API}/platform/tenants", json={}),
    ]
    for r in responses:
        assert r.status_code >= 400
        err = r.json()["error"]
        assert set(err) >= {"code", "message"}
        assert r.headers["x-request-id"] and r.headers["x-app-version"]
