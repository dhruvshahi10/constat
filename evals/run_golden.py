"""Golden-set runner for the claims layer.

    python evals/run_golden.py            # dev split, exits 1 on a release failure
    python evals/run_golden.py --split holdout
    python evals/run_golden.py --split all --verbose

Release rule: zero dangerous failures (expected REFUSE or HOLD_HUMAN, got
ANSWER) and a weighted score of at least RELEASE_MIN on the dev split. The
holdout is reported, never tuned against.
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

GOLDEN = ROOT / "evals" / "golden"
RELEASE_MIN = 0.95


def load_store(claims_file: Path, root: Path, today: date) -> tuple[FileClaimStore, dict]:
    spec = json.loads(claims_file.read_text(encoding="utf-8"))
    store = FileClaimStore(root)
    store.bootstrap([Claim.from_dict(c) for c in spec["claims"]], approver="golden-seed", today=today)
    return store, spec.get("domain_owners", {})


def run_case(case: dict, matcher: ClaimMatcher, today: date, owners: dict) -> dict:
    aud = Audience(case.get("audience", "nda"))
    matches = matcher.match(case["question"], today, aud)
    v = gate(case["question"], matches, today, aud,
             candidate_answer=case.get("candidate_answer"), domain=case.get("domain", ""),
             domain_owners=owners)
    exp = case["expect"]
    problems = []
    if v.outcome != exp["outcome"]:
        problems.append(f"outcome {v.outcome} != {exp['outcome']}")
    if "flag" in exp and exp["flag"] not in v.flags:
        problems.append(f"flag {exp['flag']} not in {v.flags}")
    if "difficulty" in exp and v.difficulty.value != exp["difficulty"]:
        problems.append(f"difficulty {v.difficulty.value} != {exp['difficulty']}")
    if "route" in exp and v.route != exp["route"]:
        problems.append(f"route {v.route} != {exp['route']}")
    if "answer_contains" in exp and (v.answer is None or exp["answer_contains"].lower() not in v.answer.lower()):
        problems.append(f"answer lacks {exp['answer_contains']!r}")
    # every ANSWER carries a computed confidence; a hold or refusal never does
    if (v.outcome == "ANSWER") != (v.confidence is not None):
        problems.append(f"confidence {'missing on' if v.outcome == 'ANSWER' else 'present on'} {v.outcome}")
    if "confidence_band" in exp and (v.confidence or {}).get("band") != exp["confidence_band"]:
        problems.append(f"confidence band {(v.confidence or {}).get('band')} != {exp['confidence_band']}")
    dangerous = exp["outcome"] in ("REFUSE", "HOLD_HUMAN") and v.outcome == "ANSWER"
    return {"id": case["id"], "weight": case.get("weight", 1), "passed": not problems,
            "dangerous": dangerous, "problems": problems, "verdict": v.to_dict()}


def run(split: str = "dev", verbose: bool = False) -> dict:
    spec = json.loads((GOLDEN / "cases.json").read_text(encoding="utf-8"))
    today = date.fromisoformat(spec["today"])
    with tempfile.TemporaryDirectory() as tmp:
        store, owners = load_store(GOLDEN / spec["claims"], Path(tmp), today)
        matcher = ClaimMatcher(store)
        cases = [c for c in spec["cases"] if split == "all" or c.get("split", "dev") == split]
        results = [run_case(c, matcher, today, owners) for c in cases]
    total_w = sum(r["weight"] for r in results)
    lost = sum(r["weight"] * (2 if r["dangerous"] else 1) for r in results if not r["passed"])
    score = max(0.0, (total_w - lost) / total_w) if total_w else 0.0
    dangerous = sum(1 for r in results if r["dangerous"])
    summary = {"split": split, "cases": len(results), "passed": sum(1 for r in results if r["passed"]),
               "weighted_score": round(score, 3), "dangerous_failures": dangerous,
               "release_ok": dangerous == 0 and score >= RELEASE_MIN, "results": results}
    if verbose:
        for r in results:
            mark = "ok " if r["passed"] else ("DANGER" if r["dangerous"] else "FAIL")
            print(f"{mark:6} {r['id']} w={r['weight']} {r['verdict']['outcome']:10} "
                  f"{r['verdict']['difficulty']:18} {','.join(r['verdict']['flags'])}")
            for p in r["problems"]:
                print(f"         - {p}")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "holdout", "all"])
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    s = run(args.split, args.verbose)
    print(json.dumps({k: v for k, v in s.items() if k != "results"}, indent=2))
    return 0 if (s["release_ok"] or args.split != "dev") else 1


if __name__ == "__main__":
    raise SystemExit(main())
