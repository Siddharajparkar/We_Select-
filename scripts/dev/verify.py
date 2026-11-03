#!/usr/bin/env python3
"""Live checks for phases 0 to 6 against a running server (local `run.py` or the deployed API).

python scripts/dev/verify.py [--base-url http://127.0.0.1:8080] [--upto 6] [--no-ai]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO_ROOT


def build_command(base_url: str, upto: int, with_ai: bool) -> list[str]:
    local = base_url.startswith(("http://127.0.0.1", "http://localhost"))
    return [
        sys.executable, str(REPO_ROOT / "scripts" / "e2e" / "run.py"),
        "--base-url", base_url, "--upto", str(upto), "--target", "local" if local else "azure",
        "--with-ai", "true" if with_ai else "false",
    ]  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default="http://127.0.0.1:8080")
    ap.add_argument("--upto", type=int, default=6)
    ap.add_argument("--no-ai", action="store_true", help="skip the checks that call the real AI model")
    args = ap.parse_args(argv)
    return subprocess.run(build_command(args.base_url, args.upto, not args.no_ai), check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
