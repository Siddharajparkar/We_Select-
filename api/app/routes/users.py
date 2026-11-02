from __future__ import annotations

from fastapi import APIRouter, Request

from ..deps import Admin, Repos
from ..schemas.auth import UserCreateIn, UserPatchIn
from ..schemas.common import UuidPath
from ..services.accounts import create_user, update_user, user_view

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
def list_users(auth: Admin, repos: Repos) -> list[dict[str, str]]:
    return [user_view(u) for u in repos.users.list(auth.tenant_id)]


@router.post("", status_code=201)
def post_user(body: UserCreateIn, request: Request, auth: Admin, repos: Repos) -> dict[str, str]:
    u = create_user(
        repos, request.app.state.passwords, auth, name=body.name, email=body.email, role=body.role,
        password=body.password,
    )  # fmt: skip
    return {"id": u.id}


@router.patch("/{user_id}")
def patch_user(user_id: UuidPath, body: UserPatchIn, auth: Admin, repos: Repos) -> dict[str, str]:
    return user_view(update_user(repos, auth, user_id, role=body.role, status=body.status))
