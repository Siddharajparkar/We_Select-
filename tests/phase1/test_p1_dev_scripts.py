"""Developer scripts (scripts/dev): config handling, Key Vault pull, secrecy, clear errors. `az` is always mocked."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

DEV = Path(__file__).resolve().parents[2] / "scripts" / "dev"


def _load(name: str) -> ModuleType:
    if str(DEV) not in sys.path:
        sys.path.insert(0, str(DEV))
    spec = importlib.util.spec_from_file_location(f"devscript_{name}", DEV / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"devscript_{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


common = _load("common")
sys.modules["common"] = common  # the scripts import `common` by this name; keep one DevError class
setup = _load("setup")
verify = _load("verify")
run_mod = _load("run")


def fake_runner(stdout: str = "", stderr: str = "", code: int = 0):  # type: ignore[no-untyped-def]
    calls: list[list[str]] = []

    def runner(cmd, **_kw):  # type: ignore[no-untyped-def]
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, code, stdout, stderr)

    runner.calls = calls  # type: ignore[attr-defined]
    return runner


def test_example_config_has_only_placeholders_and_loads_as_incomplete(tmp_path: Path) -> None:
    example = DEV.parents[1] / "config" / "azure.example.env"
    with pytest.raises(common.DevError, match="placeholder"):
        common.load_config(example)


def test_missing_config_says_how_to_fix(tmp_path: Path) -> None:
    with pytest.raises(common.DevError, match="azure.example.env"):
        common.load_config(tmp_path / "nope.env")


def test_filled_config_loads(tmp_path: Path) -> None:
    p = tmp_path / "azure.local.env"
    p.write_text("AZ_RESOURCE_GROUP=rg1\nAZ_KEY_VAULT=kv1\nAZ_SQL_SERVER=sql1\nAZ_APP=assess-api\n", encoding="utf-8")
    assert common.load_config(p)["AZ_KEY_VAULT"] == "kv1"


def test_kv_get_returns_value_and_uses_names_only() -> None:
    runner = fake_runner(stdout="top-secret-value\n")
    assert common.kv_get("kv1", "foundry-key", runner=runner, exe="az") == "top-secret-value"
    assert "foundry-key" in runner.calls[0] and "top-secret-value" not in " ".join(runner.calls[0])


def test_empty_secret_is_a_clear_error() -> None:
    with pytest.raises(common.DevError, match="put_secrets"):
        common.kv_get("kv1", "foundry-key", runner=fake_runner(stdout=""), exe="az")


def test_not_logged_in_and_no_role_have_friendly_messages() -> None:
    with pytest.raises(common.DevError, match="az login"):
        common.run_az(
            ["x"], runner=fake_runner(stderr="ERROR: Please run 'az login' to setup account.", code=1), exe="az"
        )
    with pytest.raises(common.DevError, match="Key Vault Secrets User"):
        common.run_az(
            ["x"], runner=fake_runner(stderr="ERROR: (Forbidden) caller does not have authorization", code=1), exe="az"
        )


def test_error_message_never_contains_the_arguments() -> None:
    with pytest.raises(common.DevError) as info:
        common.run_az(
            ["keyvault", "secret", "set", "--value", "HUNTER2"], runner=fake_runner(stderr="boom", code=1), exe="az"
        )
    assert "HUNTER2" not in str(info.value)


def test_every_secret_maps_to_a_real_setting() -> None:
    from app.config import Settings

    assert len(common.SECRETS) == 9
    for env_name in common.SECRETS.values():
        assert env_name in Settings.model_fields


def test_write_env_local_round_trips(tmp_path: Path) -> None:
    out = tmp_path / ".env.local"
    common.write_env_local({"A": "1", "B": "two"}, out)
    assert common.parse_env_file(out) == {"A": "1", "B": "two"}


def test_developer_settings_use_azure_but_are_not_production() -> None:
    s = common.non_secret_settings({"FOUNDRY_DEPLOYMENT": "dep"})
    assert s["APP_ENV"] == "development" and s["AI_MODE"] == "azure" and s["FOUNDRY_DEPLOYMENT"] == "dep"
    assert s["REPO_BACKEND"] == "sql" and "COOKIE_SECURE" not in s  # same cookie rules as production


def test_setup_check_mode_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = tmp_path / "azure.local.env"
    cfg.write_text("AZ_RESOURCE_GROUP=rg\nAZ_KEY_VAULT=kv\nAZ_SQL_SERVER=s\nAZ_APP=a\n", encoding="utf-8")
    env_local = tmp_path / ".env.local"
    monkeypatch.setattr(setup, "load_config", lambda: common.load_config(cfg))
    monkeypatch.setattr(setup, "run_az", lambda *_a, **_k: "sub")
    monkeypatch.setattr(setup, "check_tools", lambda: [])
    monkeypatch.setattr(setup, "ENV_LOCAL", env_local)
    assert setup.main(["--check"]) == 0
    assert not env_local.exists()
    assert "would write" in capsys.readouterr().out


def test_setup_writes_env_local_without_printing_secret_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = tmp_path / "azure.local.env"
    cfg.write_text("AZ_RESOURCE_GROUP=rg\nAZ_KEY_VAULT=kv\nAZ_SQL_SERVER=s\nAZ_APP=a\n", encoding="utf-8")
    env_local = tmp_path / ".env.local"
    monkeypatch.setattr(setup, "load_config", lambda: common.load_config(cfg))
    monkeypatch.setattr(setup, "run_az", lambda *_a, **_k: "sub")
    monkeypatch.setattr(setup, "check_tools", lambda: [])
    monkeypatch.setattr(setup, "kv_get", lambda _v, name, **_k: f"VALUE-OF-{name}")
    monkeypatch.setattr(setup, "ENV_LOCAL", env_local)
    monkeypatch.setattr(setup, "write_env_local", lambda values: common.write_env_local(values, env_local))
    assert setup.main(["--skip-probes"]) == 0
    written = common.parse_env_file(env_local)
    assert written["FOUNDRY_KEY"] == "VALUE-OF-foundry-key" and written["REPO_BACKEND"] == "sql"
    assert "VALUE-OF" not in capsys.readouterr().out


def test_setup_reports_a_clear_error_when_not_signed_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = tmp_path / "azure.local.env"
    cfg.write_text("AZ_RESOURCE_GROUP=rg\nAZ_KEY_VAULT=kv\nAZ_SQL_SERVER=s\nAZ_APP=a\n", encoding="utf-8")
    monkeypatch.setattr(setup, "load_config", lambda: common.load_config(cfg))
    monkeypatch.setattr(setup, "check_tools", lambda: [])

    def boom(*_a: object, **_k: object) -> str:
        raise common.DevError("You are not signed in to Azure. Run `az login` in this terminal, then retry.")

    monkeypatch.setattr(setup, "run_az", boom)
    assert setup.main(["--check"]) == 2
    assert "az login" in capsys.readouterr().err


def test_verify_builds_the_harness_command() -> None:
    local = verify.build_command("http://127.0.0.1:8080", 6, True)
    assert "--target" in local and local[local.index("--target") + 1] == "local" and "true" in local
    remote = verify.build_command("https://example.invalid", 6, False)
    assert remote[remote.index("--target") + 1] == "azure" and remote[-1] == "false"


def test_run_refuses_without_env_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(run_mod, "ENV_LOCAL", tmp_path / "missing")
    assert run_mod.main([]) == 2
    assert "setup.py" in capsys.readouterr().err


# ── put_secrets / sync_secrets ─────────────────────────────────────────────────────────────────
put_secrets = _load("put_secrets")
sync_secrets = _load("sync_secrets")
CFG = {
    "AZ_RESOURCE_GROUP": "rg",
    "AZ_KEY_VAULT": "kv",
    "AZ_SQL_SERVER": "sqlsrv",
    "AZ_SQL_DB": "db",
    "AZ_APP": "assess-api",
    "AZ_AI_RESOURCE": "ai",
    "AZ_STORAGE": "stor",
    "AZ_ACS": "acs",
    "AZ_APPINSIGHTS": "appi",
    "AZ_APP_IDENTITY": "ident",
    "ACS_SENDER": "DoNotReply@x.azurecomm.net",
}


class Recorder:
    """Pretends to be `az`: records calls, answers with a canned secret-looking value, remembers --file contents."""

    def __init__(self, existing: set[str] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.stored: dict[str, str] = {}
        self.existing = existing or set()

    def __call__(self, cmd, **_kw):  # type: ignore[no-untyped-def]
        self.calls.append(cmd)
        args = cmd[1:]
        if args[:3] == ["keyvault", "secret", "show"]:
            name = args[args.index("--name") + 1]
            return subprocess.CompletedProcess(
                cmd,
                0 if name in self.existing else 1,
                "id" if name in self.existing else "",
                "" if name in self.existing else "not found",
            )
        if args[:3] == ["keyvault", "secret", "set"]:
            self.stored[args[args.index("--name") + 1]] = Path(args[args.index("--file") + 1]).read_text(
                encoding="utf-8"
            )
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if args[:2] == ["identity", "show"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                "/subscriptions/s/resourceGroups/rg/providers/Microsoft.ManagedIdentity/userAssignedIdentities/ident\n",
                "",
            )
        return subprocess.CompletedProcess(cmd, 0, "AZURE-VALUE-" + "-".join(args[:2]) + "\n", "")


@pytest.fixture
def put_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(put_secrets, "load_config", lambda: dict(CFG))
    monkeypatch.setattr(sync_secrets, "load_config", lambda: dict(CFG))


def test_put_secrets_dry_run_touches_nothing(put_env: None, capsys: pytest.CaptureFixture[str]) -> None:
    rec = Recorder()
    assert put_secrets.main([], runner=rec) == 0
    out = capsys.readouterr().out
    assert rec.calls == [] and "DRY RUN" in out and out.count("<-") == 9


def test_put_secrets_apply_requires_signoff(
    put_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text("SIGN-OFF: <not approved>\n", encoding="utf-8")
    monkeypatch.setattr(common, "PLAN_FILE", plan)
    monkeypatch.setattr(put_secrets, "require_signoff", lambda: common.require_signoff(plan))
    rec = Recorder()
    assert put_secrets.main(["--apply"], runner=rec) == 2
    assert rec.calls == [] and "SIGN-OFF" in capsys.readouterr().err


def test_put_secrets_apply_stores_nine_and_never_prints_values(
    put_env: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(put_secrets, "require_signoff", lambda: None)
    n = iter(range(100))

    def counter(_n: int) -> str:
        return f"gen{next(n)}-" + "g" * 40

    rec = Recorder()
    rc = put_secrets.main(["--apply"], runner=rec, ask_password=lambda _p: "S3cretPassw0rd!", token=counter)
    assert rc == 0
    assert set(rec.stored) == set(common.SECRETS)
    assert (
        "Password=S3cretPassw0rd!" in rec.stored["database-url"]
        and "Connection Timeout=90" in rec.stored["database-url"]
    )
    assert len(rec.stored["session-secret"]) >= 32 and len(rec.stored["platform-key"]) >= 32
    assert rec.stored["session-secret"] != rec.stored["platform-key"]
    out = capsys.readouterr()
    assert "S3cretPassw0rd!" not in out.out + out.err and "AZURE-VALUE" not in out.out + out.err
    # values never travel on a command line, and `secret set` output is suppressed
    for call in rec.calls:
        if call[1:4] == ["keyvault", "secret", "set"]:
            assert "--value" not in call and call[-2:] == ["-o", "none"]
            assert "S3cretPassw0rd!" not in " ".join(call)


def test_existing_generated_secrets_are_kept_unless_rotating(put_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(put_secrets, "require_signoff", lambda: None)
    rec = Recorder(existing={"session-secret", "platform-key"})
    put_secrets.main(["--apply"], runner=rec, ask_password=lambda _p: "pw", token=lambda _n: "n" * 43)
    assert "session-secret" not in rec.stored and "platform-key" not in rec.stored
    rec2 = Recorder(existing={"session-secret", "platform-key"})
    put_secrets.main(["--apply", "--rotate"], runner=rec2, ask_password=lambda _p: "pw", token=lambda _n: "n" * 43)
    assert {"session-secret", "platform-key"} <= set(rec2.stored)


def test_unsafe_sql_passwords_are_refused() -> None:
    for bad in ("", "a;b", "a=b", "a{b", 'a"b'):
        with pytest.raises(common.DevError):
            put_secrets.build_database_url("srv", "db", bad)
    assert put_secrets.build_database_url("srv", "db", "ok").startswith("Server=tcp:srv.database.windows.net,1433;")


def test_sync_secrets_uses_key_vault_references_and_short_keys(
    put_env: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert sync_secrets.main([], runner=Recorder()) == 0 and "DRY RUN" in capsys.readouterr().out
    monkeypatch.setattr(sync_secrets, "require_signoff", lambda: None)
    rec = Recorder()
    assert sync_secrets.main(["--apply"], runner=rec) == 0
    setcall = next(c for c in rec.calls if c[1:3] == ["containerapp", "secret"])
    pairs = setcall[setcall.index("--secrets") + 1 : -2]
    assert len(pairs) == 9
    for pair in pairs:
        key, _, ref = pair.partition("=")
        assert (
            len(key) <= 20
            and ref.startswith("keyvaultref:https://kv.vault.azure.net/secrets/")
            and ",identityref:/subscriptions/" in ref
        )


# ── provision.py ───────────────────────────────────────────────────────────────────────────────
provision = _load("provision")
PCFG = {
    **CFG,
    "AZ_LOCATION": "eastus",
    "AZ_ACR": "acr1",
    "AZ_CAE": "cae1",
    "AZ_DEPLOY_IDENTITY": "dep",
    "AZ_STORAGE": "stor",
    "BLOB_CONTAINER": "jd-files",
}


class FakeAz:
    """`az` stand-in: every command succeeds unless it starts with one of the `missing` prefixes (resource not found)."""

    def __init__(self, missing: tuple[str, ...] = ()) -> None:
        self.missing = missing
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **_kw):  # type: ignore[no-untyped-def]
        self.calls.append(cmd[1:])
        line = " ".join(cmd[1:])
        if any(line.startswith(m) for m in self.missing):
            return subprocess.CompletedProcess(cmd, 1, "", "ERROR: (ResourceNotFound) not found")
        if line.startswith("storage container exists"):
            return subprocess.CompletedProcess(cmd, 0, '{"exists": false}', "")
        if "role assignment list" in line:
            return subprocess.CompletedProcess(cmd, 0, "", "")  # no existing assignment
        return subprocess.CompletedProcess(cmd, 0, "SOME-ID\n", "")

    def writes(self) -> list[list[str]]:
        return [c for c in self.calls if c[-2:] == ["-o", "none"]]


@pytest.fixture
def pcfg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provision, "load_config", lambda: dict(PCFG))


def test_provision_dry_run_writes_nothing(pcfg: None, capsys: pytest.CaptureFixture[str]) -> None:
    az = FakeAz(missing=("keyvault show",))
    assert provision.main(["keyvault"], runner=az) == 0
    assert az.writes() == [] and "WOULD" in capsys.readouterr().out


def test_provision_apply_without_signoff_is_refused(
    pcfg: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text("SIGN-OFF: <not approved>\n", encoding="utf-8")
    monkeypatch.setattr(provision, "require_signoff", lambda: common.require_signoff(plan))
    az = FakeAz(missing=("keyvault show",))
    assert provision.main(["keyvault", "--apply"], runner=az) == 2
    assert az.writes() == [] and "SIGN-OFF" in capsys.readouterr().err


def test_provision_skips_what_already_exists(pcfg: None, capsys: pytest.CaptureFixture[str]) -> None:
    az = FakeAz()
    assert provision.main(["keyvault", "--apply"], runner=az) == 0
    assert az.writes() == [] and "nothing to do" in capsys.readouterr().out


step_cmd = {"keyvault": "keyvault", "storage": "storage account", "registry": "acr", "environment": "containerapp env"}


@pytest.mark.parametrize("step", ["keyvault", "storage", "registry", "environment"])
def test_created_resources_are_tagged_and_in_the_configured_region(
    pcfg: None, monkeypatch: pytest.MonkeyPatch, step: str
) -> None:
    monkeypatch.setattr(provision, "require_signoff", lambda: None)
    az = FakeAz(missing=(f"{step_cmd[step]} show",))
    assert provision.main([step, "--apply"], runner=az) == 0
    (cmd,) = az.writes()
    assert "project=ai-assessment" in cmd and "env=mvp" in cmd and cmd[cmd.index("-l") + 1] == "eastus"


def test_key_vault_is_rbac_mode_and_storage_is_private(pcfg: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provision, "require_signoff", lambda: None)
    kv, st = FakeAz(missing=("keyvault show",)), FakeAz(missing=("storage account show",))
    provision.main(["keyvault", "--apply"], runner=kv)
    provision.main(["storage", "--apply"], runner=st)
    kvc, stc = kv.writes()[0], st.writes()[0]
    assert kvc[kvc.index("--enable-rbac-authorization") + 1] == "true"
    assert stc[stc.index("--allow-blob-public-access") + 1] == "false" and "Standard_LRS" in stc


def test_container_app_is_small_single_replica_with_placeholder_image(
    pcfg: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(provision, "require_signoff", lambda: None)
    az = FakeAz(missing=("containerapp show",))
    assert provision.main(["app", "--apply"], runner=az) == 0
    cmd = az.writes()[0]
    assert cmd[cmd.index("--cpu") + 1] == "0.25" and cmd[cmd.index("--memory") + 1] == "0.5Gi"
    assert cmd[cmd.index("--min-replicas") + 1] == "1" and cmd[cmd.index("--max-replicas") + 1] == "1"
    assert cmd[cmd.index("--image") + 1].startswith("mcr.microsoft.com/")  # no real registry name in code
    assert "--user-assigned" in cmd


def test_environment_skips_log_analytics_to_save_cost(pcfg: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provision, "require_signoff", lambda: None)
    az = FakeAz(missing=("containerapp env show",))
    provision.main(["environment", "--apply"], runner=az)
    cmd = az.writes()[0]
    assert cmd[cmd.index("--logs-destination") + 1] == "none" and "--logs-workspace-key" not in cmd


def test_role_assignments_are_least_privilege(pcfg: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provision, "require_signoff", lambda: None)
    app_az, dep_az = FakeAz(), FakeAz()
    provision.main(["roles-app", "--apply"], runner=app_az)
    provision.main(["roles-deploy", "--apply"], runner=dep_az)
    app_roles = {c[c.index("--role") + 1] for c in app_az.writes()}
    dep_roles = {c[c.index("--role") + 1] for c in dep_az.writes()}
    assert app_roles == {"AcrPull", "Key Vault Secrets User"}
    assert dep_roles == {"AcrPush", "Contributor"}
    for w in app_az.writes() + dep_az.writes():
        assert w[w.index("--role") + 1] not in ("Owner", "User Access Administrator")


def test_no_real_names_in_the_example_config() -> None:
    text = (DEV.parents[1] / "config" / "azure.example.env").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line and not line.startswith("#"):
            value = line.partition("=")[2]
            assert value.startswith("<") or value in ("eastus", "assess-api", "Phi-4-mini-instruct", "v1", "jd-files")


def test_container_app_yaml_secret_keys_match_the_sync_script_and_fit_20_chars() -> None:
    import yaml

    doc = yaml.safe_load((DEV.parents[1] / "infra" / "azure" / "assess-api.containerapp.yaml").read_text())
    env = doc["properties"]["template"]["containers"][0]["env"]
    refs = {e["secretRef"] for e in env if "secretRef" in e}
    assert refs == {common.app_secret_key(n) for n in common.SECRETS}
    assert all(len(r) <= 20 for r in refs)
    names = {e["name"] for e in env}
    assert {"APP_BASE_URL", "API_INTERNAL_URL", "BLOB_CONTAINER"} <= names


def test_config_file_with_a_windows_bom_still_parses(tmp_path: Path) -> None:
    p = tmp_path / "azure.local.env"
    p.write_bytes(b"\xef\xbb\xbfAZ_RESOURCE_GROUP=rg\nAZ_KEY_VAULT=kv\nAZ_SQL_SERVER=s\nAZ_APP=a\n")
    assert common.load_config(p)["AZ_RESOURCE_GROUP"] == "rg"


def test_az_arguments_never_contain_cmd_exe_metacharacters() -> None:
    """Regression: `--query length(@)` broke on Windows (az is a .cmd file). Every command the scripts build is safe."""
    steps_az = []
    for step in provision.STEPS:
        fake = FakeAz(
            missing=("keyvault show", "storage account show", "acr show", "containerapp env show", "containerapp show")
        )
        monkey_cfg = dict(PCFG)
        ctx = provision.Ctx(monkey_cfg, fake)
        try:
            provision.STEPS[step](ctx)
        except common.DevError:
            pass
        steps_az += fake.calls
    assert steps_az
    for call in steps_az:
        for arg in call:
            assert not any(ch in arg for ch in common.CMD_UNSAFE), (call, arg)


def test_run_az_refuses_unsafe_arguments_for_cmd_files() -> None:
    with pytest.raises(common.DevError, match="cmd.exe"):
        common.run_az(["x", "--query", "length(@)"], runner=fake_runner(), exe="C:/cli/az.cmd")
    # a real exe (macOS/Linux) is not affected
    assert common.run_az(["x", "--query", "length(@)"], runner=fake_runner(stdout="1"), exe="/usr/bin/az") == "1"


def test_sql_firewall_step_opens_only_this_laptops_ip(pcfg: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provision, "require_signoff", lambda: None)
    az = FakeAz(missing=("sql server firewall-rule show",))
    assert provision.main(["sql-firewall", "--apply"], runner=az, ip_provider=lambda: "203.0.113.7") == 0
    (cmd,) = az.writes()
    assert cmd[cmd.index("--start-ip-address") + 1] == "203.0.113.7" == cmd[cmd.index("--end-ip-address") + 1]
    assert cmd[cmd.index("-n") + 1] == "dev-203-0-113-7"
    again = FakeAz()
    provision.main(["sql-firewall", "--apply"], runner=again, ip_provider=lambda: "203.0.113.7")
    assert again.writes() == []


def test_verify_hands_the_platform_key_to_the_harness_without_printing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / ".env.local"
    f.write_text("PLATFORM_KEY=real-looking-key-value-0123456789abcdef\nOTHER=1\n", encoding="utf-8")
    env = verify.harness_env(f, base={"PATH": "x"})
    assert env["E2E_PLATFORM_KEY"] == "real-looking-key-value-0123456789abcdef"
    assert verify.harness_env(f, base={"E2E_PLATFORM_KEY": "explicit"})["E2E_PLATFORM_KEY"] == "explicit"
    assert "E2E_PLATFORM_KEY" not in verify.harness_env(tmp_path / "missing", base={})
    assert "real-looking" not in capsys.readouterr().out
