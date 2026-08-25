"""Grounding evals: provenance must describe reality, not the model's memory.

The audit finding these cover:

  * both live drafters took `location` and `excerpt` straight from the model,
    so a model could attach a real source_id to a sentence it invented and the
    run report would print that invention in the provenance strip;
  * `unsupported_material_claims` was structurally unreachable, so the release
    metric asserted a constant rather than measuring anything.

These tests drive the real live-drafter code path (GeminiDrafter.draft) with a
stubbed transport, so the citation resolver, the excerpt cap and the grounding
gate are exercised exactly as they run in production.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from constat import drafter as drafter_mod
from constat.drafter import (MAX_EXCERPT_CHARS, GeminiDrafter, MockDrafter,
                              clip_excerpt)
from constat.evidence import EvidenceStore
from constat.gates import (GROUNDING_MIN_RATIO, is_grounded, post_gate,
                            pre_gate)
from constat.models import Draft, Question
from constat.pipeline import run
from constat.retrieve import Retriever

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "data" / "evidence"
QNR = ROOT / "data" / "questionnaires" / "acme_security_questionnaire.xlsx"
TODAY = date(2026, 8, 8)

ENCRYPTION_Q = Question(question_id="G-01", row=4, domain="Encryption",
                        text="Is customer data encrypted at rest and in transit?")


@pytest.fixture(scope="module")
def store():
    return EvidenceStore("acme", EVIDENCE)


@pytest.fixture(scope="module")
def retriever(store):
    return Retriever(store)


@pytest.fixture()
def live(retriever, monkeypatch):
    """A real GeminiDrafter whose only stub is the network call."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-used")
    d = GeminiDrafter(retriever)
    d.min_interval = 0.0
    return d


def stub_response(d: GeminiDrafter, payload: dict, capture: dict | None = None):
    def _generate(user_msg: str) -> str:
        if capture is not None:
            capture["prompt"] = user_msg
        return json.dumps(payload)
    d._generate = _generate          # type: ignore[method-assign]


def top_hit(retriever, q: Question):
    return retriever.search(q.text, tenant="acme", k=4)[0]


# --- (a) citations are resolved against what was actually retrieved ----------
def test_fabricated_source_id_is_dropped(live, retriever, store):
    stub_response(live, {
        "answer": "Yes, customer data is encrypted at rest with AES-256.",
        "citations": [{"source_id": "POL-DOES-NOT-EXIST-9000", "location": "para:2",
                       "excerpt": "All customer data is encrypted."}],
        "abstained": False, "gaps": [], "risk": "low",
    })
    d = live.draft(ENCRYPTION_Q, "acme")
    assert d.citations == [], "a source that was never retrieved cannot be cited"
    assert "FABRICATED_CITATION" in d.gate_flags
    assert any("not among the excerpts retrieved" in g for g in d.gaps)

    # and citation-or-abstain then withholds the answer entirely
    d = post_gate(ENCRYPTION_Q, d, store, TODAY)
    assert d.abstained and d.answer is None and d.requires_human


def test_real_source_with_hallucinated_location_is_dropped(live, retriever, store):
    hit = top_hit(retriever, ENCRYPTION_Q)
    stub_response(live, {
        "answer": "Yes, encryption is applied everywhere.",
        "citations": [{"source_id": hit.chunk.source_id, "location": "para:9999",
                       "excerpt": "Fabricated supporting sentence."}],
        "abstained": False, "gaps": [], "risk": "low",
    })
    d = live.draft(ENCRYPTION_Q, "acme")
    assert d.citations == []
    assert "HALLUCINATED_LOCATION" in d.gate_flags
    assert any("does not exist in the source document" in g for g in d.gaps)

    d = post_gate(ENCRYPTION_Q, d, store, TODAY)
    assert d.abstained and d.answer is None


def test_retrieved_source_but_unretrieved_passage_is_dropped(live, retriever):
    """A location that exists in the store but was not shown to the drafter."""
    hits = retriever.search(ENCRYPTION_Q.text, tenant="acme", k=4)
    shown = {(h.chunk.source_id, h.chunk.location) for h in hits}
    sid = hits[0].chunk.source_id
    unseen = next(
        (c.location for c in retriever.store.chunks()
         if c.source_id == sid and (sid, c.location) not in shown), None)
    if unseen is None:
        pytest.skip("every chunk of the top source was retrieved for this question")
    stub_response(live, {
        "answer": "Yes.", "citations": [{"source_id": sid, "location": unseen,
                                         "excerpt": "invented"}],
        "abstained": False, "gaps": [], "risk": "low",
    })
    d = live.draft(ENCRYPTION_Q, "acme")
    assert d.citations == []
    assert "UNRETRIEVED_CITATION" in d.gate_flags


