"""Match a question to claims, not to document chunks.

Lexical and deterministic for v1, through the same tokenizer as retrieval so
"a word" means one thing everywhere. A claim's bag of words is its statement,
scope, keywords, topics and the questions of its approved answers; a question
that matches an approved answer's question closely enough is a REUSE hit and
carries that answer verbatim.

Confidence here is computed, never taken from a model. The matcher ranks;
`claims.gates` decides.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from ..retrieve import tokens
from .models import ApprovedAnswer, Audience, Claim
from .store import ClaimStore

GENERIC = {"customer", "data", "security", "please", "describe", "organization",
           "organisation", "company", "vendor", "policy", "process", "control",
           "controls", "place", "describe", "explain", "detail", "details"}
REUSE_MIN_JACCARD = 0.6


def _stem(t: str) -> str:
    """Tiny, symmetric suffix stripping so patch/patches/patching agree. Applied
    to both sides of every comparison, so it can only merge, never split."""
    for suf in ("ing", "ies", "es", "ed", "s"):
        if len(t) > 4 and t.endswith(suf):
            base = t[: -len(suf)] + ("y" if suf == "ies" else "")
            return base
    return t


def key_terms(text: str) -> set[str]:
    out = {_stem(t.rstrip("./-?")) for t in tokens(text or "")}
    return {t for t in out if t and len(t) > 2 and t not in GENERIC}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def claim_bag(c: Claim) -> set[str]:
    bag = key_terms(c.statement) | key_terms(c.scope) | {_stem(k.lower()) for k in c.keywords}
    bag |= {_stem(t.lower()) for t in c.topics}
    for a in c.approved_answers:
        bag |= key_terms(a.question)
    return bag


@dataclass
class Match:
    claim: Claim
    score: float                        # ranking score, not a probability
    coverage: float                     # share of the question's key terms the claim bag covers
    reused: Optional[ApprovedAnswer] = None
    matched_terms: list[str] = field(default_factory=list)


class ClaimMatcher:
    def __init__(self, store: ClaimStore):
        self.store = store

    def match(self, question: str, today: date, audience: Audience, k: int = 3,
              include_unusable: bool = True) -> list[Match]:
        """Ranked matches. Unusable claims (draft, stale, deprecated, wrong
        audience) are still returned by default so the gate can name the
        reason and route to the owner, rather than treating a known-but-stale
        fact as a novel question."""
        q = key_terms(question)
        out: list[Match] = []
        for c in self.store.list():
            if not include_unusable and not c.is_usable(today, audience)[0]:
                continue
            bag = claim_bag(c)
            hit = q & bag
            if not hit:
                continue
            coverage = len(hit) / len(q) if q else 0.0
            topic_boost = sum(1.0 for t in c.topics if t.lower() in question.lower())
            reused = self._reuse(question, c)
            score = len(hit) + topic_boost + (5.0 if reused else 0.0)
            out.append(Match(claim=c, score=score, coverage=coverage, reused=reused,
                             matched_terms=sorted(hit)))
        out.sort(key=lambda m: (m.score, m.coverage), reverse=True)
        return out[:k]

    @staticmethod
    def _reuse(question: str, c: Claim) -> Optional[ApprovedAnswer]:
        q = key_terms(question)
        best, best_j = None, 0.0
        for a in c.approved_answers:
            j = jaccard(q, key_terms(a.question))
            if j > best_j:
                best, best_j = a, j
        return best if best_j >= REUSE_MIN_JACCARD else None
