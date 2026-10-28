"""Claim store: propose-then-approve, versions, hygiene, the loop back."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constat.claims import (ApprovedAnswer, Audience, Claim, ClaimStatus, EvidenceRef,
                            FileClaimStore)
from constat.claims.atlan import from_term_payload, to_term_payload
from constat.claims.store import SentAnswerRecord

TODAY = date(2026, 10, 28)


def mk(claim_id="enc.at_rest", status=ClaimStatus.VERIFIED, **kw) -> Claim:
    base = dict(claim_id=claim_id, statement="Data at rest is encrypted with AES-256.",
                owner="raj.mehta@acme.example", scope="production stores",
                valid_from=date(2026, 1, 1), valid_until=date(2027, 1, 1),
                evidence_refs=[EvidenceRef("vanta_test", "vanta:test:rds-encryption")],
                status=status, audience=Audience.NDA)
    base.update(kw)
    return Claim(**base)


def test_propose_then_approve_bumps_version_and_records_approver(tmp_path):
    s = FileClaimStore(tmp_path)
    s.bootstrap([mk()], approver="seed", today=TODAY)
    c = s.get("enc.at_rest")
    assert c.version == 1 and c.status == ClaimStatus.VERIFIED
    old_hash = c.version_hash()

    c2 = mk(statement="Data at rest is encrypted with AES-256 via AWS KMS.")
    p = s.propose(c2, actor="raj.mehta@acme.example", reason="name the KMS", today=TODAY)
    assert s.get("enc.at_rest").version_hash() == old_hash, "a proposal writes nothing"
    assert [x.proposal_id for x in s.pending()] == [p.proposal_id]

    with pytest.raises(PermissionError):
        s.approve(p.proposal_id, approver="raj.mehta@acme.example", today=TODAY)

    c3 = s.approve(p.proposal_id, approver="priya.nair@acme.example", today=TODAY)
    assert c3.version == 2 and c3.updated_by == "priya.nair@acme.example"
    assert c3.version_hash() != old_hash
    assert s.pending() == []
    with pytest.raises(ValueError):
        s.approve(p.proposal_id, approver="priya.nair@acme.example", today=TODAY)


def test_draft_proposal_becomes_verified_on_approval(tmp_path):
    s = FileClaimStore(tmp_path)
    p = s.propose(mk(claim_id="new.claim", status=ClaimStatus.DRAFT), actor="a@x.io",
                  reason="new", today=TODAY)
    assert s.get("new.claim") is None
    c = s.approve(p.proposal_id, approver="b@x.io", today=TODAY)
    assert c.status == ClaimStatus.VERIFIED and c.version == 1


def test_reject_leaves_store_untouched(tmp_path):
    s = FileClaimStore(tmp_path)
    s.bootstrap([mk()], approver="seed", today=TODAY)
    p = s.propose(mk(statement="changed"), actor="a@x.io", reason="x", today=TODAY)
    s.reject(p.proposal_id, approver="b@x.io", today=TODAY, reason="no evidence")
    assert s.get("enc.at_rest").statement.startswith("Data at rest")
    assert s.pending() == []


def test_hygiene_refuses_team_alias_owner_blank_scope_and_unverified_without_evidence(tmp_path):
    s = FileClaimStore(tmp_path)
    with pytest.raises(ValueError, match="team alias"):
        s.bootstrap([mk(owner="security@acme.example")], approver="seed", today=TODAY)
    with pytest.raises(ValueError, match="scope"):
        s.bootstrap([mk(claim_id="x.y", scope=" ")], approver="seed", today=TODAY)
    with pytest.raises(ValueError, match="evidence"):
        s.bootstrap([mk(claim_id="x.z", evidence_refs=[])], approver="seed", today=TODAY)


def test_no_op_proposal_is_refused(tmp_path):
    s = FileClaimStore(tmp_path)
    s.bootstrap([mk()], approver="seed", today=TODAY)
    with pytest.raises(ValueError, match="changes nothing"):
        s.propose(mk(), actor="a@x.io", reason="same", today=TODAY)


def test_bootstrap_never_overwrites(tmp_path):
    s = FileClaimStore(tmp_path)
    s.bootstrap([mk()], approver="seed", today=TODAY)
    with pytest.raises(ValueError, match="overwrite"):
        s.bootstrap([mk()], approver="seed", today=TODAY)


def test_claim_id_cannot_escape_store(tmp_path):
    s = FileClaimStore(tmp_path)
    c = mk(claim_id="../../etc/passwd")
    s.bootstrap([c], approver="seed", today=TODAY)
    files = list((tmp_path / "claims").glob("*.json"))
    assert len(files) == 1 and ".." not in files[0].name


def test_usable_is_status_freshness_and_audience(tmp_path):
    c = mk()
    assert c.is_usable(TODAY, Audience.NDA) == (True, "")
    assert c.is_usable(TODAY, Audience.PUBLIC) == (False, "AUDIENCE")
    assert c.is_usable(date(2027, 6, 1), Audience.NDA) == (False, "STALE")
    assert mk(status=ClaimStatus.DRAFT).is_usable(TODAY, Audience.INTERNAL) == (False, "DRAFT")
    assert mk(status=ClaimStatus.DEPRECATED).is_usable(TODAY, Audience.INTERNAL) == (False, "DEPRECATED")


def test_version_hash_tracks_content_not_metadata(tmp_path):
    a, b = mk(), mk(updated_by="someone", notes="irrelevant")
    assert a.version_hash() == b.version_hash()
    assert mk(exceptions=["except backups"]).version_hash() != a.version_hash()


def test_sent_answer_log_and_writeback(tmp_path):
    s = FileClaimStore(tmp_path)
    s.bootstrap([mk()], approver="seed", today=TODAY)
    c = s.get("enc.at_rest")
    s.record_sent_answer(SentAnswerRecord(
        question="Is data encrypted at rest?", answer="Yes, AES-256.", claim_ids=[c.claim_id],
        claim_version_hashes=[c.version_hash()], approver="priya.nair@acme.example",
        customer="Northwind", sent_on=TODAY, audience=Audience.NDA, difficulty_class="covered"))
    recs = s.sent_answers()
    assert len(recs) == 1 and recs[0].claim_version_hashes == [c.version_hash()]

    s.add_approved_answer("enc.at_rest", ApprovedAnswer(
        question="Is data encrypted at rest?", answer="Yes, AES-256.", approver="",
        approved_on=TODAY), approver="priya.nair@acme.example", today=TODAY)
    c2 = s.get("enc.at_rest")
    assert c2.approved_answers[0].approver == "priya.nair@acme.example"
    assert c2.approved_answers[0].claim_version_hash == c.version_hash()
    assert c2.version_hash() == c.version_hash(), "an approved answer does not change the claim's content"


def test_freshness_digest_groups_by_owner(tmp_path):
    s = FileClaimStore(tmp_path)
    s.bootstrap([
        mk(claim_id="a.expired", valid_until=date(2026, 9, 1)),
        mk(claim_id="a.expiring", valid_until=date(2026, 11, 10)),
        mk(claim_id="b.draft", owner="lena.hoff@acme.example", status=ClaimStatus.DRAFT),
        mk(claim_id="b.fine", owner="lena.hoff@acme.example"),
        mk(claim_id="c.gone", status=ClaimStatus.DEPRECATED),
    ], approver="seed", today=TODAY)
    d = s.freshness_digest(TODAY)
    assert d["raj.mehta@acme.example"]["expired"] == ["a.expired"]
    assert d["raj.mehta@acme.example"]["expiring"] == ["a.expiring"]
    assert d["lena.hoff@acme.example"]["draft"] == ["b.draft"]
    assert "c.gone" not in json.dumps(d)


def test_atlan_term_payload_round_trips_and_pins_hash():
    c = mk(exceptions=["Backups in the EU archive use AES-128"], framework_map=["SOC2:CC6.1"],
           approved_answers=[ApprovedAnswer("q?", "a.", "p@x.io", TODAY)])
    p = to_term_payload(c)
    assert p["certificate_status"] == "VERIFIED" and p["atlan_tags"] == ["SOC2:CC6.1"]
    assert p["custom_metadata"]["Claim"]["version_hash"] == c.version_hash()
    back = from_term_payload(p)
    assert back.version_hash() == c.version_hash()
    assert back.exceptions == c.exceptions and back.approved_answers[0].answer == "a."
