"""Deterministic gates. These run regardless of which drafter produced the text.

Design rule from the blueprint (Appendix B): do not rely on the prompt for
tenant isolation, forbidden claims, or approval. The model drafts; the gates
decide what is allowed to leave the system.

Gate order per question:
  pre-gates  (classification): legal-commitment routing, certification-claim tagging
  post-gates (on the draft):   citation-or-abstain, approved-source-only,
                               staleness, contradiction, certification evidence
                               class, then grounding
"""
from __future__ import annotations

import re
from datetime import date

from .evidence import EvidenceStore
from .models import Coverage, Draft, Question, Risk
from .retrieve import STOP, tokens

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

# --- grounding gate ----------------------------------------------------------
# A citation surviving the gates above proves the SOURCE is citable. It does not
# prove the ANSWER says what the source says: a model can attach a legitimate
# source_id to a sentence it invented. This gate closes that hole by requiring
# lexical overlap between the released answer and the text of the chunks it
# cites, using the same tokenizer as retrieval so "a word" means one thing
# everywhere in the system.
#
# Choice of 0.35: an honest questionnaire answer restates the source in the
# answerer's own register, so it legitimately introduces framing words the
# source does not contain ("we", "our platform", the question's own vocabulary,
# the source title and version). Measured across every answerable question in
# the acme evidence set, faithful answers from the deterministic drafter score
# 0.65 to 0.94 (mean 0.82); a heavier paraphrase, which replaces roughly half
# the vocabulary, still lands near 0.5. An answer that is genuinely about other
# content scores 0.0 to 0.15. 0.35 sits in the empty band between those
# populations, roughly half the observed floor for faithful text and well above
# the ceiling for unrelated text. It is deliberately a floor, not a similarity
# score, because the cost of a false refusal here is a queued SME review while
# the cost of a false pass is a fabricated claim in a signed questionnaire.
#
# The 4-token floor exists because the ratio is too coarse to be fair on very
# short answers: a three-word answer with one non-matching word would fail at
# 0.33 for no good reason. Below the floor we require only that at least one
# content word is traceable to the cited text. An answer with no content words
# at all (a bare "Yes.") has nothing lexical to verify and is left to the
# citation gate and the human reviewer.
GROUNDING_MIN_RATIO = 0.35
GROUNDING_MIN_ANSWER_TOKENS = 4


def _content_words(text: str) -> set[str]:
    """retrieve.tokens() is the tokenizer, so "a word" means the same thing here
    as it does in retrieval. Its token pattern keeps trailing punctuation
    ("backups." at the end of a sentence), which would otherwise make the last
    word of every sentence unmatchable purely because the answer and the source
    break their sentences in different places. Trailing separators are stripped
    symmetrically on both sides, and the stopword list is re-applied afterwards
    so that "Yes." is recognised as the stopword it is rather than counted as
    an unsupported content word. Nothing else about the tokenization changes."""
    out = {t.rstrip("./-") for t in tokens(text or "")}
    return {t for t in out if t and len(t) > 1 and t not in STOP}


def grounding_score(answer: str, cited_texts: list[str]) -> tuple[float, int, int]:
    """Returns (ratio, overlapping_tokens, answer_tokens)."""
    a = _content_words(answer)
    cited: set[str] = set()
    for t in cited_texts:
        cited |= _content_words(t)
    if not a:
        return 1.0, 0, 0
    overlap = len(a & cited)
    return overlap / len(a), overlap, len(a)


def is_grounded(answer: str, cited_texts: list[str]) -> tuple[bool, float]:
    ratio, overlap, n = grounding_score(answer, cited_texts)
    if n == 0:
        return True, ratio
    if n < GROUNDING_MIN_ANSWER_TOKENS:
        return overlap >= 1, ratio
    return ratio >= GROUNDING_MIN_RATIO, ratio


def classify(q: Question) -> dict:
    is_cert = bool(CERT_PAT.search(q.text)) and bool(CERT_VERB.search(q.text))
    is_legal = bool(LEGAL_PAT.search(q.text))
    return {"certification_claim": is_cert, "legal_commitment": is_legal}


def pre_gate(q: Question, draft: Draft) -> Draft:
    flags = classify(q)
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


def post_gate(q: Question, draft: Draft, store: EvidenceStore, today: date) -> Draft:
    if draft.route == "LEGAL":
        return draft  # already terminal for automation

    stale = store.stale_ids(today)
    contradicted = store.contradicted_source_ids(today)
    is_cert = "CERT_CLAIM: certification evidence class required" in draft.gate_flags

    kept, gaps = [], []
    for c in draft.citations:
        src = store.sources.get(c.source_id)
        if src is None:
            gaps.append(f"{c.source_id}: unknown source, citation rejected")
            continue
        if not src.is_approved():
            gaps.append(f"{c.source_id}: not approved, citation rejected")
            continue
        if c.source_id in stale:
            gaps.append(
                f"{c.source_id} v{src.version}: EXPIRED {src.expiry_date.isoformat()}, "
                f"cannot support a current-state claim; route to {src.owner}"
            )
            draft.gate_flags.append(f"STALE_EVIDENCE:{c.source_id}")
            continue
        if c.source_id in contradicted:
            gaps.append(
                f"{c.source_id}: conflicting approved sources on a machine-checked assertion, "
                f"route to owners for reconciliation"
            )
            draft.gate_flags.append(f"CONTRADICTION:{c.source_id}")
            continue
        if is_cert and src.type not in CERT_EVIDENCE_TYPES:
            gaps.append(
                f"{c.source_id} (type={src.type}): not a certificate/attestation, "
                f"certification status is never inferred from plans or policies"
            )
            draft.gate_flags.append(f"CERT_INFERENCE_BLOCKED:{c.source_id}")
            continue
        kept.append(c)

    draft.citations = kept
    draft.gaps.extend(gaps)

    # grounding: runs AFTER citation filtering, so it judges the answer only
    # against evidence that is itself releasable. A model can cite a real,
    # approved, in-force source and still have written a sentence that source
    # does not support; that is the case this catches.
    if kept and draft.answer is not None:
        index = {(c.source_id, c.location): c.text for c in store.chunks()}
        cited_texts = [index.get((c.source_id, c.location), c.excerpt) for c in kept]
        grounded, ratio = is_grounded(draft.answer, cited_texts)
        if not grounded:
            draft.gate_flags.append("UNGROUNDED_ANSWER")
            draft.gaps.append(
                f"Answer is not grounded in its cited evidence: only {round(ratio * 100)}% "
                f"of its content words appear in the cited passages (floor "
                f"{round(GROUNDING_MIN_RATIO * 100)}%). Answer withheld; an SME must "
                f"write this one from the source."
            )
            kept = []
            draft.citations = []

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
            elif "UNGROUNDED_ANSWER" in draft.gate_flags:
                draft.route = "SME"
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
    return draft
