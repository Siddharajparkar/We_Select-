"""Phase 3 live checks: what proves a deploy answered (version header, request-id round trip)."""

from __future__ import annotations

import re
import socket
import ssl
from urllib.parse import urlparse

import httpx


def version_header_present(ctx):  # type: ignore[no-untyped-def]
    v = ctx.get("/api/v1/health").headers.get("x-app-version")
    assert v, "x-app-version header missing"
    assert re.fullmatch(r"[A-Za-z0-9._\-]{1,64}", v), f"unexpected version format {v!r}"


def version_matches_expected_when_given(ctx):  # type: ignore[no-untyped-def]
    if not ctx.expected_version:
        return  # not asserted locally; the pipeline passes the commit SHA
    v = ctx.get("/api/v1/health").headers.get("x-app-version")
    assert v == ctx.expected_version, (
        f"serving {v!r}, expected {ctx.expected_version!r} (old revision still answering?)"
    )


def request_id_is_echoed(ctx):  # type: ignore[no-untyped-def]
    rid = ctx.new_request_id()
    r = ctx.get("/api/v1/health", headers={"x-request-id": rid})
    assert r.headers.get("x-request-id") == rid, f"got {r.headers.get('x-request-id')!r}"


def request_id_is_generated_when_absent(ctx):  # type: ignore[no-untyped-def]
    a = ctx.get("/api/v1/health").headers.get("x-request-id")
    b = ctx.get("/api/v1/health").headers.get("x-request-id")
    assert a and b and a != b, "each request without an id must get a fresh one"


def errors_carry_the_standard_headers(ctx):  # type: ignore[no-untyped-def]
    rid = ctx.new_request_id()
    r = ctx.get("/api/v1/__e2e_not_found__", headers={"x-request-id": rid})
    assert r.headers.get("x-request-id") == rid and r.headers.get("x-app-version"), "error response lacks headers"


def _tls_context() -> ssl.SSLContext:
    """Same CA bundle httpx uses (certifi). ssl.create_default_context() can fail loading the Windows cert store."""
    import certifi

    return ssl.create_default_context(cafile=certifi.where())


def declared_oversize_probe(base_url: str, declared: int = 1_100_000) -> tuple[int, bytes]:
    """Send only headers that DECLARE an oversized body and read the answer (status, body bytes).

    The server rejects on the declared length without reading the body, so this is the exact rule real clients hit.
    """
    u = urlparse(base_url)
    https = u.scheme == "https"
    host = u.hostname or ""
    raw = socket.create_connection((host, u.port or (443 if https else 80)), timeout=15)
    sock = _tls_context().wrap_socket(raw, server_hostname=host) if https else raw
    crlf = chr(13) + chr(10)
    request = crlf.join(
        [
            "POST /api/v1/health HTTP/1.1",
            f"Host: {u.netloc}",
            "Content-Type: application/octet-stream",
            f"Content-Length: {declared}",
            "Connection: close",
            "",
            "",
        ]
    )
    try:
        sock.sendall(request.encode())
        data = b""
        try:
            while chunk := sock.recv(65536):
                data += chunk
        except (ssl.SSLError, OSError):
            pass  # the server closed without a TLS close_notify (Connection: close); keep what was already read
    finally:
        sock.close()
    if not data:
        raise AssertionError("no answer to the header-only oversize request")
    head, _, body = data.partition((crlf * 2).encode())
    return int(head.split()[1]), body


def oversized_body_is_rejected_cleanly(ctx):  # type: ignore[no-untyped-def]
    try:
        r = ctx.client.post(ctx.url("/api/v1/health"), content=b"x" * 1_100_000)
        status, code = r.status_code, r.json()["error"]["code"]
    except (httpx.TransportError, ssl.SSLError, OSError):
        # The server answers 413 and closes while the upload is still running; across a real network (the cloud
        # ingress) the reset can reach the client before it reads the answer. Prove the same rule header-only.
        status, body = declared_oversize_probe(ctx.base_url)
        code = "PAYLOAD_TOO_LARGE" if b"PAYLOAD_TOO_LARGE" in body else "?"
    assert status == 413, f"status {status}"
    assert code == "PAYLOAD_TOO_LARGE", f"code {code}"


CHECKS = [
    version_header_present,
    version_matches_expected_when_given,
    request_id_is_echoed,
    request_id_is_generated_when_absent,
    errors_carry_the_standard_headers,
    oversized_body_is_rejected_cleanly,
]
