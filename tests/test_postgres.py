"""The Postgres repository against a real Postgres (embedded via pgserver when
installed; skipped otherwise). The hosted deployment runs on this path."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pgserver = pytest.importorskip("pgserver")
pytest.importorskip("psycopg")

from constat.claims import Claim, FileClaimStore  # noqa: E402
from constat.intake.parsers import parse_xlsx  # noqa: E402
from constat.persist import (DegradationState, MetricEvent, QuestionItem, Questionnaire, State,  # noqa: E402
                             make_repo, ulid)
from constat.workflow import review as rv  # noqa: E402
from constat.workflow.metrics import compute  # noqa: E402
from constat.workflow.pipeline2 import PipelineConfig, create_items, process_questionnaire  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 6)


@pytest.fixture(scope="module")
def pg_url():
    d = tempfile.mkdtemp(prefix="constat-pg-")
    srv = pgserver.get_server(d, cleanup_mode="stop")
    try:
        import psycopg
        with psycopg.connect(srv.get_uri("postgres"), autocommit=True) as conn:
            conn.execute("DROP DATABASE IF EXISTS constat_test")
            conn.execute("CREATE DATABASE constat_test")
        yield srv.get_uri("constat_test")
    finally:
        srv.cleanup()
        shutil.rmtree(d, ignore_errors=True)


def test_repository_contract_on_postgres(pg_url):
    repo = make_repo(pg_url)
    q = Questionnaire(id=ulid(), tenant="acme", customer="N", filename="f.xlsx", sha256="s",
                      layout_json={"header_row": 3, "col_question": 3})
    repo.insert("questionnaires", q)
    assert repo.get("questionnaires", q.id).layout_json == {"header_row": 3, "col_question": 3}
    it = QuestionItem(id=ulid(), questionnaire_id=q.id, tenant="acme", ordinal=1, raw_text="r", flags=["A"],
                      blocks_deal=True, verdict_json={"outcome": "ANSWER"})
    repo.insert("question_items", it)
    got = repo.get("question_items", it.id)
    assert got.state is State.RECEIVED and got.flags == ["A"] and got.blocks_deal is True
    assert got.verdict_json == {"outcome": "ANSWER"}
    repo.update("question_items", it.id, {"state": State.REVIEW, "flags": ["B"], "blocks_deal": False})
    got = repo.get("question_items", it.id)
    assert got.state is State.REVIEW and got.flags == ["B"] and got.blocks_deal is False
    assert repo.count("question_items", {"tenant": "acme", "state": State.REVIEW}) == 1
    assert len(repo.list("question_items", {"state": [State.REVIEW, State.SENT]}, order="ordinal desc")) == 1
    repo.upsert("degradation_state", DegradationState(tenant="acme", primary_reviewer="a@x"))
    repo.upsert("degradation_state", DegradationState(tenant="acme", primary_reviewer="b@x", ladder_level=2))
    d = repo.get("degradation_state", "acme")
    assert d.primary_reviewer == "b@x" and d.ladder_level == 2
    repo.insert("metric_events", MetricEvent(id=ulid(), tenant="acme", kind="latency_ms", value_num=12.5))
    assert repo.list("metric_events", {"kind": "latency_ms"})[0].value_num == 12.5
    with pytest.raises(KeyError):
        repo.update("question_items", "missing", {"state": State.SENT})
    repo.close()


def test_full_pipeline_review_and_metrics_on_postgres(pg_url, tmp_path):
    repo = make_repo(pg_url)
    store = FileClaimStore(tmp_path / "claims")
    store.bootstrap([Claim.from_dict(c) for c in json.loads((ROOT / "evals/golden/claims_acme.json").read_text())["claims"]],
                    approver="seed", today=TODAY)
    q = Questionnaire(id=ulid(), tenant="pg", customer="GitLab", filename="g.xlsx", sha256="x")
    repo.insert("questionnaires", q)
    create_items(repo, q.id, "pg", parse_xlsx(ROOT / "data/questionnaires/gitlab_caiq_v4_subset.xlsx").questions)
    counts = process_questionnaire(repo, q.id, store, PipelineConfig(today=TODAY))
    assert sum(counts.values()) == 54 and counts.get("SENT", 0) == 0
    ctx = rv.ReviewContext(repo=repo, store=store, actor="priya.nair@acme.example", today=TODAY)
    it = repo.list("question_items", {"questionnaire_id": q.id, "state": State.REVIEW}, order="ordinal asc", limit=1)[0]
    rv.approve(ctx, it)
    rv.send(ctx, it, "GitLab")
    m = compute(repo, "pg")
    assert m["questions"] == 54 and m["by_class"]["covered"]["sent"] == 1 and m["human_edit_rate"] == 0.0
    repo.close()
