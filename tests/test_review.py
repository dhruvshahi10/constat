"""Review actions: approve writes back, edits are re-gated, bulk needs spot
checks, sends pin claim versions, ranking puts hard old questions first."""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constat.claims import Audience, Claim, FileClaimStore
from constat.intake.parsers import parse_xlsx
from constat.persist import Deal, QuestionItem, Questionnaire, State, make_repo, ulid
from constat.workflow import review as rv
from constat.workflow.pipeline2 import PipelineConfig, create_items, process_questionnaire
from constat.workflow.ranking import rank, score

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 28)


@pytest.fixture()
def world(tmp_path):
    spec = json.loads((ROOT / "evals/golden/claims_acme.json").read_text())
    store = FileClaimStore(tmp_path / "claims")
    store.bootstrap([Claim.from_dict(c) for c in spec["claims"]], approver="seed", today=TODAY)
    repo = make_repo("sqlite:///:memory:")
    q = Questionnaire(id=ulid(), tenant="acme", customer="GitLab", filename="g.xlsx", sha256="x")
    repo.insert("questionnaires", q)
    create_items(repo, q.id, "acme", parse_xlsx(ROOT / "data/questionnaires/gitlab_caiq_v4_subset.xlsx").questions)
    process_questionnaire(repo, q.id, store, PipelineConfig(today=TODAY))
    ctx = rv.ReviewContext(repo=repo, store=store, actor="priya.nair@acme.example", today=TODAY)
    return repo, store, q, ctx


def _review_items(repo, q):
    return repo.list("question_items", {"questionnaire_id": q.id, "state": State.REVIEW}, order="ordinal asc", limit=100)


def test_approve_writes_back_and_send_pins_version(world):
    repo, store, q, ctx = world
    it = _review_items(repo, q)[0]
    before = store.get(it.claim_id)
    n_before = len(before.approved_answers)
    rv.approve(ctx, it, "fine")
    assert it.state == State.APPROVED and it.final_answer == it.draft_answer
    after = store.get(it.claim_id)
    assert len(after.approved_answers) == n_before + 1
    assert after.approved_answers[-1].approver == "priya.nair@acme.example"
    assert after.version_hash() == before.version_hash()
    rv.send(ctx, it, "GitLab")
    rec = store.sent_answers()[-1]
    assert rec.claim_version_hashes == [it.claim_version_hash] and rec.customer == "GitLab"
    with pytest.raises(rv.ReviewError):
        rv.send(ctx, it, "GitLab")


def test_same_question_next_time_is_reused(world):
    repo, store, q, ctx = world
    it = _review_items(repo, q)[0]
    rv.approve(ctx, it)
    q2 = Questionnaire(id=ulid(), tenant="acme", customer="Other", filename="o.xlsx", sha256="y")
    repo.insert("questionnaires", q2)
    from constat.intake.parsers import RawQuestion
    create_items(repo, q2.id, "acme", [RawQuestion(1, it.text, it.domain)])
    process_questionnaire(repo, q2.id, store, PipelineConfig(today=TODAY))
    again = repo.list("question_items", {"questionnaire_id": q2.id}, limit=5)[0]
    assert again.difficulty == "reused" and again.draft_answer == it.final_answer


def test_edit_is_regated_and_material_edit_opens_a_proposal(world):
    repo, store, q, ctx = world
    it = _review_items(repo, q)[0]
    # an edit that invents a number is refused
    _, v = rv.edit(ctx, it, "Yes, reviewed every 7 days by the board with 99.999% coverage.")
    assert v["outcome"] != "ANSWER" and it.state in (State.HELD, State.REFUSED)
    # a faithful rewrite is approved and, being material, proposes a claim update
    it2 = next(i for i in _review_items(repo, q) if i.claim_id == "grc.isms")
    faithful = ("Yes. We keep an approved information security policy set, which the CISO reviews "
                "and re-approves at least once a year.")
    _, v2 = rv.edit(ctx, it2, faithful, "rephrased for the customer")
    assert v2["outcome"] == "ANSWER" and it2.state == State.APPROVED
    pending = store.pending()
    assert pending and pending[0].claim.claim_id == it2.claim_id and "materially rewrote" in pending[0].claim.notes


def test_route_and_reject(world):
    repo, store, q, ctx = world
    it = _review_items(repo, q)[0]
    rv.route(ctx, it, "OWNER:tom.osei@acme.example", deadline="2026-11-02", note="confirm")
    assert it.state == State.HELD and it.route == "OWNER:tom.osei@acme.example"
    assert any(e.kind == "follow_up" for e in repo.list("metric_events", {"item_id": it.id}, limit=50))
    it2 = _review_items(repo, q)[0]
    with pytest.raises(rv.ReviewError):
        rv.reject(ctx, it2, "")
    rv.reject(ctx, it2, "wrong claim")
    assert it2.state == State.REFUSED


def test_legal_hold_cannot_be_approved_from_queue(world):
    repo, store, q, ctx = world
    legal = [i for i in repo.list("question_items", {"questionnaire_id": q.id, "state": State.HELD}, limit=200)
             if "LEGAL_COMMITMENT" in i.flags]
    assert legal
    legal[0].draft_answer = "We agree."   # even with text present
    with pytest.raises(rv.ReviewError, match="LEGAL"):
        rv.approve(ctx, legal[0])


def test_bulk_approve_needs_reused_and_spot_checks(world):
    repo, store, q, ctx = world
    items = _review_items(repo, q)[:4]
    with pytest.raises(rv.ReviewError, match="REUSED"):
        rv.bulk_approve_reused(ctx, items, set())
    reused = []
    for it in items:
        repo.update("question_items", it.id, {"difficulty": "reused"})
        it.difficulty = "reused"
        reused.append(it)
    with pytest.raises(rv.ReviewError, match="spot-check 3"):
        rv.bulk_approve_reused(ctx, reused, {reused[0].id})
    done = rv.bulk_approve_reused(ctx, reused, {i.id for i in reused[:3]})
    assert len(done) == 4 and all(i.state == State.APPROVED for i in done)
    assert rv.spot_checks_required(50) == 5 and rv.spot_checks_required(2) == 3


def test_ranking_prefers_blocking_big_old(world):
    repo, store, q, ctx = world
    items = _review_items(repo, q)[:3]
    now = datetime.now(timezone.utc)
    items[0].blocks_deal = True
    items[2].created_at = (now - timedelta(days=9)).isoformat()
    big = Deal(id="d1", tenant="acme", customer="GitLab", value_usd=400_000)
    assert score(items[0], big, now) == pytest.approx(14.0, abs=0.01)
    assert score(items[2], None, now) == pytest.approx(9.0, abs=0.01)
    assert score(items[2], big, now) == pytest.approx(18.0, abs=0.01)
    ranked = rank(items, {q.id: big}, now)
    assert [r[0].id for r in ranked] == [items[2].id, items[0].id, items[1].id]