# --- (b) the model never authors an excerpt ---------------------------------
def test_model_excerpt_is_replaced_with_real_chunk_text(live, retriever):
    hit = top_hit(retriever, ENCRYPTION_Q)
    lie = "Acme guarantees quantum-resistant encryption certified by the NSA."
    stub_response(live, {
        "answer": "Data at rest is encrypted with AES-256 and TLS protects data in transit.",
        "citations": [{"source_id": hit.chunk.source_id,
                       "location": hit.chunk.location, "excerpt": lie}],
        "abstained": False, "gaps": [], "risk": "low",
    })
    d = live.draft(ENCRYPTION_Q, "acme")
    assert len(d.citations) == 1
    c = d.citations[0]
    assert lie not in c.excerpt, "model prose must never reach the provenance strip"
    assert c.excerpt, "the citation must carry the customer's own text"
    assert c.excerpt.rstrip(" …") in " ".join(hit.chunk.text.split())
    assert c.version == retriever.store.sources[c.source_id].version


def test_duplicate_citations_collapse(live, retriever):
    hit = top_hit(retriever, ENCRYPTION_Q)
    cite = {"source_id": hit.chunk.source_id, "location": hit.chunk.location,
            "excerpt": "x"}
    stub_response(live, {"answer": "Encryption is in place.",
                         "citations": [cite, dict(cite)],
                         "abstained": False, "gaps": [], "risk": "low"})
    d = live.draft(ENCRYPTION_Q, "acme")
    assert len(d.citations) == 1


# --- item 2: excerpt caps on the paths that leave the machine ---------------
def test_evidence_block_is_capped_and_receipted(live, retriever):
    capture: dict = {}
    hit = top_hit(retriever, ENCRYPTION_Q)
    stub_response(live, {"answer": None, "citations": [], "abstained": True,
                         "gaps": ["none"], "risk": "low"}, capture=capture)
    d = live.draft(ENCRYPTION_Q, "acme")
    hits = retriever.search(ENCRYPTION_Q.text, tenant="acme", k=4)
    for h in hits:
        # no chunk may appear in the prompt beyond the cap
        assert clip_excerpt(h.chunk.text) in capture["prompt"]
        if len(h.chunk.text) > MAX_EXCERPT_CHARS:
            assert h.chunk.text not in capture["prompt"]
    receipt = [f for f in d.gate_flags if f.startswith("EVIDENCE_CHARS:")]
    assert receipt, "every live draft must receipt what it transmitted"
    assert int(receipt[0].split(":")[1]) == len(capture["prompt"].split(
        "APPROVED EXCERPTS:\n", 1)[1])
    assert hit is not None


def test_clip_excerpt_never_cuts_mid_word():
    long = ("Customer content is deleted from production systems. " * 60)
    out = clip_excerpt(long, 100)
    assert len(out) <= 102
    assert out.endswith("…")
    body = out.rstrip(" …")
    assert long.startswith(body), "clip must be a prefix of the source text"
    assert not body or body[-1] not in "abcdefghijklmnopqrstuvwxyz" or \
        long[len(body)] in " ."


def test_short_text_is_returned_untouched():
    assert clip_excerpt("Short paragraph.", 100) == "Short paragraph."


# --- (c) the grounding gate --------------------------------------------------
def test_answer_with_no_overlap_is_refused(live, retriever, store):
    hit = top_hit(retriever, ENCRYPTION_Q)
    stub_response(live, {
        # cites a real, approved, in-force, retrieved passage; says something
        # that passage does not remotely support
        "answer": ("Acme's regional marketing team schedules quarterly webinars "
                   "for prospective buyers across Latin America."),
        "citations": [{"source_id": hit.chunk.source_id,
                       "location": hit.chunk.location, "excerpt": "irrelevant"}],
        "abstained": False, "gaps": [], "risk": "low",
    })
    d = live.draft(ENCRYPTION_Q, "acme")
    assert d.citations, "citation itself is legitimate; only the answer is not"

    d = post_gate(ENCRYPTION_Q, d, store, TODAY)
    assert "UNGROUNDED_ANSWER" in d.gate_flags
    assert d.answer is None and d.abstained
    assert d.citations == []
    assert d.route == "SME" and d.requires_human
    assert any("not grounded in its cited evidence" in g for g in d.gaps)


