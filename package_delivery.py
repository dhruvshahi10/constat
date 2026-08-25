"""Pramana delivery packager — turn a run into the folder a client is handed.

  python package_delivery.py --run runs/20260808-203754-acme-mock
  python package_delivery.py --run <dir> --out deliveries/
  python package_delivery.py --run <dir> --out-dir /tmp/acme-package

The output defaults to `deliveries/<engagement-date>-<tenant>/`, where the
engagement date is the run's own date — so re-packaging the same run twice
lands in the same folder rather than accumulating dated copies of one delivery.

The trust page and the commitment register are regenerated as part of the
package. They are generated with the deterministic mock drafter by default:
packaging is an assembly step and should not depend on a network call or an
API key. Pass `--drafter` if a live drafter is genuinely wanted.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from trustops.deliverable import GROUP_TITLES, DeliveryError, build  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Assemble a completed run into a client deliverable package.")
    ap.add_argument("--run", required=True, help="run directory to package")
    ap.add_argument("--out", default=str(ROOT / "deliveries"),
                    help="root the package folder is created in (default: deliveries/)")
    ap.add_argument("--out-dir", default=None,
                    help="exact package folder, overriding --out and the default name")
    ap.add_argument("--drafter", default="mock", choices=["mock", "anthropic", "gemini"],
                    help="drafter for the regenerated trust page and commitment register")
    ap.add_argument("--evidence-root", default=None,
                    help="override the evidence root recorded in the run manifest")
    args = ap.parse_args()

    try:
        pkg = build(Path(args.run), out_root=Path(args.out),
                    out_dir=Path(args.out_dir) if args.out_dir else None,
                    drafter_kind=args.drafter,
                    evidence_root=Path(args.evidence_root) if args.evidence_root else None)
    except DeliveryError as exc:
        print(f"cannot package this run: {exc}", file=sys.stderr)
        return 2

    s = pkg.summary
    print(f"\n{pkg.tenant.title} — engagement {pkg.engagement_date.isoformat()}")
    print(f"  questions               {s['questions']}")
    print(f"  answered with citations {s['answered_with_citations']} "
          f"({s['citations_released']} citations)")
    if s["human_authored"]:
        print(f"  human-authored answers  {s['human_authored']}")
    print(f"  refused (control held)  {s['refused']}")
    print(f"  open items for client   {s['open_items']}")
    for key, count in sorted(s["open_items_by_reason"].items(),
                             key=lambda kv: (-kv[1], kv[0])):
        print(f"      {count:>3}  {GROUP_TITLES.get(key, key)}")
    if s["human_decisions"]:
        print(f"  human decisions         {s['human_decisions']} "
              f"({', '.join(s['reviewers'])})")
    elif s["awaiting_sign_off"]:
        print(f"  awaiting sign-off       {s['awaiting_sign_off']}")
    print(f"  audit chain             "
          f"{'VALID' if s['audit_chain_valid'] else 'BROKEN'}"
          f"{' · signed' if s['audit_chain_signed'] else ' · unsigned'}")

    print(f"\n  {len(pkg.artifacts)} artifacts linked from the cover page:")
    for art in pkg.artifacts:
        print(f"      {art.path}")
    for note in pkg.notes:
        print(f"\n  note: {note}")

    print(f"\npackage : {pkg.out_dir}")
    print(f"open    : {pkg.index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
