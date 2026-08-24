"""Deterministic gates. These run regardless of which drafter produced the text.

Design rule from the blueprint (Appendix B): do not rely on the prompt for
tenant isolation, forbidden claims, or approval. The model drafts; the gates
decide what is allowed to leave the system.

Gate order per question:
  pre-gates  (classification): legal-commitment routing, certification-claim tagging
  post-gates (on the draft):   citation-or-abstain, approved-source-only,
                               staleness, contradiction, certification evidence class
"""
from __future__ import annotations

import re
from datetime import date

from .evidence import EvidenceStore
from .models import AnswerStatus, Coverage, Draft, Question, Risk

# --- classification patterns -------------------------------------------------
# Certification schemes are matched by SHAPE, not by an allowlist of names.
#
# The allowlist version of this pattern shipped knowing ISO 27001, 27017, 27701,
# PCI DSS, HITRUST, FedRAMP, CSA STAR and SOC 2 — and not knowing ISO 42001. A
# question asking whether we were certified to 42001 was therefore never
# classified as a certification claim, and a ROADMAP satisfied it. That is the
# exact failure this system exists to prevent, and it was found on our own trust
# page. Any ISO/IEC number now matches, as do the named schemes; an unknown
# scheme costs at most an unnecessary evidence-class check, while a missing one
# costs a false certification claim to a buyer.
CERT_PAT = re.compile(
    r"\b(iso[\s/]*(?:iec[\s/]*)?\d{4,5}(?:[-:]\d+)?|"
    r"pci[\s-]?dss|hitrust|fedramp|statramp|stateramp|csa\s+star|cyber\s+essentials|"
    r"tisax|irap|c5\b|essential\s+eight|isae\s*3402|ssae\s*1[68]|"
    r"soc\s*[123]\b(?:\s*type\s*(?:i{1,2}|[123]))?|"
    r"nist\s*(?:sp\s*)?800-\d+|cmmc|hipaa|gdpr|dora|nis\s*2)\b",
    re.I,
)
# The verb half of a certification claim. Originally certified/certificate/
# attestation/accredited only, which let "do you HOLD a SOC 2 Type II REPORT"
# through unclassified — a question that is obviously a certification claim to
# any reader. Possession and assurance language now counts too. Over-matching is
# safe here: the only consequence is requiring certificate-class evidence, which
# fails closed.
CERT_VERB = re.compile(
    r"\b(certif(?:y|ied|icate|ication)s?|attest(?:ed|ation)s?|accredit\w+|"
    r"authoriz\w+|authoris\w+|compliant|compliance|"
    r"hold|holds|held|obtain\w*|maintain\w*|"
    r"report|letter|audited|assessed|status|level)\b", re.I)
LEGAL_PAT = re.compile(
    r"\b(unlimited liability|indemnif\w*|contractual(?:ly)? (?:commit|guarantee)|"
    r"financial penalt\w*|liquidated damages|warrant(?:y|ies)\b|guarantee\s+a?\s*\d)",
    re.I,
)

# evidence classes allowed to support a certification/attestation claim
CERT_EVIDENCE_TYPES = {"certificate", "attestation"}

# --- scope patterns ----------------------------------------------------------
# Questions about the system's own configuration, or about parties other than
# the one being answered for. Isolation stops another tenant's DOCUMENTS being
# retrieved, but it does not stop the engine answering "what does Globex's
# policy say?" out of the current tenant's corpus — which silently
# re-attributes one company's control to another. That is a different failure
# from a leak and needs its own gate.
INTROSPECTION_PAT = re.compile(
    r"\b(list|enumerate|show|dump|reveal|name)\b[^.?]{0,50}\b"
    r"(tenants?|workspaces?|clients?|customers?|organi[sz]ations?|corpora|corpus)\b"
    r"|\ball\s+(?:other\s+)?(tenants?|workspaces?|clients?)\b"
    r"|\b(other|another|every)\s+(tenant|workspace|client)('?s)?\b", re.I)


def scope_flag(q: Question, tenant: str, foreign_parties: set[str] | None = None) -> str | None:
    """Name the party a question is actually about, when it is not this one."""
    if INTROSPECTION_PAT.search(q.text):
        return "SYSTEM_CONFIGURATION"
    for party in sorted(foreign_parties or (), key=len, reverse=True):
        if len(party) < 3:
            continue
        if re.search(rf"\b{re.escape(party)}\b", q.text, re.I):
            return party
    return None


def classify(q: Question) -> dict:
    is_cert = bool(CERT_PAT.search(q.text)) and bool(CERT_VERB.search(q.text))
    is_legal = bool(LEGAL_PAT.search(q.text))
    return {"certification_claim": is_cert, "legal_commitment": is_legal}


