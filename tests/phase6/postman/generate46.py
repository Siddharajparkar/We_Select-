#!/usr/bin/env python3
"""Generate the Phase 4-6 Postman v2.1 collections + environment from spec46.py.   python generate46.py [--check]"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
import spec46 as spec  # noqa: E402

SCHEMA = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
HERE = Path(__file__).parent


def js(value: Any) -> str:
    return json.dumps(value)


def get(path: str) -> str:
    """JS expression reading a dotted path (\"\" = whole body) from the parsed response."""
    return f"_.get(pm.response.json(), {js(path)})" if path else "pm.response.json()"


def test_script(expect: dict[str, Any]) -> list[str]:
    out: list[str] = []

    def t(title: str, code: str) -> None:
        out.append(f"pm.test({js(title)}, function () {{ {code} }});")

    if "status" in expect:
        t(f"status is {expect['status']}", f"pm.response.to.have.status({expect['status']});")
    for path, value in expect.get("json_has", {}).items():
        t(f"json {path} equals {value}", f"pm.expect({get(path)}).to.eql({js(value)});")
    for path, n in expect.get("json_len", {}).items():
        t(f"json {path or '(root)'} has {n} items", f"pm.expect({get(path)}).to.have.lengthOf({n});")
    for path, rx in expect.get("json_match", {}).items():
        t(f"json {path} matches {rx}", f"pm.expect(String({get(path)})).to.match(new RegExp({js(rx)}));")
    for needle in expect.get("body_not_contains", []):
        t(f"body does not contain {needle!r}", f"pm.expect(pm.response.text()).to.not.include({js(needle)});")
    for h in expect.get("headers_present", []):
        t(f"header {h} is present", f"pm.response.to.have.header({js(h)});")
    for h, rx in expect.get("headers_match", {}).items():
        t(f"header {h} matches {rx}",
          f"pm.expect(pm.response.headers.get({js(h)}) || '').to.match(new RegExp({js(rx)}, 'i'));")  # fmt: skip
    for var, src in expect.get("save", {}).items():
        if "header" in src:
            out.append(f"pm.collectionVariables.set({js(var)}, pm.response.headers.get({js(src['header'])}));")
        elif "header_regex" in src:
            h, rx = src["header_regex"]
            out.append(
                f"pm.collectionVariables.set({js(var)}, "
                f"((new RegExp({js(rx)})).exec(pm.response.headers.get({js(h)}) || '') || [])[1] || '');"
            )
        else:
            out.append(f"pm.collectionVariables.set({js(var)}, {get(src['json'])});")
    return out


def item(req: dict[str, Any]) -> dict[str, Any]:
    headers = [{"key": k, "value": v} for k, v in req.get("headers", {}).items()]
    path = req["path"]
    url: dict[str, Any] = {"raw": "{{baseUrl}}" + path, "host": ["{{baseUrl}}"],
                           "path": [p for p in path.split("?")[0].split("/") if p]}  # fmt: skip
    if "?" in path:
        url["query"] = [
            {"key": kv.split("=")[0], "value": kv.split("=", 1)[1]} for kv in path.split("?", 1)[1].split("&")
        ]
    request: dict[str, Any] = {"method": req["method"], "header": headers, "url": url}
    if req.get("body"):
        request["body"] = {
            "mode": "raw",
            "raw": json.dumps(req["body"]["json"]),
            "options": {"raw": {"language": "json"}},
        }
        request["header"] = [{"key": "Content-Type", "value": "application/json"}, *headers]
    pre = [f"pm.collectionVariables.set({js(v)}, pm.variables.replaceIn({js(tpl)}));"
           for v, tpl in req.get("pre_set", {}).items()]  # fmt: skip
    if req.get("wait_var"):  # let the background job finish (busy wait: the sandbox has no sleep)
        pre.append(
            f"var end = Date.now() + Number(pm.variables.get({js(req['wait_var'])})) * 1000; while (Date.now() < end) {{}}"
        )
    events: list[dict[str, Any]] = []
    if pre:
        events.append({"listen": "prerequest", "script": {"type": "text/javascript", "exec": pre}})
    events.append({"listen": "test", "script": {"type": "text/javascript", "exec": test_script(req.get("expect", {}))}})
    return {"name": req["name"], "event": events, "request": request}


def collection(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "info": {"name": c["name"], "description": c["description"], "schema": SCHEMA},
        "item": [item(r) for r in c["items"]],
        "variable": [{"key": k, "value": v} for k, v in spec.DEFAULT_VARIABLES.items()],
    }


def environment() -> dict[str, Any]:
    return {
        "name": "AI Assessment Platform - Local (phases 4-6)",
        "values": [{"key": k, "value": v, "enabled": True} for k, v in spec.DEFAULT_VARIABLES.items()],
        "_postman_variable_scope": "environment",
    }


def render() -> dict[str, str]:
    out = {fname: json.dumps(collection(c), indent=2) + "\n" for fname, c in spec.COLLECTIONS.values()}
    out[spec.ENVIRONMENT_FILE] = json.dumps(environment(), indent=2) + "\n"
    return out


def main() -> int:
    files = render()
    if "--check" in sys.argv:
        stale = [n for n, text in files.items() if not (HERE / n).exists() or (HERE / n).read_text() != text]
        if stale:
            print("out of date:", ", ".join(stale))
            return 1
        print("postman files are in sync with spec46.py")
        return 0
    for name, text in files.items():
        (HERE / name).write_text(text)
        print("wrote", name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
