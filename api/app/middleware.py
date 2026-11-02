"""Pure-ASGI middleware: request id, security headers, body limit, access log, error boundary.

It is the outermost user middleware, so every response - including 500s and 413s -
carries ``x-request-id`` and ``x-app-version``.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .core.errors import AppError
from .core.ids import new_id
from .core.logging import logger

MAX_BODY_BYTES = 1_000_000  # 1 MB
JD_FILE_MAX_BYTES = 2 * 1024 * 1024
MULTIPART_OVERHEAD = 64 * 1024
# Per-route ceilings (method, path regex, bytes). The JD upload route enforces the exact 2 MB file limit
# itself (400 VALIDATION_ERROR); this ceiling only stops absurd bodies early (413).
ROUTE_BODY_LIMITS: tuple[tuple[str, re.Pattern[str], int], ...] = (
    ("POST", re.compile(r"^/api/v1/assessments/[0-9a-fA-F-]{36}/jd-file$"), JD_FILE_MAX_BYTES + MULTIPART_OVERHEAD),
)
_REQUEST_ID_OK = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "strict-transport-security": "max-age=15552000; includeSubDomains",
    "cross-origin-resource-policy": "same-origin",
}


class _BodyTooLarge(Exception):
    pass


def resolve_request_id(incoming: str | None) -> str:
    """Echo a sane incoming id, otherwise generate a UUID."""
    if incoming and _REQUEST_ID_OK.match(incoming):
        return incoming
    return new_id()


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, *, app_version: str = "local", max_body: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.app_version = app_version
        self.max_body = max_body

    def limit_for(self, method: str, path: str) -> int:
        for m, rx, limit in ROUTE_BODY_LIMITS:
            if m == method and rx.match(path):
                return max(limit, self.max_body)
        return self.max_body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        request_id = resolve_request_id(headers.get("x-request-id"))
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        status_holder = {"status": 500}
        response_started = {"v": False}

        def decorate(message: Message) -> Message:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                response_started["v"] = True
                raw = list(message.get("headers", []))
                present = {k.decode("latin-1").lower() for k, _ in raw}
                extra = {"x-request-id": request_id, "x-app-version": self.app_version, **SECURITY_HEADERS}
                if scope["path"].startswith("/api/") and "cache-control" not in present:
                    extra["cache-control"] = "no-store"
                for k, v in extra.items():
                    if k not in present:
                        raw.append((k.encode("latin-1"), v.encode("latin-1")))
                message = {**message, "headers": raw}
            return message

        async def send_wrapper(message: Message) -> None:
            await send(decorate(message))

        limit = self.limit_for(scope.get("method", ""), scope["path"])
        declared = headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            await self._send_error(send_wrapper, AppError(413, "PAYLOAD_TOO_LARGE", "Request body too large"))
            self._log(scope, status_holder["status"], started, request_id)
            return

        received = {"n": 0}

        async def receive_wrapper() -> Message:
            message = await receive()
            if message["type"] == "http.request":
                received["n"] += len(message.get("body", b""))
                if received["n"] > limit:
                    raise _BodyTooLarge
            return message

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        except _BodyTooLarge:
            if not response_started["v"]:
                await self._send_error(send_wrapper, AppError(413, "PAYLOAD_TOO_LARGE", "Request body too large"))
        except Exception as exc:
            logger.error(
                "unhandled_error",
                request_id=request_id,
                error_type=type(exc).__name__,
                path=scope["path"],
            )
            if not response_started["v"]:
                await self._send_error(send_wrapper, AppError.internal())
        self._log(scope, status_holder["status"], started, request_id)

    @staticmethod
    async def _send_error(send: Send, err: AppError) -> None:
        body = json.dumps(err.to_dict()).encode()
        await send(
            {
                "type": "http.response.start",
                "status": err.status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    def _log(scope: Scope, status: int, started: float, request_id: str) -> None:
        state: Any = scope.get("state", {})
        logger.info(
            "request",
            request_id=request_id,
            method=scope["method"],
            path=scope["path"],  # query string deliberately not logged
            status=status,
            durationMs=round((time.perf_counter() - started) * 1000, 2),
            tenantId=state.get("tenant_id") if isinstance(state, dict) else None,
        )
