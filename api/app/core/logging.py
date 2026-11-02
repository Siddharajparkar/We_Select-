"""Structured JSON logger with secret redaction.

Log lines go to stdout (info/debug) or stderr (warn/error) as one JSON object
per line; Azure Container Apps forwards both to Log Analytics.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from typing import Any

REDACTED_KEYS = frozenset(
    {
        "password",
        "authorization",
        "cookie",
        "set-cookie",
        "x-platform-key",
        "token",
        "token_hash",
        "foundry_key",
        "foundry-key",
        "database_url",
        "acs_connection_string",
        "blob_connection_string",
        "applicationinsights_connection_string",
        "session_secret",
        "platform_key",
        "sessionid",
    }
)

_PATTERN = re.compile(
    r"(?P<key>password|pwd|secret|key|token|connection.?string|authorization|accountkey|sharedaccesskey)"
    r"=(?P<val>[^\s&;]+)",
    re.IGNORECASE,
)

MAX_DEPTH = 8


def _redact_string(value: str) -> str:
    return _PATTERN.sub(lambda m: f"{m.group('key')}=****", value)


def redact(obj: Any, _depth: int = 0) -> Any:
    """Return a copy of ``obj`` with secret values replaced by ``****``."""
    if _depth > MAX_DEPTH:
        return obj
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            lk = str(key).lower()
            if lk in REDACTED_KEYS or lk.replace("-", "_") in REDACTED_KEYS:
                out[str(key)] = "****"
            else:
                out[str(key)] = redact(value, _depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact(v, _depth + 1) for v in obj]
    if isinstance(obj, str):
        return _redact_string(obj)
    return obj


def _emit(level: str, message: str, meta: dict[str, Any], request_id: str | None) -> None:
    entry: dict[str, Any] = {
        "level": level,
        "message": _redact_string(message),
        "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    }
    if request_id:
        entry["requestId"] = request_id
    entry.update(redact(meta))
    line = json.dumps(entry, default=str)
    stream = sys.stderr if level in ("warn", "error") else sys.stdout
    stream.write(line + "\n")
    stream.flush()


class _Logger:
    def debug(self, message: str, request_id: str | None = None, **meta: Any) -> None:
        _emit("debug", message, meta, request_id)

    def info(self, message: str, request_id: str | None = None, **meta: Any) -> None:
        _emit("info", message, meta, request_id)

    def warn(self, message: str, request_id: str | None = None, **meta: Any) -> None:
        _emit("warn", message, meta, request_id)

    def error(self, message: str, request_id: str | None = None, **meta: Any) -> None:
        _emit("error", message, meta, request_id)


logger = _Logger()
