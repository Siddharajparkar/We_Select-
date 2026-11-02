#!/usr/bin/env python3
"""Run the Phase 4-6 Postman specification in Python (no Node, no newman).

    python run46.py --base-url http://127.0.0.1:8080 [--collection unit|integration|e2e|all]
                    [--platform-key KEY] [--wait-seconds 3]

Executes spec46.py - the same source the Postman JSON files are generated from.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).parent))
import spec46 as spec  # noqa: E402

_VAR = re.compile(r"\{\{([^}]+)\}\}")


def dotted(obj: Any, path: str) -> Any:
    if not path:
        return obj
    for part in path.split("."):
        if isinstance(obj, list):
            obj = obj[int(part)] if part.isdigit() and int(part) < len(obj) else None
        elif isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


@dataclass
class Report:
    collection: str
    results: list[tuple[str, str, bool, str]] = field(default_factory=list)

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
        if req.get("wait_var"):
            time.sleep(float(variables.get(req["wait_var"]) or 0))
        headers = {k: substitute(v, variables) for k, v in req.get("headers", {}).items()}
        content: bytes | None = None
        if req.get("body"):
            content = substitute(json.dumps(req["body"]["json"]), variables).encode()
            headers.setdefault("Content-Type", "application/json")
        name = req["name"]
        try:
            resp = http.request(
                req["method"], substitute("{{baseUrl}}" + req["path"], variables), headers=headers, content=content
            )
        except httpx.HTTPError as exc:
            report.results.append((name, "request completes", False, type(exc).__name__))
            continue

        def check(label: str, ok: bool, detail: str = "", _n: str = name) -> None:
            report.results.append((_n, label, bool(ok), "" if ok else detail))

        exp = req.get("expect", {})
        text = resp.text
        try:
            parsed: Any = resp.json()
        except ValueError:
            parsed = None
        if "status" in exp:
            check(
                f"status is {exp['status']}", resp.status_code == exp["status"], f"got {resp.status_code}: {text[:100]}"
            )
        for path, value in exp.get("json_has", {}).items():
            got = dotted(parsed, path)
            check(f"json {path} equals {value}", got == value, f"got {got!r}")
        for path, n in exp.get("json_len", {}).items():
            got = dotted(parsed, path)
            check(f"json {path or '(root)'} has {n} items", isinstance(got, list) and len(got) == n, f"got {got!r:.80}")
        for path, rx in exp.get("json_match", {}).items():
            check(
                f"json {path} matches {rx}",
                re.search(rx, str(dotted(parsed, path))) is not None,
                f"got {dotted(parsed, path)!r}",
            )
        for needle in exp.get("body_not_contains", []):
            check(f"body does not contain {needle!r}", needle not in text, "found in body")
        for h in exp.get("headers_present", []):
            check(f"header {h} is present", h in resp.headers, "missing")
        for h, rx in exp.get("headers_match", {}).items():
            check(
                f"header {h} matches {rx}",
                re.search(rx, resp.headers.get(h, ""), re.I) is not None,
                f"got {resp.headers.get(h)!r}",
            )
        for var, src in exp.get("save", {}).items():
            if "header" in src:
                variables[var] = resp.headers.get(src["header"], "")
            elif "header_regex" in src:
                m = re.search(src["header_regex"][1], resp.headers.get(src["header_regex"][0], ""))
                variables[var] = m.group(1) if m else ""
            else:
                variables[var] = str(dotted(parsed, src["json"]))
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--collection", default="all", choices=["unit", "integration", "e2e", "all"])
    ap.add_argument("--platform-key", default="")
    ap.add_argument("--wait-seconds", default="")
    args = ap.parse_args(argv)
    overrides = {k: v for k, v in {"platformKey": args.platform_key, "waitSeconds": args.wait_seconds}.items() if v}
    exit_code = 0
    for key in list(spec.COLLECTIONS) if args.collection == "all" else [args.collection]:
        rep = run(key, args.base_url, overrides)
        print(f"\n== {rep.collection}: {len(rep.results) - len(rep.failed)}/{len(rep.results)} assertions passed")
        for req, label, ok, detail in rep.results:
            if not ok:
                print(f"  FAIL [{req}] {label} {detail}")
        exit_code |= 1 if rep.failed else 0
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
