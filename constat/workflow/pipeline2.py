"""The claims pipeline: a questionnaire's items from RECEIVED to a reviewable
state. Pure orchestration over the repository, the claim store, the matcher,
a normaliser and a drafter; every item ends in exactly one state and every
model call leaves latency and cost events behind."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional

from ..claims import Audience, ClaimStore
from ..claims.drafter import ClaimDrafter, DeterministicClaimDrafter
from ..claims.gates import Verdict, gate
from ..claims.match import ClaimMatcher
from ..intake.normalise import AtomicQuestion, MockNormaliser, Normaliser, normalise_all
from ..intake.parsers import RawQuestion
from ..persist import MetricEvent, QuestionItem, Repository, State, ulid
from .items import transition

OUTCOME_STATE = {"ANSWER": State.REVIEW, "HOLD_HUMAN": State.HELD, "REFUSE": State.REFUSED}


@dataclass
class PipelineConfig:
    today: date
    audience: Audience = Audience.NDA
    domain_owners: dict[str, str] | None = None
    normaliser: Optional[Normaliser] = None
    drafter: Optional[ClaimDrafter] = None
    actor: str = "pipeline"


def _history(repo: Repository, tenant: str, limit: int = 2000) -> list[str]:
    return [i.text for i in repo.list("question_items", {"tenant": tenant, "state": State.SENT},
                                      order="created_at desc", limit=limit) if i.text]


def create_items(repo: Repository, questionnaire_id: str, tenant: str, raws: list[RawQuestion]) -> list[QuestionItem]:
    items = []
    for r in raws:
        it = QuestionItem(id=ulid(), questionnaire_id=questionnaire_id, tenant=tenant, ordinal=r.ordinal,
                          raw_text=r.text, text=r.text, domain=r.domain, row=r.row)
        repo.insert("question_items", it)
        items.append(it)
    return items


def normalise_items(repo: Repository, items: list[QuestionItem], cfg: PipelineConfig) -> list[QuestionItem]:
    """RECEIVED -> NORMALISED | QUARANTINED | HELD. A compound item yields extra
    items, inserted after it with the same questionnaire."""
    normaliser = cfg.normaliser or MockNormaliser()
    tenant = items[0].tenant if items else ""
    raws = [RawQuestion(ordinal=i.ordinal, text=i.raw_text, domain=i.domain, row=i.row) for i in items]
    t0 = time.perf_counter()
    atoms = normalise_all(raws, normaliser, history=_history(repo, tenant) if items else [])
    by_source: dict[int, list[AtomicQuestion]] = {}
    for a in atoms:
        by_source.setdefault(a.source_ordinal, []).append(a)
    out: list[QuestionItem] = []
    for it in items:
        group = by_source.get(it.ordinal, [])
        if not group:
            transition(repo, it, State.HELD, cfg.actor, "normaliser produced nothing", flags=["NORMALISE_FAILED"])
            out.append(it)
            continue
        first, rest = group[0], group[1:]
        targets = [(it, first)]
        for extra in rest:
            child = QuestionItem(id=ulid(), questionnaire_id=it.questionnaire_id, tenant=it.tenant,
                                 ordinal=it.ordinal, raw_text=it.raw_text, text=extra.text, domain=it.domain,
                                 row=it.row)
            repo.insert("question_items", child)
            targets.append((child, extra))
        for target, atom in targets:
            flags = list(target.flags)
            fields = {"text": atom.text, "normaliser_model": atom.model_id,
                      "duplicate_of": (str(atom.duplicate_of) if atom.duplicate_of else None)}
            if atom.quarantine.quarantined:
                flags.append("INJECTION_SUSPECTED")
                transition(repo, target, State.QUARANTINED, cfg.actor,
                           "; ".join(atom.quarantine.reasons), flags=flags, **fields)
            elif atom.failed:
                flags.append("NORMALISE_FAILED")
                transition(repo, target, State.HELD, cfg.actor, "normaliser failed closed", flags=flags, **fields)
            else:
                if atom.compound_of:
                    flags.append("SPLIT_FROM_COMPOUND")
                if atom.asks_for_value:
                    flags.append("ASKS_FOR_VALUE")
                transition(repo, target, State.NORMALISED, cfg.actor, flags=flags, **fields)
            out.append(target)
    repo.insert("metric_events", MetricEvent(id=ulid(), tenant=tenant, kind="latency_ms",
                                             value_num=(time.perf_counter() - t0) * 1000,
                                             payload_json={"stage": "normalise", "items": len(out),
                                                           "model": getattr(normaliser, "model_id", "mock")}))
    return out


def match_and_draft(repo: Repository, item: QuestionItem, store: ClaimStore, matcher: ClaimMatcher,
                    cfg: PipelineConfig) -> Verdict:
    """NORMALISED -> MATCHED -> DRAFTED -> REVIEW | HELD | REFUSED."""
    drafter = cfg.drafter or DeterministicClaimDrafter()
    t0 = time.perf_counter()
    matches = matcher.match(item.text, cfg.today, cfg.audience)
    top = matches[0].claim.claim_id if matches else None
    transition(repo, item, State.MATCHED, cfg.actor, f"top match {top}" if top else "no match",
               claim_id=top)
    candidate = None
    draft_flags: list[str] = []
    cost = 0.0
    if matches and matches[0].reused is None:
        d = drafter.draft(item.text, matches[0], cfg.audience)
        cost = d.cost_usd
        draft_flags = list(d.flags)
        if d.abstained or d.answer is None:
            candidate = ""       # an empty candidate fails completeness or relevance, never ships
            draft_flags.append("DRAFTER_ABSTAINED")
        else:
            candidate = d.answer
        if d.model_id != "mock":
            repo.insert("metric_events", MetricEvent(id=ulid(), tenant=item.tenant, kind="cost_usd",
                                                     item_id=item.id, value_num=cost,
                                                     payload_json={"model": d.model_id, "tokens_in": d.tokens_in,
                                                                   "tokens_out": d.tokens_out}))
    v = gate(item.text, matches, cfg.today, cfg.audience, candidate_answer=candidate,
             domain=item.domain, domain_owners=cfg.domain_owners)
    if "DRAFTER_ABSTAINED" in draft_flags and v.outcome == "ANSWER":
        v = Verdict(outcome="HOLD_HUMAN", difficulty=v.difficulty, claim_id=v.claim_id,
                    claim_version_hash=v.claim_version_hash, route=f"OWNER:{matches[0].claim.owner}",
                    flags=draft_flags, gaps=["Drafter abstained; a person writes this one from the claim."])
    transition(repo, item, State.DRAFTED, cfg.actor, claim_id=v.claim_id,
               claim_version_hash=v.claim_version_hash, draft_answer=v.answer,
               difficulty=v.difficulty.value, verdict_json=v.to_dict(),
               flags=sorted(set(item.flags) | set(v.flags) | set(draft_flags)), route=v.route)
    transition(repo, item, OUTCOME_STATE[v.outcome], cfg.actor, "; ".join(v.gaps)[:300])
    repo.insert("metric_events", MetricEvent(id=ulid(), tenant=item.tenant, kind="latency_ms", item_id=item.id,
                                             difficulty=v.difficulty.value,
                                             value_num=(time.perf_counter() - t0) * 1000,
                                             payload_json={"stage": "draft", "outcome": v.outcome}))
    return v


def process_questionnaire(repo: Repository, questionnaire_id: str, store: ClaimStore, cfg: PipelineConfig,
                          progress: Callable[[int, int], None] | None = None) -> dict:
    """Run every RECEIVED item of a questionnaire to a resting state. Returns
    counts by state. Safe to call again: items already past RECEIVED are left."""
    matcher = ClaimMatcher(store)
    received = repo.list("question_items", {"questionnaire_id": questionnaire_id, "state": State.RECEIVED},
                         order="ordinal asc", limit=5000)
    repo.update("questionnaires", questionnaire_id, {"status": "normalising"})
    normalised = normalise_items(repo, received, cfg) if received else []
    repo.update("questionnaires", questionnaire_id, {"status": "processing"})
    todo = [i for i in normalised if i.state == State.NORMALISED]
    for n, item in enumerate(todo, start=1):
        match_and_draft(repo, item, store, matcher, cfg)
        if progress:
            try:
                progress(n, len(todo))
            except Exception:  # noqa: BLE001 - telemetry never breaks a run
                pass
    counts: dict[str, int] = {}
    for it in repo.list("question_items", {"questionnaire_id": questionnaire_id}, limit=5000):
        counts[it.state.value] = counts.get(it.state.value, 0) + 1
    repo.update("questionnaires", questionnaire_id, {"status": "done"})
    return counts
