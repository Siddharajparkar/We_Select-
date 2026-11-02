#!/usr/bin/env python3
"""Generate the Postman v2.1 collections + environment from spec.py.   python generate.py [--check]"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
import spec  # noqa: E402

SCHEMA = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
HERE = Path(__file__).parent


def js(value: Any) -> str:
    return json.dumps(value)


def resolved(value: str) -> str:
    """JS expression yielding the value with {{vars}} resolved inside the Postman sandbox."""
    return f"pm.variables.replaceIn({js(value)})" if "{{" in value else js(value)


def test_script(expect: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    body: list[str] = []

    def t(title: str, code: str) -> None:
        body.append(f"pm.test({js(title)}, function () {{ {code} }});")

    if "status" in expect:
        st = expect["status"]
        if isinstance(st, str):
            t(f"status equals {st}", f"pm.response.to.have.status(parseInt({resolved(st)}, 10));")
        else:
            t(f"status is {st}", f"pm.response.to.have.status({st});")
    if "body_text" in expect:
        t("body text is exact", f"pm.expect(pm.response.text()).to.eql({js(expect['body_text'])});")
    if "body_json" in expect:
        t("body JSON is exact", f"pm.expect(pm.response.json()).to.eql({js(expect['body_json'])});")
    for path, value in expect.get("json_has", {}).items():
        t(f"json {path} equals {value}", f"pm.expect(_.get(pm.response.json(), {js(path)})).to.eql({js(value)});")
    for needle in expect.get("body_not_contains", []):
        t(f"body does not contain {needle!r}", f"pm.expect(pm.response.text()).to.not.include({js(needle)});")
    for h, v in expect.get("headers_equal", {}).items():
        t(f"header {h} equals {v}", f"pm.expect(pm.response.headers.get({js(h)})).to.eql({resolved(v)});")
    for h, v in expect.get("headers_not_equal", {}).items():
        t(f"header {h} differs from {v}", f"pm.expect(pm.response.headers.get({js(h)})).to.not.eql({resolved(v)});")
    for h in expect.get("headers_present", []):
        t(f"header {h} is present", f"pm.response.to.have.header({js(h)});")
    for h, rx in expect.get("headers_match", {}).items():
        t(
            f"header {h} matches {rx}",
            f"pm.expect(pm.response.headers.get({js(h)}) || '').to.match(new RegExp({js(rx)}, 'i'));",
        )
    saves: list[str] = []
    for var, src in expect.get("save", {}).items():
        if "header" in src:
            saves.append(f"pm.collectionVariables.set({js(var)}, pm.response.headers.get({js(src['header'])}));")
        else:
            saves.append(f"pm.collectionVariables.set({js(var)}, _.get(pm.response.json(), {js(src['json'])}));")

    when = expect.get("when_var")
    if when:
        lines.append(f"if (pm.variables.get({js(when)})) {{")
        lines += ["  " + b for b in body + saves]
        lines.append("} else {")
        lines.append(f"  pm.test({js(f'skipped: {when} not set')}, function () {{ pm.expect(true).to.be.true; }});")
        lines.append("}")
    else:
        lines += body + saves
    return lines


def item(req: dict[str, Any]) -> dict[str, Any]:
    headers = [{"key": k, "value": v} for k, v in req.get("headers", {}).items()]
    body = req.get("body")
    request: dict[str, Any] = {
        "method": req["method"],
        "header": headers,
        "url": {"raw": "{{baseUrl}}" + req["path"], "host": ["{{baseUrl}}"],
                "path": [p for p in req["path"].split("?")[0].split("/") if p],
                **({"query": [{"key": kv.split("=")[0], "value": kv.split("=", 1)[1]} for kv in req["path"].split("?", 1)[1].split("&")]} if "?" in req["path"] else {})},
    }  # fmt: skip
    events: list[dict[str, Any]] = []
    pre: list[str] = []
    for var, template in req.get("pre_set", {}).items():
        pre.append(f"pm.collectionVariables.set({js(var)}, pm.variables.replaceIn({js(template)}));")
    if body:
        if "repeat" in body:
            ch, n = body["repeat"]
            pre.append(f"pm.collectionVariables.set('bigBody', {js(ch)}.repeat({n}));")
            request["body"] = {"mode": "raw", "raw": "{{bigBody}}", "options": {"raw": {"language": "text"}}}
            request["header"] = [{"key": "Content-Type", "value": "text/plain"}, *headers]
        else:
            request["body"] = {"mode": "raw", "raw": json.dumps(body["json"]), "options": {"raw": {"language": "json"}}}
            request["header"] = [{"key": "Content-Type", "value": "application/json"}, *headers]
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
        "name": "AI Assessment Platform - Local",
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
        print("postman files are in sync with spec.py")
        return 0
    for name, text in files.items():
        (HERE / name).write_text(text)
        print("wrote", name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
