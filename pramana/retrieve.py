"""Lexical retrieval over the tenant evidence store.

v0 is deliberately embedding-free: token overlap + topic boost is transparent,
reproducible, and sufficient for a bounded questionnaire domain. The semantic
index is a v1 upgrade (see docs/PRAMANA_V0.md), and swapping it in does not
change the gates — which is the point.

Invariant enforced here: every returned chunk belongs to the requesting
tenant. A violation raises rather than degrades.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .evidence import EvidenceStore
from .models import Chunk

STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "is", "are", "do",
    "does", "you", "your", "with", "on", "at", "by", "if", "state", "provide",
    "specify", "summarize", "yes", "no", "any", "all", "what", "how", "many",
    "which", "will", "be", "from", "it", "its", "we", "our",
}


def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9][a-z0-9\-/\.]*", text.lower()) if t not in STOP and len(t) > 1}


@dataclass
class Hit:
    chunk: Chunk
    score: float


class Retriever:
    def __init__(self, store: EvidenceStore):
        self.store = store
        self._chunks = store.chunks()

    def search(self, query: str, tenant: str, k: int = 4) -> list[Hit]:
        if tenant != self.store.tenant:
            raise PermissionError(
                f"tenant mismatch: store is '{self.store.tenant}', query is '{tenant}'"
            )
        q = tokens(query)
        hits: list[Hit] = []
        for ch in self._chunks:
            overlap = len(q & tokens(ch.text))
            if overlap == 0:
                continue
            src = self.store.sources[ch.source_id]
            topic_boost = sum(1.5 for t in src.topics if t in query.lower())
            hits.append(Hit(chunk=ch, score=overlap + topic_boost))
        hits.sort(key=lambda h: h.score, reverse=True)
        for h in hits[:k]:
            # belt-and-braces: the isolation invariant, asserted at the boundary
            assert h.chunk.tenant == tenant, "cross-tenant chunk leaked past store scoping"
        return hits[:k]
