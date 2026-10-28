"""Claims layer: the owned, expiring, exception-carrying claim as the core object.

Constat v0 answered from document chunks. This layer answers from claims:
one atomic fact each, with a named owner, an evidence pointer, scope and
exceptions, an audience, a validity window and a version. Questions are
matched to claims, not to paragraphs, and the gates in `claims.gates` decide
whether a drafted answer may leave the system.

The store is an interface (`ClaimStore`) with two backends: a file-backed
store for development and demos, and an Atlan-backed store (glossary terms
plus custom metadata through pyatlan) that is a swap, not a rewrite.
"""
from .models import (Audience, ApprovedAnswer, Claim, ClaimStatus, DifficultyClass,
                     EvidenceRef, Proposal)
from .store import ClaimStore, FileClaimStore

__all__ = ["Audience", "ApprovedAnswer", "Claim", "ClaimStatus", "ClaimStore",
           "DifficultyClass", "EvidenceRef", "FileClaimStore", "Proposal"]
