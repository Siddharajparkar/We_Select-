"""Phase 0 live checks: the foundation contract."""

from __future__ import annotations


def health_returns_contract_body(ctx):  # type: ignore[no-untyped-def]
    r = ctx.get("/api/v1/health")
    assert r.status_code == 200, f"status {r.status_code}"
    assert r.text == '{"status":"ok"}', f"body {r.text!r}"


def unknown_route_uses_error_envelope(ctx):  # type: ignore[no-untyped-def]
    r = ctx.get("/api/v1/__e2e_not_found__")
    assert r.status_code == 404, f"status {r.status_code}"
    err = r.json().get("error", {})
    assert err.get("code") == "NOT_FOUND" and err.get("message"), f"envelope {r.text!r}"


def security_headers_present(ctx):  # type: ignore[no-untyped-def]
    h = ctx.get("/api/v1/health").headers
    assert h.get("x-content-type-options") == "nosniff", "missing nosniff"
    assert h.get("cache-control") == "no-store", "health must not be cached"


CHECKS = [health_returns_contract_body, unknown_route_uses_error_envelope, security_headers_present]
