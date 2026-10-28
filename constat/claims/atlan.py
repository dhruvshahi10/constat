"""Atlan-backed claim store: the same ClaimStore interface over glossary terms
and custom metadata, through pyatlan.

Mapping (every target verified on docs.atlan.com, 28 Oct 2026):
    claim_id            -> AtlasGlossaryTerm.name (inside one glossary, e.g. "Security Claims")
    statement           -> term.user_description
    owner               -> term.owner_users = [owner]
    status              -> term.certificate_status: DRAFT | VERIFIED | DEPRECATED
    framework_map       -> Atlan tags (one tag per framework control), or glossary categories
    scope, exceptions, audience, valid_from, valid_until, version, evidence_refs,
    keywords, topics, approved_answers
                        -> custom metadata set "Claim" (attribute types below)

Custom metadata set "Claim":
    scope               Text
    exceptions          Text (JSON array)      -- the completeness gate reads this
    audience            Options {public, nda, internal}
    valid_from          Date
    valid_until         Date
    version             Integer
    evidence_refs       Text (JSON array of {kind, ref, checked_on})
    keywords            Text (comma separated)
    topics              Text (comma separated)
    approved_answers    Rich text (JSON array)  -- the reuse corpus
    version_hash        Text                    -- content hash, recomputed on write

What stays outside Atlan: the gates, the matcher, the review queue and the
sent-answer log. Atlan holds the facts; this code decides what may leave.

Write semantics: propose() stores the proposal locally (a term is not written);
approve() performs the pyatlan save. This mirrors Atlan's own MCP write tools,
which return a preview and wait for approval.

pyatlan is imported lazily. Without it the class can still be constructed for
mapping and dry runs: to_term_payload() is pure and testable.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

from .models import Audience, Claim, ClaimStatus, EvidenceRef, Proposal
from .store import ClaimStore, FileClaimStore, SentAnswerRecord

CM_SET = "Claim"
CM_ATTRIBUTES = {
    "scope": "Text", "exceptions": "Text", "audience": "Options", "valid_from": "Date",
    "valid_until": "Date", "version": "Integer", "evidence_refs": "Text",
    "keywords": "Text", "topics": "Text", "approved_answers": "Rich text",
    "version_hash": "Text",
}
CERT_FOR_STATUS = {ClaimStatus.DRAFT: "DRAFT", ClaimStatus.VERIFIED: "VERIFIED",
                   ClaimStatus.DEPRECATED: "DEPRECATED"}
STATUS_FOR_CERT = {v: k for k, v in CERT_FOR_STATUS.items()}


def to_term_payload(claim: Claim) -> dict:
    """The glossary term plus custom metadata a claim becomes. Pure."""
    return {
        "name": claim.claim_id,
        "user_description": claim.statement,
        "owner_users": [claim.owner],
        "certificate_status": CERT_FOR_STATUS[claim.status],
        "atlan_tags": list(claim.framework_map),
        "custom_metadata": {
            CM_SET: {
                "scope": claim.scope,
                "exceptions": json.dumps(claim.exceptions, ensure_ascii=False),
                "audience": claim.audience.value,
                "valid_from": claim.valid_from.isoformat(),
                "valid_until": claim.valid_until.isoformat(),
                "version": claim.version,
                "evidence_refs": json.dumps(
                    [{"kind": e.kind, "ref": e.ref,
                      "checked_on": e.checked_on.isoformat() if e.checked_on else None}
                     for e in claim.evidence_refs], ensure_ascii=False),
                "keywords": ",".join(claim.keywords),
                "topics": ",".join(claim.topics),
                "approved_answers": json.dumps(
                    [{"question": a.question, "answer": a.answer, "approver": a.approver,
                      "approved_on": a.approved_on.isoformat(), "audience": a.audience.value,
                      "claim_version_hash": a.claim_version_hash}
                     for a in claim.approved_answers], ensure_ascii=False),
                "version_hash": claim.version_hash(),
            }
        },
    }


def from_term_payload(p: dict) -> Claim:
    """Inverse of to_term_payload(), for reads. Pure."""
    cm = p["custom_metadata"][CM_SET]
    d = {
        "claim_id": p["name"], "statement": p.get("user_description", ""),
        "owner": (p.get("owner_users") or [""])[0],
        "status": STATUS_FOR_CERT[p.get("certificate_status", "DRAFT")].value,
        "framework_map": list(p.get("atlan_tags", [])),
        "scope": cm.get("scope", ""), "exceptions": json.loads(cm.get("exceptions") or "[]"),
        "audience": cm.get("audience", "nda"), "valid_from": cm["valid_from"],
        "valid_until": cm["valid_until"], "version": int(cm.get("version", 1)),
        "evidence_refs": json.loads(cm.get("evidence_refs") or "[]"),
        "keywords": [k for k in (cm.get("keywords") or "").split(",") if k],
        "topics": [t for t in (cm.get("topics") or "").split(",") if t],
        "approved_answers": json.loads(cm.get("approved_answers") or "[]"),
    }
    return Claim.from_dict(d)


class AtlanClaimStore(ClaimStore):
    """Glossary-backed store. Proposals and the sent-answer log live in a local
    FileClaimStore side-car because Atlan has no proposal object and a sent
    answer is a security-team record, not a catalog asset."""

    def __init__(self, glossary_name: str, sidecar_root: Path, client=None):
        self.glossary_name = glossary_name
        self._side = FileClaimStore(sidecar_root)
        self._client = client

    # ---- pyatlan boundary ------------------------------------------------
    def _atlan(self):
        if self._client is None:
            try:
                from pyatlan.client.atlan import AtlanClient  # type: ignore
            except ImportError as e:  # pragma: no cover - depends on environment
                raise RuntimeError(
                    "pyatlan is not installed. The Atlan backend needs `pip install pyatlan` "
                    "and ATLAN_BASE_URL / ATLAN_API_KEY. The file backend works without it."
                ) from e
            self._client = AtlanClient()
        return self._client

    def list(self) -> list[Claim]:
        client = self._atlan()
        from pyatlan.model.assets import AtlasGlossaryTerm  # type: ignore
        from pyatlan.model.fluent_search import FluentSearch  # type: ignore
        req = (FluentSearch().where(FluentSearch.active_assets())
               .where(FluentSearch.asset_type(AtlasGlossaryTerm))
               .where(AtlasGlossaryTerm.ANCHOR.eq(self._glossary_qn(client)))
               .include_on_results(AtlasGlossaryTerm.USER_DESCRIPTION)
               .include_on_results(AtlasGlossaryTerm.OWNER_USERS)
               .include_on_results(AtlasGlossaryTerm.CERTIFICATE_STATUS)
               .include_on_results(AtlasGlossaryTerm.ATLAN_TAGS)
               .include_on_results(AtlasGlossaryTerm.CUSTOM_METADATA)).to_request()
        out = []
        for term in client.asset.search(req):
            out.append(self._term_to_claim(term))
        return out

    def get(self, claim_id: str) -> Optional[Claim]:
        for c in self.list():
            if c.claim_id == claim_id:
                return c
        return None

    def propose(self, claim: Claim, actor: str, reason: str, today: date) -> Proposal:
        return self._side.propose(claim, actor, reason, today)

    def approve(self, proposal_id: str, approver: str, today: date) -> Claim:
        claim = self._side.approve(proposal_id, approver, today)
        self._save_term(claim)
        return claim

    def reject(self, proposal_id: str, approver: str, today: date, reason: str = "") -> Proposal:
        return self._side.reject(proposal_id, approver, today, reason)

    def pending(self) -> list[Proposal]:
        return self._side.pending()

    def record_sent_answer(self, rec: SentAnswerRecord) -> None:
        self._side.record_sent_answer(rec)

    def sent_answers(self) -> list[SentAnswerRecord]:
        return self._side.sent_answers()

    # ---- internals -------------------------------------------------------
    def _glossary_qn(self, client) -> str:
        from pyatlan.model.assets import AtlasGlossary  # type: ignore
        g = client.asset.find_glossary_by_name(self.glossary_name)
        return g.qualified_name

    def _save_term(self, claim: Claim) -> None:
        client = self._atlan()
        from pyatlan.model.assets import AtlasGlossaryTerm  # type: ignore
        from pyatlan.model.enums import CertificateStatus  # type: ignore
        from pyatlan.model.custom_metadata import CustomMetadataDict  # type: ignore
        payload = to_term_payload(claim)
        glossary_qn = self._glossary_qn(client)
        existing = None
        try:
            existing = client.asset.find_term_by_name(claim.claim_id, glossary_qn)
        except Exception:  # noqa: BLE001 - not found
            existing = None
        term = (AtlasGlossaryTerm.updater(existing.qualified_name, existing.name, existing.anchor.guid)
                if existing else
                AtlasGlossaryTerm.creator(name=claim.claim_id, glossary_qualified_name=glossary_qn))
        term.user_description = payload["user_description"]
        term.owner_users = set(payload["owner_users"])
        term.certificate_status = CertificateStatus[payload["certificate_status"]]
        cm = CustomMetadataDict(client=client, name=CM_SET)
        for k, v in payload["custom_metadata"][CM_SET].items():
            cm[k] = v
        term.set_custom_metadata(client=client, custom_metadata=cm)
        client.asset.save(term)

    def _term_to_claim(self, term) -> Claim:
        cm_all = {}
        try:
            cm_all = {CM_SET: dict(term.get_custom_metadata(client=self._client, name=CM_SET))}
        except Exception:  # noqa: BLE001 - missing set means an unmanaged term
            cm_all = {CM_SET: {}}
        payload = {
            "name": term.name, "user_description": term.user_description or "",
            "owner_users": sorted(term.owner_users or []),
            "certificate_status": (term.certificate_status.value if term.certificate_status else "DRAFT"),
            "atlan_tags": [t.type_name for t in (term.atlan_tags or [])],
            "custom_metadata": cm_all,
        }
        return from_term_payload(payload)
