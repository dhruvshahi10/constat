"""Load test: a 200-question workbook through the pipeline with the mock
normaliser and deterministic drafter, timing per stage.

    python scripts/load_test.py [--questions 200]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from constat.claims import Audience, Claim, FileClaimStore  # noqa: E402
from constat.intake.parsers import parse_xlsx  # noqa: E402
from constat.persist import Questionnaire, make_repo, ulid  # noqa: E402
from constat.workflow.pipeline2 import PipelineConfig, create_items, process_questionnaire  # noqa: E402


def build_workbook(path: Path, n: int) -> None:
    from openpyxl import Workbook
    base = parse_xlsx(ROOT / "data/questionnaires/gitlab_caiq_v4_subset.xlsx").questions
    wb = Workbook(); ws = wb.active
    ws.append(["ID", "Domain", "Question", "Response", "Notes"])
    for i in range(n):
        q = base[i % len(base)]
        ws.append([f"L-{i + 1}", q.domain, q.text + ("" if i < len(base) else f" (variant {i // len(base)})"), "", ""])
    wb.save(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", type=int, default=200)
    a = ap.parse_args()
    today = date(2026, 10, 28)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        build_workbook(tmp / "load.xlsx", a.questions)
        store = FileClaimStore(tmp / "claims")
        store.bootstrap([Claim.from_dict(c) for c in json.loads((ROOT / "evals/golden/claims_acme.json").read_text())["claims"]],
                        approver="seed", today=today)
        repo = make_repo(f"sqlite:///{tmp / 'side.db'}")
        t0 = time.perf_counter()
        parsed = parse_xlsx(tmp / "load.xlsx")
        t1 = time.perf_counter()
        q = Questionnaire(id=ulid(), tenant="load", customer="Load", filename="load.xlsx", sha256="x")
        repo.insert("questionnaires", q)
        create_items(repo, q.id, "load", parsed.questions)
        t2 = time.perf_counter()
        counts = process_questionnaire(repo, q.id, store, PipelineConfig(today=today, audience=Audience.NDA))
        t3 = time.perf_counter()
        per_q = (t3 - t2) / max(1, a.questions) * 1000
        print(json.dumps({"questions": a.questions, "parse_ms": round((t1 - t0) * 1000), "insert_ms": round((t2 - t1) * 1000),
                          "pipeline_ms": round((t3 - t2) * 1000), "per_question_ms": round(per_q, 1), "counts": counts}, indent=2))
        return 0 if per_q < 500 else 1


if __name__ == "__main__":
    raise SystemExit(main())
