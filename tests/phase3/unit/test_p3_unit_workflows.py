"""Phase 3 unit: GitHub Actions workflows - structure, gating and safety rules (parsed YAML)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
WF = REPO / ".github" / "workflows"
ALL = sorted(p.name for p in WF.glob("*.yml"))


def load(name: str) -> dict[str, Any]:
    data = yaml.safe_load((WF / name).read_text())
    if True in data and "on" not in data:  # YAML 1.1 parses the key `on` as boolean True
        data["on"] = data.pop(True)
    return data  # type: ignore[no-any-return]


def steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return job["steps"]  # type: ignore[no-any-return]


def run_text(job: dict[str, Any]) -> str:
    return "\n".join(str(s.get("run", "")) for s in steps(job))


def test_expected_workflows_exist() -> None:
    assert {"deploy.yml", "live-e2e.yml", "nightly.yml", "rollback.yml", "load-test.yml"} <= set(ALL)


@pytest.mark.parametrize("name", ALL)
def test_no_node_or_npm_anywhere(name: str) -> None:
    text = (WF / name).read_text().lower()
    for banned in ("setup-node", "npm ci", "npm run", "npm audit", "node-version", "run.mjs", "package-lock"):
        assert banned not in text, f"{name} still references {banned}"


@pytest.mark.parametrize("name", ALL)
def test_actions_are_pinned_to_a_version_and_no_pull_request_target(name: str) -> None:
    text = (WF / name).read_text()
    assert "pull_request_target" not in text
    for use in re.findall(r"uses:\s*(\S+)", text):
        assert "@" in use, f"{use} must be pinned"
        assert not re.search(r"@(main|master|latest)$", use), f"{use} must not float"


@pytest.mark.parametrize("name", ALL)
def test_workflows_default_to_read_only_token(name: str) -> None:
    wf = load(name)
    top = wf.get("permissions")
    job_perms = [j.get("permissions") for j in wf["jobs"].values()]
    assert top == {"contents": "read"} or all(
        p is not None for p in job_perms
    ), f"{name}: set least-privilege permissions"


def test_deploy_triggers_cover_branches_prs_and_manual() -> None:
    on = load("deploy.yml")["on"]
    assert set(on["push"]["branches"]) >= {"main", "phase/**", "feature/**"}
    assert on["pull_request"]["branches"] == ["main"] and "workflow_dispatch" in on


def test_deploy_job_graph_and_gating() -> None:
    wf = load("deploy.yml")
    assert set(wf["jobs"]) == {"fast", "container", "security", "deploy"}
    deploy = wf["jobs"]["deploy"]
    assert set(deploy["needs"]) == {"fast", "container", "security"}
    cond = deploy["if"]
    assert "refs/heads/main" in cond and "push" in cond and "vars.AZURE_DEPLOY_ENABLED == 'true'" in cond
    assert deploy["permissions"] == {"id-token": "write", "contents": "read"}


def test_concurrency_never_cancels_main() -> None:
    c = load("deploy.yml")["concurrency"]
    assert "github.ref" in c["group"]
    assert "refs/heads/main" in c["cancel-in-progress"] and "!=" in c["cancel-in-progress"]


def test_fast_gate_runs_python_quality_tools_and_tests() -> None:
    fast = load("deploy.yml")["jobs"]["fast"]
    text = run_text(fast)
    for needle in ("ruff check", "ruff format --check", "mypy app", "pytest tests", "shellcheck", "run-plan.sh"):
        assert needle in text, needle
    assert any(s.get("uses", "").startswith("actions/setup-python@v5") for s in steps(fast))
    assert "pip install -r api/requirements-dev.txt" in text


def test_container_job_uses_sql_server_2022_azurite_and_masks_secrets() -> None:
    job = load("deploy.yml")["jobs"]["container"]
    text = run_text(job)
    assert "mcr.microsoft.com/mssql/server:2022" in text and "azure-storage/azurite" in text
    assert text.count("::add-mask::") >= 3
    assert "prepare_sql.py" in text and "app.migrations.runner" in text and "(none pending)" in text
    assert "docker build" in text and "--build-arg GIT_SHA" in text
    assert any("trivy-action" in s.get("uses", "") for s in steps(job))
    assert not re.search(
        r"MSSQL_SA_PASSWORD=[A-Za-z0-9!]{6,}", (WF / "deploy.yml").read_text()
    ), "no committed SA password"


def test_security_job_scans_secrets_and_dependencies() -> None:
    sec = load("deploy.yml")["jobs"]["security"]
    assert any("gitleaks" in s.get("uses", "") for s in steps(sec))
    assert "pip-audit" in run_text(sec)


def test_deploy_steps_order_and_safety() -> None:
    steps_ = steps(load("deploy.yml")["jobs"]["deploy"])
    names = [s.get("name", "") for s in steps_]
    idx = {
        k: next(i for i, n in enumerate(names) if k in n)
        for k in (
            "Azure login",
            "Record current image",
            "ingress",
            "Build and push",
            "Update Container App",
            "Smoke",
            "Roll back",
        )
    }
    assert (
        idx["Azure login"]
        < idx["Record current image"]
        < idx["ingress"]
        < idx["Build and push"]
        < idx["Update Container App"]
        < idx["Smoke"]
        < idx["Roll back"]
    )
    login = steps_[idx["Azure login"]]
    assert login["uses"].startswith("azure/login@v2")
    assert set(login["with"]) == {"client-id", "tenant-id", "subscription-id"}
    assert all("secrets." in v for v in login["with"].values())
    text = run_text(load("deploy.yml")["jobs"]["deploy"])
    assert "--target-port 8080" in text, "ingress target port must be fixed BEFORE the image update"
    assert "${GITHUB_SHA}" in text and ":latest" not in text
    assert "GIT_SHA=" in text
    smoke = steps_[idx["Smoke"]]
    assert smoke["env"]["EXPECTED_VERSION"] == "${{ github.sha }}"
    assert steps_[idx["Roll back"]]["if"].startswith("failure()")


def test_no_credentials_in_any_workflow() -> None:
    for name in ALL:
        text = (WF / name).read_text()
        assert not re.search(r"(client-secret|AZURE_CREDENTIALS|--password|-p\s+\S+\s+-u)", text), name
        assert "secrets.AZURE_CLIENT_SECRET" not in text


def test_live_e2e_uses_python_harness() -> None:
    wf = load("live-e2e.yml")
    text = run_text(wf["jobs"]["live-e2e"])
    assert "python scripts/e2e/run.py" in text and "--expected-version" in text
    assert set(wf["on"]["workflow_dispatch"]["inputs"]) >= {"base_url", "upto_phase", "expected_version"}


def test_azure_touching_workflows_are_gated_and_oidc_enabled() -> None:
    for name in ("rollback.yml", "nightly.yml"):
        wf = load(name)
        gated = [j for j in wf["jobs"].values() if "azure/login" in str(j)]
        assert gated, name
        for job in gated:
            assert job["if"] == "vars.AZURE_DEPLOY_ENABLED == 'true'"
            assert job["permissions"]["id-token"] == "write"


def test_nightly_runs_python_tests_on_schedule() -> None:
    wf = load("nightly.yml")
    assert wf["on"]["schedule"][0]["cron"] == "0 2 * * *"
    assert "pytest tests" in run_text(wf["jobs"]["nightly-fast"])


def test_load_test_has_no_stress_profile() -> None:
    wf = load("load-test.yml")
    assert wf["on"]["workflow_dispatch"]["inputs"]["profile"]["options"] == ["target"]
