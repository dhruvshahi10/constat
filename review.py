"""Pramana review CLI — a named human signs off on a run.

  python review.py list    --run runs/20260824-…-acme-mock
  python review.py list    --run <dir> --pending
  python review.py approve --run <dir> --id IAM-01.1 --actor "Priya Nair <priya@corp.com>"
  python review.py edit    --run <dir> --id IVS-01.1 --actor "…" --answer "Frankfurt and Dublin."
  python review.py reject  --run <dir> --id A&A-02.1 --actor "…" --note "not certified yet"
  python review.py export  --run <dir>
  python review.py summary --run <dir>

`approve` accepts what the gates released and is unavailable when nothing was.
An answer a human writes is recorded as HUMAN_AUTHORED — visibly not
evidence-backed, in the contract and in the delivered workbook.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from trustops.review import ReviewError, ReviewSession   # noqa: E402

CHIP = {"evidence_backed": "OK ", "partial": "~~ ", "requires_human": "?? ",
        "no_evidence": "XX ", "routed": ">> ", "human_authored": "HU "}


def cmd_list(session: ReviewSession, args) -> int:
    items = session.queue(pending_only=args.pending)
    if not items:
        print("nothing pending — every question has been decided")
        return 0
    for item in items:
        mark = CHIP.get(item.status, "   ")
        decided = f"  [{item.decided.action} by {item.decided.actor}]" if item.decided else ""
        print(f"\n{mark}{item.question_id:<12} {item.status.upper():<16}{decided}")
        print(f"   Q: {item.text[:96]}")
        if item.citations:
            print("   cited: " + ", ".join(
                f"{c['source_id']} v{c['version']}@{c['location']}" for c in item.citations))
        for gap in item.gaps[:2]:
            print(f"   gap: {gap[:96]}")
        print(f"   you can: {', '.join(item.allowed)}")
    print(f"\n{len(items)} item(s)")
    return 0


def cmd_decide(session: ReviewSession, args) -> int:
    decision = session.decide(args.id, args.command, actor=args.actor,
                              note=getattr(args, "note", "") or "",
                              answer=getattr(args, "answer", None))
    draft = session.drafts[args.id]
    print(f"{args.id}: {decision.action} by {decision.actor} → status {draft.status.label}")
    if decision.action == "edit":
        print("   recorded as HUMAN_AUTHORED — this answer is not evidence-backed and the "
              "delivered workbook says so.")
    print(f"   audit chain valid: {session.summary()['audit_chain_valid']}")
    return 0


def cmd_export(session: ReviewSession, args) -> int:
    print(f"exported → {session.export()}")
    return 0


def cmd_summary(session: ReviewSession, args) -> int:
    print(json.dumps(session.summary(), indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Pramana human review")
    ap.add_argument("--run", required=True, type=Path, help="a run directory")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list"); p.add_argument("--pending", action="store_true")
    p.set_defaults(func=cmd_list)
    for action in ("approve", "edit", "reject"):
        p = sub.add_parser(action)
        p.add_argument("--id", required=True)
        p.add_argument("--actor", required=True)
        p.add_argument("--note", default="")
        if action == "edit":
            p.add_argument("--answer", required=True)
        p.set_defaults(func=cmd_decide)
    sub.add_parser("export").set_defaults(func=cmd_export)
    sub.add_parser("summary").set_defaults(func=cmd_summary)

    args = ap.parse_args()
    try:
        session = ReviewSession(args.run)
        return args.func(session, args)
    except ReviewError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
