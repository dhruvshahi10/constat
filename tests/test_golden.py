"""The golden set is the release gate for the claims layer."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.run_golden import RELEASE_MIN, run


def test_dev_split_releases():
    s = run("dev")
    failed = [r for r in s["results"] if not r["passed"]]
    assert s["dangerous_failures"] == 0, [(r["id"], r["problems"]) for r in failed]
    assert s["weighted_score"] >= RELEASE_MIN, [(r["id"], r["problems"]) for r in failed]


def test_holdout_has_no_dangerous_failures():
    s = run("holdout")
    assert s["dangerous_failures"] == 0, [(r["id"], r["problems"]) for r in s["results"] if r["dangerous"]]
