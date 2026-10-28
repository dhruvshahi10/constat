"""Drafting on claims. The drafter sees one claim (statement, scope,
numbered exceptions, audience) and the question; it may rephrase, it may not
add. The gate judges the result exactly as it judges a deterministic draft.
REUSED verdicts never reach a model."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

from .gates import claim_values, default_answer, new_numbers  # noqa: F401 - re-exported
from .match import Match
from .models import Audience, Claim

CLAIM_PROMPT_VERSION = "claim-contract-v1"
# USD per million tokens, input / output. Update deliberately; cost events depend on it.
PRICES = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-4-5-20250929": (3.00, 15.00),
    "mock": (0.0, 0.0),
}


@dataclass
class ClaimDraft:
    answer: str | None
    abstained: bool = False
    reason: str = ""
    model_id: str = "mock"
    prompt_version: str = CLAIM_PROMPT_VERSION
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    flags: list[str] = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        pi, po = PRICES.get(self.model_id, (0.0, 0.0))
        return round((self.tokens_in * pi + self.tokens_out * po) / 1_000_000, 6)


class ClaimDrafter(Protocol):
    model_id: str

    def draft(self, question: str, match: Match, audience: Audience) -> ClaimDraft: ...


class DeterministicClaimDrafter:
    model_id = "mock"

    def draft(self, question: str, match: Match, audience: Audience) -> ClaimDraft:
        return ClaimDraft(answer=default_answer(match.claim), model_id=self.model_id)


SYSTEM = (
    "You write one security questionnaire answer from exactly one approved claim. Rules: restate "
    "only what the claim states; carry every listed exception into the answer, in full meaning; "
    "introduce no number, date, version, product name or commitment that the claim does not "
    "contain; never claim a certification, guarantee, SLA or 'always/never/100%'; write in the "
    "first person plural, plainly, under 90 words, no bullet points. If the claim does not answer "
    "the question, abstain. Return ONLY JSON: {\"answer\": string|null, \"carried_exceptions\": "
    "[int], \"abstained\": bool, \"reason\": string}."
)


class HaikuClaimDrafter:
    model_id = "claude-haiku-4-5-20251001"

    def __init__(self, api_key: str, model: str | None = None, timeout: float = 30.0):
        self.api_key = api_key
        if model:
            self.model_id = model
        self.timeout = timeout

    def draft(self, question: str, match: Match, audience: Audience) -> ClaimDraft:
        c = match.claim
        exceptions = "\n".join(f"  {i + 1}. {e}" for i, e in enumerate(c.exceptions)) or "  (none)"
        user = (f"QUESTION: {question}\n\nCLAIM {c.claim_id} (audience: {c.audience.value}; valid until "
                f"{c.valid_until.isoformat()})\nSTATEMENT: {c.statement}\nSCOPE: {c.scope}\n"
                f"EXCEPTIONS THAT MUST APPEAR:\n{exceptions}\n")
        body = json.dumps({"model": self.model_id, "max_tokens": 600, "temperature": 0,
                           "system": SYSTEM, "messages": [{"role": "user", "content": user}]}).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body, method="POST",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"})
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                obj = json.loads(r.read().decode())
            text = "".join(b.get("text", "") for b in obj.get("content", []) if b.get("type") == "text")
            usage = obj.get("usage", {})
            parsed = json.loads(text.strip().removeprefix("```json").removesuffix("```").strip())
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, ValueError) as e:
            return ClaimDraft(answer=None, abstained=True, reason=f"CONTRACT_PARSE_FAILURE: {type(e).__name__}",
                              model_id=self.model_id, latency_ms=int((time.perf_counter() - t0) * 1000),
                              flags=["CONTRACT_PARSE_FAILURE"])
        d = ClaimDraft(answer=parsed.get("answer") if isinstance(parsed.get("answer"), str) else None,
                       abstained=bool(parsed.get("abstained")), reason=str(parsed.get("reason", "")),
                       model_id=self.model_id, tokens_in=int(usage.get("input_tokens", 0)),
                       tokens_out=int(usage.get("output_tokens", 0)),
                       latency_ms=int((time.perf_counter() - t0) * 1000))
        if d.answer:
            introduced = new_numbers(d.answer, c)
            if introduced:
                d.flags.append("NEW_VALUE_INTRODUCED")
                d.reason = f"drafter introduced values not in the claim: {', '.join(introduced)}"
                d.answer, d.abstained = None, True
        return d
