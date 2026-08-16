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
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from .drafter import make_drafter
from .evidence import EvidenceStore
from .export import export_answers, ingest_questionnaire
from .gates import post_gate, pre_gate
from .models import Coverage, Draft, QState, Question
from .retrieve import Retriever

GENESIS = "0" * 64


class AuditLog:
    def __init__(self, path: Path):
        self.path = path
        self.prev = GENESIS
        path.parent.mkdir(parents=True, exist_ok=True)
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
            # a tamper-evident log that loses its last events to the page cache
            # on a hard kill is evidence of nothing; pay the fsync per event
            f.flush()
            os.fsync(f.fileno())
        self.prev = event_hash

    @classmethod
    def resume(cls, path: Path) -> "AuditLog":
        """Reopen an existing log to append without truncating.

        Refuses to continue a broken chain: appending to a tampered log would
        launder the tampering behind fresh valid links.
        """
        if not cls.verify_chain(path):
            raise ValueError(f"{path.name}: audit chain invalid; refusing to append")
        log = cls.__new__(cls)
        log.path = path
        log.prev = GENESIS
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if lines:
            log.prev = json.loads(lines[-1])["hash"]
        return log

    @staticmethod
    def verify_chain(path: Path) -> bool:
        """True only if every line links. A malformed line is a broken chain.

        A process killed mid-append leaves a torn last line. That is a failed
        verification, not a crash: raising JSONDecodeError here made resume()
        500 forever and put the whole run permanently out of reach.
        """
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return False
        prev = GENESIS
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                claimed = obj.pop("hash")
                if obj.get("prev_hash") != prev:
                    return False
                payload = json.dumps(obj, sort_keys=True, ensure_ascii=False)
                if hashlib.sha256(payload.encode()).hexdigest() != claimed:
                    return False
            except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
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
        approval_mode: str = "simulated",
        retriever=None,
        progress: Callable[[int, int], None] | None = None) -> RunResult:
    """approval_mode: "simulated" auto-approves gate-clean complete drafts with a
    labeled stand-in reviewer (demo/CLI). "human" approves nothing: clean drafts
    rest at GRC_REVIEW until a named reviewer acts via trustops.server.review.

    retriever: injectable Retriever-compatible instance (e.g. SemanticRetriever);
    defaults to the lexical Retriever over the same store.

    progress: optional callback(questions_done, questions_total) invoked after
    each question. Observation only — it can never change the run's outcome, so
    anything it raises is swallowed.
    """
    if approval_mode not in ("simulated", "human"):
        raise ValueError(f"unknown approval_mode '{approval_mode}'")
    today = today or date.today()
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    audit = AuditLog(out_dir / "audit_log.jsonl")
    store = EvidenceStore(tenant, evidence_root)
    retriever = retriever or Retriever(store)
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
    total_q = len(questions)
    for done, q in enumerate(questions, start=1):
        d = Draft(question_id=q.question_id, answer=None)
        d = pre_gate(q, d)
        if d.route != "LEGAL":
            d = drafter.draft(q, tenant)
            d = pre_gate(q, d)          # re-apply flags onto the drafted object
        else:
            d.drafter, d.model_version, d.prompt_version = "gate", "n/a", "pre-gate-v1"
        q.state = QState.DRAFTED
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

        # simulated named-reviewer approval — only for clean, complete drafts,
        # and only in demo mode; hosted ("human") runs approve nothing here
        if (approval_mode == "simulated"
                and q.state == QState.GRC_REVIEW and d.evidence_coverage == Coverage.COMPLETE
                and not d.requires_human):
            q.state = QState.DELIVERED
            audit.append(reviewer, "APPROVED", q.question_id,
                         {"mode": "SIMULATED_DEMO_APPROVAL",
                          "citations": [f"{c.source_id}@{c.location}" for c in d.citations]})
        drafts[q.question_id] = d
        if progress is not None:
            try:
                progress(done, total_q)
            except Exception:  # noqa: BLE001 — telemetry never breaks a run
                pass

    # DELIVERED — export back into the original format
    delivered = out_dir / f"{questionnaire.stem}__DELIVERED.xlsx"
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
    # A tripwire, not a measurement, and it should be described as one. post_gate
    # nulls the answer whenever no citation survives, so this can only become
    # non-zero if some future change lets an answer past that rule. It is worth
    # keeping for exactly that reason, but it was never evidence of quality: an
    # audit correctly called the headline "zero unsupported claims" a tautology,
    # because the two conditions cannot co-occur by construction.
    unsupported = sum(
        1 for d in drafts.values() if d.answer is not None and not d.citations
    )
    # These two do vary, and they are what the release rule actually rests on.
    # The grounding gate refuses a drafted answer whose words are not traceable
    # to the passages it cited; the citation resolver drops citations a model
    # attached to sources or locations it was never shown.
    ungrounded = sum(
        1 for d in drafts.values() if "UNGROUNDED_ANSWER" in d.gate_flags)
    citations_dropped = sum(
        1 for d in drafts.values() for f in d.gate_flags
        if f in ("FABRICATED_CITATION", "HALLUCINATED_LOCATION",
                 "UNRETRIEVED_CITATION"))
    metrics = {
        "questions": n,
        "cited_draft_coverage": round(cited / n, 3),
        "abstention_rate": round(abstained / n, 3),
        "exception_queue": exceptions,
        "auto_approved_delivered": delivered_n,
        "awaiting_human_review": review_n,
        # invariant assertion: MUST be 0, and is 0 by construction (see above)
        "unsupported_material_claims": unsupported,
        "ungrounded_refusals": ungrounded,
        "citations_dropped": citations_dropped,
        "approval_mode": approval_mode,
        "cycle_seconds": round(elapsed, 2),
        "drafter": drafter_kind,
        "audit_chain_valid": AuditLog.verify_chain(out_dir / "audit_log.jsonl"),
    }
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (out_dir / "contracts.json").write_text(
        json.dumps({qid: d.to_contract() for qid, d in drafts.items()}, indent=2,
                   ensure_ascii=False),
        encoding="utf-8",
    )
    # rehydration record for post-run review (trustops.server.review)
    (out_dir / "state.json").write_text(json.dumps({
        "tenant": tenant,
        "drafter": drafter_kind,
        "approval_mode": approval_mode,
        "questionnaire": questionnaire.name,
        "run_date": today.isoformat(),
        "questions": [{"question_id": q.question_id, "row": q.row,
                       "domain": q.domain, "text": q.text, "state": q.state.value}
                      for q in questions],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    audit.append("system", "RUN_COMPLETE", tenant, metrics)

    return RunResult(tenant=tenant, questions=questions, drafts=drafts,
                     metrics=metrics, out_dir=out_dir, delivered_xlsx=delivered,
                     audit_path=out_dir / "audit_log.jsonl",
                     integrity_notes=integrity)