def pre_gate(q: Question, draft: Draft, tenant: str = "",
             foreign_parties: set[str] | None = None) -> Draft:
    flags = classify(q)
    other = scope_flag(q, tenant, foreign_parties)
    if other:
        subject = ("this system's own configuration" if other == "SYSTEM_CONFIGURATION"
                   else f"'{other}'")
        draft.answer = None
        draft.abstained = True
        draft.citations = []
        draft.evidence_coverage = Coverage.NONE
        draft.risk = Risk.HIGH
        draft.requires_human = True
        draft.route = draft.route or "SME"
        draft.gate_flags.append(f"OUT_OF_SCOPE_PARTY:{other}")
        draft.gaps.append(
            f"Question concerns {subject}, not "
            f"{'this workspace' if not tenant else tenant}. Answering it from this "
            f"workspace's evidence would attribute one party's controls to another; "
            f"refused and routed to a human.")
    if flags["legal_commitment"]:
        draft.answer = None
        draft.abstained = True
        draft.citations = []
        draft.evidence_coverage = Coverage.NONE
        draft.risk = Risk.HIGH
        draft.requires_human = True
        draft.route = "LEGAL"
        draft.gate_flags.append("LEGAL_COMMITMENT: routed to counsel; never drafted as fact")
        draft.gaps.append("Question requests a contractual/legal commitment; outside answerable scope.")
    if flags["certification_claim"]:
        draft.gate_flags.append("CERT_CLAIM: certification evidence class required")
    return draft


def answer_status(draft: Draft) -> AnswerStatus:
    """Derive the published status from what actually survived the gates.

    Ordered so the most restrictive true statement wins. Nothing here consults
    the drafter's opinion of itself; `draft.citations` at this point contains
    only citations the gates kept.
    """
    if draft.route == "LEGAL":
        return AnswerStatus.ROUTED
    if not draft.citations or draft.answer is None or draft.abstained:
        return AnswerStatus.NO_EVIDENCE
    if draft.gaps:
        return AnswerStatus.PARTIAL
    if draft.requires_human:
        return AnswerStatus.REQUIRES_HUMAN
    return AnswerStatus.EVIDENCE_BACKED


def post_gate(q: Question, draft: Draft, store: EvidenceStore, today: date) -> Draft:
    if draft.route == "LEGAL" or any(f.startswith("OUT_OF_SCOPE_PARTY")
                                     for f in draft.gate_flags):
        draft.citations = []
        draft.answer = None
        draft.abstained = True
        draft.evidence_coverage = Coverage.NONE
        draft.status = answer_status(draft)
        return draft  # already terminal for automation

    stale = store.stale_ids(today)
    contradicted = store.contradicted_source_ids(today)
    is_cert = "CERT_CLAIM: certification evidence class required" in draft.gate_flags

    kept, gaps = [], []
    for c in draft.citations:
        src = store.sources.get(c.source_id)
        if src is None:
            gaps.append(f"{c.source_id}: unknown source — citation rejected")
            continue
        if not src.is_approved():
            gaps.append(f"{c.source_id}: not approved — citation rejected")
            continue
        if c.source_id in stale:
            gaps.append(
                f"{c.source_id} v{src.version}: EXPIRED {src.expiry_date.isoformat()} — "
                f"cannot support a current-state claim; route to {src.owner}"
            )
            draft.gate_flags.append(f"STALE_EVIDENCE:{c.source_id}")
            continue
        if c.source_id in contradicted:
            gaps.append(
                f"{c.source_id}: conflicting approved sources on a machine-checked assertion — "
                f"route to owners for reconciliation"
            )
            draft.gate_flags.append(f"CONTRADICTION:{c.source_id}")
            continue
        if is_cert and src.type not in CERT_EVIDENCE_TYPES:
            gaps.append(
                f"{c.source_id} (type={src.type}): not a certificate/attestation — "
                f"certification status is never inferred from plans or policies"
            )
            draft.gate_flags.append(f"CERT_INFERENCE_BLOCKED:{c.source_id}")
            continue
        kept.append(c)

    draft.citations = kept
    draft.gaps.extend(gaps)

    # citation-or-abstain: no surviving citations => no answer leaves the system
    if not kept:
        draft.answer = None
        draft.abstained = True
        draft.evidence_coverage = Coverage.NONE
        draft.requires_human = True
        if draft.route is None:
            if any(f.startswith("CONTRADICTION") for f in draft.gate_flags):
                key_owners = sorted({
                    s.owner for srcs in store.contradictions(today).values() for s in srcs
                })
                draft.route = "SOURCE_OWNER:" + ",".join(key_owners)
            elif any(f.startswith(("STALE_EVIDENCE", "CERT_INFERENCE_BLOCKED")) for f in draft.gate_flags):
                draft.route = "SME"
            else:
                draft.route = "SME"
                draft.gaps.append("No approved evidence retrieved for this question.")
    else:
        draft.evidence_coverage = (
            Coverage.COMPLETE if len(kept) >= 1 and not gaps else Coverage.PARTIAL
        )
        # coverage gaps keep a human in the loop even when something is citable
        draft.requires_human = bool(gaps) or draft.risk == Risk.HIGH or is_cert
    draft.status = answer_status(draft)
    return draft
