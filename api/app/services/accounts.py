"""Tenant bootstrap and user administration (Prompt A 4.6 / 4.7). Shared by the API and the seed tool."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.errors import AppError
from ..repositories import Repositories
from ..repositories.models import RepositoryError, User
from ..security.passwords import PasswordService
from .auth import AuthContext


def _email_exists() -> AppError:
    return AppError.conflict("EMAIL_EXISTS", "That email address is already registered")


@dataclass(frozen=True)
class CreatedTenant:
    tenant_id: str
    admin_user_id: str


def create_tenant_with_admin(
    repos: Repositories, passwords: PasswordService, *, name: str, admin_name: str, admin_email: str, password: str
) -> CreatedTenant:
    """One transaction: tenant + first admin (+ audit). Email clash anywhere -> 409 EMAIL_EXISTS (R1)."""
    password_hash = passwords.hash(password)

    def work(r: Repositories) -> CreatedTenant:
        tenant = r.tenants.create(name=name)
        admin = r.users.create(tenant.id, name=admin_name, email=admin_email, password_hash=password_hash, role="admin")
        r.audit.log(tenant.id, action="tenant.create", entity_type="tenant", entity_id=tenant.id,
                    actor_id=None, details={"adminUserId": admin.id})  # fmt: skip
        return CreatedTenant(tenant.id, admin.id)

    try:
        return repos.with_transaction(work)
    except RepositoryError as exc:
        if exc.code == "EMAIL_EXISTS":
            raise _email_exists() from None
        raise


def user_view(u: User) -> dict[str, str]:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "status": u.status}


def create_user(
    repos: Repositories, passwords: PasswordService, auth: AuthContext, *, name: str, email: str, role: str,
    password: str,
) -> User:  # fmt: skip
    password_hash = passwords.hash(password)

    def work(r: Repositories) -> User:
        u = r.users.create(auth.tenant_id, name=name, email=email, password_hash=password_hash, role=role)
        r.audit.log(auth.tenant_id, action="user.create", entity_type="user", entity_id=u.id,
                    actor_id=auth.user_id, details={"role": role})  # fmt: skip
        return u

    try:
        return repos.with_transaction(work)
    except RepositoryError as exc:
        if exc.code == "EMAIL_EXISTS":
            raise _email_exists() from None
        raise


def update_user(repos: Repositories, auth: AuthContext, user_id: str, *, role: str | None, status: str | None) -> User:
    if role is None and status is None:
        raise AppError.bad_request("Provide role and/or status")

    def work(r: Repositories) -> User:
        target = r.users.find_by_id(auth.tenant_id, user_id)
        if target is None:
            raise AppError.not_found("User not found")  # also for another tenant's id
        loses_admin = target.role == "admin" and target.status == "active" and (
            (role is not None and role != "admin") or status == "disabled"
        )  # fmt: skip
        if loses_admin and r.users.count_active_admins(auth.tenant_id) <= 1:
            raise AppError.conflict("CONFLICT", "Cannot disable or demote the last active admin of the tenant")
        updated = r.users.update(auth.tenant_id, user_id, role=role, status=status)
        assert updated is not None
        if status == "disabled":
            r.sessions.delete_by_user_id(auth.tenant_id, user_id)  # takes effect immediately
        r.audit.log(auth.tenant_id, action="user.update", entity_type="user", entity_id=user_id,
                    actor_id=auth.user_id, details={"role": role, "status": status})  # fmt: skip
        return updated

    return repos.with_transaction(work)
