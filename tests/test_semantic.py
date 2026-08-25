"""Evals (b) and (d): cross-tenant index isolation, and the IVS-01.1 flip
with zero regressions on the planted traps.

These run with the always-available HashedNgramEmbedder. When fastembed and
its model cache are present (the Docker image), the same assertions run again
under the production model via the `semantic` marker parametrization.
"""
from datetime import date
from pathlib import Path

import pytest

from constat.evidence import EvidenceStore
from constat.pipeline import run
from constat.semantic import (HashedNgramEmbedder, SemanticRetriever,
                               build_index, best_embedder)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "data" / "evidence"
QNR = ROOT / "data" / "questionnaires" / "acme_security_questionnaire.xlsx"
TODAY = date(2026, 8, 8)


def _embedders():
    yield HashedNgramEmbedder()
    prod = best_embedder()
    if not isinstance(prod, HashedNgramEmbedder):
        yield prod


# --- (b) cross-tenant index isolation ---------------------------------------
@pytest.fixture()
def two_tenants(tmp_path):
    """Two tenants with deliberately similar text."""
    for tenant, sid in (("alpha", "POL-A"), ("beta", "POL-B")):
        d = tmp_path / "evidence" / tenant
        d.mkdir(parents=True)
        (d / f"{sid}.md").write_text(f"""---
source_id: {sid}
title: Information Security Policy
type: policy
version: "1.0"
effective_date: 2026-01-01
expiry_date: 2027-01-01
owner: sec@{tenant}.example
approval_status: approved
topics: hosting, cloud provider
---

Production infrastructure is hosted on Amazon Web Services in us-east-1.
""", encoding="utf-8")
    return tmp_path


def test_cross_tenant_index_isolation(two_tenants, tmp_path):
    emb = HashedNgramEmbedder()
    stores = {t: EvidenceStore(t, two_tenants / "evidence") for t in ("alpha", "beta")}
    idx = {t: tmp_path / "idx" / t for t in ("alpha", "beta")}
    for t in ("alpha", "beta"):
        build_index(stores[t], idx[t], emb)

    r = SemanticRetriever(stores["alpha"], idx["alpha"], emb)
    hits = r.search("Where is data hosted?", "alpha", k=10)
    assert hits and all(h.chunk.tenant == "alpha" for h in hits)

    # querying with the wrong tenant name raises, never filters silently
    with pytest.raises(PermissionError):
        r.search("Where is data hosted?", "beta", k=10)

    # a store pointed at tenant B cannot open tenant A's index
    with pytest.raises(PermissionError):
        SemanticRetriever(stores["beta"], idx["alpha"], emb)


def test_tampered_index_meta_raises(two_tenants, tmp_path):
    import json
    emb = HashedNgramEmbedder()
    store_a = EvidenceStore("alpha", two_tenants / "evidence")
    idx = tmp_path / "idx-a"
    build_index(store_a, idx, emb)
    raw = json.loads((idx / "index.json").read_text())
    raw["tenant"] = "beta"  # attacker restamps the index
    (idx / "index.json").write_text(json.dumps(raw))
    store_b = EvidenceStore("beta", two_tenants / "evidence")
    with pytest.raises((PermissionError, ValueError)):
        SemanticRetriever(store_b, idx, emb)  # corpus/tenant checks refuse


def test_stale_index_refused(two_tenants, tmp_path):
    emb = HashedNgramEmbedder()
    store = EvidenceStore("alpha", two_tenants / "evidence")
    idx = tmp_path / "idx"
    build_index(store, idx, emb)
    # evidence changes after the index was built
    extra = two_tenants / "evidence" / "alpha" / "POL-NEW.md"
    extra.write_text((two_tenants / "evidence" / "alpha" / "POL-A.md")
                     .read_text().replace("POL-A", "POL-NEW"), encoding="utf-8")
    fresh = EvidenceStore("alpha", two_tenants / "evidence")
    with pytest.raises(ValueError, match="stale"):
        SemanticRetriever(fresh, idx, emb)


# --- (d) the flip, with zero regressions -------------------------------------
@pytest.mark.parametrize("embedder", list(_embedders()), ids=lambda e: e.name)
def test_ivs_flips_and_traps_hold(embedder, tmp_path):
    store = EvidenceStore("acme", EVIDENCE)
    idx = tmp_path / "idx"
    build_index(store, idx, embedder)
    retriever = SemanticRetriever(store, idx, embedder)
    res = run(QNR, tenant="acme", evidence_root=EVIDENCE, out_dir=tmp_path / "run",
              drafter_kind="mock", today=TODAY, retriever=retriever)
    d = res.drafts

    # THE FLIP: hosting question is now cited to the subprocessor list
    ivs = d["IVS-01.1"]
    assert not ivs.abstained, "IVS-01.1 must flip from retrieval miss to cited"
    assert any(c.source_id == "LST-SUBPROC-001" for c in ivs.citations)

    # traps unmoved (T1 to T4 semantics)
    assert d["A&A-02.1"].abstained and not d["A&A-02.1"].citations       # cert
    assert d["DSP-01.1"].abstained                                       # contradiction
    assert any(f.startswith("CONTRADICTION") for f in d["DSP-01.1"].gate_flags)
    assert d["AIS-01.1"].abstained                                       # stale pentest
    assert any(f.startswith("STALE") for f in d["AIS-01.1"].gate_flags)
    assert d["LGL-01.1"].route == "LEGAL"                                # legal

    # release gate and chain
    assert res.metrics["unsupported_material_claims"] == 0
    assert res.metrics["audit_chain_valid"] is True
    # coverage strictly better than the lexical baseline (17/24)
    assert res.metrics["cited_draft_coverage"] > 17 / 24


def test_junk_query_still_fails_closed(tmp_path):
    emb = HashedNgramEmbedder()
    store = EvidenceStore("acme", EVIDENCE)
    build_index(store, tmp_path, emb)
    r = SemanticRetriever(store, tmp_path, emb)
    hits = r.search("llama grooming schedule for the office alpaca", "acme", k=4)
    assert all(h.score < 3.0 for h in hits), "junk must stay under the drafter threshold"
