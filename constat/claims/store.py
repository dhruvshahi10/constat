"""Claim stores.

`ClaimStore` is the interface the matcher, gates and surfaces depend on.
`FileClaimStore` is the development backend: one JSON file per claim, a
proposals file, and an append-only answer log. `constat.claims.atlan` holds
the Atlan backend, which maps the same interface onto glossary terms and
custom metadata through pyatlan.

Write semantics are the same in both backends, on purpose: a write is a
Proposal until a human approves it. That is how Atlan's own MCP write tools
behave (preview, then wait for approval), and it is the rule the challenge
round asked for: the system drafts, a person ships.
"""
from __future__ import annotations

import hashlib
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .models import ApprovedAnswer, Audience, Claim, ClaimStatus, Proposal


@dataclass
class SentAnswerRecord:
    """What left the building, and what it rested on. Written once per sent
    answer; the version hash pins the claim content at that moment."""
    question: str
    answer: str
    claim_ids: list[str]
    claim_version_hashes: list[str]
    approver: str
    customer: str
    sent_on: date
    audience: Audience
    difficulty_class: str


class ClaimStore(ABC):
    # ---- reads ----------------------------------------------------------
    @abstractmethod
    def list(self) -> list[Claim]: ...

    @abstractmethod
    def get(self, claim_id: str) -> Optional[Claim]: ...

    def usable(self, today: date, audience: Audience) -> list[Claim]:
        return [c for c in self.list() if c.is_usable(today, audience)[0]]

    # ---- writes: propose, then approve ----------------------------------
    @abstractmethod
    def propose(self, claim: Claim, actor: str, reason: str, today: date) -> Proposal: ...

    @abstractmethod
    def approve(self, proposal_id: str, approver: str, today: date) -> Claim: ...

    @abstractmethod
    def reject(self, proposal_id: str, approver: str, today: date, reason: str = "") -> Proposal: ...

    @abstractmethod
    def pending(self) -> list[Proposal]: ...

    # ---- the loop back --------------------------------------------------
    @abstractmethod
    def record_sent_answer(self, rec: SentAnswerRecord) -> None: ...

    @abstractmethod
    def sent_answers(self) -> list[SentAnswerRecord]: ...

    # ---- views ----------------------------------------------------------
    def freshness_digest(self, today: date, expiring_days: int = 30) -> dict[str, dict[str, list[str]]]:
        """owner -> {expired: [...], expiring: [...], draft: [...]}.

        Grouped by owner because that is who has to act. An owner with
        several expiring claims gets one message, not several."""
        out: dict[str, dict[str, list[str]]] = {}
        for c in self.list():
            bucket = None
            if c.status == ClaimStatus.DEPRECATED:
                continue
            if c.status == ClaimStatus.DRAFT:
                bucket = "draft"
            elif c.valid_until < today:
                bucket = "expired"
            elif (c.valid_until - today).days <= expiring_days:
                bucket = "expiring"
            if bucket:
                out.setdefault(c.owner, {"expired": [], "expiring": [], "draft": []})[bucket].append(c.claim_id)
        return out


_VOLATILE = {"version", "version_hash", "updated_by", "updated_on", "approved_answers"}


def _proposable_fields(c: Claim) -> dict:
    """Everything a proposal may change: content fields plus notes, keywords,
    topics, framework map and owner. Volatile bookkeeping is left out."""
    return {k: v for k, v in c.to_dict().items() if k not in _VOLATILE}


