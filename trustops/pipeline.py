"""Pipeline: RECEIVED -> CLASSIFIED -> DRAFTED -> (EXCEPTION | GRC_REVIEW) -> DELIVERED.

Every transition writes a hash-chained, append-only audit event (JSONL). Each
event carries the sha256 of the previous event, so the log is tamper-evident:
edit any historical line and verify_chain() fails from that point on.

Demo note: in production, GRC_REVIEW is an interactive human approval. In demo
mode a simulated named reviewer approves only drafts that (a) survived every
gate, (b) have complete coverage, and (c) are not flagged requires_human for
risk reasons — everything else stays queued for a human. The simulation is
labeled as such in the log and the report.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from .drafter import make_drafter
from .evidence import EvidenceStore
from .export import export_answers, ingest_questionnaire
from .gates import post_gate, pre_gate
from .models import AnswerStatus, Coverage, Draft, QState, Question
from .retrieve import Retriever

GENESIS = "0" * 64


class AuditLog:
    def __init__(self, path: Path, resume: bool = False):
        self.path = path
        self.prev = GENESIS
        path.parent.mkdir(parents=True, exist_ok=True)
        if resume and path.is_file():
            # A review session continues the SAME chain rather than starting a
            # new one: a human decision belongs to the run it decided on, and a
            # second file would make the two independently forgeable.
            lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
            if lines:
                self.prev = json.loads(lines[-1])["hash"]
            return
        path.write_text("", encoding="utf-8")

    def append(self, actor: str, action: str, subject: str, detail: dict | None = None) -> None:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "action": action,
            "subject": subject,
            "detail": detail or {},
            "prev_hash": self.prev,
        }
        payload = json.dumps(event, sort_keys=True, ensure_ascii=False)
        event_hash = hashlib.sha256(payload.encode()).hexdigest()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({**event, "hash": event_hash}, ensure_ascii=False) + "\n")
        self.prev = event_hash

    @staticmethod
    def verify_chain(path: Path) -> bool:
        prev = GENESIS
        for line in path.read_text(encoding="utf-8").splitlines():
            obj = json.loads(line)
            claimed = obj.pop("hash")
            if obj.get("prev_hash") != prev:
                return False
            payload = json.dumps(obj, sort_keys=True, ensure_ascii=False)
            if hashlib.sha256(payload.encode()).hexdigest() != claimed:
                return False
            prev = claimed
        return True


@dataclass
class RunResult:
    tenant: str
    questions: list[Question]
    drafts: dict[str, Draft]
    metrics: dict
    out_dir: Path
    delivered_xlsx: Path
    audit_path: Path
    integrity_notes: dict = field(default_factory=dict)


def run(questionnaire: Path, tenant: str, evidence_root: Path, out_dir: Path,
        drafter_kind: str = "mock", today: date | None = None,
        reviewer: str = "demo-grc-reviewer (simulated)",
        reviewer_mode: str = "simulated") -> RunResult:
    """Execute a questionnaire end to end.

    `reviewer_mode="manual"` performs no approvals at all: every drafted answer
    waits for a named human in the review session. `"simulated"` keeps the
    labelled demo behaviour — it approves only gate-clean, complete-coverage
    drafts, and every such event is written to the log as SIMULATED_DEMO_APPROVAL.
    """
    if reviewer_mode not in ("simulated", "manual"):
        raise ValueError(f"unknown reviewer_mode '{reviewer_mode}'")
    today = today or date.today()
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    audit = AuditLog(out_dir / "audit_log.jsonl")
    store = EvidenceStore(tenant, evidence_root)
    retriever = Retriever(store)
    drafter = make_drafter(drafter_kind, retriever)

    # RECEIVED — checksum the artifact before anything touches it
    checksum = hashlib.sha256(questionnaire.read_bytes()).hexdigest()
    audit.append("system", "RECEIVED", questionnaire.name,
                 {"sha256": checksum, "tenant": tenant})

    # CLASSIFIED
    questions = ingest_questionnaire(questionnaire)
    for q in questions:
        q.state = QState.CLASSIFIED
    audit.append("system", "CLASSIFIED", questionnaire.name,
                 {"question_count": len(questions)})

    # integrity views computed once, up front
    contradictions = store.contradictions(today)
    integrity = {
        "stale_sources": sorted(store.stale_ids(today)),
        "contradictions": {
            k: [f"{s.source_id}={s.assertions[k]}" for s in v]
            for k, v in contradictions.items()
        },
    }
    if integrity["stale_sources"] or integrity["contradictions"]:
        audit.append("system", "EVIDENCE_INTEGRITY_SCAN", tenant, integrity)

    drafts: dict[str, Draft] = {}
    first_draft_at: float | None = None
    for q in questions:
        d = Draft(question_id=q.question_id, answer=None)
        d = pre_gate(q, d)
        if d.route != "LEGAL":
            d = drafter.draft(q, tenant)
            d = pre_gate(q, d)          # re-apply flags onto the drafted object
        else:
            d.drafter, d.model_version, d.prompt_version = "gate", "n/a", "pre-gate-v1"
        q.state = QState.DRAFTED
        if first_draft_at is None:
            first_draft_at = time.perf_counter()
        d = post_gate(q, d, store, today)

        if d.abstained or d.route:
            q.state = QState.EXCEPTION
            audit.append("gate", "EXCEPTION", q.question_id,
                         {"route": d.route, "flags": d.gate_flags, "gaps": d.gaps})
        else:
            q.state = QState.GRC_REVIEW
            audit.append(drafter.name if hasattr(drafter, "name") else "drafter",
                         "DRAFTED", q.question_id,
                         {"citations": [c.source_id for c in d.citations],
                          "coverage": d.evidence_coverage.value})

        # simulated named-reviewer approval — only for clean, complete drafts
        if (reviewer_mode == "simulated" and q.state == QState.GRC_REVIEW
                and d.evidence_coverage == Coverage.COMPLETE and not d.requires_human):
            q.state = QState.DELIVERED
            audit.append(reviewer, "APPROVED", q.question_id,
                         {"mode": "SIMULATED_DEMO_APPROVAL",
                          "citations": [f"{c.source_id}@{c.location}" for c in d.citations]})
        drafts[q.question_id] = d

    # A run manifest so a review session can reopen this run later: which file,
    # which tenant, and the row identity of every question.
    (out_dir / "manifest.json").write_text(json.dumps({
        "tenant": tenant,
        "questionnaire": str(questionnaire.resolve()),
        "evidence_root": str(Path(evidence_root).resolve()),
        "drafter": drafter_kind,
        "reviewer_mode": reviewer_mode,
        "run_date": today.isoformat(),
        "questions": [{"question_id": q.question_id, "row": q.row,
                       "domain": q.domain, "text": q.text, "state": q.state.value}
                      for q in questions],
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    # DELIVERED — export back into the original format
    delivered = out_dir / f"{questionnaire.stem}__DELIVERED{questionnaire.suffix}"
    export_answers(questionnaire, delivered, questions, drafts)
    audit.append("system", "EXPORTED", delivered.name,
                 {"sha256": hashlib.sha256(delivered.read_bytes()).hexdigest()})

    elapsed = time.perf_counter() - t0
    n = len(questions)
    cited = sum(1 for d in drafts.values() if d.citations and not d.abstained)
    abstained = sum(1 for d in drafts.values() if d.abstained)
    exceptions = sum(1 for q in questions if q.state == QState.EXCEPTION)
    delivered_n = sum(1 for q in questions if q.state == QState.DELIVERED)
    review_n = sum(1 for q in questions if q.state == QState.GRC_REVIEW)
    unsupported = sum(
        1 for d in drafts.values() if d.answer is not None and not d.citations
    )
    metrics = {
        "questions": n,
        "cited_draft_coverage": round(cited / n, 3),
        "abstention_rate": round(abstained / n, 3),
        "exception_queue": exceptions,
        "auto_approved_delivered": delivered_n,
        "awaiting_human_review": review_n,
        "unsupported_material_claims": unsupported,   # release gate: MUST be 0
        "cycle_seconds": round(elapsed, 2),
        "time_to_first_draft_seconds": round(first_draft_at - t0, 3) if first_draft_at else None,
        "zero_human_edit_rate": round(delivered_n / n, 3) if n else 0.0,
        "refusals_with_named_gap": round(
            sum(1 for d in drafts.values() if d.abstained and d.gaps) / abstained, 3
        ) if abstained else 1.0,
        "status_counts": {s.value: sum(1 for d in drafts.values() if d.status is s)
                          for s in AnswerStatus},
        "reviewer_mode": reviewer_mode,
        "drafter": drafter_kind,
        "audit_chain_valid": AuditLog.verify_chain(out_dir / "audit_log.jsonl"),
    }
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (out_dir / "contracts.json").write_text(
        json.dumps({qid: d.to_contract() for qid, d in drafts.items()}, indent=2,
                   ensure_ascii=False),
        encoding="utf-8",
    )
    audit.append("system", "RUN_COMPLETE", tenant, metrics)

    return RunResult(tenant=tenant, questions=questions, drafts=drafts,
                     metrics=metrics, out_dir=out_dir, delivered_xlsx=delivered,
                     audit_path=out_dir / "audit_log.jsonl",
                     integrity_notes=integrity)
