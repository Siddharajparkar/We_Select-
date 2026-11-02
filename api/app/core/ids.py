"""Identifier and token helpers."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.IGNORECASE)
_UUID4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.IGNORECASE)


def new_id() -> str:
    """A new random UUID v4 (lowercase string)."""
    return str(uuid.uuid4())


def hash_token(token: str) -> str:
    """SHA-256 hex digest of a token. Only hashes are ever stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_secure_token() -> str:
    """256-bit random token, URL-safe base64 without padding."""
    return secrets.token_urlsafe(32)


def timing_safe_equal(a: str, b: str) -> bool:
    """Constant-time comparison of two strings."""
    return hmac.compare_digest(hashlib.sha256(a.encode("utf-8")).digest(), hashlib.sha256(b.encode("utf-8")).digest())


def is_uuid(value: object) -> bool:
    """True for a well-formed UUID string (any RFC 4122 version)."""
    return isinstance(value, str) and bool(_UUID_RE.match(value))


def is_uuid4(value: object) -> bool:
    return isinstance(value, str) and bool(_UUID4_RE.match(value))
