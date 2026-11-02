"""In-memory files provider (default for dev/test) and shared path sanitising."""

from __future__ import annotations

import re

from .ports import SaveJdInput

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_file_name(name: str, limit: int = 120) -> str:
    """Strip separators/control chars and cap at ``limit`` chars, keeping the extension."""
    safe = re.sub(r"[/\\]", "_", name)
    safe = _CONTROL.sub("", safe)
    if len(safe) > limit:
        dot = safe.rfind(".")
        if dot > 0:
            ext = safe[dot:]
            safe = safe[: limit - len(ext)] + ext
        else:
            safe = safe[:limit]
    return safe or "file"


def blob_path(data: SaveJdInput) -> str:
    return f"{data.tenant_id}/{data.assessment_id}/{sanitize_file_name(data.file_name)}"


class MemoryFilesProvider:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    def save_jd(self, data: SaveJdInput) -> str:
        path = blob_path(data)
        self.store[path] = data.content
        return path

    def get_jd(self, path: str) -> bytes:
        try:
            return self.store[path]
        except KeyError:
            raise FileNotFoundError(path) from None

    def delete_jd(self, path: str) -> None:
        self.store.pop(path, None)
