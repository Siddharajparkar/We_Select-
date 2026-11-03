#!/usr/bin/env python3
"""Print the values to enter in GitHub (Settings > Secrets and variables > Actions). Read-only; changes nothing.

    python scripts/dev/github_settings.py

The identifiers are printed to YOUR terminal only. Enter them in the GitHub UI yourself; never paste them into a file,
a commit, a pull request or a chat.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DevError, Runner, load_config, run_az


def collect(cfg: dict[str, str], *, runner: Runner = subprocess.run) -> dict[str, dict[str, str]]:
    ident = run_az(
        [
            "identity",
            "show",
            "-g",
            cfg["AZ_RESOURCE_GROUP"],
            "-n",
            cfg["AZ_DEPLOY_IDENTITY"],
            "--query",
            "clientId",
            "-o",
            "tsv",
        ],
        runner=runner,
    ).strip()
    acct = run_az(["account", "show", "--query", "[tenantId, id]", "-o", "tsv"], runner=runner).split()
    if len(acct) != 2 or not ident:
        raise DevError("Could not read the deploy identity or the subscription. Run `az login` and check the config.")
    return {
        "secrets": {"AZURE_CLIENT_ID": ident, "AZURE_TENANT_ID": acct[0], "AZURE_SUBSCRIPTION_ID": acct[1]},
        "variables": {
            "AZURE_RESOURCE_GROUP": cfg["AZ_RESOURCE_GROUP"],
            "AZURE_ACR_NAME": cfg["AZ_ACR"],
            "AZURE_DEPLOY_ENABLED": "false  (set to true LAST, after the first checks)",
        },
    }


def main(runner: Runner = subprocess.run) -> int:
    try:
        data = collect(load_config(), runner=runner)
    except DevError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print("GitHub > repo Settings > Secrets and variables > Actions > Secrets (New repository secret):")
    for k, v in data["secrets"].items():
        print(f"  {k} = {v}")
    print("\nSame page > Variables (New repository variable):")
    for k, v in data["variables"].items():
        print(f"  {k} = {v}")
    print("\nSettings > Environments > New environment named exactly: production")
    print("Do not paste these values into chat, files or pull requests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
