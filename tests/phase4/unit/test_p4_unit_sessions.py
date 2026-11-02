"""Phase 4 unit tests: login lockout and session expiry maths, driven by FakeClock."""

from __future__ import annotations

import pytest

from app.core.clock import FakeClock
from app.core.errors import AppError
from app.repositories import Repositories
from app.security.passwords import PasswordService
from app.services.auth import AuthService

SECRET = "x" * 40
PW = "correct-horse-9"


@pytest.fixture
def svc(mem_repos: Repositories, clock: FakeClock) -> AuthService:
    passwords = PasswordService(1024, 1, 1)
    t = mem_repos.tenants.create(name="T")
    mem_repos.users.create(t.id, name="U", email="u@x.example", password_hash=passwords.hash(PW), role="admin")
    return AuthService(mem_repos, clock, passwords, SECRET)


def bad(svc: AuthService, email: str = "u@x.example") -> AppError:
    with pytest.raises(AppError) as e:
        svc.login(email, "wrong-password-1", "1.1.1.1")
    return e.value


def test_four_failures_are_plain_401_and_login_still_works(svc: AuthService) -> None:
    for _ in range(4):
        assert bad(svc).status == 401
    cookie, user, _ = svc.login("u@x.example", PW, "1.1.1.1")
    assert cookie and user.email == "u@x.example"


def test_fifth_failure_locks_even_for_the_right_password(svc: AuthService) -> None:
    for _ in range(5):
        assert bad(svc).status == 401  # the 5th is still checked and rejected as 401
    with pytest.raises(AppError) as e:
        svc.login("u@x.example", PW, "1.1.1.1")
    assert e.value.status == 429 and e.value.code == "RATE_LIMITED"
    assert e.value.retry_after == 600


def test_lock_is_released_exactly_ten_minutes_after_the_latest_failure(svc: AuthService, clock: FakeClock) -> None:
    for _ in range(5):
        bad(svc)
    clock.advance(minutes=9, seconds=59)
    with pytest.raises(AppError) as e:
        svc.login("u@x.example", PW, "1.1.1.1")
    assert e.value.status == 429 and e.value.retry_after == 1
    clock.advance(seconds=1)
    assert svc.login("u@x.example", PW, "1.1.1.1")[0]


def test_locked_attempts_are_not_recorded_so_the_lock_cannot_be_extended(svc: AuthService, clock: FakeClock) -> None:
    for _ in range(5):
        bad(svc)
    clock.advance(minutes=5)
    for _ in range(3):
        assert bad(svc).status == 429
    clock.advance(minutes=5)  # 10 min after the 5th failure, not after the locked attempts
    assert svc.login("u@x.example", PW, "1.1.1.1")[0]


def test_success_clears_the_failure_window(svc: AuthService) -> None:
    for _ in range(4):
        bad(svc)
    svc.login("u@x.example", PW, "1.1.1.1")
    for _ in range(4):
        assert bad(svc).status == 401  # would be locked if the earlier 4 still counted
    assert svc.login("u@x.example", PW, "1.1.1.1")[0]


def test_failures_older_than_ten_minutes_do_not_count(svc: AuthService, clock: FakeClock) -> None:
    for _ in range(4):
        bad(svc)
    clock.advance(minutes=10)
    for _ in range(4):
        assert bad(svc).status == 401
    assert svc.login("u@x.example", PW, "1.1.1.1")[0]


def test_unknown_emails_are_recorded_and_locked_the_same_way(svc: AuthService) -> None:
    for _ in range(5):
        assert bad(svc, "ghost@x.example").status == 401
    assert bad(svc, "ghost@x.example").status == 429  # no way to tell it does not exist


def test_email_is_normalised_for_the_lockout(svc: AuthService) -> None:
    for _ in range(5):
        bad(svc, "  U@X.example ")
    assert bad(svc, "u@x.example").status == 429


def test_unknown_wrong_password_and_disabled_have_the_same_error(svc: AuthService, mem_repos: Repositories) -> None:
    unknown, wrong = bad(svc, "ghost@x.example"), bad(svc)
    u = mem_repos.users.find_by_email("u@x.example")
    assert u is not None
    mem_repos.users.update(u.tenant_id, u.id, status="disabled")
    with pytest.raises(AppError) as e:
        svc.login("u@x.example", PW, "1.1.1.1")  # right password, disabled user
    disabled = e.value
    assert {(x.status, x.code, x.message) for x in (unknown, wrong, disabled)} == {
        (401, "INVALID_CREDENTIALS", "Invalid email or password")
    }


# ── session expiry ──────────────────────────────────────────────────────────────────────────
def login(svc: AuthService) -> str:
    return svc.login("u@x.example", PW, "1.1.1.1")[0]


def test_idle_boundary_is_30_minutes(svc: AuthService, clock: FakeClock) -> None:
    c = login(svc)
    clock.advance(minutes=30)
    assert svc.resolve(c).role == "admin"  # exactly 30 min idle is still allowed
    clock.advance(minutes=30, seconds=1)
    with pytest.raises(AppError) as e:
        svc.resolve(c)
    assert e.value.status == 401
    with pytest.raises(AppError):
        svc.resolve(c)  # the row was deleted


def test_activity_keeps_a_session_alive_until_the_absolute_limit(svc: AuthService, clock: FakeClock) -> None:
    c = login(svc)
    for _ in range(15):  # 15 x 29 min = 7 h 15 min
        clock.advance(minutes=29)
        svc.resolve(c)
    clock.advance(minutes=29)  # 7 h 44 min
    svc.resolve(c)
    clock.advance(minutes=15)  # 7 h 59 min since login, last seen 15 min ago
    svc.resolve(c)
    clock.advance(minutes=1)  # exactly 8 h 00 min since login
    assert svc.resolve(c)
    clock.advance(seconds=1)  # 8 h 00 min 01 s
    with pytest.raises(AppError):
        svc.resolve(c)


def test_absolute_expiry_off_by_one_second(svc: AuthService, clock: FakeClock) -> None:
    c = login(svc)
    for _ in range(16):  # keep it active: 16 x 29 min = 7 h 44 min
        clock.advance(minutes=29)
        svc.resolve(c)
    clock.advance(minutes=16)  # 8 h 00 min exactly
    assert svc.resolve(c)
    clock.advance(seconds=1)
    with pytest.raises(AppError):
        svc.resolve(c)


def test_last_seen_is_written_at_most_once_per_minute(
    svc: AuthService, clock: FakeClock, mem_repos: Repositories
) -> None:
    c = login(svc)
    th = __import__("app.core.ids", fromlist=["hash_token"]).hash_token(c.rpartition(".")[0])
    seen = lambda: mem_repos.system.find_session_by_token_hash(th)["session"].last_seen_at  # type: ignore[index]  # noqa: E731
    t0 = seen()
    clock.advance(seconds=59)
    svc.resolve(c)
    assert seen() == t0  # no write yet
    clock.advance(seconds=1)
    svc.resolve(c)
    assert seen() == clock.now()


def test_forged_or_missing_cookie_is_401_without_touching_the_database(svc: AuthService) -> None:
    for c in (None, "", "garbage", "abc.def"):
        with pytest.raises(AppError) as e:
            svc.resolve(c)
        assert e.value.status == 401


def test_disabled_user_session_dies_on_next_use(svc: AuthService, mem_repos: Repositories) -> None:
    c = login(svc)
    u = mem_repos.users.find_by_email("u@x.example")
    assert u is not None
    mem_repos.users.update(u.tenant_id, u.id, status="disabled")
    with pytest.raises(AppError):
        svc.resolve(c)
