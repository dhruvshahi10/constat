"""Product context on claims: a fact about one product never answers for another."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constat.claims import Audience, Claim, ClaimStatus, EvidenceRef, FileClaimStore
from constat.claims import gates as gates_mod
from constat.claims import importer
from constat.claims.atlan import CM_ATTRIBUTES, CM_OPTIONS, from_term_payload, to_term_payload
from constat.claims.gates import gate
from constat.claims.match import ClaimMatcher, Match
from constat.claims.scope import effective_scope, named_data_classes, named_products, scope_gaps
from constat.intake.parsers import RawQuestion

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 28)


def mk(**kw) -> Claim:
    base = dict(claim_id="t.claim", statement="Metadata is encrypted at rest with AES-256.",
                owner="raj.mehta@acme.example", scope="Acme catalog", valid_from=date(2026, 1, 1),
                valid_until=date(2027, 1, 1), evidence_refs=[EvidenceRef("standard", "STD-1")],
                status=ClaimStatus.VERIFIED)
    base.update(kw)
    return Claim(**base)


@pytest.fixture(scope="module")
def matcher(tmp_path_factory):
    spec = json.loads((ROOT / "evals/golden/claims_acme.json").read_text(encoding="utf-8"))
    store = FileClaimStore(tmp_path_factory.mktemp("claims"))
    store.bootstrap([Claim.from_dict(c) for c in spec["claims"]], approver="seed", today=TODAY)
    return ClaimMatcher(store)


def verdict(matcher, q):
    return gate(q, matcher.match(q, TODAY, Audience.NDA), TODAY, Audience.NDA)


# vocabulary ----------------------------------------------------------------
@pytest.mark.parametrize("text,products,classes", [
    ("Is metadata processed by your AI features encrypted?", {"ai-features"}, {"metadata"}),
    ("Does the Model Context Protocol server log requests?", {"mcp"}, set()),
    ("Are LLM prompts stored?", {"ai-features"}, {"prompts"}),
    ("Is our data shared with the data catalogue?", {"catalog"}, {"customer-data"}),
    ("Is customer's data encrypted?", set(), {"customer-data"}),
    ("Do you maintain an approved security policy?", set(), set()),
    ("Is the airline's data said to be rained on?", set(), set()),       # no "ai" inside words
])
def test_detection_is_word_bounded(text, products, classes):
    assert named_products(text) == products and named_data_classes(text) == classes


def test_declared_scope_is_authoritative_and_empty_falls_back_to_own_text():
    declared = mk(products=["catalog"], statement="The catalog and the AI assistant encrypt metadata.")
    assert effective_scope(declared)[0] == {"catalog"}
    legacy = mk(statement="Customer data at rest is encrypted.", scope="Acme production data stores")
    assert effective_scope(legacy) == (set(), {"customer-data"})


def test_exceptions_never_widen_a_claim():
    c = mk(statement="Customer data at rest is encrypted.", exceptions=["Prompts sent to AI features are excluded"])
    assert scope_gaps("Are prompts encrypted at rest?", c) == ["prompts"]


# the gate ------------------------------------------------------------------
def test_catalog_claim_never_answers_an_ai_feature_question(matcher):
    v = verdict(matcher, "Is metadata processed by your AI features encrypted at rest?")
    assert v.outcome == "HOLD_HUMAN" and v.flags == ["PRODUCT_SCOPE_MISMATCH"]
    assert v.claim_id == "catalog.metadata_at_rest" and v.route == "OWNER:raj.mehta@acme.example"
    assert "AI features" in v.gaps[0] and v.answer is None


def test_scope_gate_is_what_stops_it(matcher, monkeypatch):
    """Without the scope gate the same question is answered: the gate is load-bearing."""
    monkeypatch.setattr(gates_mod, "scope_gaps", lambda q, c: [])
    v = verdict(matcher, "Is metadata processed by your AI features encrypted at rest?")
    assert v.outcome == "ANSWER" and v.claim_id == "catalog.metadata_at_rest"


def test_stale_and_audience_are_judged_before_scope():
    c = mk(valid_until=date(2026, 6, 1), products=["catalog"])
    v = gate("Is metadata in your AI assistant encrypted at rest?",
             [Match(claim=c, score=3, coverage=1.0, matched_terms=["metadata", "encrypt", "rest"])],
             TODAY, Audience.NDA)
    assert v.outcome == "REFUSE" and v.flags == ["STALE_CLAIM"]


def test_scoped_claim_answers_its_own_product(matcher):
    v = verdict(matcher, "Is metadata in your data catalog encrypted at rest?")
    assert v.outcome == "ANSWER" and v.claim_id == "catalog.metadata_at_rest"


def test_generic_question_prefers_the_broad_claim_on_a_tie(matcher):
    top = matcher.match("encrypted at rest", TODAY, Audience.NDA)[0]
    assert top.claim.claim_id == "crypto.at_rest"


# model, hash, hygiene ------------------------------------------------------
def test_round_trip_and_legacy_hash_is_unchanged():
    legacy = mk()
    d = legacy.to_dict()
    assert d["products"] == [] and d["deployment"] == "" and d["data_classes"] == []
    old_shape = {k: v for k, v in d.items() if k not in ("products", "deployment", "data_classes")}
    assert Claim.from_dict(old_shape).version_hash() == legacy.version_hash()
    scoped = mk(products=["catalog"], data_classes=["metadata"], deployment="saas-multi-tenant")
    assert scoped.version_hash() != legacy.version_hash()
    back = Claim.from_dict(scoped.to_dict())
    assert back.products == ["catalog"] and back.deployment == "saas-multi-tenant"
    assert back.version_hash() == scoped.version_hash()
    # order of a declared list is not content
    assert mk(data_classes=["prompts", "metadata"]).version_hash() == mk(data_classes=["metadata", "prompts"]).version_hash()


def test_unknown_product_is_refused_at_proposal(tmp_path):
    c = mk(products=["ai-feature"], data_classes=["pii"], deployment="on-prem", status=ClaimStatus.DRAFT)
    problems = c.validate()
    assert any("ai-feature" in p for p in problems) and any("pii" in p for p in problems)
    assert any("on-prem" in p for p in problems)
    with pytest.raises(ValueError):
        FileClaimStore(tmp_path).propose(c, actor="lena.hoff@acme.example", reason="new", today=TODAY)


# Atlan mapping ---------------------------------------------------------------
def test_atlan_payload_carries_product_context():
    c = mk(products=["catalog", "mcp"], data_classes=["metadata"], deployment="saas-multi-tenant")
    cm = to_term_payload(c)["custom_metadata"]["Claim"]
    assert cm["products"] == ["catalog", "mcp"] and cm["data_classes"] == ["metadata"]
    assert cm["deployment"] == "saas-multi-tenant"
    assert {"products", "deployment", "data_classes"} <= set(CM_ATTRIBUTES)
    assert CM_OPTIONS["products"][2] is True and CM_OPTIONS["deployment"][2] is False
    back = from_term_payload(to_term_payload(c))
    assert back.version_hash() == c.version_hash()


def test_atlan_read_accepts_text_and_set_fallbacks():
    p = to_term_payload(mk(products=["catalog"]))
    p["custom_metadata"]["Claim"]["products"] = "catalog, mcp"
    p["custom_metadata"]["Claim"]["data_classes"] = {"prompts", "metadata"}
    back = from_term_payload(p)
    assert back.products == ["catalog", "mcp"] and back.data_classes == ["metadata", "prompts"]
    legacy = to_term_payload(mk())
    for k in ("products", "deployment", "data_classes"):
        legacy["custom_metadata"]["Claim"].pop(k)
    assert from_term_payload(legacy).products == []


def test_setup_plan_names_each_option_set():
    sys.path.insert(0, str(ROOT / "scripts"))
    import atlan_setup
    attrs = {a["name"]: a for a in atlan_setup.plan([], "Security Claims")["custom_metadata_set"]["attributes"]}
    assert attrs["products"]["options_name"] == "constat_products" and attrs["products"]["multi_valued"]
    assert attrs["audience"]["options_name"] == "constat_audience" and not attrs["audience"]["multi_valued"]
    assert "options_name" not in attrs["scope"]


# import flow -----------------------------------------------------------------
def test_import_suggests_scope_and_drafts_a_product_claim(tmp_path):
    spec = json.loads((ROOT / "evals/golden/claims_acme.json").read_text())
    store = FileClaimStore(tmp_path / "claims")
    store.bootstrap([Claim.from_dict(c) for c in spec["claims"]], approver="seed", today=TODAY)
    rows = [RawQuestion(1, "Is metadata processed by your AI features encrypted at rest?", "Cryptography",
                        answer="Yes. Metadata sent to AI features is encrypted at rest with AES-256 in the AI service store.")]
    prev = importer.preview(rows, store, filename="globex.xlsx", customer="Globex", audience=Audience.NDA,
                            actor="priya.nair@acme.example", today=TODAY)
    row = prev.rows[0]
    assert row.action == "new_claim", row
    assert row.products == ["ai-features"] and row.data_classes == ["metadata"]
    assert "different product" in row.reason
    # a stored preview written before these fields existed still loads
    old = prev.to_dict()
    for r in old["rows"]:
        r.pop("products"), r.pop("data_classes")
    assert importer.ImportPreview.from_dict(old).rows[0].products == []
    res = importer.commit(prev, {1: "new_claim"}, store, actor="priya.nair@acme.example", today=TODAY)
    assert res.proposals == 1
    draft = store.pending()[-1].claim
    assert draft.status == ClaimStatus.DRAFT
    assert draft.products == ["ai-features"] and draft.data_classes == ["metadata"]
