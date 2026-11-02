"""Phase 6 unit: the Phase 4-6 Postman collections are valid v2.1, in sync with spec46.py, and the spec is executable."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

POSTMAN = Path(__file__).resolve().parents[1] / "postman"
sys.path.insert(0, str(POSTMAN))
import generate46  # noqa: E402
import run46  # noqa: E402
import spec46  # noqa: E402


def test_three_collections_and_an_environment_exist() -> None:
    assert sorted(p.name for p in POSTMAN.glob("*.json")) == [
        "AssessPlatform_Phase4to6_E2E.postman_collection.json",
        "AssessPlatform_Phase4to6_Integration.postman_collection.json",
        "AssessPlatform_Phase4to6_Local.postman_environment.json",
        "AssessPlatform_Phase4to6_Unit.postman_collection.json",
    ]


def test_committed_files_are_in_sync_with_the_spec() -> None:
    for name, text in generate46.render().items():
        assert (POSTMAN / name).read_text() == text, f"{name} is stale: run `python tests/phase6/postman/generate46.py`"


@pytest.mark.parametrize("key", list(spec46.COLLECTIONS))
def test_collection_is_valid_postman_v21_with_tests_on_every_request(key: str) -> None:
    fname, src = spec46.COLLECTIONS[key]
    c = json.loads((POSTMAN / fname).read_text())
    assert c["info"]["schema"].endswith("/v2.1.0/collection.json") and c["info"]["description"]
    assert len(c["item"]) == len(src["items"]) >= 10
    assert {v["key"] for v in c["variable"]} == set(spec46.DEFAULT_VARIABLES)
    for it in c["item"]:
        assert it["request"]["url"]["raw"].startswith("{{baseUrl}}/api/v1/")
        script = "\n".join(next(e for e in it["event"] if e["listen"] == "test")["script"]["exec"])
        assert "pm.test(" in script, it["name"]


def test_no_secret_values_are_committed() -> None:
    text = "".join(p.read_text() for p in POSTMAN.glob("*.json"))
    assert "dev-only-platform-key" in text  # the documented local default only
    for forbidden in ("sk-", "AccountKey=", "api-key", "BEGIN PRIVATE KEY"):
        assert forbidden not in text


def test_wait_steps_use_a_variable_not_a_hard_coded_delay() -> None:
    text = (POSTMAN / "AssessPlatform_Phase4to6_E2E.postman_collection.json").read_text()
    assert 'pm.variables.get(\\"waitSeconds\\")' in text or "pm.variables.get(" in text


def test_runner_helpers() -> None:
    assert run46.dotted([{"id": "x"}], "0.id") == "x" and run46.dotted({"a": {"b": 2}}, "a.b") == 2
    assert run46.dotted([], "0.id") is None and run46.dotted({"a": 1}, "") == {"a": 1}
    v = {"x": "1"}
    assert run46.substitute("a{{x}}b{{missing}}", v) == "a1b"
    assert len(run46.substitute("{{$guid}}", v)) == 36


@pytest.mark.parametrize("key", list(spec46.COLLECTIONS))
def test_spec_passes_against_the_in_process_app(key: str, tmp_path: Path) -> None:
    """Run each collection through the Python runner against a real local server."""
    import httpx

    from conftest import start_server, wait_ready

    proc, base = start_server({"JOB_TICK_SECONDS": "0.2"})
    try:
        wait_ready(base, proc)
        rep = run46.run(key, base, {"waitSeconds": "1.5"}, httpx.Client(timeout=30.0))
        assert not rep.failed, rep.failed
        assert len(rep.results) >= 30
    finally:
        proc.terminate()
        proc.wait(timeout=15)
