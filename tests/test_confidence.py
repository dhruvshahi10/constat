"""Computed confidence: derived from the facts the gates read, never from a model, never an outcome."""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constat.claims import Audience, Claim, ClaimStatus, EvidenceRef, FileClaimStore
from constat.claims.confidence import HIGH, compute
from constat.claims.gates import gate
from constat.claims.match import ClaimMatcher

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 28)


def mk(refs, until=date(2027, 6, 1)) -> Claim:
    return Claim(claim_id="t.c", statement="Customer data at rest is encrypted with AES-256.", owner="raj.mehta@acme.example",
                 scope="Acme production", valid_from=date(2026, 1, 1), valid_until=until, evidence_refs=refs,
                 status=ClaimStatus.VERIFIED)


VANTA = [EvidenceRef("vanta_test", "vanta:test:rds")]
POLICY = [EvidenceRef("policy", "POL-1 v1")]
STATEMENT = [EvidenceRef("statement", "said so")]


def test_each_factor_moves_the_score_the_right_way():
    base = compute(mk(POLICY), 1.0, False, TODAY).score
    assert compute(mk(VANTA), 1.0, False, TODAY).score > base > compute(mk(STATEMENT), 1.0, False, TODAY).score
    assert compute(mk(POLICY), 1.0, True, TODAY).score > base                     # a person approved this wording
    assert compute(mk(POLICY), 0.6, False, TODAY).score < base                    # narrower match
    assert compute(mk(POLICY, until=TODAY + timedelta(days=10)), 1.0, False, TODAY).score < base


def test_a_dated_check_counts_only_while_recent():
    recent = [EvidenceRef("certificate", "CRT-1", checked_on=TODAY - timedelta(days=30))]
    old = [EvidenceRef("certificate", "CRT-1", checked_on=TODAY - timedelta(days=200))]
    assert compute(mk(recent), 1.0, False, TODAY).factors["evidence"] == 1.0
    assert compute(mk(old), 1.0, False, TODAY).factors["evidence"] == 0.9


def test_a_statement_alone_can_never_be_high_confidence():
    """However perfect the match, a drafted answer resting on a bare statement is read first."""
    c = compute(mk(STATEMENT), 1.0, False, TODAY)
    assert c.score < HIGH and c.band == "medium"
    assert any("statement only" in b for b in c.basis)


def test_every_factor_has_a_sentence_and_the_score_is_bounded():
    c = compute(mk(STATEMENT, until=TODAY + timedelta(days=3)), 0.5, False, TODAY)
    assert 0.0 <= c.score <= 1.0 and c.band == "low" and len(c.basis) == 4
    assert "expires in 3 days" in c.basis[2]


@pytest.fixture(scope="module")
def matcher(tmp_path_factory):
    spec = json.loads((ROOT / "evals/golden/claims_acme.json").read_text(encoding="utf-8"))
    store = FileClaimStore(tmp_path_factory.mktemp("claims"))
    store.bootstrap([Claim.from_dict(c) for c in spec["claims"]], approver="seed", today=TODAY)
    return ClaimMatcher(store)


@pytest.mark.parametrize("q,outcome", [
    ("Is multi-factor authentication enforced for all workforce access to production and corporate systems?", "ANSWER"),
    ("Do you support FIDO2 hardware keys for customer SSO?", "REFUSE"),
    ("What are your remediation SLAs for critical and high vulnerabilities?", "HOLD_HUMAN"),
])
def test_only_an_answer_carries_confidence(matcher, q, outcome):
    v = gate(q, matcher.match(q, TODAY, Audience.NDA), TODAY, Audience.NDA)
    assert v.outcome == outcome
    assert (v.confidence is not None) == (outcome == "ANSWER")
    if v.confidence:
        assert set(v.confidence) == {"score", "band", "factors", "basis"} and v.to_dict()["confidence"] == v.confidence
