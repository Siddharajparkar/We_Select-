#!/usr/bin/env python3
"""Give the assess-api Container App its production settings (run once, after sync_secrets.py).

    python scripts/dev/configure_app.py            # dry run: prints the setting NAMES it would apply
    python scripts/dev/configure_app.py --apply    # az containerapp update --set-env-vars (needs the SIGN-OFF line)

Secret-backed settings use ``secretref:<key>`` (the Key Vault references made by sync_secrets.py); nothing secret is
passed here. The ingress port and the image are handled by the deploy pipeline, not by this script.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SECRETS, DevError, Runner, app_secret_key, load_config, require_signoff, run_az


def plain_settings(cfg: dict[str, str], fqdn: str) -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "PORT": "8080",
        "REPO_BACKEND": "sql",
        "DB_SCHEMA": "assess",
        "AI_MODE": "azure",
        "EMAIL_MODE": "azure",
        "FILES_MODE": "azure",
        "FOUNDRY_API_STYLE": cfg.get("FOUNDRY_API_STYLE", "v1"),
        "FOUNDRY_DEPLOYMENT": cfg.get("FOUNDRY_DEPLOYMENT", "Phi-4-mini-instruct"),
        "BLOB_CONTAINER": cfg.get("BLOB_CONTAINER", "jd-files"),
        "APP_BASE_URL": f"https://{fqdn}",
        "API_INTERNAL_URL": "http://localhost:8080",
    }


def secret_settings() -> dict[str, str]:
    """ENV_VAR -> secretref:<container app secret key> for each of the nine Key Vault secrets."""
    return {env_name: f"secretref:{app_secret_key(kv_name)}" for kv_name, env_name in SECRETS.items()}


def main(argv: list[str] | None = None, *, runner: Runner = subprocess.run) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    try:
        cfg = load_config()
        rg, app = cfg["AZ_RESOURCE_GROUP"], cfg["AZ_APP"]
        fqdn = run_az(
            [
                "containerapp",
                "show",
                "-g",
                rg,
                "-n",
                app,
                "--query",
                "properties.configuration.ingress.fqdn",
                "-o",
                "tsv",
            ],
            runner=runner,
        ).strip()
        if not fqdn:
            raise DevError("The app has no ingress address yet; create it first (provision.py app).")
        settings = {**plain_settings(cfg, fqdn), **secret_settings()}
        print(f"{'APPLY' if args.apply else 'DRY RUN'}: {len(settings)} settings on '{app}' (names only):")
        for name in settings:
            print(f"  {name}")
        if not args.apply:
            print("Re-run with --apply to write.")
            return 0
        require_signoff()
        run_az(
            [
                "containerapp",
                "update",
                "-g",
                rg,
                "-n",
                app,
                "--set-env-vars",
                *[f"{k}={v}" for k, v in settings.items()],
                "-o",
                "none",
            ],
            runner=runner,
        )
        print("Done. Verify names:  az containerapp show ... --query properties.template.containers[0].env[].name")
        return 0
    except DevError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
