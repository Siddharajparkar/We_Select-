"""Phase 3 live checks: what proves a deploy answered (version header, request-id round trip)."""

from __future__ import annotations

import re


def version_header_present(ctx):  # type: ignore[no-untyped-def]
    v = ctx.get("/api/v1/health").headers.get("x-app-version")
    assert v, "x-app-version header missing"
    assert re.fullmatch(r"[A-Za-z0-9._\-]{1,64}", v), f"unexpected version format {v!r}"


def version_matches_expected_when_given(ctx):  # type: ignore[no-untyped-def]
    if not ctx.expected_version:
        return  # not asserted locally; the pipeline passes the commit SHA
    v = ctx.get("/api/v1/health").headers.get("x-app-version")
    assert (
        v == ctx.expected_version
    ), f"serving {v!r}, expected {ctx.expected_version!r} (old revision still answering?)"


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


def oversized_body_is_rejected_cleanly(ctx):  # type: ignore[no-untyped-def]
    r = ctx.client.post(ctx.url("/api/v1/health"), content=b"x" * 1_100_000)
    assert r.status_code == 413, f"status {r.status_code}"
    assert r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


CHECKS = [
    version_header_present,
    version_matches_expected_when_given,
    request_id_is_echoed,
    request_id_is_generated_when_absent,
    errors_carry_the_standard_headers,
    oversized_body_is_rejected_cleanly,
]
