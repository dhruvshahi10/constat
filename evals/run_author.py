"""Golden set for the claim-drafting assistant.

    python evals/run_author.py            # exits 1 on a dangerous failure
    python evals/run_author.py --verbose

Runs the deterministic extractor over the synthetic corpus (evals/author)
and checks each case. Dangerous: a sentence drafted that must never be, or
a draft that drops the exception its source attaches. Release needs zero.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from constat.claims.author import SentenceAuthor, SourceDoc  # noqa: E402

AUTHOR = ROOT / "evals" / "author"


def _doc(entry: dict) -> SourceDoc:
    return SourceDoc(source_id=entry["source_id"], version=entry["version"], title=entry["title"],
                     text=(AUTHOR / entry["file"]).read_text(encoding="utf-8"), kind=entry["kind"],
                     products=entry.get("products", []))


def run_case(case: dict, res) -> dict:
    problems, dangerous = [], False
    if case["expect"] == "draft":
        d = next((d for d in res.drafts if d.statement.startswith(case["statement_starts"])), None)
        if d is None:
            problems.append("not drafted")
        else:
            if "exception_contains" in case and case["exception_contains"] not in " ".join(d.exceptions):
                problems.append(f"exception lost: {case['exception_contains']!r} not in {d.exceptions}")
                dangerous = True
            for k in ("products", "data_classes"):
                if k in case and sorted(getattr(d, k)) != sorted(case[k]):
                    problems.append(f"{k} {getattr(d, k)} != {case[k]}")
    else:
        drafted = [d for d in res.drafts if case["text_contains"] in d.statement
                   or any(case["text_contains"] in e for e in d.exceptions)]
        if drafted:
            problems.append(f"drafted: {drafted[0].statement[:80]}")
            dangerous = True
        skip = next((s for s in res.skipped if case["text_contains"] in s.text), None)
        if case["expect"] == "skip" and (skip is None or not skip.reason.startswith(case["reason_starts"])):
            problems.append(f"skip reason {skip.reason if skip else None!r} does not start {case['reason_starts']!r}")
        if case["expect"] == "absent" and skip is not None:
            problems.append("reported as a skipped sentence; it is not prose")
    return {"id": case["id"], "passed": not problems, "dangerous": dangerous, "problems": problems}


def run(verbose: bool = False) -> dict:
    spec = json.loads((AUTHOR / "cases.json").read_text(encoding="utf-8"))
    manifest = json.loads((AUTHOR / "sources.json").read_text(encoding="utf-8"))
    entries = {e["source_id"]: e for e in manifest["sources"]}
    entries[spec["noise"]["source_id"]] = spec["noise"]
    results_by_source = {sid: SentenceAuthor().extract(_doc(e)) for sid, e in entries.items()}
    results = [run_case(c, results_by_source[c["source"]]) for c in spec["cases"]]
    summary = {"cases": len(results), "passed": sum(r["passed"] for r in results),
               "dangerous_failures": sum(r["dangerous"] for r in results),
               "drafts": {sid: len(r.drafts) for sid, r in results_by_source.items()},
               "results": results}
    summary["release_ok"] = summary["dangerous_failures"] == 0
    if verbose:
        for r in results:
            mark = "ok " if r["passed"] else ("DANGER" if r["dangerous"] else "FAIL")
            print(f"{mark:6} {r['id']}")
            for p in r["problems"]:
                print(f"         - {p}")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    s = run(ap.parse_args().verbose)
    print(json.dumps({k: v for k, v in s.items() if k != "results"}, indent=2))
    return 0 if s["release_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
