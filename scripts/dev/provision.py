#!/usr/bin/env python3
"""Create the Azure resources of docs/PROVISIONING_PLAN.md, one step at a time. Idempotent; dry run by default.

    python scripts/dev/provision.py <step> [--apply]

Steps (run in this order, verify each before the next):
    keyvault  storage  container  registry  environment  identities  roles-owner  roles-app  app  registry-link
    roles-deploy  sql-firewall  oidc

``--apply`` needs the human SIGN-OFF line in the plan. A step whose resource already exists is skipped. Nothing here
prints a key or connection string. Everything created is tagged project=ai-assessment env=mvp.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DevError, Runner, load_config, public_ip, require_signoff, run_az

TAGS = ["project=ai-assessment", "env=mvp"]
PLACEHOLDER_IMAGE = "mcr.microsoft.com/k8se/quickstart:latest"  # public; replaced by the pipeline's first deploy


class Ctx:
    def __init__(self, cfg: dict[str, str], runner: Runner, ip_provider: Callable[[], str] = public_ip) -> None:
        self.cfg, self.runner, self.ip_provider = cfg, runner, ip_provider
        self.rg = cfg["AZ_RESOURCE_GROUP"]
        self.loc = cfg.get("AZ_LOCATION", "eastus")

    def az(self, args: list[str]) -> str:
        return run_az(args, runner=self.runner)

    def exists(self, args: list[str]) -> bool:
        try:
            self.az(args)
            return True
        except DevError:
            return False

    def need(self, key: str) -> str:
        value = self.cfg.get(key, "")
        if not value or value.startswith("<"):
            raise DevError(f"{key} is not set in config/azure.local.env")
        return value

    def ident(self, key: str, field: str) -> str:
        return self.az(["identity", "show", "-g", self.rg, "-n", self.need(key), "--query", field, "-o", "tsv"]).strip()

    def resource_id(self, args: list[str]) -> str:
        return self.az([*args, "--query", "id", "-o", "tsv"]).strip()


Action = tuple[str, list[str]]  # (description, az args)


def _keyvault(c: Ctx) -> list[Action]:
    n = c.need("AZ_KEY_VAULT")
    if c.exists(["keyvault", "show", "-n", n, "-g", c.rg, "--query", "id", "-o", "tsv"]):
        return []
    return [
        (f"create Key Vault {n} (RBAC mode, soft delete 7 days)",
         ["keyvault", "create", "-g", c.rg, "-n", n, "-l", c.loc, "--sku", "standard",
          "--enable-rbac-authorization", "true", "--retention-days", "7", "--tags", *TAGS]),
    ]  # fmt: skip


def _storage(c: Ctx) -> list[Action]:
    n = c.need("AZ_STORAGE")
    if c.exists(["storage", "account", "show", "-g", c.rg, "-n", n, "--query", "id", "-o", "tsv"]):
        return []
    return [
        (f"create storage account {n} (Standard_LRS, no public blob access, TLS 1.2)",
         ["storage", "account", "create", "-g", c.rg, "-n", n, "-l", c.loc, "--sku", "Standard_LRS",
          "--kind", "StorageV2", "--allow-blob-public-access", "false", "--min-tls-version", "TLS1_2",
          "--tags", *TAGS]),
    ]  # fmt: skip


def _container(c: Ctx) -> list[Action]:
    n, name = c.need("AZ_STORAGE"), c.cfg.get("BLOB_CONTAINER", "jd-files")
    out = c.az(["storage", "container", "exists", "--account-name", n, "--name", name, "--auth-mode", "key"])
    if json.loads(out or "{}").get("exists"):
        return []
    return [
        (f"create private container {name}",
         ["storage", "container", "create", "--account-name", n, "--name", name, "--public-access", "off",
          "--auth-mode", "key"]),
    ]  # fmt: skip


def _registry(c: Ctx) -> list[Action]:
    n = c.need("AZ_ACR")
    if c.exists(["acr", "show", "-g", c.rg, "-n", n, "--query", "id", "-o", "tsv"]):
        return []
    return [
        (f"create container registry {n} (Basic, admin user disabled)",
         ["acr", "create", "-g", c.rg, "-n", n, "-l", c.loc, "--sku", "Basic", "--admin-enabled", "false",
          "--tags", *TAGS]),
    ]  # fmt: skip


def _environment(c: Ctx) -> list[Action]:
    n = c.need("AZ_CAE")
    if c.exists(["containerapp", "env", "show", "-g", c.rg, "-n", n, "--query", "id", "-o", "tsv"]):
        return []
    return [
        (f"create Container Apps environment {n} (Consumption, no Log Analytics: telemetry goes to Application Insights)",
         ["containerapp", "env", "create", "-g", c.rg, "-n", n, "-l", c.loc, "--logs-destination", "none",
          "--enable-workload-profiles", "false", "--tags", *TAGS]),
    ]  # fmt: skip


def _identities(c: Ctx) -> list[Action]:
    acts: list[Action] = []
    for key in ("AZ_APP_IDENTITY", "AZ_DEPLOY_IDENTITY"):
        n = c.need(key)
        if not c.exists(["identity", "show", "-g", c.rg, "-n", n, "--query", "id", "-o", "tsv"]):
            acts.append(
                (
                    f"create user-assigned identity {n}",
                    ["identity", "create", "-g", c.rg, "-n", n, "-l", c.loc, "--tags", *TAGS],
                )
            )
    return acts


def _assign(c: Ctx, principal_id: str, ptype: str, role: str, scope: str, why: str) -> list[Action]:
    # No parentheses in --query: on Windows az is a .cmd file and cmd.exe breaks on an unquoted ")".
    have = c.az(
        ["role", "assignment", "list", "--assignee", principal_id, "--role", role, "--scope", scope,
         "--query", "[].id", "-o", "tsv"]
    ).strip()  # fmt: skip
    if have:
        return []
    return [
        (f"{role}: {why}",
         ["role", "assignment", "create", "--assignee-object-id", principal_id,
          "--assignee-principal-type", ptype, "--role", role, "--scope", scope]),
    ]  # fmt: skip


def _roles_owner(c: Ctx) -> list[Action]:
    me = c.az(["ad", "signed-in-user", "show", "--query", "id", "-o", "tsv"]).strip()
    kv = c.resource_id(["keyvault", "show", "-g", c.rg, "-n", c.need("AZ_KEY_VAULT")])
    return _assign(c, me, "User", "Key Vault Secrets Officer", kv, "you can store the app secrets")


def _roles_app(c: Ctx) -> list[Action]:
    pid = c.ident("AZ_APP_IDENTITY", "principalId")
    acr = c.resource_id(["acr", "show", "-g", c.rg, "-n", c.need("AZ_ACR")])
    kv = c.resource_id(["keyvault", "show", "-g", c.rg, "-n", c.need("AZ_KEY_VAULT")])
    return _assign(c, pid, "ServicePrincipal", "AcrPull", acr, "the app pulls its image") + _assign(
        c, pid, "ServicePrincipal", "Key Vault Secrets User", kv, "the app reads Key Vault references"
    )


def _app(c: Ctx) -> list[Action]:
    n = c.need("AZ_APP")
    if c.exists(["containerapp", "show", "-g", c.rg, "-n", n, "--query", "id", "-o", "tsv"]):
        return []
    ident = c.ident("AZ_APP_IDENTITY", "id")
    return [
        (f"create Container App {n} from a public placeholder image (0.25 vCPU / 0.5 GiB, exactly 1 replica)",
         ["containerapp", "create", "-g", c.rg, "-n", n, "--environment", c.need("AZ_CAE"),
          "--image", PLACEHOLDER_IMAGE, "--ingress", "external", "--target-port", "80",
          "--cpu", "0.25", "--memory", "0.5Gi", "--min-replicas", "1", "--max-replicas", "1",
          "--user-assigned", ident, "--tags", *TAGS]),
    ]  # fmt: skip


def _registry_link(c: Ctx) -> list[Action]:
    ident = c.ident("AZ_APP_IDENTITY", "id")
    server = f"{c.need('AZ_ACR')}.azurecr.io"
    return [
        (f"let the app pull from {server} with its identity",
         ["containerapp", "registry", "set", "-g", c.rg, "-n", c.need("AZ_APP"), "--server", server,
          "--identity", ident]),
    ]  # fmt: skip


def _roles_deploy(c: Ctx) -> list[Action]:
    pid = c.ident("AZ_DEPLOY_IDENTITY", "principalId")
    acr = c.resource_id(["acr", "show", "-g", c.rg, "-n", c.need("AZ_ACR")])
    app = c.resource_id(["containerapp", "show", "-g", c.rg, "-n", c.need("AZ_APP")])
    return _assign(c, pid, "ServicePrincipal", "AcrPush", acr, "the pipeline pushes images") + _assign(
        c, pid, "ServicePrincipal", "Contributor", app, "the pipeline updates the assess-api app only"
    )


def _sql_firewall(c: Ctx) -> list[Action]:
    ip = c.ip_provider()
    name = "dev-" + ip.replace(".", "-")
    server = c.need("AZ_SQL_SERVER")
    if c.exists(
        ["sql", "server", "firewall-rule", "show", "-g", c.rg, "-s", server, "-n", name, "--query", "name", "-o", "tsv"]
    ):
        return []
    return [
        (f"allow this laptop ({ip}) to reach the SQL server",
         ["sql", "server", "firewall-rule", "create", "-g", c.rg, "-s", server, "-n", name,
          "--start-ip-address", ip, "--end-ip-address", ip]),
    ]  # fmt: skip


ISSUER = "https://token.actions.githubusercontent.com"
AUDIENCE = "api://AzureADTokenExchange"


def _oidc(c: Ctx) -> list[Action]:
    """GitHub Actions federated credentials for the deploy identity: the main branch and the production environment.

    The deploy job runs in the `production` environment (subject ...:environment:production); rollback and nightly
    run from main without an environment (subject ...:ref:refs/heads/main). Both are needed.

    GitHub may qualify the owner and repository with their numeric ids in the token subject, for example
    ``repo:<owner>@<id>/<repo>@<id>:environment:production`` (the failed login prints the exact subject). Set
    GITHUB_SUBJECT_REPO in config/azure.local.env to ``<owner>@<id>/<repo>@<id>`` to create credentials for that form too.
    """
    ident = c.need("AZ_DEPLOY_IDENTITY")
    forms = {"": c.need("GITHUB_REPO")}
    subject_repo = c.cfg.get("GITHUB_SUBJECT_REPO", "")
    if subject_repo and not subject_repo.startswith("<"):
        forms["-id"] = subject_repo
    wanted: dict[str, str] = {}
    for suffix, repo in forms.items():
        wanted[f"gh-main-branch{suffix}"] = f"repo:{repo}:ref:refs/heads/main"
        wanted[f"gh-env-production{suffix}"] = f"repo:{repo}:environment:production"
    acts: list[Action] = []
    for name, subject in wanted.items():
        if c.exists(["identity", "federated-credential", "show", "-g", c.rg, "--identity-name", ident, "-n", name,
                     "--query", "name", "-o", "tsv"]):  # fmt: skip
            continue
        acts.append(
            (f"trust GitHub Actions subject {subject}",
             ["identity", "federated-credential", "create", "-g", c.rg, "--identity-name", ident, "-n", name,
              "--issuer", ISSUER, "--subject", subject, "--audiences", AUDIENCE])
        )  # fmt: skip
    return acts


STEPS: dict[str, Callable[[Ctx], list[Action]]] = {
    "keyvault": _keyvault,
    "storage": _storage,
    "container": _container,
    "registry": _registry,
    "environment": _environment,
    "identities": _identities,
    "roles-owner": _roles_owner,
    "roles-app": _roles_app,
    "app": _app,
    "registry-link": _registry_link,
    "roles-deploy": _roles_deploy,
    "sql-firewall": _sql_firewall,
    "oidc": _oidc,
}


def main(
    argv: list[str] | None = None, *, runner: Runner = subprocess.run, ip_provider: Callable[[], str] = public_ip
) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("step", choices=list(STEPS))
    ap.add_argument("--apply", action="store_true", help="perform the changes (default: dry run)")
    args = ap.parse_args(argv)
    try:
        c = Ctx(load_config(), runner, ip_provider)
        actions = STEPS[args.step](c)
        if not actions:
            print(f"  nothing to do: '{args.step}' already in place")
            return 0
        for desc, cmd in actions:
            print(f"  {'DO     ' if args.apply else 'WOULD  '} {desc}")
            if args.apply:
                require_signoff()
                c.az([*cmd, "-o", "none"])
        if not args.apply:
            print("Dry run only. Re-run with --apply to make the change.")
        return 0
    except DevError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