def test_faithful_answer_survives_the_grounding_gate(live, retriever, store):
    hit = top_hit(retriever, ENCRYPTION_Q)
    stub_response(live, {
        "answer": f"Per the approved standard: {hit.chunk.text[:220]}",
        "citations": [{"source_id": hit.chunk.source_id,
                       "location": hit.chunk.location, "excerpt": "x"}],
        "abstained": False, "gaps": [], "risk": "low",
    })
    d = live.draft(ENCRYPTION_Q, "acme")
    d = post_gate(ENCRYPTION_Q, d, store, TODAY)
    assert "UNGROUNDED_ANSWER" not in d.gate_flags
    assert d.answer and d.citations


def test_grounding_threshold_boundaries():
    chunk = ("Data at rest is encrypted with AES-256 across databases, object "
             "storage and backups.")
    ok, ratio = is_grounded("Data at rest is encrypted with AES-256.", [chunk])
    assert ok and ratio >= GROUNDING_MIN_RATIO
    ok, ratio = is_grounded("Weekly pizza budgets are approved by facilities.", [chunk])
    assert not ok and ratio < GROUNDING_MIN_RATIO
    # short-answer floor: one traceable content word is enough
    assert is_grounded("AES-256.", [chunk])[0]
    # an answer with no content words at all has nothing lexical to check
    assert is_grounded("Yes.", [chunk])[0]


def test_mock_drafter_answer_passes_untouched(retriever, store):
    q = Question(question_id="G-02", row=4, domain="Encryption",
                 text="Is data at rest encrypted?")
    d = MockDrafter(retriever).draft(q, "acme")
    assert d.answer, "positive control: the deterministic drafter answers this"
    before = (d.answer, [(c.source_id, c.location, c.excerpt) for c in d.citations])
    d = post_gate(q, d, store, TODAY)
    assert "UNGROUNDED_ANSWER" not in d.gate_flags
    assert d.answer == before[0]
    assert [(c.source_id, c.location, c.excerpt) for c in d.citations] == before[1]


def test_grounding_runs_after_citation_filtering(store, retriever):
    """A citation killed by staleness must not be able to ground an answer."""
    q = Question(question_id="G-03", row=4, domain="Testing",
                 text="Have you completed a penetration test in the last 12 months?")
    d = MockDrafter(retriever).draft(q, "acme")
    d = post_gate(q, d, store, TODAY)
    assert d.abstained
    assert any(f.startswith("STALE_EVIDENCE") for f in d.gate_flags)
    # the stale route wins; grounding never gets to relabel a stale refusal
    assert "UNGROUNDED_ANSWER" not in d.gate_flags


# --- (d) T1-T6 are unchanged by any of the above ----------------------------
@pytest.fixture(scope="module")
def constitution_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("grounding_run")
    return run(QNR, tenant="acme", evidence_root=EVIDENCE, out_dir=out,
               drafter_kind="mock", today=TODAY)


def test_t1_certification_still_never_inferred(constitution_run):
    d = constitution_run.drafts["A&A-02.1"]
    assert d.abstained and d.answer is None and not d.citations
    assert any("CERT" in f for f in d.gate_flags)


def test_t2_contradiction_still_routes_to_owners(constitution_run):
    d = constitution_run.drafts["DSP-01.1"]
    assert d.abstained
    assert any(f.startswith("CONTRADICTION") for f in d.gate_flags)
    assert d.route and d.route.startswith("SOURCE_OWNER:")


def test_t3_stale_evidence_still_quarantined(constitution_run):
    d = constitution_run.drafts["AIS-01.1"]
    assert d.abstained and d.answer is None
    assert any(f.startswith("STALE_EVIDENCE:RPT-PEN-2024") for f in d.gate_flags)


def test_t4_legal_still_routed_before_drafting(constitution_run):
    d = constitution_run.drafts["LGL-01.1"]
    assert d.route == "LEGAL" and d.answer is None and not d.citations


def test_t5_tenant_isolation_still_holds(retriever):
    hits = retriever.search("multi-factor authentication encryption risk assessment",
                            tenant="acme", k=10)
    assert hits and all(h.chunk.tenant == "acme" for h in hits)
    with pytest.raises(PermissionError):
        retriever.search("anything", tenant="globex")


def test_t6_and_p1_positive_control_intact(constitution_run):
    d = constitution_run.drafts["A&A-01.1"]
    assert not d.abstained and d.answer
    assert any(c.source_id == "CRT-SOC2-2025" for c in d.citations)
    assert constitution_run.delivered_xlsx.exists()
    assert constitution_run.metrics["unsupported_material_claims"] == 0


def test_pre_gate_untouched_by_grounding():
    q = Question(question_id="G-04", row=4, domain="Legal",
                 text="Will you accept unlimited liability for a security breach?")
    d = pre_gate(q, Draft(question_id=q.question_id, answer=None))
    assert d.route == "LEGAL"


def test_module_exposes_the_cap():
    assert drafter_mod.MAX_EXCERPT_CHARS == 1200
