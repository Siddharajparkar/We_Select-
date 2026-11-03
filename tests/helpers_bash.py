"""Locate a bash that understands the paths the tests pass it.

On Windows ``bash`` on PATH is often WSL (``System32\bash.exe``), a separate Linux filesystem that cannot see
``C:/...`` paths. Prefer Git Bash (next to ``git``); elsewhere use plain ``bash``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def find_bash() -> str | None:
    if os.name != "nt":
        return shutil.which("bash")
    candidates: list[Path] = []
    git = shutil.which("git")
    if git:
        root = Path(git).resolve().parent.parent  # ...\Git\cmd\git.exe -> ...\Git
        candidates += [root / "bin" / "bash.exe", root / "usr" / "bin" / "bash.exe"]
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LocalAppData")):
        if base:
            candidates += [
                Path(base) / "Git" / "bin" / "bash.exe",
                Path(base) / "Programs" / "Git" / "bin" / "bash.exe",
            ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None  # WSL's bash is deliberately not used


BASH = find_bash()
BASH_AVAILABLE = BASH is not None
