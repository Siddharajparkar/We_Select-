"""Staff authentication: sessions, login lockout (Prompt A 4.2 / 4.3)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta

from ..core.clock import Clock
from ..core.errors import AppError
from ..core.ids import generate_secure_token, hash_token
from ..repositories import Repositories
from ..repositories.models import Tenant, User
from ..security import cookies
from ..security.passwords import PasswordService

SESSION_ABSOLUTE = timedelta(hours=8)
SESSION_IDLE = timedelta(minutes=30)
TOUCH_INTERVAL = timedelta(seconds=60)
LOCK_FAILURES = 5
LOCK_WINDOW = timedelta(minutes=10)
COOKIE_NAME = "sid"
COOKIE_MAX_AGE = int(SESSION_ABSOLUTE.total_seconds())


@dataclass(frozen=True)
class AuthContext:
    """Who is calling. ``tenant_id`` is ONLY ever read from here, never from request input."""

    user_id: str
    tenant_id: str
    role: str
    user_name: str
    tenant_name: str
    session_hash: str


def invalid_credentials() -> AppError:
    return AppError(401, "INVALID_CREDENTIALS", "Invalid email or password")


class AuthService:
    def __init__(self, repos: Repositories, clock: Clock, passwords: PasswordService, secret: str) -> None:
        self.repos, self.clock, self.passwords, self.secret = repos, clock, passwords, secret

    # ── login ─────────────────────────────────────────────────────────────────────────────
    def login(self, email: str, password: str, ip: str) -> tuple[str, User, Tenant]:
        email = email.strip().lower()
        now = self.clock.now()
        failures, last_failure = self.repos.login_attempts.failure_state(email, now - LOCK_WINDOW)
        if failures >= LOCK_FAILURES and last_failure is not None:
            wait = max(1, math.ceil((last_failure + LOCK_WINDOW - now).total_seconds()))
            raise AppError.too_many_requests("RATE_LIMITED", "Too many failed sign-in attempts. Try again later.", wait)

        user = self.repos.users.find_by_email(email)
        tenant = self.repos.tenants.find_by_id(user.tenant_id) if user else None
        if user is None or tenant is None:
            self.passwords.verify_dummy(password)  # equalise timing for unknown emails
            self.repos.login_attempts.record(email=email, ip_address=ip, success=False)
            raise invalid_credentials()
        password_ok = self.passwords.verify(user.password_hash, password)
        if not password_ok or user.status != "active" or tenant.status != "active":
            self.repos.login_attempts.record(email=email, ip_address=ip, success=False)
            raise invalid_credentials()  # same body for wrong password, disabled user, suspended tenant

        self.repos.login_attempts.clear_failures(email)
        self.repos.login_attempts.record(email=email, ip_address=ip, success=True)
        raw = generate_secure_token()
        self.repos.sessions.create(
            user.tenant_id, user_id=user.id, token_hash=hash_token(raw), expires_at=now + SESSION_ABSOLUTE
        )
        return cookies.sign(raw, self.secret), user, tenant

    # ── per-request resolution ────────────────────────────────────────────────────────────
    def resolve(self, cookie_value: str | None) -> AuthContext:
        raw = cookies.verify(cookie_value, self.secret)  # constant-time, before any DB access
        if raw is None:
            raise AppError.unauthenticated()
        token_hash = hash_token(raw)
        found = self.repos.system.find_session_by_token_hash(token_hash)
        if found is None:
            raise AppError.unauthenticated()
        session, user, tenant = found["session"], found["user"], found["tenant"]
        now = self.clock.now()
        expired = now > session.expires_at or now - session.last_seen_at > SESSION_IDLE
        if expired or user.status != "active" or tenant.status != "active":
            self.repos.sessions.delete_by_token_hash(token_hash)
            raise AppError.unauthenticated()
        if now - session.last_seen_at >= TOUCH_INTERVAL:
            self.repos.sessions.touch(token_hash, now)  # at most one write per minute
        return AuthContext(user.id, tenant.id, user.role, user.name, tenant.name, token_hash)

    def logout(self, ctx: AuthContext) -> None:
        self.repos.sessions.delete_by_token_hash(ctx.session_hash)
