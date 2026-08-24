"""Shared configuration for the serverless functions.

The functions run the same engine as the CLI and the local console — same
retrieval, same gates, same refusal logic. Nothing about safety is re-implemented
for the web; if it were, the website would be a different product from the one
the eval suite tests.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "data" / "evidence"

# Workspaces the public demo is allowed to touch. `globex` is the isolation
# decoy and is deliberately not exposed: it exists to be unreachable.
PUBLIC_TENANTS = ("acme", "northwind", "pramana")

MAX_QUESTION_CHARS = 600


def public_tenants() -> list[str]:
    return [t for t in PUBLIC_TENANTS if (EVIDENCE / t).is_dir()]
