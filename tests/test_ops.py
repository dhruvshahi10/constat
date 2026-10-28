"""Metrics by class, the degradation rule, the ladder and the hard limits."""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constat.claims import Audience, Claim, FileClaimStore
from constat.intake.parsers import parse_xlsx
from constat.persist import Deal, MetricEvent, Questionnaire, State, make_repo, ulid
from constat.workflow import degradation as dg
from constat.workflow import ladder
from constat.workflow import review as rv
from constat.workflow.metrics import compute
from constat.workflow.pipeline2 import PipelineConfig, create_items, process_questionnaire

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 28)


@pytest.fixture()
def world(tmp_path):
    spec = json.loads((ROOT / "evals/golden/claims_acme.json").read_text())
    store = FileClaimStore(tmp_path / "claims")
    store.bootstrap([Claim.from_dict(c) for c in spec["claims"]], approver="seed", today=TODAY)
    repo = make_repo("sqlite:///:memory:")
    deal = Deal(id="deal1", tenant="acme", customer="Northwind", value_usd=400_000, approved_customer=True)
    repo.insert("deals", deal)
    q = Questionnaire(id=ulid(), tenant="acme", customer="Northwind", filename="a.xlsx", sha256="x", deal_id="deal1")
    repo.insert("questionnaires", q)
    create_items(repo, q.id, "acme", parse_xlsx(ROOT / "data/questionnaires/acme_security_questionnaire.xlsx").questions)
    process_questionnaire(repo, q.id, store, PipelineConfig(today=TODAY))
    ctx = rv.ReviewContext(repo=repo, store=store, actor="priya.nair@acme.example", today=TODAY)
    return repo, store, q, deal, ctx


def test_metrics_by_class_and_oldest_open_hard(world):
    repo, store, q, deal, ctx = world
    m = compute(repo, "acme")
    assert m["questions"] == 24 and set(m["by_class"]) >= {"covered", "contractual"}
    assert m["shipped_wrong"] == 0 and m["stop_signal"] is False
    assert "deal1" in m["oldest_open_hard"] and m["oldest_open_hard"]["deal1"]["difficulty"] in ("novel", "contractual")
    it = repo.list("question_items", {"questionnaire_id": q.id, "state": State.REVIEW}, limit=1)[0]
    rv.approve(ctx, it); rv.send(ctx, it, "Northwind")
    repo.insert("metric_events", MetricEvent(id=ulid(), tenant="acme", kind="shipped_wrong", item_id=it.id, value_num=1))
    m2 = compute(repo, "acme", deal_id="deal1")
    assert m2["stop_signal"] is True and m2["human_edit_rate"] == 0.0


def test_degradation_flips_after_72_hours_and_escalates_blockers(world):
    repo, store, q, deal, ctx = world
    dg.set_reviewers(repo, "acme", primary="priya.nair@acme.example", backup="tom.osei@acme.example", ladder_level=2)
    it = repo.list("question_items", {"questionnaire_id": q.id, "state": State.REVIEW}, limit=1)[0]
    rv.approve(ctx, it)
    held = repo.list("question_items", {"questionnaire_id": q.id, "state": State.HELD}, limit=5)
    repo.update("question_items", held[0].id, {"blocks_deal": True})
    now = datetime.now(timezone.utc)
    rep = dg.evaluate(repo, "acme", now)
    assert rep.mode == "normal" and rep.idle_hours is not None and rep.idle_hours < 1
    later = now + timedelta(hours=80)
    rep2 = dg.evaluate(repo, "acme", later)
    assert rep2.mode == "degraded" and rep2.backup_reviewer == "tom.osei@acme.example"
    assert rep2.escalations and rep2.escalations[0].items[0]["item_id"] == held[0].id
    assert rep2.ae_status and rep2.ae_status[0]["held"] >= 1
    assert repo.get("degradation_state", "acme").mode == "degraded"
    rv.approve(ctx, repo.list("question_items", {"questionnaire_id": q.id, "state": State.REVIEW}, limit=1)[0])
    # a fresh action by the primary brings it back only if it is recent relative to "now"
    rep3 = dg.evaluate(repo, "acme", datetime.now(timezone.utc))
    assert rep3.mode == "normal"


def test_ladder_hard_limits_and_levels(world):
    repo, store, q, deal, ctx = world
    items = repo.list("question_items", {"questionnaire_id": q.id}, limit=100)
    review = next(i for i in items if i.state == State.REVIEW and i.difficulty == "covered")
    contractual = next(i for i in items if i.difficulty == "contractual")
    assert ladder.hard_limit(contractual)
    assert ladder.decide(3, contractual, deal, store, TODAY, Audience.NDA).auto_send is False
    assert ladder.decide(1, review, deal, store, TODAY, Audience.NDA).auto_send is False
    d2 = ladder.decide(2, review, deal, store, TODAY, Audience.NDA)
    assert d2.auto_send is False and "does not automate covered" in d2.reason
    repo.update("question_items", review.id, {"difficulty": "reused"}); review.difficulty = "reused"
    assert ladder.decide(2, review, deal, store, TODAY, Audience.NDA).auto_send is True
    assert ladder.decide(2, review, deal, store, TODAY, Audience.PUBLIC).auto_send is False
    unapproved = Deal(id="d2", tenant="acme", customer="X", approved_customer=False)
    assert ladder.decide(2, review, unapproved, store, TODAY, Audience.NDA).auto_send is False
    review.claim_version_hash = "stale-hash"
    assert "changed" in ladder.decide(2, review, deal, store, TODAY, Audience.NDA).reason
    review.claim_version_hash = store.get(review.claim_id).version_hash()
    review.difficulty = "covered"
    assert ladder.decide(3, review, deal, store, TODAY, Audience.NDA, metrics={"shipped_wrong": 1}).auto_send is False
    ok = ladder.decide(3, review, deal, store, TODAY, Audience.NDA,
                       metrics={"shipped_wrong": 0, "human_edit_rate": 0.05, "weeks_observed": 5})
    assert ok.auto_send is True
