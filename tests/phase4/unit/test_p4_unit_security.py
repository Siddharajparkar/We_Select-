"""Phase 4 unit tests: password hashing, signed cookies, rate limiter, config rules."""

from __future__ import annotations

import pytest

from app.config import ConfigError, load_settings
from app.core.clock import FakeClock
from app.core.errors import AppError
from app.security import cookies
from app.security.passwords import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, PasswordService
from app.services.rate_limit import SlidingWindowLimiter


@pytest.fixture(scope="module")
def pw() -> PasswordService:
    return PasswordService(memory_kib=1024, time_cost=1, parallelism=1)


def test_hash_is_argon2id_and_verifies(pw: PasswordService) -> None:
    h = pw.hash("correct-horse-9")
    assert h.startswith("$argon2id$")
    assert pw.verify(h, "correct-horse-9")
    assert not pw.verify(h, "correct-horse-8")


def test_hashes_are_salted(pw: PasswordService) -> None:
    assert pw.hash("same-password-1") != pw.hash("same-password-1")


def test_garbage_hash_never_raises(pw: PasswordService) -> None:
    assert pw.verify("not-a-hash", "x") is False
    assert pw.verify("", "x") is False


def test_dummy_verification_runs_and_returns_nothing(pw: PasswordService) -> None:
    assert pw.verify_dummy("whatever") is None


def test_production_default_parameters_meet_the_floor() -> None:
    s = load_settings()
    assert (s.ARGON2_MEMORY_KIB, s.ARGON2_TIME_COST, s.ARGON2_PARALLELISM) == (19456, 2, 1)
    h = PasswordService(s.ARGON2_MEMORY_KIB, s.ARGON2_TIME_COST, s.ARGON2_PARALLELISM).hash("correct-horse-9")
    assert "m=19456,t=2,p=1" in h


def test_password_bounds_constants() -> None:
    assert (PASSWORD_MIN_LENGTH, PASSWORD_MAX_LENGTH) == (10, 128)


# ── cookies ─────────────────────────────────────────────────────────────────────────────────
SECRET = "s" * 40


def test_cookie_round_trip() -> None:
    assert cookies.verify(cookies.sign("abc_DEF-123", SECRET), SECRET) == "abc_DEF-123"


def test_tampered_value_is_rejected() -> None:
    signed = cookies.sign("session-id", SECRET)
    value, _, sig = signed.rpartition(".")
    assert cookies.verify(f"other-id.{sig}", SECRET) is None
    assert cookies.verify(f"{value}.{sig[:-2]}xx", SECRET) is None


def test_wrong_secret_is_rejected() -> None:
    assert cookies.verify(cookies.sign("x", SECRET), "t" * 40) is None


@pytest.mark.parametrize("bad", [None, "", "nodot", ".", "a.", ".sig", "x" * 600])
def test_malformed_cookies_are_rejected(bad: str | None) -> None:
    assert cookies.verify(bad, SECRET) is None


# ── rate limiter ────────────────────────────────────────────────────────────────────────────
def test_limiter_allows_up_to_limit_then_429_with_retry_after(clock: FakeClock) -> None:
    lim = SlidingWindowLimiter(clock, limit=3, window_seconds=60)
    for _ in range(3):
        lim.check("1.2.3.4")
    with pytest.raises(AppError) as e:
        lim.check("1.2.3.4")
    assert e.value.status == 429 and e.value.code == "RATE_LIMITED" and e.value.retry_after == 60


def test_limiter_is_per_key_and_window_slides(clock: FakeClock) -> None:
    lim = SlidingWindowLimiter(clock, limit=1, window_seconds=60)
    lim.check("a")
    lim.check("b")  # different key unaffected
    with pytest.raises(AppError):
        lim.check("a")
    clock.advance(seconds=59)
    with pytest.raises(AppError):
        lim.check("a")
    clock.advance(seconds=1)
    lim.check("a")  # window slid


# ── config ──────────────────────────────────────────────────────────────────────────────────
def test_cookie_secure_defaults_on_and_cannot_be_disabled_in_production() -> None:
    assert load_settings().COOKIE_SECURE is True
    prod = dict(
        APP_ENV="production", AI_MODE="azure", EMAIL_MODE="azure", FILES_MODE="azure", REPO_BACKEND="sql",
        DATABASE_URL="x", FOUNDRY_ENDPOINT="e", FOUNDRY_KEY="k", ACS_CONNECTION_STRING="c", ACS_SENDER="s",
        BLOB_CONNECTION_STRING="b", SESSION_SECRET="a" * 40, PLATFORM_KEY="b" * 40,
    )  # fmt: skip
    assert load_settings(**prod).COOKIE_SECURE is True
    with pytest.raises(ConfigError, match="COOKIE_SECURE"):
        load_settings(**prod, COOKIE_SECURE=False)
