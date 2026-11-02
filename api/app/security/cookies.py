"""Signed cookie values: ``<value>.<base64url(HMAC-SHA256(secret, value))>``.

The signature is verified in constant time BEFORE the database is touched (Prompt A 4.2).
"""

from __future__ import annotations

import base64
import hashlib
import hmac


def _sig(value: str, secret: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")


def sign(value: str, secret: str) -> str:
    return f"{value}.{_sig(value, secret)}"


def verify(cookie: str | None, secret: str) -> str | None:
    """Return the original value when the signature is valid, else ``None``."""
    if not cookie or "." not in cookie or len(cookie) > 512:
        return None
    value, _, signature = cookie.rpartition(".")
    if not value or not hmac.compare_digest(_sig(value, secret), signature):
        return None
    return value