class FileClaimStore(ClaimStore):
    """Directory layout:
        <root>/claims/<claim_id>.json
        <root>/proposals.json
        <root>/sent_answers.jsonl       (append-only)
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        (self.root / "claims").mkdir(parents=True, exist_ok=True)
        self._proposals_path = self.root / "proposals.json"
        self._sent_path = self.root / "sent_answers.jsonl"
        if not self._proposals_path.exists():
            self._proposals_path.write_text("[]", encoding="utf-8")

    # ---- reads ----------------------------------------------------------
    def list(self) -> list[Claim]:
        out = []
        for p in sorted((self.root / "claims").glob("*.json")):
            out.append(Claim.from_dict(json.loads(p.read_text(encoding="utf-8"))))
        return out

    def get(self, claim_id: str) -> Optional[Claim]:
        p = self._claim_path(claim_id)
        if not p.exists():
            return None
        return Claim.from_dict(json.loads(p.read_text(encoding="utf-8")))

    # ---- writes ---------------------------------------------------------
    def propose(self, claim: Claim, actor: str, reason: str, today: date) -> Proposal:
        problems = claim.validate()
        if problems:
            raise ValueError(f"claim {claim.claim_id}: " + "; ".join(problems))
        existing = self.get(claim.claim_id)
        prev_hash = existing.version_hash() if existing else ""
        if existing and _proposable_fields(existing) == _proposable_fields(claim):
            raise ValueError(f"claim {claim.claim_id}: proposal changes nothing")
        pid = hashlib.sha256(
            f"{claim.claim_id}|{claim.version_hash()}|{actor}|{today.isoformat()}|{len(self._load_proposals())}"
            .encode()).hexdigest()[:12]
        prop = Proposal(proposal_id=pid, claim=claim, actor=actor, reason=reason,
                        created_on=today, previous_version_hash=prev_hash)
        props = self._load_proposals()
        props.append(prop)
        self._save_proposals(props)
        return prop

    def approve(self, proposal_id: str, approver: str, today: date) -> Claim:
        props = self._load_proposals()
        prop = self._find(props, proposal_id)
        if prop.status != "pending":
            raise ValueError(f"proposal {proposal_id} is {prop.status}")
        if approver == prop.actor:
            raise PermissionError("a proposal is approved by someone other than its author")
        existing = self.get(prop.claim.claim_id)
        claim = prop.claim
        claim.version = (existing.version + 1) if existing else 1
        claim.updated_by = approver
        claim.updated_on = today
        if claim.status == ClaimStatus.DRAFT:
            # approving a proposal is what makes a claim verified
            claim.status = ClaimStatus.VERIFIED
        self._write_claim(claim)
        prop.status, prop.decided_by, prop.decided_on = "approved", approver, today
        self._save_proposals(props)
        return claim

    def reject(self, proposal_id: str, approver: str, today: date, reason: str = "") -> Proposal:
        props = self._load_proposals()
        prop = self._find(props, proposal_id)
        if prop.status != "pending":
            raise ValueError(f"proposal {proposal_id} is {prop.status}")
        prop.status, prop.decided_by, prop.decided_on = "rejected", approver, today
        if reason:
            prop.reason = f"{prop.reason} | rejected: {reason}"
        self._save_proposals(props)
        return prop

    def pending(self) -> list[Proposal]:
        return [p for p in self._load_proposals() if p.status == "pending"]

    def bootstrap(self, claims: Iterable[Claim], approver: str, today: date) -> int:
        """Seed a store from an authored claim set. Every claim is written as
        approved by `approver`, recorded as such; this is the one path that
        skips propose/approve, and it refuses to overwrite an existing claim."""
        n = 0
        for c in claims:
            if self.get(c.claim_id) is not None:
                raise ValueError(f"bootstrap refuses to overwrite existing claim {c.claim_id}")
            problems = c.validate()
            if problems:
                raise ValueError(f"claim {c.claim_id}: " + "; ".join(problems))
            c.updated_by, c.updated_on = approver, today
            self._write_claim(c)
            n += 1
        return n

    # ---- the loop back --------------------------------------------------
    def record_sent_answer(self, rec: SentAnswerRecord) -> None:
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "question": rec.question, "answer": rec.answer,
            "claim_ids": rec.claim_ids, "claim_version_hashes": rec.claim_version_hashes,
            "approver": rec.approver, "customer": rec.customer,
            "sent_on": rec.sent_on.isoformat(), "audience": rec.audience.value,
            "difficulty_class": rec.difficulty_class,
        }
        with self._sent_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def sent_answers(self) -> list[SentAnswerRecord]:
        if not self._sent_path.exists():
            return []
        out = []
        for line in self._sent_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            out.append(SentAnswerRecord(
                question=r["question"], answer=r["answer"], claim_ids=r["claim_ids"],
                claim_version_hashes=r["claim_version_hashes"], approver=r["approver"],
                customer=r["customer"], sent_on=date.fromisoformat(r["sent_on"]),
                audience=Audience(r["audience"]), difficulty_class=r["difficulty_class"]))
        return out

    def add_approved_answer(self, claim_id: str, answer: ApprovedAnswer, approver: str,
                            today: date) -> Claim:
        """Writeback: a reviewer-approved answer becomes reusable. This is a
        direct write because the approval already happened in the review
        step; the approver is recorded on the answer itself."""
        c = self.get(claim_id)
        if c is None:
            raise KeyError(claim_id)
        answer.claim_version_hash = c.version_hash()
        answer.approver = approver
        c.approved_answers.append(answer)
        c.updated_by, c.updated_on = approver, today
        self._write_claim(c)
        return c

    # ---- internals ------------------------------------------------------
    def _claim_path(self, claim_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in claim_id)
        while ".." in safe:
            safe = safe.replace("..", "_")
        safe = safe.lstrip(".") or "_"
        p = (self.root / "claims" / f"{safe}.json").resolve()
        if p.parent != (self.root / "claims").resolve():
            raise PermissionError(f"claim id {claim_id!r} escapes the store directory")
        return p

    def _write_claim(self, claim: Claim) -> None:
        self._claim_path(claim.claim_id).write_text(
            json.dumps(claim.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    def _load_proposals(self) -> list[Proposal]:
        return [Proposal.from_dict(d) for d in json.loads(self._proposals_path.read_text(encoding="utf-8"))]

    def _save_proposals(self, props: list[Proposal]) -> None:
        self._proposals_path.write_text(
            json.dumps([p.to_dict() for p in props], indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _find(props: list[Proposal], pid: str) -> Proposal:
        for p in props:
            if p.proposal_id == pid:
                return p
        raise KeyError(f"no proposal {pid}")
