from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from ..core.errors import AppError
from ..core.ids import timing_safe_equal
from ..deps import Cfg, Repos, client_ip
from ..schemas.auth import TenantCreateIn
from ..services.accounts import create_tenant_with_admin

router = APIRouter(prefix="/platform", tags=["platform"])


def require_platform_key(
    request: Request, cfg: Cfg, x_platform_key: Annotated[str | None, Header(alias="X-Platform-Key")] = None
) -> None:
    """Endpoint 4 guard (R24): rate limit first, then constant-time key check; 401 either way."""
    request.app.state.platform_limiter.check(client_ip(request))
    if not x_platform_key or not timing_safe_equal(x_platform_key, cfg.PLATFORM_KEY):
        raise AppError.unauthenticated("Invalid platform key")


@router.post("/tenants", status_code=201, dependencies=[Depends(require_platform_key)])
def create_tenant(body: TenantCreateIn, request: Request, repos: Repos) -> dict[str, str]:
    created = create_tenant_with_admin(
        repos, request.app.state.passwords, name=body.name, admin_name=body.adminName,
        admin_email=body.adminEmail, password=body.password,
    )  # fmt: skip
    return {"tenantId": created.tenant_id, "adminUserId": created.admin_user_id}
