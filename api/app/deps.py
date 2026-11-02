"""FastAPI dependencies: repositories, clock, authentication and role checks."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from .config import Settings
from .core.clock import Clock
from .core.errors import AppError
from .providers import Providers
from .repositories import Repositories
from .services.auth import COOKIE_NAME, AuthContext, AuthService


def get_repos(request: Request) -> Repositories:
    return request.app.state.repos  # type: ignore[no-any-return]


def get_clock(request: Request) -> Clock:
    return request.app.state.clock  # type: ignore[no-any-return]


def get_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_providers(request: Request) -> Providers:
    return request.app.state.providers  # type: ignore[no-any-return]


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth  # type: ignore[no-any-return]


def client_ip(request: Request) -> str:
    return (request.client.host if request.client else "unknown")[:45]


def current_auth(request: Request, svc: Annotated[AuthService, Depends(get_auth_service)]) -> AuthContext:
    """``requireAuth``: valid session cookie -> caller identity (tenant comes from here only)."""
    ctx = svc.resolve(request.cookies.get(COOKIE_NAME))
    request.state.tenant_id = ctx.tenant_id  # picked up by the access log
    return ctx


def require_staff(auth: Annotated[AuthContext, Depends(current_auth)]) -> AuthContext:
    """``requireStaff``: recruiter or admin."""
    if auth.role not in ("admin", "recruiter"):
        raise AppError.forbidden()
    return auth


def require_admin(auth: Annotated[AuthContext, Depends(current_auth)]) -> AuthContext:
    if auth.role != "admin":
        raise AppError.forbidden()
    return auth


Repos = Annotated[Repositories, Depends(get_repos)]
Clk = Annotated[Clock, Depends(get_clock)]
Cfg = Annotated[Settings, Depends(get_settings)]
Prov = Annotated[Providers, Depends(get_providers)]
Auth = Annotated[AuthContext, Depends(current_auth)]
Staff = Annotated[AuthContext, Depends(require_staff)]
Admin = Annotated[AuthContext, Depends(require_admin)]
