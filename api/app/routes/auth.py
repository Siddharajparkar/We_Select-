from __future__ import annotations

from fastapi import APIRouter, Request, Response

from ..deps import Auth, Cfg, Repos, client_ip
from ..schemas.auth import LoginIn
from ..services.auth import COOKIE_MAX_AGE, COOKIE_NAME, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _cookie_args(secure: bool) -> dict[str, object]:
    return {"httponly": True, "secure": secure, "samesite": "lax", "path": "/"}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, cfg: Cfg) -> dict[str, object]:
    svc: AuthService = request.app.state.auth
    cookie, user, tenant = svc.login(body.email, body.password, client_ip(request))
    response.set_cookie(COOKIE_NAME, cookie, max_age=COOKIE_MAX_AGE, **_cookie_args(cfg.COOKIE_SECURE))  # type: ignore[arg-type]
    return {
        "user": {"id": user.id, "name": user.name, "role": user.role},
        "tenant": {"id": tenant.id, "name": tenant.name},
    }


@router.post("/logout", status_code=204)
def logout(request: Request, auth: Auth, cfg: Cfg) -> Response:
    request.app.state.auth.logout(auth)
    resp = Response(status_code=204)
    resp.delete_cookie(COOKIE_NAME, **_cookie_args(cfg.COOKIE_SECURE))  # type: ignore[arg-type]
    return resp


@router.get("/me")
def me(auth: Auth, repos: Repos) -> dict[str, object]:
    return {
        "user": {"id": auth.user_id, "name": auth.user_name, "role": auth.role},
        "tenant": {"id": auth.tenant_id, "name": auth.tenant_name},
    }
