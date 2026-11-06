"""Injection suite: every case must be quarantined at intake or refused by the
gate. Two paths are exercised: the raw screen (what the normaliser sees) and
the gate (what a question that slipped through would get). A case with
"via": "pdf" is laid out as PDF lines and parsed first, so a wrap or a page
layout cannot launder an attack past intake.

    python evals/run_injection.py [--verbose]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from constat.claims import Audience, Claim, FileClaimStore  # noqa: E402
from constat.claims.gates import gate  # noqa: E402
from constat.claims.match import ClaimMatcher  # noqa: E402
from constat.intake.quarantine import screen_raw  # noqa: E402

CASES = ROOT / "evals" / "injection" / "cases.json"
GOLDEN_CLAIMS = ROOT / "evals" / "golden" / "claims_acme.json"


def _via_pdf(case: dict, matcher: ClaimMatcher, today: date) -> dict:
    """Every question the PDF parser finds must be quarantined or refused,
    and it must find at least one: an attack the parser drops silently is a
    lost question, which is its own failure."""
    from evals.pdf_fixture import make_pdf
    from constat.intake.parsers import parse_pdf
    questions = parse_pdf(make_pdf([case["lines"]])).questions
    outcomes = []
    for pq in questions:
        if screen_raw(pq.text).quarantined:
            outcomes.append("QUARANTINED")
            continue
        outcomes.append(gate(pq.text, matcher.match(pq.text, today, Audience.NDA), today, Audience.NDA).outcome)
    passed = bool(questions) and all(o in ("QUARANTINED", "REFUSE") for o in outcomes)
    return {"id": case["id"], "stage": "pdf", "outcome": ",".join(outcomes) or "NO_QUESTION", "passed": passed,
            "reasons": [pq.text[:80] for pq in questions]}


def run(verbose: bool = False) -> dict:
    spec = json.loads(CASES.read_text(encoding="utf-8"))
    today = date(2026, 10, 28)
    with tempfile.TemporaryDirectory() as tmp:
        store = FileClaimStore(Path(tmp))
        store.bootstrap([Claim.from_dict(c) for c in json.loads(GOLDEN_CLAIMS.read_text())["claims"]],
                        approver="seed", today=today)
        matcher = ClaimMatcher(store)
        results = []
        for case in spec["cases"]:
            if case.get("via") == "pdf":
                results.append(_via_pdf(case, matcher, today))
                continue
            q = screen_raw(case["text"])
            if q.quarantined:
                results.append({"id": case["id"], "stage": "intake", "outcome": "QUARANTINED", "passed": True,
                                "reasons": q.reasons})
                continue
            v = gate(case["text"], matcher.match(case["text"], today, Audience.NDA), today, Audience.NDA)
            passed = v.outcome == "REFUSE"
            results.append({"id": case["id"], "stage": "gate", "outcome": v.outcome, "passed": passed,
                            "flags": v.flags, "answer": v.answer})
    failed = [r for r in results if not r["passed"]]
    if verbose:
        for r in results:
            mark = "ok  " if r["passed"] else "FAIL"
            print(f"{mark} {r['id']} {r['stage']:6} {r['outcome']:11} {','.join(r.get('reasons', r.get('flags', [])))[:80]}")
    return {"cases": len(results), "passed": len(results) - len(failed), "pass_rate": round((len(results) - len(failed)) / len(results), 3),
            "failed": [r["id"] for r in failed], "results": results}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    s = run(a.verbose)
    print(json.dumps({k: v for k, v in s.items() if k != "results"}, indent=2))
    return 0 if not s["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
