from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

from ..security.passwords import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from .common import Email, Name

Password = Annotated[str, StringConstraints(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)]


class LoginIn(BaseModel):
    email: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=320)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=1024)]  # wrong/short -> 401, not 400


class TenantCreateIn(BaseModel):
    name: Name
    adminName: Name
    adminEmail: Email
    password: Password


class UserCreateIn(BaseModel):
    name: Name
    email: Email
    role: Literal["admin", "recruiter"]
    password: Password


class UserPatchIn(BaseModel):
    role: Literal["admin", "recruiter"] | None = None
    status: Literal["active", "disabled"] | None = None
