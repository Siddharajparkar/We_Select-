"""Shared request-validation helpers."""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import Path
from pydantic import AfterValidator, StringConstraints

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"

# A malformed id in a path is a 400 VALIDATION_ERROR (R32); a well-formed unknown/foreign id is a 404 later.
UuidPath = Annotated[str, Path(pattern=UUID_PATTERN)]


def _check_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 320 or not _EMAIL.match(value):
        raise ValueError("must be a valid email address")
    return value


Email = Annotated[str, AfterValidator(_check_email)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
