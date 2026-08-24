"""Pramana onboarding CLI — turn a client's real documents into a governed corpus.

  python onboard.py tenants
  python onboard.py new-tenant --tenant northwind --name "Northwind Health"
  python onboard.py stage      --tenant northwind --from ~/Downloads/northwind-policies
  python onboard.py review     --tenant northwind
  python onboard.py promote    --tenant northwind --id POL-ACCESS-CONTROL \
      --actor "Priya Nair <priya@northwind.example>"
  python onboard.py inspect    --questionnaire ~/Downloads/buyer-caiq.xlsx

Staging never approves anything. Until a named human promotes a source, the
citation gate treats it as unapproved and refuses to answer from it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from trustops import tenants as tn                                  # noqa: E402
from trustops.export import layout_of                               # noqa: E402
from trustops.ingest import (ExtractionError, promote,              # noqa: E402
                             stage_corpus, staging_dir)

EVIDENCE = ROOT / "data" / "evidence"


def cmd_tenants(args) -> int:
    rows = tn.list_tenants(args.evidence_root)
    if not rows:
        print(f"no tenant workspaces under {args.evidence_root}")
        return 0
    print(f"{'SLUG':<18} {'DISPLAY NAME':<28} {'SOURCES':>7} {'STAGED':>7}  OWNER")
    for t in rows:
        print(f"{t.slug:<18} {t.title:<28} "
              f"{tn.source_count(args.evidence_root, t.slug):>7} "
              f"{tn.staged_count(args.evidence_root, t.slug):>7}  {t.owner}")
    return 0


def cmd_new_tenant(args) -> int:
    t = tn.create_tenant(args.evidence_root, args.tenant, display_name=args.name,
                         owner=args.owner, contact_email=args.contact,
                         headline=args.headline)
    print(f"created workspace '{t.slug}' → {Path(args.evidence_root) / t.slug}")
    print(f"next: python onboard.py stage --tenant {t.slug} --from <folder of documents>")
    return 0


def cmd_stage(args) -> int:
    src = Path(args.source).expanduser()
    if not src.is_dir():
        print(f"error: --from must be a directory (got {src})", file=sys.stderr)
        return 2
    if not (Path(args.evidence_root) / args.tenant).is_dir():
        print(f"error: no workspace for '{args.tenant}'. Create it first:\n"
              f"  python onboard.py new-tenant --tenant {args.tenant}", file=sys.stderr)
        return 2
    result = stage_corpus(args.tenant, src, args.evidence_root)
    print(f"staged {len(result.staged)} source(s) → {result.staging_dir}")
    for p in result.staged:
        flags = ", ".join(p.inferred) or "nothing inferred"
        print(f"  {p.source_id:<26} {p.meta['type']:<12} confirm: {flags}")
    if result.failed:
        print(f"\ncould not ingest {len(result.failed)}:")
        for path, reason in result.failed:
            print(f"  {path.name}: {reason}")
    print(f"\nreview queue: {result.review_path}")
    print("Nothing is citable until promoted — staged sources are approval_status: draft.")
    return 0


def cmd_review(args) -> int:
    path = staging_dir(args.evidence_root, args.tenant) / "REVIEW.md"
    if not path.is_file():
        print(f"no review queue for '{args.tenant}' — run `stage` first")
        return 1
    print(path.read_text(encoding="utf-8"))
    return 0


def cmd_promote(args) -> int:
    try:
        target = promote(args.tenant, args.id, args.evidence_root, args.actor,
                         approve=not args.as_draft)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    state = "draft (still not citable)" if args.as_draft else "approved"
    print(f"{args.id} → {target}  [{state}, by {args.actor}]")
    return 0


def cmd_inspect(args) -> int:
    path = Path(args.questionnaire).expanduser()
    layout = layout_of(path)
    print(f"{path.name}: {layout.as_dict()}")
    from trustops.export import ingest_questionnaire
    questions = ingest_questionnaire(path, layout)
    print(f"{len(questions)} question(s) detected")
    for q in questions[:5]:
        print(f"  {q.question_id:<12} row={q.row:<4} {q.text[:66]}")
    if len(questions) > 5:
        print(f"  … {len(questions) - 5} more")
    if not questions:
        print("No questions found. Check that the sheet has a question column header "
              "(question / control / requirement / description).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Pramana onboarding — client corpus and questionnaires")
    ap.add_argument("--evidence-root", default=str(EVIDENCE), type=Path)
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("tenants", help="list client workspaces").set_defaults(func=cmd_tenants)

    p = sub.add_parser("new-tenant", help="create a client workspace")
    p.add_argument("--tenant", required=True)
    p.add_argument("--name", default="")
    p.add_argument("--owner", default="")
    p.add_argument("--contact", default="")
    p.add_argument("--headline", default="")
    p.set_defaults(func=cmd_new_tenant)

    p = sub.add_parser("stage", help="extract and stage a folder of client documents")
    p.add_argument("--tenant", required=True)
    p.add_argument("--from", dest="source", required=True)
    p.set_defaults(func=cmd_stage)

    p = sub.add_parser("review", help="print the review queue")
    p.add_argument("--tenant", required=True)
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("promote", help="approve a staged source under a named human")
    p.add_argument("--tenant", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--actor", required=True, help='e.g. "Priya Nair <priya@corp.com>"')
    p.add_argument("--as-draft", action="store_true",
                   help="promote into the corpus but leave it unapproved (not citable)")
    p.set_defaults(func=cmd_promote)

    p = sub.add_parser("inspect", help="show the detected layout of a questionnaire file")
    p.add_argument("--questionnaire", required=True)
    p.set_defaults(func=cmd_inspect)

    args = ap.parse_args()
    try:
        return args.func(args)
    except ExtractionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
