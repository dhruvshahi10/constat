"""Human review — the step that turns a draft into a representation.

A questionnaire answer is a material security statement made to a buyer. The
engine can establish that a statement is supported by an approved, in-force
document; it cannot take responsibility for making it. A named person does
that, and this module is where that happens.

Three properties matter more than the ergonomics:

  1. Decisions extend the run's own hash chain. A review is not a separate log
     that could be reconciled later — it is more events on the same tamper-
     evident chain as the run it decided on.
  2. Approval cannot manufacture evidence. `approve` is only available for an
     answer that already survived the gates. A human who wants to answer an
     unsupported question must `edit`, and the result is labelled
     HUMAN_AUTHORED — visibly not evidence-backed, in the contract and in the
     exported workbook.
  3. Decisions are replayable. They live in `review.json`, applied on load, so
     reopening a run shows exactly the state the last reviewer left.
"""
from __future__ import annotations

import getpass
import json
import socket
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .export import export_answers
from .models import AnswerStatus, Approval, Coverage, Draft, QState, Question
from .pipeline import AuditLog

ACTIONS = ("approve", "edit", "reject")


class ReviewError(RuntimeError):
    """A decision the process does not permit — never silently ignored."""


@dataclass
class Decision:
    question_id: str
    action: str
    actor: str
    timestamp: str
    note: str = ""
    answer_before: str | None = None
    answer_after: str | None = None


@dataclass
class QueueItem:
    question_id: str
    domain: str
    text: str
    status: str
    answer: str | None
    citations: list[dict]
    gaps: list[str]
    route: str | None
    gate_flags: list[str]
    decided: Decision | None = None
    allowed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["decided"] = asdict(self.decided) if self.decided else None
        return d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _operator() -> dict:
    """Who the operating system says is running this, next to who the reviewer
    claims to be.

    `--actor` is self-asserted: anyone can type any name. Recording the OS user
    and host alongside it does not make the claim authenticated, and this does
    not pretend otherwise — it corroborates. Two fields that disagree are a
    question worth asking during an audit, and they are inside the signed,
    hash-chained event, so neither can be quietly changed afterwards."""
    try:
        user = getpass.getuser()
    except Exception:            # no controlling terminal / no passwd entry
        user = "unknown"
    try:
        host = socket.gethostname()
    except Exception:
        host = "unknown"
    return {"os_user": user, "host": host}


