"""Queue ranking: deal value, whether the question blocks the deal, and age.
`score = value_rank * 3 + blocks_deal * 5 + age_days`. Oldest hard questions
rise even on small deals, which is the point: easy work must not bury them."""
from __future__ import annotations

from datetime import datetime, timezone

from ..persist import Deal, QuestionItem


def value_rank(deal: Deal | None) -> int:
    if deal is None or deal.value_usd <= 0:
        return 0
    if deal.value_usd < 50_000:
        return 1
    if deal.value_usd < 250_000:
        return 2
    return 3


def age_days(item: QuestionItem, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    created = datetime.fromisoformat(item.created_at)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return max(0.0, (now - created).total_seconds() / 86400)


def score(item: QuestionItem, deal: Deal | None, now: datetime | None = None) -> float:
    return round(value_rank(deal) * 3 + (5 if item.blocks_deal else 0) + age_days(item, now), 3)


def rank(items: list[QuestionItem], deals: dict[str, Deal], now: datetime | None = None) -> list[tuple[QuestionItem, float]]:
    scored = [(it, score(it, deals.get(it.questionnaire_id), now)) for it in items]
    scored.sort(key=lambda t: (-t[1], t[0].ordinal))
    return scored
