#!/usr/bin/env python3
"""Run the Phase 3 Postman specification in Python (no Node, no newman).

    python run_collection.py --base-url http://127.0.0.1:8080 [--collection unit|integration|e2e|all]
                             [--expected-version SHA] [--docs-status 200|404]

Executes spec.py - the same source the Postman JSON files are generated from.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).parent))
import spec  # noqa: E402

_VAR = re.compile(r"\{\{([^}]+)\}\}")


def _dotted(obj: Any, path: str) -> Any:
    for part in path.split("."):
        obj = obj.get(part) if isinstance(obj, dict) else None
    return obj


@dataclass
class Report:
    collection: str
    results: list[tuple[str, str, bool, str]] = field(default_factory=list)  # (request, assertion, ok, detail)

    @property
    def failed(self) -> list[tuple[str, str, bool, str]]:
        return [r for r in self.results if not r[2]]


def substitute(text: str, variables: dict[str, str]) -> str:
    def repl(m: re.Match[str]) -> str:
        name = m.group(1).strip()
        return str(uuid.uuid4()) if name == "$guid" else variables.get(name, "")

    return _VAR.sub(repl, text)


def run(
    collection_key: str, base_url: str, overrides: dict[str, str] | None = None, client: httpx.Client | None = None
) -> Report:
    _, coll = spec.COLLECTIONS[collection_key]
    variables = {**spec.DEFAULT_VARIABLES, **(overrides or {}), "baseUrl": base_url.rstrip("/")}
    report = Report(coll["name"])
    http = client or httpx.Client(timeout=30.0, follow_redirects=False)

    for req in coll["items"]:
        for var, template in req.get("pre_set", {}).items():
            variables[var] = substitute(template, variables)
        headers = {k: substitute(v, variables) for k, v in req.get("headers", {}).items()}
        content: bytes | None = None
        body = req.get("body")
        if body and "repeat" in body:
            content = body["repeat"][0].encode() * body["repeat"][1]
            headers.setdefault("Content-Type", "text/plain")
        elif body:
            content = json.dumps(body["json"]).encode()
            headers.setdefault("Content-Type", "application/json")
        url = substitute("{{baseUrl}}" + req["path"], variables)
        name = req["name"]
        try:
            resp = http.request(req["method"], url, headers=headers, content=content)
        except httpx.HTTPError as exc:
            report.results.append((name, "request completes", False, f"{type(exc).__name__}"))
            continue

        exp = req.get("expect", {})
        when = exp.get("when_var")
        if when and not variables.get(when):
            report.results.append((name, f"skipped ({when} not set)", True, ""))
            continue

        def check(label: str, ok: bool, detail: str = "", _name: str = name) -> None:
            report.results.append((_name, label, bool(ok), "" if ok else detail))

        text = resp.text
        parsed: Any = None
        try:
            parsed = resp.json()
        except ValueError:
            pass

        if "status" in exp:
            want = int(substitute(exp["status"], variables)) if isinstance(exp["status"], str) else exp["status"]
            check(f"status is {want}", resp.status_code == want, f"got {resp.status_code}")
        if "body_text" in exp:
            check("body text is exact", text == exp["body_text"], f"got {text[:80]!r}")
        if "body_json" in exp:
            check("body JSON is exact", parsed == exp["body_json"], f"got {text[:80]!r}")
        for path, value in exp.get("json_has", {}).items():
            check(f"json {path} equals {value}", _dotted(parsed, path) == value, f"got {_dotted(parsed, path)!r}")
        for needle in exp.get("body_not_contains", []):
            check(f"body does not contain {needle!r}", needle not in text, "found in body")
        for h, v in exp.get("headers_equal", {}).items():
            want = substitute(v, variables)
            check(f"header {h} equals {want}", resp.headers.get(h) == want, f"got {resp.headers.get(h)!r}")
        for h, v in exp.get("headers_not_equal", {}).items():
            want = substitute(v, variables)
            check(f"header {h} differs from {want}", resp.headers.get(h) != want, "headers are equal")
        for h in exp.get("headers_present", []):
            check(f"header {h} is present", h in resp.headers, "missing")
        for h, rx in exp.get("headers_match", {}).items():
            check(
                f"header {h} matches {rx}",
                re.search(rx, resp.headers.get(h, ""), re.I) is not None,
                f"got {resp.headers.get(h)!r}",
            )
        for var, src in exp.get("save", {}).items():
            variables[var] = (
                resp.headers.get(src["header"], "") if "header" in src else str(_dotted(parsed, src["json"]))
            )
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--collection", default="all", choices=["unit", "integration", "e2e", "all"])
    ap.add_argument("--expected-version", default="")
    ap.add_argument("--docs-status", default="200")
    args = ap.parse_args(argv)
    keys = list(spec.COLLECTIONS) if args.collection == "all" else [args.collection]
    overrides = {"expectedVersion": args.expected_version, "docsStatus": args.docs_status}
    exit_code = 0
    for key in keys:
        rep = run(key, args.base_url, overrides)
        passed = len(rep.results) - len(rep.failed)
        print(f"\n== {rep.collection}: {passed}/{len(rep.results)} assertions passed")
        for req, label, ok, detail in rep.results:
            if not ok:
                print(f"  FAIL [{req}] {label} {detail}")
        exit_code |= 1 if rep.failed else 0
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
