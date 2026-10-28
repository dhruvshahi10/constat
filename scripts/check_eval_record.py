"""CI gate: a change to a model id or a prompt version must ship with a new
model-evaluation record in evals/records/ in the same change.

    python scripts/check_eval_record.py --base origin/main
"""
from __future__ import annotations

import argparse
import subprocess
import sys

WATCHED = ("constat/claims/drafter.py", "constat/intake/normalise.py", "constat/drafter.py")
MARKERS = ("CLAIM_PROMPT_VERSION", "NORMALISER_PROMPT_VERSION", "PROMPT_VERSION", "model_id =", "claude-")


def changed(base: str) -> list[str]:
    out = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"], capture_output=True, text=True, check=False)
    return [l.strip() for l in out.stdout.splitlines() if l.strip()]


def diff_text(base: str, path: str) -> str:
    return subprocess.run(["git", "diff", f"{base}...HEAD", "--", path], capture_output=True, text=True, check=False).stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main")
    a = ap.parse_args()
    files = changed(a.base)
    model_change = any(f in WATCHED and any(m in diff_text(a.base, f) for m in MARKERS) for f in files)
    new_record = any(f.startswith("evals/records/") and f.endswith(".json") for f in files)
    if model_change and not new_record:
        print("A model id or prompt version changed without a new evals/records/*.json. "
              "Run evals/run_live.py and commit the record.", file=sys.stderr)
        return 1
    print("eval-record gate: ok" + (" (model change with record)" if model_change else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
