"""Load KEY=VALUE pairs from a git-ignored .env at the repo root.

Stdlib-only convenience so keys can be pasted into a file instead of
exported in a shell. Values from .env win for the keys it names (so
fixing the file fixes the app without a restart); they are never logged.
"""
from __future__ import annotations

import os
from pathlib import Path


def load_env(root: Path) -> None:
    p = root / ".env"
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v:
            os.environ[k] = v
