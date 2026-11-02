"""Phase 3 unit: the three Postman files are valid v2.1 collections and in sync with spec.py."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

POSTMAN = Path(__file__).resolve().parents[1] / "postman"
sys.path.insert(0, str(POSTMAN))
import generate  # noqa: E402
import run_collection  # noqa: E402
import spec  # noqa: E402


def test_exactly_three_collections_plus_environment_exist() -> None:
    files = sorted(p.name for p in POSTMAN.glob("*.json"))
    assert files == [
        "AssessPlatform_Local.postman_environment.json",
        "AssessPlatform_Phase3_E2E.postman_collection.json",
        "AssessPlatform_Phase3_Integration.postman_collection.json",
        "AssessPlatform_Phase3_Unit.postman_collection.json",
    ]


def test_committed_files_are_in_sync_with_the_spec() -> None:
    for name, text in generate.render().items():
        assert (POSTMAN / name).read_text() == text, f"{name} is stale: run `python tests/phase3/postman/generate.py`"


@pytest.mark.parametrize("key", list(spec.COLLECTIONS))
def test_collection_is_valid_postman_v21(key: str) -> None:
    fname, src = spec.COLLECTIONS[key]
    c = json.loads((POSTMAN / fname).read_text())
    assert c["info"]["schema"] == "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    assert c["info"]["name"] == src["name"] and c["info"]["description"]
    assert len(c["item"]) == len(src["items"]) >= 7
    assert {v["key"] for v in c["variable"]} == set(spec.DEFAULT_VARIABLES)
    for it in c["item"]:
        req = it["request"]
        assert req["method"] in {"GET", "POST", "DELETE", "PUT", "PATCH", "HEAD"}
        assert req["url"]["raw"].startswith("{{baseUrl}}/api/v1/")
        test = next(e for e in it["event"] if e["listen"] == "test")
        script = "\n".join(test["script"]["exec"])
        assert "pm.test(" in script, it["name"]
        assert test["script"]["type"] == "text/javascript"


@pytest.mark.parametrize("key", list(spec.COLLECTIONS))
def test_every_expectation_became_a_pm_test(key: str) -> None:
    fname, src = spec.COLLECTIONS[key]
    c = json.loads((POSTMAN / fname).read_text())
    for req, it in zip(src["items"], c["item"], strict=True):
        exp = req["expect"]
        want = (
            int("status" in exp) + int("body_text" in exp) + int("body_json" in exp)
            + len(exp.get("json_has", {})) + len(exp.get("body_not_contains", []))
            + len(exp.get("headers_equal", {})) + len(exp.get("headers_not_equal", {}))
            + len(exp.get("headers_present", [])) + len(exp.get("headers_match", {}))
        )  # fmt: skip
        script = "\n".join(next(e for e in it["event"] if e["listen"] == "test")["script"]["exec"])
        got = len(re.findall(r"pm\.test\(", script))
        assert got == want + (1 if exp.get("when_var") else 0), (req["name"], got, want)


def test_big_bodies_are_generated_in_the_sandbox_not_stored() -> None:
    for fname, _ in spec.COLLECTIONS.values():
        assert (POSTMAN / fname).stat().st_size < 50_000
    text = (POSTMAN / "AssessPlatform_Phase3_Unit.postman_collection.json").read_text()
    assert ".repeat(1100000)" in text


def test_environment_file_has_the_tunable_variables() -> None:
    env = json.loads((POSTMAN / spec.ENVIRONMENT_FILE).read_text())
    keys = {v["key"] for v in env["values"]}
    assert keys == {"baseUrl", "expectedVersion", "docsStatus"}


def test_no_secrets_or_real_hosts_in_postman_files() -> None:
    for p in POSTMAN.glob("*.json"):
        text = p.read_text()
        assert "azurecontainerapps.io" not in text and "database.windows.net" not in text
        assert not re.search(r"(?i)(api[-_]?key|password|bearer)\s*\"?\s*:\s*\"[A-Za-z0-9]{8,}", text)


def test_variable_substitution_in_the_python_runner() -> None:
    out = run_collection.substitute("{{baseUrl}}/x/{{missing}}/{{$guid}}", {"baseUrl": "http://h"})
    assert out.startswith("http://h/x//") and re.search(r"[0-9a-f-]{36}$", out)
