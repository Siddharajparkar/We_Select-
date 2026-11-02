# Phase 4 report — authentication, tenants and users (endpoints 1-7)

Branch `phase/04-auth`. Stack: Python 3.12, FastAPI, Pydantic v2, Argon2id (`argon2-cffi`).

## Implemented
- **Endpoints 1-7:** `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /platform/tenants`, `GET/POST /users`, `PATCH /users/{id}` (`api/app/routes/{auth,platform,users}.py`).
- **Passwords:** Argon2id (19 MiB, 2 iterations, 1 lane; env override), 10-128 characters, dummy verification for unknown emails (`security/passwords.py`).
- **Sessions:** 32-byte random id in a signed cookie `sid` (`<id>.<HMAC-SHA256>`, constant-time check before any DB access); only the SHA-256 hash is stored; HttpOnly, Secure, SameSite=Lax, Max-Age 28800; idle 30 min, absolute 8 h, `last_seen_at` written at most once per minute (`services/auth.py`, migration `0002_sessions_last_seen.sql`).
- **Lockout:** 5 failures per normalised email in 10 minutes gives `429 RATE_LIMITED` with `Retry-After`, without checking the password; unknown emails count too; a success clears the failure rows; locked attempts are not recorded so the lock cannot be extended.
- **Guards:** `current_auth`, `require_staff`, `require_admin` (`deps.py`); the tenant id comes only from the session (AST test over `routes/`); platform key compared in constant time, 10 requests per minute per IP, 401 for missing or wrong key.
- **Rules:** R1 (globally unique email, case-insensitive, 409 EMAIL_EXISTS), R24, R32 (malformed uuid in a path is 400), last-admin guard (409 CONFLICT), disabling a user deletes their sessions, every change audited.
- **Seed tool:** `python -m app.tools.seed_tenant --name ... --admin-name ... --admin-email ...` (password from stdin or a hidden prompt, never printed).

## Tests (all local, in-memory repositories, FakeClock)
`tests/phase4/unit` (security, lockout and expiry maths, AST guards, seed tool), `tests/phase4/integration` (HTTP: auth, accounts, role matrix, cross-tenant, envelope), `tests/phase4/e2e` (real uvicorn). Live harness: `scripts/e2e/checks/p04_auth.py`.

## UNVERIFIED (CI / office)
Migration 0002 on SQL Server and Azure SQL; Argon2 wheels inside the production image; `Secure` cookie arrival over the real Azure HTTPS URL; live checks with `E2E_PLATFORM_KEY` (office).
