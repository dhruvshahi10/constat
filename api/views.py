"""Response shapes the UI needs beyond the raw rows: an item carries its
questionnaire's customer and deal, its ranking inputs and the verdict under
one name."""
from __future__ import annotations

from datetime import datetime, timezone

from constat.persist import Deal, QuestionItem, Questionnaire, Repository
from constat.workflow.ranking import age_days, value_rank


class ViewCache:
    def __init__(self, repo: Repository):
        self.repo = repo
        self._q: dict[str, Questionnaire | None] = {}
        self._d: dict[str, Deal | None] = {}

    def questionnaire(self, qid: str) -> Questionnaire | None:
        if qid not in self._q:
            self._q[qid] = self.repo.get("questionnaires", qid)
        return self._q[qid]

    def deal(self, deal_id: str | None) -> Deal | None:
        if not deal_id:
            return None
        if deal_id not in self._d:
            self._d[deal_id] = self.repo.get("deals", deal_id)
        return self._d[deal_id]


def item_view(it: QuestionItem, cache: ViewCache, score: float | None = None) -> dict:
    q = cache.questionnaire(it.questionnaire_id)
    deal = cache.deal(q.deal_id if q else None)
    d = it.to_row() | {"verdict_json": it.verdict_json, "flags": it.flags}
    d["verdict"] = it.verdict_json if it.verdict_json.get("outcome") else None
    d["customer"] = q.customer if q else ""
    d["deal_id"] = (q.deal_id if q else None) or ""
    d["received_at"] = q.received_at if q else it.created_at
    d["value_rank"] = value_rank(deal)
    d["age_days"] = round(age_days(it, datetime.now(timezone.utc)), 2)
    if score is not None:
        d["score"] = score
    return d
