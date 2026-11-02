"""Create a tenant and its first admin (Prompt A 4.8).

    python -m app.tools.seed_tenant --name "Acme" --admin-name "Ada" --admin-email ada@example.com

The password is read from stdin (piped) or prompted without echo; it is never printed or logged.
Uses the same service function as ``POST /platform/tenants``. Connects through the usual settings
(``REPO_BACKEND``/``DATABASE_URL``), so run it with the database variables set in your own shell.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from typing import TextIO

from ..config import ConfigError, load_settings
from ..core.errors import AppError
from ..repositories import create_repositories
from ..schemas.common import _check_email
from ..security.passwords import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, PasswordService
from ..services.accounts import create_tenant_with_admin


def read_password(stream: TextIO | None = None) -> str:
    src = stream or sys.stdin
    if src.isatty():
        return getpass.getpass("Admin password: ")
    return src.readline().rstrip("\r\n")


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True)
    ap.add_argument("--admin-name", required=True)
    ap.add_argument("--admin-email", required=True)
    args = ap.parse_args(argv)
    try:
        s = load_settings()
    except ConfigError as exc:
        print(f"invalid configuration: {exc}", file=sys.stderr)
        return 2
    try:
        args.admin_email = _check_email(args.admin_email)
    except ValueError:
        print("admin email is not a valid email address", file=sys.stderr)
        return 2
    pw_input = read_password(stdin)
    if not PASSWORD_MIN_LENGTH <= len(pw_input) <= PASSWORD_MAX_LENGTH:
        print(f"password must be {PASSWORD_MIN_LENGTH} to {PASSWORD_MAX_LENGTH} characters", file=sys.stderr)
        return 2
    repos = create_repositories(s.REPO_BACKEND, database_url=s.DATABASE_URL, schema=s.DB_SCHEMA)
    try:
        created = create_tenant_with_admin(
            repos,
            PasswordService(s.ARGON2_MEMORY_KIB, s.ARGON2_TIME_COST, s.ARGON2_PARALLELISM),
            name=args.name,
            admin_name=args.admin_name,
            admin_email=args.admin_email,
            password=pw_input,
        )
    except AppError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 1
    finally:
        repos.db.dispose()
    print(f"tenantId={created.tenant_id}\nadminUserId={created.admin_user_id}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
