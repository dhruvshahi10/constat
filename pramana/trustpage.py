"""Trust page generator — the deflection half of the product.

A questionnaire that never arrives costs nothing to answer. Given a workspace's
evidence corpus, this runs the standard buyer question set through the same
pipeline a real questionnaire uses and publishes only the subset that came back
fully evidence-backed, each with the document, version and paragraph behind it.

What is NOT published is the point. A question whose answer was partial, needed
sign-off, was refused, or was routed to counsel appears as an open item to
request through security review — never as an answer. A trust page that answers
everything is a trust page nobody should believe, and generating one from a thin
corpus would be the easiest way for this product to start lying on its own
front door.

The deflection rate — answers published over the standard set — is the number a
buyer's security team actually feels, and it is measured here rather than
asserted.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .drafter import make_drafter
from .evidence import EvidenceStore
from .gates import post_gate, pre_gate
from .models import Coverage, Draft, Question
from .retrieve import Retriever

DEFAULT_QUESTION_SET = Path(__file__).resolve().parents[1] / "data" / "trust_questions.json"


@dataclass
class TrustAnswer:
    question_id: str
    domain: str
    question: str
    answer: str | None
    citations: list[dict]
    gap: str | None
    published: bool


@dataclass
class TrustResult:
    slug: str
    display_name: str
    generated: date
    answers: list[TrustAnswer]

    @property
    def shown(self) -> list[TrustAnswer]:
        return [a for a in self.answers if a.published]

    @property
    def open_items(self) -> list[TrustAnswer]:
        return [a for a in self.answers if not a.published]

    @property
    def deflection_rate(self) -> float:
        return round(len(self.shown) / len(self.answers), 3) if self.answers else 0.0

    def to_dict(self) -> dict:
        return {
            "workspace": self.slug,
            "display_name": self.display_name,
            "generated": self.generated.isoformat(),
            "questions": len(self.answers),
            "published": len(self.shown),
            "open_items": len(self.open_items),
            "deflection_rate": self.deflection_rate,
            "answers": [{"question_id": a.question_id, "domain": a.domain,
                         "question": a.question, "published": a.published,
                         "answer": a.answer, "citations": a.citations}
                        for a in self.answers],
        }


def load_question_set(path: Path | None = None) -> list[dict]:
    data = json.loads(Path(path or DEFAULT_QUESTION_SET).read_text(encoding="utf-8"))
    return data["questions"]


def _publishable(d: Draft) -> bool:
    """Only a fully evidence-backed answer is published without a human.

    Partial coverage means the gates recorded a gap against the answer even
    though something survived; that is a fine thing to send a reviewer and a bad
    thing to put on a public page unsigned.
    """
    return (not d.abstained
            and bool(d.answer)
            and bool(d.citations)
            and d.evidence_coverage is Coverage.COMPLETE
            and d.route is None)


def generate(slug: str, evidence_root: Path, display_name: str = "",
             today: date | None = None, question_set: Path | None = None,
             drafter_kind: str = "mock") -> TrustResult:
    today = today or date.today()
    store = EvidenceStore(slug, evidence_root)
    retriever = Retriever(store)
    drafter = make_drafter(drafter_kind, retriever)

    answers: list[TrustAnswer] = []
    for spec in load_question_set(question_set):
        q = Question(question_id=spec["id"], row=0, domain=spec["domain"], text=spec["text"])
        d = Draft(question_id=q.question_id, answer=None)
        d = pre_gate(q, d)
        if d.route != "LEGAL":
            d = drafter.draft(q, slug)
            d = pre_gate(q, d)
        d = post_gate(q, d, store, today)
        ok = _publishable(d)
        answers.append(TrustAnswer(
            question_id=q.question_id, domain=q.domain, question=q.text,
            answer=d.answer if ok else None,
            citations=[{"source_id": c.source_id, "version": c.version,
                        "location": c.location} for c in d.citations] if ok else [],
            gap=(d.gaps[0] if d.gaps else None), published=ok))

    return TrustResult(slug=slug, display_name=display_name or slug.title(),
                       generated=today, answers=answers)