class ReviewSession:
    """Reopen a completed run and record named-human decisions on it."""

    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        manifest_path = self.run_dir / "manifest.json"
        contracts_path = self.run_dir / "contracts.json"
        if not manifest_path.is_file() or not contracts_path.is_file():
            raise ReviewError(
                f"{self.run_dir} is not a reviewable run "
                f"(needs manifest.json and contracts.json — re-run to regenerate)")
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.drafts: dict[str, Draft] = {
            qid: Draft.from_contract(c)
            for qid, c in json.loads(contracts_path.read_text(encoding="utf-8")).items()}
        self.questions: list[Question] = [
            Question(question_id=q["question_id"], row=q["row"], domain=q["domain"],
                     text=q["text"], state=QState(q["state"]))
            for q in self.manifest["questions"]]
        self.decisions: dict[str, Decision] = {}
        self._load_decisions()

    # --- persistence ---------------------------------------------------------
    @property
    def decisions_path(self) -> Path:
        return self.run_dir / "review.json"

    def _load_decisions(self) -> None:
        if not self.decisions_path.is_file():
            return
        raw = json.loads(self.decisions_path.read_text(encoding="utf-8"))
        for item in raw.get("decisions", []):
            decision = Decision(**item)
            self.decisions[decision.question_id] = decision
            self._apply(decision)

    def _save_decisions(self) -> None:
        self.decisions_path.write_text(json.dumps({
            "run_dir": self.run_dir.name,
            "tenant": self.manifest["tenant"],
            "decisions": [asdict(d) for d in self.decisions.values()],
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- state ---------------------------------------------------------------
    def _question(self, question_id: str) -> Question:
        for q in self.questions:
            if q.question_id == question_id:
                return q
        raise ReviewError(f"no question '{question_id}' in this run")

    def _allowed_actions(self, draft: Draft) -> list[str]:
        # `approve` accepts what the gates released. It cannot conjure evidence,
        # so it is unavailable when nothing was released.
        if draft.status.released:
            return ["approve", "edit", "reject"]
        return ["edit", "reject"]

    def _apply(self, decision: Decision) -> None:
        draft = self.drafts[decision.question_id]
        question = self._question(decision.question_id)
        if decision.action == "approve":
            draft.requires_human = False
            question.state = QState.DELIVERED
        elif decision.action == "edit":
            draft.answer = decision.answer_after
            draft.abstained = False
            draft.requires_human = False
            draft.status = AnswerStatus.HUMAN_AUTHORED
            draft.evidence_coverage = (Coverage.PARTIAL if draft.citations else Coverage.NONE)
            question.state = QState.DELIVERED
        elif decision.action == "reject":
            draft.answer = None
            draft.abstained = True
            draft.requires_human = True
            draft.status = AnswerStatus.NO_EVIDENCE
            draft.evidence_coverage = Coverage.NONE
            question.state = QState.EXCEPTION

    def queue(self, pending_only: bool = False) -> list[QueueItem]:
        items: list[QueueItem] = []
        for q in self.questions:
            d = self.drafts[q.question_id]
            decided = self.decisions.get(q.question_id)
            if pending_only and (decided or q.state == QState.DELIVERED):
                continue
            items.append(QueueItem(
                question_id=q.question_id, domain=q.domain, text=q.text,
                status=d.status.value, answer=d.answer,
                citations=[{"source_id": c.source_id, "version": c.version,
                            "location": c.location} for c in d.citations],
                gaps=list(d.gaps), route=d.route, gate_flags=list(d.gate_flags),
                decided=decided, allowed=self._allowed_actions(d)))
        return items

    # --- the decision ---------------------------------------------------------
    def decide(self, question_id: str, action: str, actor: str, note: str = "",
               answer: str | None = None) -> Decision:
        if action not in ACTIONS:
            raise ReviewError(f"unknown action '{action}' (use {', '.join(ACTIONS)})")
        if not actor or "@" not in actor:
            # interface-neutral: this message is surfaced verbatim by both the
            # CLI and the console, so it must not name a flag that only one has
            raise ReviewError('a review needs a named reviewer — give a name and work '
                              'email, e.g. "Priya Nair <priya@company.com>"')
        if question_id not in self.drafts:
            raise ReviewError(f"no question '{question_id}' in this run")
        draft = self.drafts[question_id]
        if action not in self._allowed_actions(draft):
            raise ReviewError(
                f"{question_id} is {draft.status.label}: nothing was released for you to "
                f"approve. Use 'edit' to supply a human-authored answer (it will be "
                f"labelled HUMAN_AUTHORED, not evidence-backed), or 'reject'.")
        if action == "edit" and not (answer or "").strip():
            raise ReviewError("edit requires the answer text you are taking responsibility for")

        decision = Decision(
            question_id=question_id, action=action, actor=actor, timestamp=_now(),
            note=note, answer_before=draft.answer,
            answer_after=(answer.strip() if action == "edit" and answer else draft.answer))
        self._apply(decision)
        self.decisions[question_id] = decision
        self._save_decisions()
        self._write_audit(decision)
        return decision

    def _write_audit(self, decision: Decision) -> None:
        audit = AuditLog(self.run_dir / "audit_log.jsonl", resume=True)
        approval = Approval(question_id=decision.question_id, actor=decision.actor,
                            action={"approve": "approved", "edit": "edited",
                                    "reject": "rejected"}[decision.action],
                            timestamp=decision.timestamp, note=decision.note)
        draft = self.drafts[decision.question_id]
        audit.append(decision.actor, approval.action.upper(), decision.question_id, {
            "mode": "HUMAN_REVIEW",
            "claimed_actor": decision.actor,
            "operator": _operator(),
            "actor_authentication": "none — self-asserted, corroborated by OS identity",
            "status_after": draft.status.value,
            "citations": [f"{c.source_id}@{c.location}" for c in draft.citations],
            "note": decision.note,
            "answer_replaced": decision.action == "edit",
        })

    # --- outputs --------------------------------------------------------------
    def export(self) -> Path:
        """Re-export the client's workbook reflecting every decision so far."""
        source = Path(self.manifest["questionnaire"])
        if not source.is_file():
            raise ReviewError(f"original questionnaire is gone: {source}")
        target = self.run_dir / f"{source.stem}__DELIVERED{source.suffix}"
        export_answers(source, target, self.questions, self.drafts)
        audit = AuditLog(self.run_dir / "audit_log.jsonl", resume=True)
        audit.append("system", "RE_EXPORTED", target.name,
                     {"after_decisions": len(self.decisions)})
        return target

    def summary(self) -> dict:
        total = len(self.questions)
        by_status: dict[str, int] = {}
        for d in self.drafts.values():
            by_status[d.status.value] = by_status.get(d.status.value, 0) + 1
        actions = {a: sum(1 for d in self.decisions.values() if d.action == a) for a in ACTIONS}
        reviewed = len(self.decisions)
        return {
            "run": self.run_dir.name,
            "tenant": self.manifest["tenant"],
            "questions": total,
            "reviewed": reviewed,
            "pending": len(self.queue(pending_only=True)),
            "actions": actions,
            "status_counts": by_status,
            # the outcome metric a buyer asks about: shipped with no human rewrite
            "zero_human_edit_rate": round((total - actions["edit"]) / total, 3) if total else 0.0,
            "reviewers": sorted({d.actor for d in self.decisions.values()}),
            "audit_chain_valid": AuditLog.verify_chain(self.run_dir / "audit_log.jsonl"),
        }
