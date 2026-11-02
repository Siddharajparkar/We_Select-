#!/usr/bin/env python3
"""Live E2E harness (Prompt A 3.8).

    python scripts/e2e/run.py --base-url http://127.0.0.1:8080 [--upto 6] [--expected-version SHA]

Each phase adds a module ``scripts/e2e/checks/pNN_*.py`` exposing ``CHECKS`` (functions taking a
``Ctx`` and raising ``AssertionError`` on failure). Prints PASS/FAIL per check; exits non-zero on any failure.
No third-party dependencies except httpx (already an API dependency).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

CHECKS_DIR = Path(__file__).parent / "checks"


class SkipCheck(Exception):
    """Raised by a check that must not run on this target (for example real AI without --with-ai)."""


@dataclass
class Ctx:
    Skip = SkipCheck

    base_url: str
    expected_version: str | None = None
    with_ai: bool = False
    with_email: bool = False
    target: str = "local"
    client: httpx.Client = field(default_factory=lambda: httpx.Client(timeout=15.0))
    state: dict[str, Any] = field(default_factory=dict)  # shared between checks (tenants, ids, cookies)

    @property
    def platform_key(self) -> str:
        """Never printed. Local runs fall back to the development default; Azure runs need E2E_PLATFORM_KEY."""
        key = os.environ.get("E2E_PLATFORM_KEY", "")
        if not key and self.target == "local":
            key = "dev-only-platform-key-change-me-00000"
        assert key, "E2E_PLATFORM_KEY is not set"
        return key

    def request(self, method: str, path: str, sid: str | None = None, **kw: Any) -> httpx.Response:
        """Send with an explicit Cookie header: the cookie is Secure, so an http:// client would not replay it."""
        headers = dict(kw.pop("headers", {}))
        if sid:
            headers["Cookie"] = f"sid={sid}"
        return self.client.request(method, self.url(path), headers=headers, **kw)

    def url(self, path: str) -> str:
        return self.base_url.rstrip("/") + path

    def get(self, path: str, **kw: object) -> httpx.Response:
        return self.client.get(self.url(path), **kw)  # type: ignore[arg-type]

    def new_request_id(self) -> str:
        return f"e2e-{uuid.uuid4()}"


def load_checks(upto: int) -> list[tuple[int, str, Callable[[Ctx], None]]]:
    found: list[tuple[int, str, Callable[[Ctx], None]]] = []
    for path in sorted(CHECKS_DIR.glob("p[0-9][0-9]_*.py")):
        phase = int(re.match(r"p(\d\d)_", path.name).group(1))  # type: ignore[union-attr]
        if phase > upto:
            continue
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for fn in getattr(mod, "CHECKS", []):
            found.append((phase, fn.__name__, fn))
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--upto", type=int, default=6, help="highest phase number to check")
    ap.add_argument("--expected-version", default=None, help="x-app-version the server must report")
    ap.add_argument("--target", default="local", choices=["local", "azure"])
    ap.add_argument("--with-ai", default="false")
    ap.add_argument("--with-email", default="false")
    args = ap.parse_args(argv)

    ctx = Ctx(args.base_url, args.expected_version, args.with_ai == "true", args.with_email == "true", args.target)
    checks = load_checks(args.upto)
    if not checks:
        print("no checks found", file=sys.stderr)
        return 2
    failed = skipped = 0
    for phase, name, fn in checks:
        started = time.perf_counter()
        try:
            fn(ctx)
            status, detail = "PASS", ""
        except SkipCheck as exc:
            status, detail = "SKIP", f" - {exc}"
            skipped += 1
        except AssertionError as exc:
            status, detail = "FAIL", f" - {exc}"
            failed += 1
        except httpx.HTTPError as exc:
            status, detail = "FAIL", f" - network: {type(exc).__name__}"
            failed += 1
        except Exception as exc:
            status, detail = "FAIL", f" - {type(exc).__name__}: {exc}"
            failed += 1
        print(f"{status} phase{phase:02d} {name} ({(time.perf_counter() - started) * 1000:.0f} ms){detail}")
    print(
        f"\nE2E {'FAIL' if failed else 'PASS'}: {len(checks) - failed - skipped}/{len(checks)} checks passed"
        f"{f', {skipped} skipped' if skipped else ''} (target={args.target}, upto={args.upto})"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
