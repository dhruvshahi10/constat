"""Mint or list bearer principals.

    python scripts/principals.py add --tenant constat --email priya@x.io --role owner
    python scripts/principals.py list --tenant constat
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.auth import create_principal  # noqa: E402
from api.deps import get_repo  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("--tenant", required=True); a.add_argument("--email", required=True)
    a.add_argument("--role", default="reviewer", choices=["reviewer", "owner", "admin"])
    l = sub.add_parser("list"); l.add_argument("--tenant", required=True)
    args = ap.parse_args()
    repo = get_repo()
    if args.cmd == "add":
        p, token = create_principal(repo, args.tenant, args.email, args.role)
        print(f"{p.email} ({p.role}) in {p.tenant}\nToken (shown once): {token}")
    else:
        for p in repo.list("principals", {"tenant": args.tenant}):
            print(f"{p.email:40} {p.role:9} {p.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
