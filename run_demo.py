"""TrustOps demo runner.

  python3 run_demo.py                       # offline deterministic run
  python3 run_demo.py --drafter gemini      # live LLM run, $0 (needs GEMINI_API_KEY)
  python3 run_demo.py --drafter anthropic   # live LLM run (needs ANTHROPIC_API_KEY)
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from trustops.envfile import load_env
from trustops.pipeline import run
from trustops.report import write_report

ROOT = Path(__file__).resolve().parent
load_env(ROOT)


def main() -> None:
    ap = argparse.ArgumentParser(description="TrustOps v0 — evidence-gated questionnaire engine")
    ap.add_argument("--tenant", default="acme")
    ap.add_argument("--drafter", default="mock", choices=["mock", "anthropic", "gemini"])
    ap.add_argument("--questionnaire",
                    default=str(ROOT / "data/questionnaires/acme_security_questionnaire.xlsx"))
    ap.add_argument("--today", default=None, help="YYYY-MM-DD (defaults to system date)")
    args = ap.parse_args()

    today = date.fromisoformat(args.today) if args.today else date.today()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = ROOT / "runs" / f"{stamp}-{args.tenant}-{args.drafter}"

    res = run(Path(args.questionnaire), tenant=args.tenant,
              evidence_root=ROOT / "data/evidence", out_dir=out,
              drafter_kind=args.drafter, today=today)
    report_path = write_report(res, today)

    print(json.dumps(res.metrics, indent=2))
    print(f"\ndelivered : {res.delivered_xlsx}")
    print(f"report    : {report_path}")
    print(f"audit log : {res.audit_path}")


if __name__ == "__main__":
    main()
